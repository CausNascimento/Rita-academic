"""Extração de texto completo por página/capítulo."""

from __future__ import annotations

from pathlib import Path

PDF_EXT = {".pdf"}
EPUB_EXT = {".epub"}
MD_EXT = {".md", ".markdown"}
TXT_EXT = {".txt"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac", ".opus", ".webm", ".mp4"}


def detect_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in EPUB_EXT:
        return "epub"
    if ext in MD_EXT:
        return "md"
    if ext in TXT_EXT:
        return "txt"
    if ext in AUDIO_EXT:
        return "audio"
    return "other"


def extract_pages(path: Path, doc_type: str) -> list[str]:
    """Retorna uma lista de textos: um por página (PDF), por capítulo (EPUB) ou único."""
    if doc_type == "pdf":
        return extract_pdf(path)
    if doc_type == "epub":
        return extract_epub(path)
    if doc_type in ("md", "txt"):
        return [path.read_text(encoding="utf-8", errors="replace")]
    return []


def extract_pdf(path: Path) -> list[str]:
    import pymupdf

    pages: list[str] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pages.append(page.get_text("text"))
    return pages


def extract_epub(path: Path) -> list[str]:
    import warnings

    from bs4 import BeautifulSoup

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import ebooklib
        from ebooklib import epub

        book = epub.read_epub(str(path), options={"ignore_ncx": True})
    chapters: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text("\n", strip=True)
        if text:
            chapters.append(text)
    return chapters
