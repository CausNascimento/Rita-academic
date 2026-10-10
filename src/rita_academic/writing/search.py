"""Busca unificada e recuperação de passagens com citação."""

from __future__ import annotations

from typing import Any

from rita_academic.db import Database
from rita_academic.writing import references


def _owner(db: Database, doc_id: str) -> dict[str, Any] | None:
    """Documento dono do registro; para notas, resolve o documento vinculado."""
    doc = db.get_document(doc_id)
    if doc:
        return doc
    note = db.get_note(doc_id)
    if note:
        if note.get("doc_id"):
            d = db.get_document(note["doc_id"])
            if d:
                return d
        return {"id": note["id"], "title": note.get("title") or note["path"], "authors": [],
                "year": None, "rel_path": note["path"], "path": note["path"], "type": "md"}
    return None


def search(db: Database, query: str, kinds: list[str] | None = None,
           doc_ids: list[str] | None = None, tags: list[str] | None = None,
           limit: int = 20) -> list[dict[str, Any]]:
    if tags:
        tagged = {d["id"] for t in tags for d in db.list_documents(tag=t, limit=10_000)}
        tagged |= {n["id"] for t in tags for n in db.list_notes(tag=t)}
        doc_ids = sorted(tagged & set(doc_ids)) if doc_ids else sorted(tagged)
        if not doc_ids:
            return []
    hits = db.search(query, kinds=kinds, doc_ids=doc_ids, limit=limit)
    out = []
    for h in hits:
        owner = _owner(db, h["doc_id"]) or {}
        out.append({
            "doc_id": h["doc_id"],
            "title": owner.get("title"),
            "source_kind": h["source_kind"],
            "ref": h["ref"],
            "snippet": h["snippet"],
            "score": float(h["score"]),
        })
    return out


def get_passage(db: Database, doc_id: str, page: int | None = None,
                start_ts: float | None = None, heading: str | None = None,
                context_chars: int = 1500) -> dict[str, Any]:
    doc = _owner(db, doc_id)
    if not doc:
        raise ValueError(f"Documento ou nota não encontrado: {doc_id}")
    if page is not None:
        text = db.get_page(doc_id, page)
        if text is None:
            raise ValueError(f"Página {page} não indexada para {doc_id}")
        kind, ref = "page", str(page)
    elif start_ts is not None:
        segs = db.get_transcript(doc_id)
        window = [s for s in segs if start_ts - 30 <= s["start"] <= start_ts + 60]
        text = " ".join(s["text"] for s in window)
        kind, ref = "transcript", f"{start_ts:.1f}"
    else:
        rows = db.query(
            "SELECT heading, text FROM note_blocks WHERE note_id=? ORDER BY seq", (doc_id,))
        if heading:
            rows = [r for r in rows if (r["heading"] or "").lower() == heading.lower()]
        text = "\n\n".join(r["text"] for r in rows)
        kind, ref = "note", heading
    if len(text) > context_chars:
        text = text[:context_chars].rstrip() + " […]"
    return {"doc_id": doc_id, "title": doc.get("title"), "source_kind": kind, "ref": ref,
            "text": text, "citation": references.citation(doc, kind, ref)}
