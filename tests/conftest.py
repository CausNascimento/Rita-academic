from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pymupdf
import pytest

from rita_academic.audio.transcriber import FakeTranscriber
from rita_academic.config import Settings
from rita_academic.db import Database
from rita_academic.server import build_server

PAGE1 = ("A educação é um ato político. Ensinar não é transferir conhecimento, mas criar as "
         "possibilidades para a sua própria produção ou a sua construção. Não há docência sem "
         "discência.")
PAGE2 = ("Quem ensina aprende ao ensinar e quem aprende ensina ao aprender. A autonomia é um "
         "processo de amadurecimento do ser para si. Metodologia da pesquisa qualitativa.")
PAGE3 = "Referências. FREIRE, Paulo. Pedagogia da autonomia. São Paulo: Paz e Terra, 1996. ISBN 978-85-7753-163-9"


@pytest.fixture
def library(tmp_path: Path) -> Settings:
    root = tmp_path / "Biblioteca"
    (root / "_inbox").mkdir(parents=True)
    settings = Settings.from_env(env={}, library_root=str(root))
    settings.ensure_dirs()
    return settings


@pytest.fixture
def sample_pdf(library: Settings) -> Path:
    path = library.inbox_dir / "Freire, Paulo - 1996 - Pedagogia da autonomia.pdf"
    doc = pymupdf.open()
    for text in (PAGE1, PAGE2, PAGE3):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 700), text, fontsize=12, fontname="helv")
    doc.set_metadata({"title": "Pedagogia da autonomia", "author": "Paulo Freire",
                      "creationDate": "D:19960101000000"})
    # Destaque amarelo em "ato político" (página 1)
    p1 = doc[0]
    quads = p1.search_for("ato político", quads=True)
    a = p1.add_highlight_annot(quads)
    a.set_colors(stroke=(1, 1, 0))
    a.set_info(content="conceito-chave")
    a.update()
    # Sublinhado verde em "Não há docência sem discência" (pode quebrar linha)
    quads = p1.search_for("Não há docência sem discência", quads=True)
    u = p1.add_underline_annot(quads)
    u.set_colors(stroke=(0, 1, 0))
    u.update()
    # Nota adesiva na página 2
    n = doc[1].add_text_annot(pymupdf.Point(60, 60), "voltar aqui para o artigo")
    n.update()
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_md(library: Settings) -> Path:
    p = library.library_root / "Textos" / "nota-metodologia.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: Notas sobre metodologia\nauthors: [Silva, Ana]\nyear: 2020\n"
                 "tags: [metodologia]\n---\n# Notas sobre metodologia\n\nEntrevistas semiestruturadas "
                 "e análise de conteúdo.\n", encoding="utf-8")
    return p


@pytest.fixture
def tiny_wav(library: Settings) -> Path:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg não disponível")
    p = library.inbox_dir / "leitura-cap3.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=16000:cl=mono", "-t", "1", str(p)], check=True)
    return p


READING_SEGMENTS = [
    {"start": 0.0, "end": 3.0, "text": "Capítulo três, página quarenta e dois."},
    {"start": 3.0, "end": 8.0, "text": "Destaque isso: a educação é um ato político, nunca neutro. Fim do destaque."},
    {"start": 8.0, "end": 12.0, "text": "Nota: isso conversa com a pedagogia crítica. Fim da nota."},
    {"start": 12.0, "end": 15.0, "text": "Página 43. Aqui ele fala de autonomia."},
    {"start": 15.0, "end": 20.0, "text": "Destaque. Ensinar não é transferir conhecimento"},
    {"start": 20.0, "end": 24.0, "text": "mas criar as possibilidades para a sua produção. Fim do destaque."},
]


@pytest.fixture
def fake_transcriber() -> FakeTranscriber:
    return FakeTranscriber(READING_SEGMENTS)


@pytest.fixture
def db(library: Settings) -> Database:
    d = Database(library.db_path)
    yield d
    d.close()


@pytest.fixture
def server(library: Settings, fake_transcriber: FakeTranscriber, db: Database):
    return build_server(settings=library, transcriber=fake_transcriber, db=db)
