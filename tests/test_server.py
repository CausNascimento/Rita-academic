import asyncio
import json

import pytest
from mcp import Client


async def _wait_job(client, job_id, timeout=10.0):
    for _ in range(int(timeout / 0.1)):
        j = (await client.call_tool("get_job", {"job_id": job_id})).structured_content
        if j["status"] in ("done", "error", "cancelled"):
            return j
        await asyncio.sleep(0.1)
    raise AssertionError("job não terminou")


@pytest.mark.anyio
async def test_end_to_end(server, sample_pdf, tiny_wav, fake_transcriber):
    async with Client(server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert {"scan_library", "extract_pdf_annotations", "search", "audio_to_fichamento"} <= names

        rep = (await c.call_tool("scan_library", {})).structured_content
        assert rep["added"] == 2 and rep["errors"] == []  # pdf + wav

        docs = (await c.call_tool("list_documents", {"type": "pdf"})).structured_content["result"]
        doc_id = docs[0]["id"]

        annots = (await c.call_tool("extract_pdf_annotations", {"doc_id": doc_id})).structured_content["result"]
        assert len(annots) == 3

        md = (await c.call_tool("annotations_to_markdown", {"doc_id": doc_id})).content[0].text
        assert "ato político" in md

        prompt = await c.get_prompt("fichamento", {"doc_id": doc_id})
        text = prompt.messages[0].content.text
        assert "Referência ABNT sugerida" in text and "ato político" in text

        path = (await c.call_tool("write_fichamento", {
            "doc_id": doc_id, "markdown": "## Resumo\n\nUm resumo.\n", "tags": ["pedagogia"]})).content[0].text
        assert path.endswith("Pedagogia da autonomia.md")
        fich = (await c.call_tool("get_fichamento", {"doc_id": doc_id})).structured_content
        assert fich["frontmatter"]["tags"] == ["pedagogia"]

        res = await c.read_resource(f"rita://doc/{doc_id}/fichamento")
        assert "Um resumo." in res.contents[0].text
        page = await c.read_resource(f"rita://doc/{doc_id}/page/2")
        assert page.contents[0].text.startswith("Quem ensina")

        hits = (await c.call_tool("search", {"query": "resumo", "kinds": ["note"]})).structured_content["result"]
        assert hits and hits[0]["source_kind"] == "note"

        passage = (await c.call_tool("get_passage", {"doc_id": doc_id, "page": 1})).structured_content
        assert passage["citation"]["abnt_inline"] == "(FREIRE, 1996, p. 1)"

        refs = (await c.call_tool("export_references", {"doc_ids": [doc_id], "format": "bibtex"})).content[0].text
        assert refs.startswith("@book{freire1996")

        # Leitura gravada -> fichamento do livro
        job = (await c.call_tool("audio_to_fichamento", {
            "path_or_doc_id": str(tiny_wav), "target_doc_id": doc_id})).structured_content
        assert job["status"] in ("queued", "running")
        done = await _wait_job(c, job["id"])
        assert done["status"] == "done", done
        assert done["result"]["items"] == 3 and done["result"]["pages_seen"] == [42, 43]
        assert fake_transcriber.calls

        fich = (await c.call_tool("get_fichamento", {"doc_id": doc_id})).structured_content
        assert "(p. 42, 00:03)" in fich["markdown"] and "nunca neutro" in fich["markdown"]
        assert "Um resumo." in fich["markdown"]

        audio_id = done["result"]["audio_doc_id"]
        segs = (await c.call_tool("get_transcript", {"doc_id": audio_id})).structured_content["result"]
        assert len(segs) == 6
        sess = (await c.call_tool("parse_reading_commands", {"doc_id": audio_id})).structured_content
        assert sess["items"][0]["page"] == 42

        hits = (await c.call_tool("search", {"query": "autonomia", "kinds": ["transcript"]})).structured_content["result"]
        assert hits and hits[0]["source_kind"] == "transcript"

        summary = json.loads((await c.read_resource("rita://library/summary")).contents[0].text)
        assert summary["counts"] == {"pdf": 1, "audio": 1} and summary["notes"] == 1


@pytest.mark.anyio
async def test_transcribe_wait_and_session_without_target(server, tiny_wav):
    async with Client(server) as c:
        out = (await c.call_tool("transcribe_audio", {
            "path_or_doc_id": str(tiny_wav), "wait": True})).structured_content
        assert len(out["segments"]) == 6
        r = (await c.call_tool("reading_session_to_fichamento", {
            "audio_doc_id": out["doc_id"], "write": False})).structured_content
        assert r["written"] is False and "### Capítulo 3" in r["markdown"]
        r = (await c.call_tool("reading_session_to_fichamento", {
            "audio_doc_id": out["doc_id"]})).structured_content
        assert r["written"] and r["path"].endswith("leitura-cap3 (reading session).md")
        notes = (await c.call_tool("list_notes", {"kind": "reading_session"})).structured_content["result"]
        assert len(notes) == 1


@pytest.mark.anyio
async def test_organize_via_tools(server, sample_pdf):
    async with Client(server) as c:
        await c.call_tool("scan_library", {})
        props = (await c.call_tool("propose_organization", {})).structured_content["result"]
        assert len(props) == 1 and props[0]["reason"] == "na caixa de entrada"
        res = (await c.call_tool("organize_documents", {
            "doc_ids": [props[0]["doc_id"]], "apply": True})).structured_content["result"]
        assert res[0]["applied"] is True
        docs = (await c.call_tool("list_documents", {"unorganized_only": True})).structured_content["result"]
        assert docs == []
