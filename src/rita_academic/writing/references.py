"""Formatação de referências (ABNT simplificada e BibTeX) e citações."""

from __future__ import annotations

import re
from typing import Any

from rita_academic.textutil import slugify


def split_name(name: str) -> tuple[str, str]:
    """Retorna (sobrenome, prenomes)."""
    name = name.strip()
    if "," in name:
        sur, given = name.split(",", 1)
        return sur.strip(), given.strip()
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def abnt_author(name: str) -> str:
    sur, given = split_name(name)
    return f"{sur.upper()}, {given}".rstrip(", ")


def author_year(doc: dict[str, Any]) -> str:
    authors = doc.get("authors") or []
    year = doc.get("year") or "s.d."
    if not authors:
        title = (doc.get("title") or "Sem título").split(":")[0]
        return f"{title.upper()}, {year}"
    surnames = [split_name(a)[0].upper() for a in authors]
    if len(surnames) == 1:
        who = surnames[0]
    elif len(surnames) <= 3:
        who = "; ".join(surnames)
    else:
        who = f"{surnames[0]} et al."
    return f"{who}, {year}"


def abnt_inline(doc: dict[str, Any], locator: str | None = None) -> str:
    base = author_year(doc)
    return f"({base}, {locator})" if locator else f"({base})"


def abnt_reference(doc: dict[str, Any]) -> str:
    authors = doc.get("authors") or []
    if authors:
        who = "; ".join(abnt_author(a) for a in authors[:3])
        if len(authors) > 3:
            who += " et al."
    else:
        who = (doc.get("title") or "SEM TÍTULO").split(":")[0].upper()
    title = doc.get("title") or "Sem título"
    parts = [f"{who}.", f"**{title}**."]
    if doc.get("publisher"):
        parts.append(f"{doc['publisher']},")
    parts.append(f"{doc.get('year') or '[s.d.]'}.")
    if doc.get("doi"):
        parts.append(f"DOI: {doc['doi']}.")
    elif doc.get("isbn"):
        parts.append(f"ISBN {doc['isbn']}.")
    return " ".join(parts)


def bibtex(doc: dict[str, Any]) -> str:
    authors = doc.get("authors") or []
    first_sur = split_name(authors[0])[0] if authors else "anon"
    key = slugify(f"{first_sur}{doc.get('year') or ''}", 40).replace("-", "")
    kind = "book" if doc.get("isbn") else "article" if doc.get("doi") else "misc"
    fields = {
        "title": doc.get("title") or "",
        "author": " and ".join(f"{split_name(a)[0]}, {split_name(a)[1]}".rstrip(", ") for a in authors),
        "year": doc.get("year"),
        "publisher": doc.get("publisher"),
        "doi": doc.get("doi"),
        "isbn": doc.get("isbn"),
        "language": doc.get("language"),
    }
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v not in (None, ""))
    return f"@{kind}{{{key},\n{body}\n}}"


def locator_for(source_kind: str, ref: str | None) -> str | None:
    if ref is None:
        return None
    if source_kind in ("page", "annotation"):
        return f"p. {ref}"
    if source_kind == "transcript":
        try:
            s = int(float(ref))
            return f"gravação {s // 60:02d}:{s % 60:02d}"
        except ValueError:
            return None
    return re.sub(r"\s+", " ", ref) or None


def citation(doc: dict[str, Any], source_kind: str, ref: str | None) -> dict[str, Any]:
    loc = locator_for(source_kind, ref)
    return {
        "author_year": author_year(doc),
        "abnt_inline": abnt_inline(doc, loc),
        "locator": loc,
        "reference": abnt_reference(doc),
    }
