from rita_academic.library import scanner
from rita_academic.writing import references, search


def test_search_and_passage_with_citation(db, library, sample_pdf, sample_md):
    scanner.scan(db, library)
    hits = search.search(db, "ato politico")
    assert hits and hits[0]["source_kind"] == "page" and hits[0]["ref"] == "1"
    assert "[ato] [político]" in hits[0]["snippet"] or "[ato]" in hits[0]["snippet"]
    hits_tag = search.search(db, "entrevistas", tags=["metodologia"])
    assert hits_tag and hits_tag[0]["title"] == "Notas sobre metodologia"
    assert search.search(db, "entrevistas", tags=["inexistente"]) == []

    p = search.get_passage(db, hits[0]["doc_id"], page=1)
    assert p["text"].startswith("A educação")
    assert p["citation"]["abnt_inline"] == "(FREIRE, 1996, p. 1)"
    assert p["citation"]["author_year"] == "FREIRE, 1996"
    assert p["citation"]["reference"].startswith("FREIRE, Paulo. **Pedagogia da autonomia**.")


def test_references_formats():
    doc = {"title": "O poder simbólico", "authors": ["Bourdieu, Pierre"], "year": 1989,
           "publisher": "Bertrand Brasil", "isbn": "123"}
    assert references.abnt_reference(doc) == (
        "BOURDIEU, Pierre. **O poder simbólico**. Bertrand Brasil, 1989. ISBN 123.")
    bib = references.bibtex(doc)
    assert bib.startswith("@book{bourdieu1989,") and "author = {Bourdieu, Pierre}" in bib
    many = {"title": "T", "authors": ["A Um", "B Dois", "C Tres", "D Quatro"], "year": 2001}
    assert references.author_year(many) == "UM et al., 2001"
    assert references.abnt_inline(many, "p. 3") == "(UM et al., 2001, p. 3)"
    assert references.locator_for("transcript", "125.0") == "gravação 02:05"
