"""Varredura da biblioteca: descobre arquivos, indexa texto e metadados."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rita_academic.config import Settings
from rita_academic.db import Database
from rita_academic.library import extract, metadata
from rita_academic.textutil import now_iso

SKIP_DIRS = {".rita", ".git", "__pycache__", ".venv", "node_modules"}
ProgressCb = Callable[[int, int, str], None]


def content_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:16]


def iter_files(root: Path, settings: Settings) -> list[Path]:
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS or part.startswith(".") for part in p.relative_to(root).parts):
            continue
        # Fichamentos não são "documentos"; são indexados pelo módulo de notas.
        if settings.notes_dir in p.parents:
            continue
        if extract.detect_type(p) == "other":
            continue
        files.append(p)
    return files


def scan(
    db: Database,
    settings: Settings,
    path: Path | None = None,
    full: bool = False,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    root = settings.library_root
    base = (path or root).resolve()
    if root not in base.parents and base != root:
        raise ValueError(f"Caminho fora da biblioteca: {base}")
    files = iter_files(base, settings)
    report = {"scanned": 0, "added": 0, "updated": 0, "unchanged": 0, "removed": 0, "errors": []}
    seen_paths: set[str] = set()

    for i, p in enumerate(files, start=1):
        if progress:
            progress(i, len(files), str(p.relative_to(root)))
        report["scanned"] += 1
        try:
            outcome = index_file(db, settings, p, full=full)
            report[outcome] += 1
            seen_paths.add(str(p))
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"{p.relative_to(root)}: {exc}")

    # Remove registros cujos arquivos sumiram (apenas dentro do escopo varrido).
    for row in db.query("SELECT id, path FROM documents"):
        rp = Path(row["path"])
        if (base == rp or base in rp.parents) and str(rp) not in seen_paths and not rp.exists():
            db.delete_document(row["id"])
            report["removed"] += 1
    return report


def index_file(db: Database, settings: Settings, p: Path, full: bool = False) -> str:
    stat = p.stat()
    existing = db.get_document_by_path(str(p))
    if existing and not full and existing["mtime"] == stat.st_mtime and existing["size"] == stat.st_size:
        return "unchanged"

    doc_type = extract.detect_type(p)
    doc_id = content_hash(p)
    by_id = db.get_document(doc_id)
    # Arquivo movido/renomeado: mantém o registro, atualiza caminho.
    if by_id and by_id["path"] != str(p) and not Path(by_id["path"]).exists():
        db.execute("UPDATE documents SET path=?, rel_path=? WHERE id=?",
                   (str(p), str(p.relative_to(settings.library_root)), doc_id))
        existing = db.get_document(doc_id)

    pages = extract.extract_pages(p, doc_type) if doc_type != "audio" else []
    has_text = any(t.strip() for t in pages) if doc_type != "audio" else True
    meta = metadata.extract(p, doc_type, first_pages=pages[:3] if pages else None)

    doc: dict[str, Any] = {
        "id": doc_id,
        "path": str(p),
        "rel_path": str(p.relative_to(settings.library_root)),
        "type": doc_type,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "added_at": (existing or {}).get("added_at") or now_iso(),
        "indexed_at": now_iso(),
        "has_text": has_text,
        "pages": meta.get("pages") or (len(pages) if doc_type == "pdf" else None),
    }
    # Metadados editados manualmente têm prioridade sobre os re-extraídos.
    for k in ("title", "authors", "year", "publisher", "doi", "isbn", "language", "tags"):
        if existing and existing.get(k) not in (None, "", []):
            doc[k] = existing[k]
        elif meta.get(k) not in (None, "", []):
            doc[k] = meta[k]
    if existing and existing["id"] != doc_id:
        # Conteúdo mudou: o id muda. Remove o antigo para não duplicar.
        db.delete_document(existing["id"])
    db.upsert_document(doc)
    if pages:
        db.replace_pages(doc_id, pages)
    return "updated" if existing else "added"
