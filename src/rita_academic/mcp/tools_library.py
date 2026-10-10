"""Ferramentas de organização da biblioteca."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from rita_academic.library import metadata, organizer, scanner
from rita_academic.models import Document, DocumentSummary, MoveProposal, MoveResult, ScanReport
from rita_academic.state import get_state
from rita_academic.textutil import now_iso


def _doc(d: dict[str, Any]) -> Document:
    return Document(**{k: v for k, v in d.items() if k in Document.model_fields})


def _summary(d: dict[str, Any]) -> DocumentSummary:
    return DocumentSummary(**{k: v for k, v in d.items() if k in DocumentSummary.model_fields})


def register(server: MCPServer) -> None:
    @server.tool(description=(
        "Varre a biblioteca (ou uma subpasta) e indexa documentos novos/alterados: extrai texto "
        "completo e metadados. Use full=true para reindexar tudo."))
    async def scan_library(ctx: Context, path: str | None = None, full: bool = False) -> ScanReport:
        st = get_state()
        base = Path(path).expanduser() if path else None
        if base and not base.is_absolute():
            base = st.settings.library_root / base

        def progress(i: int, n: int, name: str) -> None:
            import anyio

            anyio.from_thread.run(ctx.report_progress, float(i), float(n), name)

        import anyio

        report = await anyio.to_thread.run_sync(
            lambda: scanner.scan(st.db, st.settings, base, full, progress))
        from rita_academic.fichamento import store

        await anyio.to_thread.run_sync(lambda: store.reindex_all(st.db, st.settings))
        return ScanReport(**report)

    @server.tool(description="Lista documentos indexados com filtros opcionais (tipo, tag, autor, ano).")
    def list_documents(type: str | None = None, tag: str | None = None, author: str | None = None,
                       year: int | None = None, unorganized_only: bool = False,
                       limit: int = 50, offset: int = 0) -> list[DocumentSummary]:
        st = get_state()
        docs = st.db.list_documents(type, tag, author, year, limit if not unorganized_only else 10_000, offset)
        if unorganized_only:
            docs = [d for d in docs if st.settings.inbox_dir in Path(d["path"]).parents][:limit]
        return [_summary(d) for d in docs]

    @server.tool(description="Metadados completos de um documento pelo id.")
    def get_document(doc_id: str) -> Document:
        d = get_state().db.get_document(doc_id)
        if not d:
            raise ValueError(f"Documento não encontrado: {doc_id}")
        return _doc(d)

    @server.tool(description="Busca documentos por título, autor, ano ou caminho (não busca no texto; para isso use search).")
    def search_metadata(query: str, limit: int = 20) -> list[DocumentSummary]:
        st = get_state()
        q = f"%{query.lower()}%"
        rows = st.db.query(
            "SELECT * FROM documents WHERE lower(title) LIKE ? OR lower(authors) LIKE ? "
            "OR lower(rel_path) LIKE ? OR CAST(year AS TEXT) LIKE ? ORDER BY title LIMIT ?",
            (q, q, q, q, limit))
        from rita_academic.db import row_to_doc

        return [_summary(row_to_doc(r)) for r in rows]

    @server.tool(description=(
        "Re-extrai metadados (título, autores, ano, DOI, ISBN) do arquivo. Com refresh=true, "
        "sobrescreve valores já preenchidos manualmente."))
    def extract_metadata(doc_id: str, refresh: bool = False) -> Document:
        st = get_state()
        d = st.db.get_document(doc_id)
        if not d:
            raise ValueError(f"Documento não encontrado: {doc_id}")
        meta = metadata.extract(Path(d["path"]), d["type"])
        for k in ("title", "authors", "year", "publisher", "doi", "isbn", "language", "pages"):
            if meta.get(k) not in (None, "", []) and (refresh or d.get(k) in (None, "", [])):
                d[k] = meta[k]
        d["indexed_at"] = now_iso()
        st.db.upsert_document(d)
        return _doc(st.db.get_document(doc_id))  # type: ignore[arg-type]

    @server.tool(description="Atualiza metadados de um documento (só os campos informados).")
    def update_metadata(doc_id: str, title: str | None = None, authors: list[str] | None = None,
                        year: int | None = None, publisher: str | None = None, doi: str | None = None,
                        isbn: str | None = None, language: str | None = None,
                        tags: list[str] | None = None) -> Document:
        st = get_state()
        d = st.db.get_document(doc_id)
        if not d:
            raise ValueError(f"Documento não encontrado: {doc_id}")
        for k, v in {"title": title, "authors": authors, "year": year, "publisher": publisher,
                     "doi": doi, "isbn": isbn, "language": language, "tags": tags}.items():
            if v is not None:
                d[k] = v
        st.db.upsert_document(d)
        return _doc(st.db.get_document(doc_id))  # type: ignore[arg-type]

    @server.tool(description="Adiciona tags a um documento.")
    def add_tags(doc_id: str, tags: list[str]) -> Document:
        st = get_state()
        d = st.db.get_document(doc_id)
        if not d:
            raise ValueError(f"Documento não encontrado: {doc_id}")
        d["tags"] = sorted(set(d.get("tags") or []) | {t.strip() for t in tags if t.strip()})
        st.db.upsert_document(d)
        return _doc(d)

    @server.tool(description="Remove tags de um documento.")
    def remove_tags(doc_id: str, tags: list[str]) -> Document:
        st = get_state()
        d = st.db.get_document(doc_id)
        if not d:
            raise ValueError(f"Documento não encontrado: {doc_id}")
        d["tags"] = [t for t in d.get("tags") or [] if t not in set(tags)]
        st.db.upsert_document(d)
        return _doc(d)

    @server.tool(description=(
        "Propõe (sem mover nada) para onde cada documento iria segundo o padrão de pastas "
        "configurado: Tipo/Autor/Ano - Título.ext. Sem doc_ids, avalia toda a biblioteca."))
    def propose_organization(doc_ids: list[str] | None = None) -> list[MoveProposal]:
        st = get_state()
        return [MoveProposal(**p) for p in organizer.propose(st.db, st.settings, doc_ids)]

    @server.tool(description=(
        "Move documentos para o lugar padrão. Com apply=false (padrão) só simula. "
        "Nunca move para fora da biblioteca nem sobrescreve arquivos."))
    def organize_documents(doc_ids: list[str], apply: bool = False) -> list[MoveResult]:
        st = get_state()
        return [MoveResult(**r) for r in organizer.apply_moves(st.db, st.settings, doc_ids, apply)]
