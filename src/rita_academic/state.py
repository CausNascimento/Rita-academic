"""Estado compartilhado do servidor (criado no lifespan)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rita_academic.audio.jobs import JobManager
from rita_academic.config import Settings
from rita_academic.db import Database


@dataclass
class AppState:
    settings: Settings
    db: Database
    jobs: JobManager
    transcriber: Any  # Transcriber (faster-whisper ou Fake)


_STATE: AppState | None = None


def set_state(state: AppState | None) -> None:
    global _STATE
    _STATE = state


def get_state() -> AppState:
    if _STATE is None:
        raise RuntimeError("Servidor não inicializado (lifespan ainda não rodou).")
    return _STATE
