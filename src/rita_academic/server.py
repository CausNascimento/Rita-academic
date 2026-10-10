"""Instância do servidor MCP e ciclo de vida."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer

from rita_academic import __version__
from rita_academic.audio.jobs import JobManager
from rita_academic.config import Settings
from rita_academic.db import Database
from rita_academic.state import AppState, get_state, set_state

INSTRUCTIONS = """\
Rita Academic é a biblioteca acadêmica pessoal da usuária, acessível por ferramentas.
Fluxos típicos:
- Organizar: scan_library -> list_documents -> extract_metadata/update_metadata -> \
propose_organization -> organize_documents(apply=true).
- Fichamento de PDF: extract_pdf_annotations -> annotations_to_markdown -> \
(você redige o fichamento) -> write_fichamento / append_to_fichamento. Use o prompt "fichamento".
- Pesquisa para escrita: search -> get_passage (traz a citação pronta) -> export_references.
- Leitura gravada de livro físico: audio_to_fichamento(path) devolve um job; acompanhe com \
get_job; ao concluir, o fichamento é gravado e o resultado traz o Markdown. Comandos de voz \
reconhecidos (em português): "destaque isso" … "fim do destaque", "nota:" … "fim da nota", \
"página 42", "capítulo 3", "cancela".
Todo o raciocínio (resumir, interpretar, redigir) é seu; o servidor só fornece dados.
"""


def build_server(settings: Settings | None = None, transcriber: Any | None = None,
                 db: Database | None = None) -> MCPServer:
    """Cria o servidor. Parâmetros opcionais permitem injeção em testes."""

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppState]:
        st = settings or Settings.from_env()
        st.ensure_dirs()
        database = db or Database(st.db_path)
        tr = transcriber
        if tr is None:
            from rita_academic.audio.transcriber import FasterWhisperTranscriber

            tr = FasterWhisperTranscriber(
                model=st.whisper_model, device=st.whisper_device,
                compute_type=st.whisper_compute_type, cache_dir=st.cache_dir,
                default_language=st.language)
        state = AppState(settings=st, db=database, jobs=JobManager(database), transcriber=tr)
        set_state(state)
        try:
            yield state
        finally:
            state.jobs.shutdown()
            if db is None:
                database.close()
            set_state(None)

    server = MCPServer(
        name="rita-academic",
        title="Rita Academic",
        description="Biblioteca acadêmica local: organização, fichamento, busca e leituras gravadas.",
        instructions=INSTRUCTIONS,
        version=__version__,
        lifespan=lifespan,
    )
    from rita_academic.mcp import (
        prompts,
        resources,
        tools_audio,
        tools_fichamento,
        tools_library,
        tools_writing,
    )

    tools_library.register(server)
    tools_fichamento.register(server)
    tools_writing.register(server)
    tools_audio.register(server)
    resources.register(server)
    prompts.register(server)

    @server.tool(description="Verifica se o servidor está ativo e mostra a configuração básica.")
    def ping() -> dict[str, Any]:
        s = get_state().settings
        return {"ok": True, "version": __version__, "library_root": str(s.library_root),
                "notes_dir": str(s.notes_dir), "whisper_model": s.whisper_model,
                "language": s.language}

    return server
