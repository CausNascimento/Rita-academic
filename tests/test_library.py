from pathlib import Path

from rita_academic.library import metadata, organizer, scanner


def test_scan_indexes_pdf_and_md(db, library, sample_pdf, sample_md):
    report = scanner.scan(db, library)
    assert report["added"] == 2 and report["errors"] == []
    docs = db.list_documents()
    pdf = next(d for d in docs if d["type"] == "pdf")
    assert pdf["title"] == "Pedagogia da autonomia"
    assert pdf["authors"] == ["Paulo Freire"]
    assert pdf["year"] == 1996
    assert pdf["pages"] == 3
    assert pdf["isbn"] == "9788577531639"
    assert db.get_page(pdf["id"], 2).startswith("Quem ensina")
    md = next(d for d in docs if d["type"] == "md")
    assert md["title"] == "Notas sobre metodologia" and md["tags"] == ["metodologia"]
    # Segunda varredura: nada muda
    report2 = scanner.scan(db, library)
    assert report2["unchanged"] == 2 and report2["added"] == 0


def test_scan_detects_move_and_removal(db, library, sample_pdf):
    scanner.scan(db, library)
    doc_id = db.list_documents()[0]["id"]
    new = library.library_root / "Livros" / sample_pdf.name
    new.parent.mkdir()
    sample_pdf.rename(new)
    scanner.scan(db, library)
    d = db.get_document(doc_id)
    assert d and Path(d["path"]) == new
    assert len(db.list_documents()) == 1
    new.unlink()
    rep = scanner.scan(db, library)
    assert rep["removed"] == 1 and db.list_documents() == []


def test_filename_metadata():
    m = metadata.from_filename(Path("Bourdieu, Pierre - 1989 - O poder simbólico.pdf"))
    assert m == {"title": "O poder simbólico", "year": 1989, "authors": ["Bourdieu, Pierre"]}
    m = metadata.from_filename(Path("Santos (2002) Para uma sociologia das ausências.pdf"))
    assert m["authors"] == ["Santos"] and m["year"] == 2002


def test_organizer_proposal_and_move(db, library, sample_pdf):
    scanner.scan(db, library)
    props = organizer.propose(db, library)
    assert len(props) == 1
    assert props[0]["to_path"].endswith(
        "Artigos e livros/Freire/1996 - Pedagogia da autonomia.pdf")
    doc_id = props[0]["doc_id"]
    dry = organizer.apply_moves(db, library, [doc_id], apply=False)
    assert dry[0]["applied"] is False and dry[0]["error"] is None and sample_pdf.exists()
    res = organizer.apply_moves(db, library, [doc_id], apply=True)
    assert res[0]["applied"] is True
    assert not sample_pdf.exists() and Path(res[0]["to_path"]).exists()
    assert db.get_document(doc_id)["path"] == res[0]["to_path"]
    again = organizer.apply_moves(db, library, [doc_id], apply=True)
    assert again[0]["error"] == "já está no lugar"
