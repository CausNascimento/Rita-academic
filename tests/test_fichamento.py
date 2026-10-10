import frontmatter

from rita_academic.fichamento import pdf_annotations, render, store
from rita_academic.library import scanner


def _doc(db, library, sample_pdf):
    scanner.scan(db, library)
    return db.list_documents()[0]


def test_extract_annotations(db, library, sample_pdf):
    doc = _doc(db, library, sample_pdf)
    annots = pdf_annotations.extract_annotations(sample_pdf, doc["id"])
    kinds = {a["kind"] for a in annots}
    assert kinds == {"highlight", "underline", "note"}
    hl = next(a for a in annots if a["kind"] == "highlight")
    assert hl["text"].rstrip(".") == "ato político" and hl["page"] == 1
    assert hl["color_name"] == "amarelo" and hl["color_hex"] == "#ffff00"
    assert hl["comment"] == "conceito-chave"
    ul = next(a for a in annots if a["kind"] == "underline")
    assert ul["text"].rstrip(".") == "Não há docência sem discência" and ul["color_name"] == "verde"
    note = next(a for a in annots if a["kind"] == "note")
    assert note["page"] == 2 and note["comment"] == "voltar aqui para o artigo"


def test_render_and_search_annotations(db, library, sample_pdf):
    doc = _doc(db, library, sample_pdf)
    annots = pdf_annotations.extract_annotations(sample_pdf, doc["id"])
    db.replace_annotations(doc["id"], annots)
    md = render.annotations_to_markdown(db.list_annotations(doc["id"]))
    assert "### p. 1" in md and '"ato político." — nota: conceito-chave' in md
    by_color = render.annotations_to_markdown(db.list_annotations(doc["id"]), "color")
    assert "### Cor: amarelo" in by_color
    hits = db.search("politico", kinds=["annotation"])
    assert hits and hits[0]["source_kind"] == "annotation" and hits[0]["ref"] == "1"


def test_store_write_append_and_index(db, library, sample_pdf):
    doc = _doc(db, library, sample_pdf)
    path = store.note_path(doc, library)
    assert path.parent == library.notes_dir and path.name == "Pedagogia da autonomia.md"
    skel = frontmatter.loads(store.skeleton(doc))
    assert skel.metadata["rita_doc_id"] == doc["id"]
    assert "## Destaques" in skel.content

    store.write(path, "## Resumo\n\nTexto do resumo.\n\n## Notas\n", {"title": doc["title"]}, db, doc["id"])
    post = frontmatter.load(path)
    assert post.metadata["rita_doc_id"] == doc["id"] and post.metadata["kind"] == "fichamento"

    store.append(path, "Notas", "- primeira nota", {}, db, doc["id"])
    store.append(path, "Notas", "- segunda nota", {}, db, doc["id"])
    store.append(path, "Citações para uso", '"ato político" (FREIRE, 1996, p. 1)', {}, db, doc["id"])
    body = frontmatter.load(path).content
    assert body.index("primeira nota") < body.index("segunda nota")
    assert body.index("## Notas") < body.index("## Citações para uso")
    assert "Texto do resumo." in body

    notes = db.list_notes()
    assert len(notes) == 1 and notes[0]["doc_id"] == doc["id"]
    hits = db.search("segunda nota", kinds=["note"])
    assert hits and hits[0]["ref"] == "Notas"


def test_insert_under_section_creates_missing():
    out = store.insert_under_section("## A\n\nx\n", "B", "y")
    assert out.endswith("## B\n\ny\n")
