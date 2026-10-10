"""Transcrição de áudio: protocolo + implementação faster-whisper + fake para testes."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, ClassVar, Protocol

ProgressCb = Callable[[float, float | None, str], None]


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path, language: str | None = None,
                   progress: ProgressCb | None = None) -> list[dict[str, Any]]: ...


def normalize_audio(src: Path, cache_dir: Path) -> Path:
    """Converte para WAV 16 kHz mono via ffmpeg (evita problemas de codec)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    dst = cache_dir / (src.stem + ".16k.wav")
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000",
           "-vn", str(dst)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError:
        return src  # sem ffmpeg: faster-whisper tenta decodificar diretamente
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg falhou: {exc.stderr.decode(errors='replace')}") from exc
    return dst


class FasterWhisperTranscriber:
    _model_cache: ClassVar[dict[tuple[str, str, str], Any]] = {}

    def __init__(self, model: str = "small", device: str = "cpu", compute_type: str = "int8",
                 cache_dir: Path | None = None, default_language: str = "pt"):
        self.model_name, self.device, self.compute_type = model, device, compute_type
        self.cache_dir = cache_dir
        self.default_language = default_language
        self.cancel_check: Callable[[], bool] | None = None

    def _model(self) -> Any:
        key = (self.model_name, self.device, self.compute_type)
        if key not in self._model_cache:
            from faster_whisper import WhisperModel

            self._model_cache[key] = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type)
        return self._model_cache[key]

    def transcribe(self, audio_path: Path, language: str | None = None,
                   progress: ProgressCb | None = None) -> list[dict[str, Any]]:
        path = normalize_audio(audio_path, self.cache_dir) if self.cache_dir else audio_path
        model = self._model()
        segments_iter, info = model.transcribe(
            str(path), language=language or self.default_language, vad_filter=True,
            beam_size=5)
        total = float(info.duration) if getattr(info, "duration", None) else None
        out: list[dict[str, Any]] = []
        for seg in self._iter(segments_iter):
            out.append({"start": float(seg.start), "end": float(seg.end), "text": seg.text.strip()})
            if progress:
                progress(float(seg.end), total, seg.text.strip()[:80])
            if self.cancel_check and self.cancel_check():
                break
        return out

    @staticmethod
    def _iter(it: Iterator[Any]) -> Iterator[Any]:
        yield from it


class FakeTranscriber:
    """Devolve segmentos roteirizados; usado em testes e para desenvolvimento offline."""

    def __init__(self, segments: list[dict[str, Any]]):
        self.segments = segments
        self.calls: list[Path] = []

    def transcribe(self, audio_path: Path, language: str | None = None,
                   progress: ProgressCb | None = None) -> list[dict[str, Any]]:
        self.calls.append(audio_path)
        total = self.segments[-1]["end"] if self.segments else None
        for s in self.segments:
            if progress:
                progress(s["end"], total, s["text"])
        return list(self.segments)
