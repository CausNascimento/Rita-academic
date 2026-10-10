"""Renderização determinística de anotações e sessões de leitura em Markdown."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

KIND_LABEL = {"highlight": "destaque", "underline": "sublinhado", "strikeout": "riscado",
              "squiggly": "ondulado", "note": "nota adesiva", "freetext": "texto livre"}


def annotations_to_markdown(annots: list[dict[str, Any]], group_by: str = "page") -> str:
    if not annots:
        return "_Nenhum destaque encontrado no PDF._"
    lines: list[str] = []
    if group_by == "color":
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for a in annots:
            groups[a.get("color_name") or "sem cor"].append(a)
        for color, items in groups.items():
            lines.append(f"### Cor: {color}")
            for a in sorted(items, key=lambda x: (x["page"], x["id"])):
                lines.append(_annot_line(a, with_page=True))
            lines.append("")
    else:
        groups_p: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for a in annots:
            groups_p[a["page"]].append(a)
        for page in sorted(groups_p):
            lines.append(f"### p. {page}")
            for a in groups_p[page]:
                lines.append(_annot_line(a, with_page=False))
            lines.append("")
    return "\n".join(lines).strip()


def _annot_line(a: dict[str, Any], with_page: bool) -> str:
    label = KIND_LABEL.get(a["kind"], a["kind"])
    meta = []
    if with_page:
        meta.append(f"p. {a['page']}")
    if a.get("color_name") and a["kind"] not in ("note", "freetext"):
        meta.append(a["color_name"])
    meta.append(label)
    head = f"- ({', '.join(meta)})"
    body = ""
    if a.get("text"):
        body += f' "{a["text"]}"'
    if a.get("comment"):
        body += f" — nota: {a['comment']}"
    return head + (body or " _(sem texto)_")


def reading_session_to_markdown(session: dict[str, Any]) -> str:
    items = session.get("items") or []
    if not items:
        return "_Nenhum destaque ou nota reconhecido na gravação._"
    lines: list[str] = []
    current_chapter = None
    for it in items:
        if it.get("chapter") and it["chapter"] != current_chapter:
            current_chapter = it["chapter"]
            lines.append(f"### Capítulo {current_chapter}")
        loc = []
        if it.get("page") is not None:
            loc.append(f"p. {it['page']}")
        if it.get("section"):
            loc.append(f"seção {it['section']}")
        loc.append(_fmt_ts(it["start"]))
        if it["kind"] == "highlight":
            lines.append(f"- ({', '.join(loc)}) \"{it['text']}\"")
        else:
            lines.append(f"- ({', '.join(loc)}) nota: {it['text']}")
    unparsed = session.get("unparsed") or []
    if unparsed:
        lines.append("")
        lines.append("### Trechos não interpretados")
        for s in unparsed:
            lines.append(f"- ({_fmt_ts(s['start'])}) {s['text']}")
    return "\n".join(lines)


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"
