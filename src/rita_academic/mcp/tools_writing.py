"""Ferramentas de busca e citação (base para a skill de escrita)."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from rita_academic.models import Passage, SearchHit
from rita_academic.state import get_state
from rita_academic.writing import references
from rita_academic.writing import search as search_mod


def register(server: MCPServer) -> None:
    @server.tool(description=(
        "Busca em texto completo (sem acentos, prefixos) em páginas, destaques, fichamentos e "
        "transcrições. kinds: page, annotation, note, transcript. Retorna trechos com "
        "doc_id e referência (página/tempo) para usar em get_passage."))
    def search(query: str, kinds: list[str] | None = None, doc_ids: list[str] | None = None,
               tags: list[str] | None = None, limit: int = 20) -> list[SearchHit]:
        st = get_state()
        return [SearchHit(**h) for h in search_mod.search(st.db, query, kinds, doc_ids, tags, limit)]

    @server.tool(description=(
        "Recupera uma passagem com citação pronta (autor-data e ABNT com localizador). "
        "Informe page (PDF/EPUB), start_ts (transcrição, em segundos) ou heading (nota)."))
    def get_passage(doc_id: str, page: int | None = None, start_ts: float | None = None,
                    heading: str | None = None, context_chars: int = 1500) -> Passage:
        st = get_state()
        return Passage(**search_mod.get_passage(st.db, doc_id, page, start_ts, heading, context_chars))

    @server.tool(description="Exporta referências dos documentos em BibTeX ou ABNT (uma por linha).")
    def export_references(doc_ids: list[str], format: str = "abnt") -> str:
        st = get_state()
        out = []
        for doc_id in doc_ids:
            d = st.db.get_document(doc_id)
            if not d:
                out.append(f"% documento não encontrado: {doc_id}")
                continue
            out.append(references.bibtex(d) if format == "bibtex" else references.abnt_reference(d))
        return "\n\n".join(out) if format == "bibtex" else "\n".join(out)
