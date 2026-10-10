"""Prompts MCP (templates em português) que orientam o cliente de IA."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from rita_academic.fichamento import render
from rita_academic.state import get_state
from rita_academic.writing import references

FICHAMENTO_GUIDE = """\
Produza um fichamento acadêmico em português, em Markdown, com estas seções (nessa ordem):

## Referência
Referência completa em ABNT (use a sugerida abaixo e corrija o que faltar).

## Resumo
Resumo analítico de 1 a 3 parágrafos: tese central, argumento, método e conclusões do texto.

## Destaques
Reproduza cada destaque como citação direta entre aspas com a página, e comente em uma linha \
por que ele importa (conceito, evidência, formulação feliz, ponto discutível). Agrupe por tema \
quando fizer sentido; mantenha a cor entre parênteses se ela tiver sido usada com significado.

## Notas
Suas observações críticas, relações com outros autores da biblioteca (use a ferramenta `search` \
para verificar) e perguntas em aberto.

## Citações para uso
3 a 8 trechos prontos para citar em um artigo, no formato: "trecho" (AUTOR, ano, p. X).

Ao terminar, grave com `write_fichamento(doc_id, markdown)`.
"""


def register(server: MCPServer) -> None:
    @server.prompt(name="fichamento", description=(
        "Monta o pedido de fichamento de um documento, já incluindo metadados, referência ABNT "
        "sugerida e os destaques extraídos do PDF."))
    def fichamento(doc_id: str) -> str:
        st = get_state()
        d = st.db.get_document(doc_id)
        if not d:
            raise ValueError(f"Documento não encontrado: {doc_id}")
        annots = st.db.list_annotations(doc_id)
        if not annots and d["type"] == "pdf":
            hint = ("_Nenhum destaque extraído ainda. Chame `extract_pdf_annotations` "
                    f"(doc_id=\"{doc_id}\") primeiro, depois `annotations_to_markdown`._")
        else:
            hint = render.annotations_to_markdown(annots)
        return (
            f"{FICHAMENTO_GUIDE}\n---\n"
            f"**doc_id:** `{doc_id}`\n"
            f"**Título:** {d.get('title')}\n**Autores:** {', '.join(d.get('authors') or []) or '?'}\n"
            f"**Ano:** {d.get('year') or '?'}\n"
            f"**Referência ABNT sugerida:** {references.abnt_reference(d)}\n\n"
            f"### Destaques extraídos do PDF\n{hint}\n\n"
            "Se precisar do texto de alguma página para contextualizar um destaque, use "
            "`get_passage(doc_id, page=N)`."
        )

    @server.prompt(name="fichamento_de_leitura_gravada", description=(
        "Pedido de fichamento a partir de uma leitura gravada já transcrita (destaques e notas "
        "ditados em voz alta)."))
    def fichamento_de_leitura_gravada(audio_doc_id: str, target_doc_id: str | None = None) -> str:
        st = get_state()
        segs = st.db.get_transcript(audio_doc_id)
        if not segs:
            return (f"O áudio `{audio_doc_id}` ainda não foi transcrito. Chame "
                    f"`transcribe_audio(\"{audio_doc_id}\")`, acompanhe com `get_job` e repita.")
        from rita_academic.audio import session as session_mod

        sess = session_mod.build_session(segs, st.settings)
        md = render.reading_session_to_markdown(sess)
        target = st.db.get_document(target_doc_id) if target_doc_id else None
        head = ""
        if target:
            head = (f"**Livro:** {target.get('title')} — {', '.join(target.get('authors') or [])} "
                    f"({target.get('year') or '?'}); doc_id `{target_doc_id}`\n\n")
        return (
            f"{FICHAMENTO_GUIDE}\n---\n{head}"
            "A leitura foi feita em voz alta de um livro físico. Os destaques abaixo foram "
            "ditados (podem ter pequenos erros de transcrição: corrija pontuação e grafia óbvias, "
            "sem alterar o sentido). Os trechos não interpretados são comentários soltos da "
            "leitora; use-os na seção Notas quando fizerem sentido.\n\n"
            f"### Destaques e notas ditados\n{md}\n\n"
            + (f"Grave com `write_fichamento(\"{target_doc_id}\", markdown)` ou acrescente com "
               f"`append_to_fichamento`." if target else
               "Como o livro ainda não está na biblioteca, grave o resultado com "
               f"`reading_session_to_fichamento(\"{audio_doc_id}\")` ou cadastre o livro "
               "(um PDF/EPUB/MD) e use `write_fichamento` nele.")
        )

    @server.prompt(name="organizar_biblioteca", description=(
        "Roteiro para organizar a caixa de entrada: indexar, completar metadados e mover para "
        "as pastas padrão."))
    def organizar_biblioteca() -> str:
        st = get_state()
        return (
            "Organize a biblioteca acadêmica seguindo estes passos, confirmando comigo antes de mover:\n"
            "1. `scan_library()` para indexar novidades.\n"
            "2. `list_documents(unorganized_only=true)` para ver o que está em "
            f"`{st.settings.inbox_dir.name}`.\n"
            "3. Para cada documento com título/autor/ano faltando ou errado: "
            "`extract_metadata(doc_id)`; se continuar incompleto, leia a primeira página com "
            "`get_passage(doc_id, page=1)` e preencha com `update_metadata`. Sugira tags temáticas "
            "(`add_tags`).\n"
            "4. `propose_organization()` e me mostre a tabela de→para.\n"
            "5. Após minha confirmação, `organize_documents(doc_ids, apply=true)`.\n"
            f"Padrão de pastas: `{st.settings.organize_template}`."
        )
