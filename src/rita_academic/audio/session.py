"""Pipeline: transcrição -> sessão de leitura -> fichamento em Markdown."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rita_academic.audio.commands import CommandParser
from rita_academic.config import Settings
from rita_academic.db import Database
from rita_academic.fichamento import render, store


def build_session(segments: list[dict[str, Any]], settings: Settings,
                  keywords: dict[str, Any] | None = None) -> dict[str, Any]:
    parser = CommandParser(keywords or settings.keywords)
    return parser.parse(segments)


def session_to_fichamento(db: Database, settings: Settings, session: dict[str, Any],
                          audio_doc: dict[str, Any], target_doc: dict[str, Any] | None,
                          write: bool = True) -> dict[str, Any]:
    doc = target_doc or audio_doc
    kind = "reading_session" if target_doc is None else "fichamento"
    path = store.note_path(doc, settings, kind=kind)
    md = render.reading_session_to_markdown(session)
    header = (f"_Leitura gravada: `{audio_doc.get('rel_path')}`"
              + (f", páginas {', '.join(map(str, session.get('pages_seen') or []))}" if session.get("pages_seen") else "")
              + "._")
    block = f"{header}\n\n{md}"
    if not write:
        return {"path": str(path), "markdown": block, "written": False}
    fm = {
        "rita_doc_id": doc["id"], "title": doc.get("title"), "authors": doc.get("authors") or [],
        "year": doc.get("year"), "tags": doc.get("tags") or [], "source": doc.get("rel_path"),
        "audio_source": audio_doc.get("rel_path"),
    }
    store.append(path, "Destaques", block, fm, db, doc["id"], kind=kind)
    return {"path": str(path), "markdown": block, "written": True}


def audio_doc_for(db: Database, settings: Settings, audio_path: Path) -> dict[str, Any]:
    """Garante que o áudio esteja registrado como documento (dentro da biblioteca)."""
    from rita_academic.library.scanner import content_hash, index_file

    p = audio_path.expanduser().resolve()
    root = settings.library_root.resolve()
    if root not in p.parents:
        # Copia para a pasta de leituras gravadas da biblioteca.
        dst_dir = settings.library_root / "Leituras gravadas"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / p.name
        if not dst.exists():
            import shutil

            shutil.copy2(p, dst)
        p = dst
    index_file(db, settings, p, full=False)
    return db.get_document(content_hash(p))  # type: ignore[return-value]
