"""Parser determinístico de comandos de voz em português.

Transforma segmentos de transcrição em destaques e notas estruturados,
com página/capítulo/seção de contexto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from rita_academic.textutil import normalize

UNITS = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "quatorze": 14, "catorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
    "dezoito": 18, "dezenove": 19,
}
TENS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60,
        "setenta": 70, "oitenta": 80, "noventa": 90}
HUNDREDS = {"cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200, "trezentos": 300,
            "trezentas": 300, "quatrocentos": 400, "quatrocentas": 400, "quinhentos": 500,
            "quinhentas": 500, "seiscentos": 600, "seiscentas": 600, "setecentos": 700,
            "setecentas": 700, "oitocentos": 800, "oitocentas": 800, "novecentos": 900,
            "novecentas": 900}
NUMBER_WORDS = set(UNITS) | set(TENS) | set(HUNDREDS) | {"e", "mil"}
ROMAN_RE = re.compile(r"^(?=[ivxlc]+$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")


def words_to_int(tokens: list[str]) -> int | None:
    """'quarenta e dois' -> 42; 'cento e vinte' -> 120; '42' -> 42."""
    if not tokens:
        return None
    if len(tokens) == 1 and tokens[0].isdigit():
        return int(tokens[0])
    total, current = 0, 0
    seen = False
    for t in tokens:
        if t == "e":
            continue
        if t == "mil":
            current = (current or 1) * 1000
            total += current
            current = 0
            seen = True
        elif t in HUNDREDS:
            current += HUNDREDS[t]
            seen = True
        elif t in TENS:
            current += TENS[t]
            seen = True
        elif t in UNITS:
            current += UNITS[t]
            seen = True
        elif t.isdigit():
            current += int(t)
            seen = True
        else:
            return None
    return total + current if seen else None


@dataclass
class _State:
    mode: str = "idle"  # idle | highlight | note
    buffer: list[str] = field(default_factory=list)
    start: float = 0.0
    end: float = 0.0
    page: int | None = None
    chapter: str | None = None
    section: str | None = None
    last_end: float = 0.0


class CommandParser:
    def __init__(self, keywords: dict[str, Any]):
        self.kw = {k: [normalize(x) for x in v] if isinstance(v, list) else v
                   for k, v in keywords.items()}
        self.note_gap = float(self.kw.get("note_gap_seconds", 4.0))
        # Ordena por tamanho (frases maiores primeiro) para evitar casar "nota" dentro de "fim da nota".
        self._phrase_cmds: list[tuple[str, str]] = sorted(
            [(p, cmd) for cmd in ("highlight_end", "note_end", "highlight_start", "note_start",
                                   "cancel") for p in self.kw.get(cmd, [])],
            key=lambda x: -len(x[0]))
        self._loc_words = {w: cmd for cmd in ("page", "chapter", "section")
                           for w in self.kw.get(cmd, [])}

    # ------------------------------------------------------------------
    def parse(self, segments: list[dict[str, Any]]) -> dict[str, Any]:
        st = _State()
        items: list[dict[str, Any]] = []
        unparsed: list[dict[str, Any]] = []
        pages_seen: list[int] = []

        def close(kind_hint: str | None = None) -> None:
            text = " ".join(st.buffer).strip()
            if st.mode != "idle" and text:
                items.append({"kind": st.mode if st.mode != "note" else "note", "text": text,
                              "page": st.page, "chapter": st.chapter, "section": st.section,
                              "start": st.start, "end": st.end})
            st.mode, st.buffer = "idle", []

        for seg in segments:
            raw_text = seg["text"]
            start, end = float(seg["start"]), float(seg["end"])
            # Pausa longa fecha uma nota aberta (não um destaque: leitura pode ter pausas).
            if st.mode == "note" and start - st.last_end > self.note_gap:
                close()
            tokens = self._tokenize(raw_text)
            events = self._events(tokens)
            segment_touched = False
            for ev in events:
                segment_touched = True
                kind, payload = ev["kind"], ev["payload"]
                if kind == "text":
                    if st.mode != "idle":
                        st.buffer.append(payload)
                        st.end = end
                    else:
                        unparsed.append({"start": start, "end": end, "text": payload})
                elif kind == "page":
                    st.page = payload
                    if payload not in pages_seen:
                        pages_seen.append(payload)
                elif kind == "chapter":
                    st.chapter = payload
                elif kind == "section":
                    st.section = payload
                elif kind == "highlight_start":
                    close()
                    st.mode, st.start, st.end = "highlight", start, end
                elif kind == "note_start":
                    close()
                    st.mode, st.start, st.end = "note", start, end
                elif kind in ("highlight_end", "note_end"):
                    st.end = end
                    close()
                elif kind == "cancel":
                    if st.mode != "idle":
                        st.mode, st.buffer = "idle", []
                    elif items:
                        items.pop()
            if not segment_touched and raw_text.strip():
                unparsed.append({"start": start, "end": end, "text": raw_text.strip()})
            st.last_end = end
        close()
        return {"items": items, "unparsed": unparsed, "pages_seen": pages_seen}

    # ------------------------------------------------------------------
    def _tokenize(self, text: str) -> list[tuple[str, str]]:
        """Lista de (token_normalizado, token_original) preservando a grafia original."""
        out: list[tuple[str, str]] = []
        for orig in re.findall(r"\w+|[^\w\s]", text, re.UNICODE):
            norm = normalize(orig)
            if norm:
                out.append((norm, orig))
            elif orig in ".,;:!?":
                out.append(("", orig))
        return out

    def _events(self, tokens: list[tuple[str, str]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        buf: list[str] = []
        i = 0
        norms = [n for n, _ in tokens]

        def flush_text() -> None:
            text = " ".join(buf).strip()
            text = re.sub(r"\s+([.,;:!?])", r"\1", text)
            if text and re.search(r"\w", text):
                events.append({"kind": "text", "payload": text})
            buf.clear()

        while i < len(tokens):
            norm, orig = tokens[i]
            if norm == "":
                buf.append(orig)
                i += 1
                continue
            # Localizadores: "pagina 42", "pagina quarenta e dois", "capitulo iii"
            if norm in self._loc_words:
                cmd = self._loc_words[norm]
                j = i + 1
                num_tokens: list[str] = []
                while j < len(norms) and (norms[j].isdigit() or norms[j] in NUMBER_WORDS
                                          or (cmd != "page" and ROMAN_RE.match(norms[j]))):
                    if norms[j] == "e" and (j + 1 >= len(norms) or norms[j + 1] not in NUMBER_WORDS
                                            and not norms[j + 1].isdigit()):
                        break
                    num_tokens.append(norms[j])
                    j += 1
                value: Any = None
                if num_tokens:
                    value = words_to_int(num_tokens)
                    if value is None and cmd != "page" and ROMAN_RE.match(num_tokens[0]):
                        value = num_tokens[0].upper()
                if value is not None:
                    flush_text()
                    events.append({"kind": cmd, "payload": value if cmd == "page" else str(value)})
                    # Remove pontuação logo após o número ("página 42.")
                    if j < len(tokens) and tokens[j][0] == "":
                        j += 1
                    i = j
                    continue
            # Comandos por frase
            matched = False
            for phrase, cmd in self._phrase_cmds:
                plen = len(phrase.split())
                if norms[i:i + plen] == phrase.split():
                    flush_text()
                    events.append({"kind": cmd, "payload": None})
                    i += plen
                    # Pontuação/“isso” residual após o comando
                    if i < len(tokens) and tokens[i][0] == "":
                        i += 1
                    matched = True
                    break
            if matched:
                continue
            buf.append(orig)
            i += 1
        flush_text()
        return events
