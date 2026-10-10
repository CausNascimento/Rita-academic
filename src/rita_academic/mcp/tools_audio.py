"""Ferramentas de transcrição e leitura gravada."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from rita_academic.audio import session as session_mod
from rita_academic.audio.jobs import JobHandle
from rita_academic.models import Job, ReadingSession, Segment
from rita_academic.state import AppState, get_state


def _job(j: dict[str, Any]) -> Job:
    return Job(**{k: v for k, v in j.items() if k in Job.model_fields})


def _resolve_audio(st: AppState, path_or_doc_id: str) -> dict[str, Any]:
    d = st.db.get_document(path_or_doc_id)
    if d:
        return d
    p = Path(path_or_doc_id).expanduser()
    if not p.is_absolute():
        p = st.settings.library_root / p
    if not p.exists():
        raise ValueError(f"Áudio não encontrado: {path_or_doc_id}")
    return session_mod.audio_doc_for(st.db, st.settings, p)


def _transcribe_job(st: AppState, audio_doc: dict[str, Any], language: str | None,
                    handle: JobHandle | None = None) -> list[dict[str, Any]]:
    def progress(done: float, total: float | None, msg: str) -> None:
        if handle:
            handle.report(done, total, msg)

    tr = st.transcriber
    if handle and hasattr(tr, "cancel_check"):
        tr.cancel_check = handle.cancelled
    segments = tr.transcribe(Path(audio_doc["path"]), language or st.settings.language, progress)
    st.db.replace_transcript(audio_doc["id"], segments)
    return segments


def register(server: MCPServer) -> None:
    @server.tool(description=(
        "Transcreve um arquivo de áudio (caminho ou doc_id) com faster-whisper, localmente. "
        "Por padrão roda em segundo plano e devolve um job: acompanhe com get_job. "
        "Com wait=true, espera e devolve a transcrição (pode demorar minutos)."))
    async def transcribe_audio(ctx: Context, path_or_doc_id: str, language: str | None = None,
                               wait: bool = False) -> dict[str, Any]:
        st = get_state()
        audio_doc = _resolve_audio(st, path_or_doc_id)
        if wait:
            import anyio

            def progress(done: float, total: float | None, msg: str) -> None:
                anyio.from_thread.run(ctx.report_progress, done, total, msg)

            def run() -> list[dict[str, Any]]:
                tr = st.transcriber
                segs = tr.transcribe(Path(audio_doc["path"]), language or st.settings.language, progress)
                st.db.replace_transcript(audio_doc["id"], segs)
                return segs

            segs = await anyio.to_thread.run_sync(run)
            return {"doc_id": audio_doc["id"], "segments": segs}
        job = st.jobs.submit("transcribe", lambda h: {
            "doc_id": audio_doc["id"],
            "segments": len(_transcribe_job(st, audio_doc, language, h))})
        return _job(job).model_dump()

    @server.tool(description="Estado de um job (queued, running, done, error, cancelled), progresso e resultado.")
    def get_job(job_id: str) -> Job:
        j = get_state().db.get_job(job_id)
        if not j:
            raise ValueError(f"Job não encontrado: {job_id}")
        return _job(j)

    @server.tool(description="Lista os jobs mais recentes.")
    def list_jobs(limit: int = 20) -> list[Job]:
        return [_job(j) for j in get_state().db.list_jobs(limit)]

    @server.tool(description="Cancela um job em fila ou em execução.")
    def cancel_job(job_id: str) -> bool:
        return get_state().jobs.cancel(job_id)

    @server.tool(description="Transcrição já feita de um áudio (segmentos com tempo inicial/final).")
    def get_transcript(doc_id: str) -> list[Segment]:
        return [Segment(**s) for s in get_state().db.get_transcript(doc_id)]

    @server.tool(description=(
        "Interpreta os comandos de voz de uma transcrição (destaque isso/fim do destaque, "
        "nota/fim da nota, página N, capítulo N, cancela) e devolve destaques e notas "
        "estruturados com página. Passe doc_id de um áudio já transcrito ou segments."))
    def parse_reading_commands(doc_id: str | None = None,
                               segments: list[dict[str, Any]] | None = None) -> ReadingSession:
        st = get_state()
        if segments is None:
            if not doc_id:
                raise ValueError("Informe doc_id ou segments.")
            segments = st.db.get_transcript(doc_id)
        return ReadingSession(**session_mod.build_session(segments, st.settings))

    @server.tool(description=(
        "Converte uma leitura gravada já transcrita em fichamento Markdown. Se target_doc_id "
        "for informado (o livro na biblioteca), acrescenta à seção Destaques do fichamento "
        "dele; senão cria uma nota 'reading session' própria. write=false só devolve o texto."))
    def reading_session_to_fichamento(audio_doc_id: str, target_doc_id: str | None = None,
                                      write: bool = True) -> dict[str, Any]:
        st = get_state()
        audio_doc = st.db.get_document(audio_doc_id)
        if not audio_doc:
            raise ValueError(f"Áudio não encontrado: {audio_doc_id}")
        segs = st.db.get_transcript(audio_doc_id)
        if not segs:
            raise ValueError("Esse áudio ainda não foi transcrito. Use transcribe_audio.")
        target = st.db.get_document(target_doc_id) if target_doc_id else None
        if target_doc_id and not target:
            raise ValueError(f"Documento alvo não encontrado: {target_doc_id}")
        sess = session_mod.build_session(segs, st.settings)
        return session_mod.session_to_fichamento(st.db, st.settings, sess, audio_doc, target, write)

    @server.tool(description=(
        "Pipeline completo em segundo plano: transcreve o áudio, interpreta os comandos de voz "
        "e grava o fichamento. Devolve um job; quando status=done, result traz path e markdown."))
    def audio_to_fichamento(path_or_doc_id: str, target_doc_id: str | None = None,
                            language: str | None = None) -> Job:
        st = get_state()
        audio_doc = _resolve_audio(st, path_or_doc_id)
        target = st.db.get_document(target_doc_id) if target_doc_id else None
        if target_doc_id and not target:
            raise ValueError(f"Documento alvo não encontrado: {target_doc_id}")

        def run(h: JobHandle) -> dict[str, Any]:
            segs = _transcribe_job(st, audio_doc, language, h)
            if h.cancelled():
                return {"doc_id": audio_doc["id"], "cancelled": True}
            h.update(message="interpretando comandos de voz")
            sess = session_mod.build_session(segs, st.settings)
            out = session_mod.session_to_fichamento(st.db, st.settings, sess, audio_doc, target, True)
            out.update({"audio_doc_id": audio_doc["id"], "items": len(sess["items"]),
                        "unparsed": len(sess["unparsed"]), "pages_seen": sess["pages_seen"]})
            return out

        return _job(st.jobs.submit("audio_to_fichamento", run))
