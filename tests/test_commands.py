import pytest

from rita_academic.audio.commands import CommandParser, words_to_int
from rita_academic.config import DEFAULT_KEYWORDS


@pytest.fixture
def parser():
    return CommandParser(DEFAULT_KEYWORDS)


@pytest.mark.parametrize("words,expected", [
    ("quarenta e dois", 42), ("cento e vinte e tres", 123), ("mil e dois", 1002),
    ("12", 12), ("duzentas e dez", 210), ("cem", 100), ("dezenove", 19),
])
def test_words_to_int(words, expected):
    assert words_to_int(words.split()) == expected


def test_highlight_with_page_and_chapter(parser):
    out = parser.parse([
        {"start": 0, "end": 2, "text": "Capítulo três, página quarenta e dois."},
        {"start": 2, "end": 6, "text": "Destaque isso: a educação é um ato político. Fim do destaque."},
    ])
    assert len(out["items"]) == 1
    it = out["items"][0]
    assert it["kind"] == "highlight"
    assert it["text"] == "a educação é um ato político."
    assert it["page"] == 42 and it["chapter"] == "3"
    assert out["pages_seen"] == [42]
    assert out["unparsed"] == []


def test_highlight_spans_segments(parser):
    out = parser.parse([
        {"start": 0, "end": 3, "text": "Página 7. Destaque. Ensinar não é transferir"},
        {"start": 3, "end": 6, "text": "conhecimento. Fim do destaque."},
    ])
    assert out["items"][0]["text"] == "Ensinar não é transferir conhecimento."
    assert out["items"][0]["start"] == 0 and out["items"][0]["end"] == 6


def test_note_and_unparsed(parser):
    out = parser.parse([
        {"start": 0, "end": 3, "text": "Nota: comparar com Bourdieu. Fim da nota."},
        {"start": 3, "end": 5, "text": "Esse trecho é confuso."},
    ])
    assert out["items"][0]["kind"] == "note"
    assert out["items"][0]["text"] == "comparar com Bourdieu."
    assert out["unparsed"][0]["text"] == "Esse trecho é confuso."


def test_note_closed_by_long_pause(parser):
    out = parser.parse([
        {"start": 0, "end": 3, "text": "Nota: isso é importante"},
        {"start": 10, "end": 12, "text": "Página 9."},
    ])
    assert out["items"][0]["kind"] == "note"
    assert out["items"][0]["text"] == "isso é importante"


def test_cancel_removes_open_or_last(parser):
    out = parser.parse([
        {"start": 0, "end": 3, "text": "Destaque isso: frase errada. Cancela."},
        {"start": 3, "end": 6, "text": "Destaque isso: frase certa. Fim do destaque."},
        {"start": 6, "end": 7, "text": "Apaga isso."},
    ])
    assert out["items"] == []


def test_roman_chapter_and_section(parser):
    out = parser.parse([
        {"start": 0, "end": 3, "text": "Capítulo IV, seção dois, página 100. Destaque isso: x. Fim do destaque."},
    ])
    it = out["items"][0]
    assert it["chapter"] == "IV" and it["section"] == "2" and it["page"] == 100


def test_custom_keywords():
    kw = dict(DEFAULT_KEYWORDS)
    kw["highlight_start"] = ["grifa"]
    kw["highlight_end"] = ["chega"]
    p = CommandParser(kw)
    out = p.parse([{"start": 0, "end": 2, "text": "Grifa: texto do livro. Chega."}])
    assert out["items"][0]["text"] == "texto do livro."


def test_unterminated_highlight_closes_at_end(parser):
    out = parser.parse([{"start": 0, "end": 2, "text": "Destaque isso: fica aberto"}])
    assert out["items"][0]["text"] == "fica aberto"
