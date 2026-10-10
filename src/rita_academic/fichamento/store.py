"""Leitura e escrita de fichamentos em Markdown com frontmatter YAML."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import frontmatter

from rita_academic.config import Settings
from rita_academic.db import Database
from rita_academic.textutil import now_iso, safe_filename

SECTIONS = ["Referência", "Resumo", "Destaques", "Notas", "Citações para uso"]
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def note_path(doc: dict[str, Any], settings: Settings, kind: str = "fichamento") -> Path:
    src = Path(doc["path"])
    base = safe_filename(doc.get("title") or src.stem)
    suffix = "" if kind == "fichamento" else f" ({kind.replace('_', ' ')})"
    name = f"{base}{suffix}.md"
    if settings.notes_mode == "next_to_source":
        return src.with_name(name)
    return settings.notes_dir / name


def skeleton(doc: dict[str, Any], kind: str = "fichamento") -> str:
    fm = {
        "rita_doc_id": doc["id"],
        "title": doc.get("title"),
        "authors": doc.get("authors") or [],
        "year": doc.get("year"),
        "tags": doc.get("tags") or [],
        "source": doc.get("rel_path"),
        "kind": kind,
        "updated": now_iso()[:10],
    }
    body = "\n\n".join(f"## {s}\n" for s in SECTIONS)
    return frontmatter.dumps(frontmatter.Post(body, **fm), sort_keys=False) + "\n"


def read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "frontmatter": {}, "markdown": ""}
    post = frontmatter.load(path)
    return {"path": str(path), "exists": True, "frontmatter": dict(post.metadata),
            "markdown": post.content}


def write(path: Path, markdown: str, fm: dict[str, Any], db: Database, doc_id: str | None,
          kind: str = "fichamento") -> Path:
    fm = dict(fm)
    fm.setdefault("kind", kind)
    if doc_id:
        fm.setdefault("rita_doc_id", doc_id)
    fm["updated"] = now_iso()[:10]
    # Se o markdown já vier com frontmatter, mescla.
    if markdown.lstrip().startswith("---"):
        post = frontmatter.loads(markdown)
        merged = {**post.metadata, **fm}
        markdown = post.content
        fm = merged
    path.parent.mkdir(parents=True, exist_ok=True)
    text = frontmatter.dumps(frontmatter.Post(markdown.strip() + "\n", **fm), sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")
    index_note(db, path, fm, markdown, doc_id)
    return path


def append(path: Path, section: str, markdown: str, fm_default: dict[str, Any], db: Database,
           doc_id: str | None, kind: str = "fichamento") -> Path:
    cur = read(path)
    body = cur["markdown"] if cur["exists"] else frontmatter.loads(
        _skeleton_text(fm_default, kind)).content
    fm = cur["frontmatter"] or fm_default
    body = insert_under_section(body, section, markdown)
    return write(path, body, fm, db, doc_id, kind)


def _skeleton_text(fm: dict[str, Any], kind: str) -> str:
    body = "\n\n".join(f"## {s}\n" for s in SECTIONS)
    return frontmatter.dumps(frontmatter.Post(body, **{**fm, "kind": kind}), sort_keys=False)


def insert_under_section(body: str, section: str, addition: str) -> str:
    addition = addition.strip("\n")
    headings = list(HEADING_RE.finditer(body))
    target = None
    for i, m in enumerate(headings):
        if m.group(1).strip().lower() == section.strip().lower():
            target = i
            break
    if target is None:
        return body.rstrip("\n") + f"\n\n## {section}\n\n{addition}\n"
    start = headings[target].end()
    end = headings[target + 1].start() if target + 1 < len(headings) else len(body)
    segment = body[start:end].rstrip("\n")
    new_segment = f"{segment}\n\n{addition}\n\n" if segment.strip() else f"\n\n{addition}\n\n"
    return body[:start] + new_segment + body[end:]


def split_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    heading = None
    buf: list[str] = []

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            blocks.append({"heading": heading, "text": text})
        buf.clear()

    for line in markdown.splitlines():
        m = HEADING_RE.match(line)
        if m:
            flush()
            heading = m.group(1).strip()
        else:
            buf.append(line)
    flush()
    return blocks


def note_id_for(path: Path) -> str:
    return "note-" + hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]


def index_note(db: Database, path: Path, fm: dict[str, Any], markdown: str,
               doc_id: str | None) -> None:
    db.upsert_note(
        {"id": note_id_for(path), "doc_id": doc_id or fm.get("rita_doc_id"), "path": str(path),
         "title": fm.get("title"), "tags": fm.get("tags") or [], "kind": fm.get("kind", "fichamento"),
         "updated_at": now_iso()},
        split_blocks(markdown),
    )


def reindex_all(db: Database, settings: Settings) -> int:
    n = 0
    if not settings.notes_dir.exists():
        return 0
    for p in settings.notes_dir.rglob("*.md"):
        post = frontmatter.load(p)
        index_note(db, p, dict(post.metadata), post.content, post.metadata.get("rita_doc_id"))
        n += 1
    return n
