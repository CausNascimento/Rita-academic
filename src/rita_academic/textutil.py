"""Utilitários de texto compartilhados."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC

from unidecode import unidecode

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Minúsculas, sem acentos, sem pontuação, espaços colapsados."""
    text = unidecode(unicodedata.normalize("NFKC", text)).lower()
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def slugify(text: str, max_len: int = 80) -> str:
    s = normalize(text).replace(" ", "-")
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len] or "sem-titulo"


def safe_filename(text: str, max_len: int = 120) -> str:
    """Nome de arquivo legível (mantém acentos), sem caracteres proibidos."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    text = _WS.sub(" ", text).strip(" .")
    return text[:max_len] or "sem-titulo"


def now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat()
