"""Ferramentas de fichamento."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from rita_academic.fichamento import pdf_annotations, render, store
from rita_academic.models import Annotation, NoteSummary
from rita_academic.state import get_state


def _require_doc(doc_id: str) -> dict[str, Any]:
    d = get_state().db.get_document(doc_id)
    if not d:
        raise ValueError(f"Documento não encontrado: {doc_id}")
    return d


def register(server: MCPServer) -> None:
    @server.tool(description=(
        "Extrai os destaques e notas feitos no PDF em qualquer leitor (anotações nativas: "
        "highlight, underline, strikeout, squiggly, note). Retorna texto, página e cor. "
        "Em PDFs escaneados sem camada de texto, avisa que precisa de OCR."))
    def extract_pdf_annotations(doc_id: str, kinds: list[str] | None = None) -> list[Annotation]:
        st = get_state()
        d = _require_doc(doc_id)
        if d["type"] != "pdf":
            raise ValueError("Só PDFs têm anotações extraíveis.")
        path = Path(d["path"])
        annots = pdf_annotations.extract_annotations(path, doc_id, kinds)
        if annots and not any(a["text"] for a in annots if a["kind"] != "note") \
                and not pdf_annotations.page_has_text(path):
            raise ValueError(
                "O PDF não tem camada de texto (parece escaneado). Faça OCR antes "
                "(por exemplo com ocrmypdf) para que os destaques tenham texto.")
        st.db.replace_annotations(doc_id, annots)
        return [Annotation(**a) for a in annots]

    @server.tool(description=(
        "Renderiza os destaques já extraídos em Markdown determinístico, agrupados por página "
        "(padrão) ou por cor. Útil como matéria-prima da seção Destaques do fichamento."))
    def annotations_to_markdown(doc_id: str, group_by: str = "page") -> str:
        st = get_state()
        _require_doc(doc_id)
        annots = st.db.list_annotations(doc_id)
        return render.annotations_to_markdown(annots, group_by)

    @server.tool(description=(
        "Lê o fichamento de um documento (frontmatter + markdown). Se não existir, devolve um "
        "esqueleto com as seções padrão: Referência, Resumo, Destaques, Notas, Citações para uso."))
    def get_fichamento(doc_id: str) -> dict[str, Any]:
        st = get_state()
        d = _require_doc(doc_id)
        path = store.note_path(d, st.settings)
        cur = store.read(path)
        if not cur["exists"]:
            import frontmatter

            post = frontmatter.loads(store.skeleton(d))
            cur.update({"frontmatter": dict(post.metadata), "markdown": post.content})
        return cur

    @server.tool(description=(
        "Grava (substitui) o fichamento completo de um documento em Markdown. O frontmatter "
        "YAML é gerado/mesclado automaticamente; tags opcionais."))
    def write_fichamento(doc_id: str, markdown: str, tags: list[str] | None = None) -> str:
        st = get_state()
        d = _require_doc(doc_id)
        path = store.note_path(d, st.settings)
        cur = store.read(path)
        fm = cur["frontmatter"] or {
            "rita_doc_id": d["id"], "title": d.get("title"), "authors": d.get("authors") or [],
            "year": d.get("year"), "source": d.get("rel_path")}
        if tags is not None:
            fm["tags"] = tags
        return str(store.write(path, markdown, fm, st.db, doc_id))

    @server.tool(description=(
        "Acrescenta Markdown ao final de uma seção do fichamento (cria a seção, e o "
        "fichamento, se não existirem). Seções padrão: Referência, Resumo, Destaques, Notas, "
        "Citações para uso."))
    def append_to_fichamento(doc_id: str, section: str, markdown: str) -> str:
        st = get_state()
        d = _require_doc(doc_id)
        path = store.note_path(d, st.settings)
        fm = {"rita_doc_id": d["id"], "title": d.get("title"), "authors": d.get("authors") or [],
              "year": d.get("year"), "tags": d.get("tags") or [], "source": d.get("rel_path")}
        return str(store.append(path, section, markdown, fm, st.db, doc_id))

    @server.tool(description="Lista fichamentos/notas por tag e/ou tipo (fichamento, reading_session).")
    def list_notes(tag: str | None = None, kind: str | None = None) -> list[NoteSummary]:
        st = get_state()
        return [NoteSummary(**{k: v for k, v in n.items() if k in NoteSummary.model_fields})
                for n in st.db.list_notes(tag, kind)]
