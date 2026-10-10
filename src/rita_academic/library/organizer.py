"""Proposta e aplicação de organização de arquivos na biblioteca."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from rita_academic.config import Settings
from rita_academic.db import Database
from rita_academic.textutil import safe_filename

TYPE_DIRS = {"pdf": "Artigos e livros", "epub": "Artigos e livros", "md": "Textos",
             "txt": "Textos", "audio": "Leituras gravadas", "other": "Outros"}


def author_sort(authors: list[str]) -> str:
    if not authors:
        return "Autor desconhecido"
    first = authors[0].strip()
    if "," in first:
        surname = first.split(",")[0].strip()
    else:
        parts = first.split()
        surname = parts[-1] if parts else first
    return safe_filename(surname.title() if surname.isupper() else surname)


def target_path(doc: dict[str, Any], settings: Settings) -> Path:
    src = Path(doc["path"])
    fields = {
        "type": TYPE_DIRS.get(doc["type"], "Outros"),
        "author_sort": author_sort(doc.get("authors") or []),
        "year": doc.get("year") or "s.d.",
        "title": safe_filename(doc.get("title") or src.stem),
        "ext": src.suffix.lower(),
    }
    rel = settings.organize_template.format(**fields)
    rel = "/".join(safe_filename(part) if i < rel.count("/") else part
                   for i, part in enumerate(rel.split("/")))
    return settings.library_root / rel


def propose(db: Database, settings: Settings, doc_ids: list[str] | None = None) -> list[dict[str, Any]]:
    docs = [db.get_document(d) for d in doc_ids] if doc_ids else db.list_documents(limit=10_000)
    out = []
    for doc in docs:
        if not doc:
            continue
        src = Path(doc["path"])
        dst = target_path(doc, settings)
        if src.resolve() == dst.resolve():
            continue
        reason = "na caixa de entrada" if settings.inbox_dir in src.parents else "fora do padrão"
        out.append({"doc_id": doc["id"], "from_path": str(src), "to_path": str(dst), "reason": reason})
    return out


def apply_moves(db: Database, settings: Settings, doc_ids: list[str], apply: bool) -> list[dict[str, Any]]:
    results = []
    for doc_id in doc_ids:
        doc = db.get_document(doc_id)
        if not doc:
            results.append({"doc_id": doc_id, "from_path": "", "to_path": "", "applied": False,
                            "error": "documento não encontrado"})
            continue
        src = Path(doc["path"])
        dst = target_path(doc, settings)
        res = {"doc_id": doc_id, "from_path": str(src), "to_path": str(dst), "applied": False, "error": None}
        root = settings.library_root.resolve()
        if root not in dst.resolve().parents:
            res["error"] = "destino fora da biblioteca"
        elif src.resolve() == dst.resolve():
            res["error"] = "já está no lugar"
        elif dst.exists():
            res["error"] = "já existe um arquivo no destino"
        elif apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            db.execute("UPDATE documents SET path=?, rel_path=? WHERE id=?",
                       (str(dst), str(dst.relative_to(root)), doc_id))
            res["applied"] = True
        results.append(res)
    return results
