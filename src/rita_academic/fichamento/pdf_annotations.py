"""Extrai destaques e notas feitos em leitores de PDF comuns (anotações nativas)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pymupdf

KIND_BY_TYPE = {
    pymupdf.PDF_ANNOT_HIGHLIGHT: "highlight",
    pymupdf.PDF_ANNOT_UNDERLINE: "underline",
    pymupdf.PDF_ANNOT_STRIKE_OUT: "strikeout",
    pymupdf.PDF_ANNOT_SQUIGGLY: "squiggly",
    pymupdf.PDF_ANNOT_TEXT: "note",
    pymupdf.PDF_ANNOT_FREE_TEXT: "freetext",
}

NAMED_COLORS = {
    "amarelo": (1.0, 1.0, 0.0),
    "verde": (0.0, 1.0, 0.0),
    "azul": (0.0, 0.5, 1.0),
    "rosa": (1.0, 0.4, 0.7),
    "laranja": (1.0, 0.6, 0.0),
    "vermelho": (1.0, 0.0, 0.0),
    "roxo": (0.6, 0.3, 0.9),
    "cinza": (0.6, 0.6, 0.6),
}


def color_to_hex(rgb: list[float] | tuple[float, ...] | None) -> str | None:
    if not rgb or len(rgb) < 3:
        return None
    r, g, b = (round(max(0, min(1, c)) * 255) for c in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def color_name(rgb: list[float] | tuple[float, ...] | None) -> str | None:
    if not rgb or len(rgb) < 3:
        return None
    best, best_d = None, 10.0
    for name, ref in NAMED_COLORS.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb[:3], ref))
        if d < best_d:
            best, best_d = name, d
    return best


def _quad_text(page: pymupdf.Page, annot: pymupdf.Annot) -> str:
    """Texto coberto pelos quadriláteros do destaque (robusto a múltiplas linhas)."""
    verts = annot.vertices or []
    rects: list[pymupdf.Rect] = []
    for i in range(0, len(verts) - 3, 4):
        q = pymupdf.Quad(verts[i : i + 4])
        rects.append(q.rect)
    if not rects:
        rects = [annot.rect]
    words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,wno
    picked: list[tuple[int, int, int, str]] = []
    for r in rects:
        r = pymupdf.Rect(r)
        for w in words:
            wr = pymupdf.Rect(w[:4])
            inter = wr & r
            if not inter.is_empty and inter.get_area() >= 0.5 * wr.get_area():
                picked.append((w[5], w[6], w[7], w[4]))
    if not picked:
        return page.get_textbox(annot.rect).strip()
    picked = sorted(set(picked))
    return _join_words(picked)


def _join_words(words: list[tuple[int, int, int, str]]) -> str:
    out: list[str] = []
    prev_line = None
    for block, line, _, word in words:
        key = (block, line)
        if prev_line is not None and key != prev_line and out and out[-1].endswith("-"):
            out[-1] = out[-1][:-1]
            out.append(word)
            prev_line = key
            continue
        out.append(word)
        prev_line = key
    text = " ".join(out)
    return re.sub(r"\s+", " ", text).strip()


def extract_annotations(path: Path, doc_id: str, kinds: list[str] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            for annot in page.annots():
                kind = KIND_BY_TYPE.get(annot.type[0])
                if not kind or (kinds and kind not in kinds):
                    continue
                info = annot.info or {}
                colors = annot.colors or {}
                rgb = colors.get("stroke") or colors.get("fill")
                comment = (info.get("content") or "").strip()
                if kind in ("note", "freetext"):
                    text = ""
                else:
                    text = _quad_text(page, annot)
                raw = f"{doc_id}|{page.number}|{kind}|{text}|{comment}|{annot.rect}"
                out.append({
                    "id": hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12],
                    "doc_id": doc_id,
                    "page": page.number + 1,
                    "kind": kind,
                    "color_hex": color_to_hex(rgb),
                    "color_name": color_name(rgb),
                    "text": text,
                    "comment": comment,
                    "author": (info.get("title") or None),
                    "created": _pdf_date(info.get("creationDate") or info.get("modDate")),
                })
    return out


def page_has_text(path: Path) -> bool:
    with pymupdf.open(path) as doc:
        for i in range(min(5, doc.page_count)):
            if doc[i].get_text("text").strip():
                return True
    return False


def _pdf_date(s: str | None) -> str | None:
    if not s:
        return None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", s)
    if not m:
        return s
    y, mo, d, h, mi = m.groups()
    return f"{y}-{mo}-{d}" + (f"T{h}:{mi or '00'}" if h else "")
