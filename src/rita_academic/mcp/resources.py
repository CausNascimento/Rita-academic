"""Recursos MCP (leitura por URI). Usam ids, nunca caminhos."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from rita_academic.fichamento import store
from rita_academic.state import get_state


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def register(server: MCPServer) -> None:
    @server.resource("rita://library/summary", mime_type="application/json",
                     description="Resumo da biblioteca: pasta raiz, contagens, documentos recentes.")
    def library_summary() -> str:
        st = get_state()
        counts = {r["type"]: r["n"] for r in st.db.query(
            "SELECT type, COUNT(*) AS n FROM documents GROUP BY type")}
        recent = st.db.query("SELECT id, title, rel_path FROM documents ORDER BY added_at DESC LIMIT 10")
        return _dump({"library_root": str(st.settings.library_root), "counts": counts,
                      "notes": st.db.one("SELECT COUNT(*) AS n FROM notes")["n"],
                      "recent": [dict(r) for r in recent]})

    @server.resource("rita://doc/{doc_id}", mime_type="application/json",
                     description="Metadados de um documento.")
    def doc_meta(doc_id: str) -> str:
        d = get_state().db.get_document(doc_id)
        if not d:
            raise ValueError(f"Documento não encontrado: {doc_id}")
        return _dump(d)

    @server.resource("rita://doc/{doc_id}/page/{page}", mime_type="text/plain",
                     description="Texto de uma página (PDF) ou capítulo (EPUB).")
    def doc_page(doc_id: str, page: int) -> str:
        text = get_state().db.get_page(doc_id, int(page))
        if text is None:
            raise ValueError(f"Página {page} não indexada para {doc_id}")
        return text

    @server.resource("rita://doc/{doc_id}/fichamento", mime_type="text/markdown",
                     description="Fichamento do documento em Markdown.")
    def doc_fichamento(doc_id: str) -> str:
        st = get_state()
        d = st.db.get_document(doc_id)
        if not d:
            raise ValueError(f"Documento não encontrado: {doc_id}")
        path = store.note_path(d, st.settings)
        return path.read_text(encoding="utf-8") if path.exists() else store.skeleton(d)

    @server.resource("rita://job/{job_id}", mime_type="application/json",
                     description="Estado de um job.")
    def job(job_id: str) -> str:
        j = get_state().db.get_job(job_id)
        if not j:
            raise ValueError(f"Job não encontrado: {job_id}")
        return _dump(j)

    @server.resource("rita://config/keywords", mime_type="application/json",
                     description="Tabela ativa de comandos de voz (português).")
    def keywords() -> str:
        return _dump(get_state().settings.keywords)
