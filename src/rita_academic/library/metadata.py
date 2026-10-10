"""Extração heurística de metadados bibliográficos."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)
ISBN_RE = re.compile(r"ISBN(?:-1[03])?:?\s*((?:97[89][- ]?)?\d{1,5}[- ]?\d{1,7}[- ]?\d{1,7}[- ]?[\dXx])")
YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")
# "Sobrenome, Nome - 2019 - Título.pdf" | "Autor (2019) Título" | "2019 - Título"
FILENAME_PATTERNS = [
    re.compile(r"^(?P<author>[^-]+?)\s*-\s*(?P<year>\d{4})\s*-\s*(?P<title>.+)$"),
    re.compile(r"^(?P<author>[^(]+?)\s*\((?P<year>\d{4})\)\s*[-–.]?\s*(?P<title>.+)$"),
    re.compile(r"^(?P<year>\d{4})\s*-\s*(?P<title>.+)$"),
]


def from_filename(path: Path) -> dict[str, Any]:
    stem = path.stem.replace("_", " ").strip()
    for pat in FILENAME_PATTERNS:
        m = pat.match(stem)
        if m:
            d = m.groupdict()
            out: dict[str, Any] = {"title": d["title"].strip()}
            if d.get("year"):
                out["year"] = int(d["year"])
            if d.get("author"):
                out["authors"] = [a.strip() for a in re.split(r";|&| e ", d["author"]) if a.strip()]
            return out
    return {"title": stem}


def from_pdf(path: Path, first_pages: list[str] | None = None) -> dict[str, Any]:
    import pymupdf

    out: dict[str, Any] = {}
    with pymupdf.open(path) as doc:
        meta = doc.metadata or {}
        out["pages"] = doc.page_count
        if first_pages is None:
            first_pages = [doc[i].get_text("text") for i in range(min(3, doc.page_count))]
    title = (meta.get("title") or "").strip()
    if title and not _looks_like_junk_title(title):
        out["title"] = title
    author = (meta.get("author") or "").strip()
    if author:
        out["authors"] = [a.strip() for a in re.split(r";|,\s*(?=[A-ZÀ-Ý])|&| and | e ", author) if a.strip()]
    cd = meta.get("creationDate") or ""
    m = re.search(r"D:(\d{4})", cd)
    if m:
        out["year"] = int(m.group(1))
    head = "\n".join(first_pages or [])
    out.update(_scan_text(head))
    return out


def from_epub(path: Path) -> dict[str, Any]:
    import warnings

    out: dict[str, Any] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from ebooklib import epub

        book = epub.read_epub(str(path), options={"ignore_ncx": True})

    def md(name: str) -> list[str]:
        return [v for v, _ in book.get_metadata("DC", name)]

    if md("title"):
        out["title"] = md("title")[0]
    if md("creator"):
        out["authors"] = md("creator")
    if md("publisher"):
        out["publisher"] = md("publisher")[0]
    if md("language"):
        out["language"] = md("language")[0]
    for d in md("date"):
        m = YEAR_RE.search(d)
        if m:
            out["year"] = int(m.group(1))
            break
    for ident in md("identifier"):
        m = ISBN_RE.search("ISBN " + ident)
        if m:
            out["isbn"] = m.group(1).replace("-", "").replace(" ", "")
    return out


def from_markdown(path: Path) -> dict[str, Any]:
    import frontmatter

    out: dict[str, Any] = {}
    try:
        post = frontmatter.load(path)
    except Exception:  # noqa: BLE001 - frontmatter inválido não deve derrubar a varredura
        return out
    fm = post.metadata or {}
    for k in ("title", "year", "publisher", "doi", "isbn", "language"):
        if fm.get(k) is not None:
            out[k] = fm[k]
    if fm.get("authors"):
        out["authors"] = fm["authors"] if isinstance(fm["authors"], list) else [str(fm["authors"])]
    elif fm.get("author"):
        out["authors"] = [str(fm["author"])]
    if fm.get("tags"):
        out["tags"] = list(fm["tags"]) if isinstance(fm["tags"], list) else [str(fm["tags"])]
    if "title" not in out:
        m = re.search(r"^#\s+(.+)$", post.content, re.MULTILINE)
        if m:
            out["title"] = m.group(1).strip()
    return out


def extract(path: Path, doc_type: str, first_pages: list[str] | None = None) -> dict[str, Any]:
    """Combina fontes: metadados embutidos > heurística de texto > nome do arquivo."""
    base = from_filename(path)
    rich: dict[str, Any] = {}
    try:
        if doc_type == "pdf":
            rich = from_pdf(path, first_pages)
        elif doc_type == "epub":
            rich = from_epub(path)
        elif doc_type == "md":
            rich = from_markdown(path)
    except Exception:  # noqa: BLE001 - arquivo corrompido: fica só com o nome
        rich = {}
    merged = dict(base)
    for k, v in rich.items():
        if v not in (None, "", [], {}):
            merged[k] = v
    if "year" in merged:
        try:
            merged["year"] = int(merged["year"])
        except (TypeError, ValueError):
            merged.pop("year")
    return merged


def _scan_text(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    m = DOI_RE.search(text)
    if m:
        out["doi"] = m.group(1).rstrip(".,;)")
    m = ISBN_RE.search(text)
    if m:
        out["isbn"] = m.group(1).replace("-", "").replace(" ", "")
    return out


def _looks_like_junk_title(title: str) -> bool:
    t = title.lower()
    return (
        t.endswith((".doc", ".docx", ".indd", ".pdf", ".qxd", ".tex"))
        or t in {"untitled", "sem título", "microsoft word", "document"}
        or t.startswith(("microsoft word", "untitled", "doi:"))
    )
