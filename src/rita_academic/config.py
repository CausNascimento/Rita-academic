"""Configuração do servidor via variáveis de ambiente (prefixo RITA_)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_KEYWORDS: dict[str, Any] = {
    # Comandos de voz em português. Todas as entradas são comparadas após
    # normalização (minúsculas, sem acentos, sem pontuação).
    "highlight_start": [
        "inicio do destaque", "inicio de destaque", "destaque isso", "destaca isso",
        "destacar isso", "marcar isso", "marca isso", "destaque", "destacar", "marcar",
    ],
    "highlight_end": [
        "fim do destaque", "fim de destaque", "fecha destaque", "fecha o destaque",
        "fim da marcacao", "fecha marcacao", "fim destaque",
    ],
    "note_start": [
        "inicio da nota", "nota minha", "minha nota", "observacao", "comentario",
        "nota",
    ],
    "note_end": ["fim da nota", "fim de nota", "fecha nota", "fecha a nota", "fim nota"],
    "page": ["pagina"],
    "chapter": ["capitulo"],
    "section": ["secao", "parte"],
    "cancel": ["cancela isso", "cancela", "apaga isso", "apaga", "esquece isso"],
    # Pausa (em segundos) entre segmentos que encerra uma nota aberta.
    "note_gap_seconds": 4.0,
}


@dataclass
class Settings:
    library_root: Path
    inbox_dir: Path
    notes_dir: Path
    notes_mode: str  # "notes_dir" | "next_to_source"
    db_path: Path
    cache_dir: Path
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    language: str = "pt"
    organize_template: str = "{type}/{author_sort}/{year} - {title}{ext}"
    http_host: str = "127.0.0.1"
    http_port: int = 8765
    keywords: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_KEYWORDS))

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, library_root: str | None = None) -> Settings:
        env = dict(os.environ if env is None else env)
        root_str = library_root or env.get("RITA_LIBRARY_ROOT")
        if not root_str:
            raise RuntimeError(
                "Defina RITA_LIBRARY_ROOT (pasta raiz da biblioteca) ou use --library."
            )
        root = Path(root_str).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

        def p(name: str, default: Path) -> Path:
            v = env.get(name)
            return Path(v).expanduser().resolve() if v else default

        keywords = dict(DEFAULT_KEYWORDS)
        kw_path = env.get("RITA_COMMAND_KEYWORDS")
        if kw_path:
            with open(kw_path, encoding="utf-8") as fh:
                override = yaml.safe_load(fh) or {}
            keywords.update(override)

        return cls(
            library_root=root,
            inbox_dir=p("RITA_INBOX_DIR", root / "_inbox"),
            notes_dir=p("RITA_NOTES_DIR", root / "_notes"),
            notes_mode=env.get("RITA_NOTES_MODE", "notes_dir"),
            db_path=p("RITA_DB_PATH", root / ".rita" / "index.sqlite"),
            cache_dir=p("RITA_CACHE_DIR", root / ".rita" / "cache"),
            whisper_model=env.get("RITA_WHISPER_MODEL", "small"),
            whisper_device=env.get("RITA_WHISPER_DEVICE", "cpu"),
            whisper_compute_type=env.get("RITA_WHISPER_COMPUTE_TYPE", "int8"),
            language=env.get("RITA_LANGUAGE", "pt"),
            organize_template=env.get(
                "RITA_ORGANIZE_TEMPLATE", "{type}/{author_sort}/{year} - {title}{ext}"
            ),
            http_host=env.get("RITA_HTTP_HOST", "127.0.0.1"),
            http_port=int(env.get("RITA_HTTP_PORT", "8765")),
            keywords=keywords,
        )

    def ensure_dirs(self) -> None:
        for d in (self.inbox_dir, self.notes_dir, self.db_path.parent, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)
