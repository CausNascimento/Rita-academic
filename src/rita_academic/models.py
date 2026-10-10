"""Modelos de dados (pydantic) usados nas respostas das ferramentas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DocType = Literal["pdf", "epub", "md", "txt", "audio", "other"]
AnnotationKind = Literal["highlight", "underline", "strikeout", "squiggly", "note", "freetext"]


class DocumentSummary(BaseModel):
    id: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    type: DocType = "other"
    rel_path: str
    tags: list[str] = Field(default_factory=list)


class Document(DocumentSummary):
    path: str
    publisher: str | None = None
    doi: str | None = None
    isbn: str | None = None
    language: str | None = None
    pages: int | None = None
    size: int = 0
    added_at: str | None = None
    indexed_at: str | None = None
    has_text: bool = True


class Annotation(BaseModel):
    id: str
    doc_id: str
    page: int
    kind: AnnotationKind
    color_hex: str | None = None
    color_name: str | None = None
    text: str = ""
    comment: str = ""
    author: str | None = None
    created: str | None = None


class Citation(BaseModel):
    author_year: str
    abnt_inline: str
    locator: str | None = None
    reference: str


class Passage(BaseModel):
    doc_id: str
    title: str | None
    source_kind: str
    ref: str | None
    text: str
    citation: Citation


class SearchHit(BaseModel):
    doc_id: str
    title: str | None
    source_kind: str
    ref: str | None
    snippet: str
    score: float


class NoteSummary(BaseModel):
    id: str
    doc_id: str | None
    path: str
    title: str | None
    kind: str
    tags: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class Segment(BaseModel):
    start: float
    end: float
    text: str


class ReadingItem(BaseModel):
    kind: Literal["highlight", "note"]
    text: str
    page: int | None = None
    chapter: str | None = None
    section: str | None = None
    start: float
    end: float


class ReadingSession(BaseModel):
    items: list[ReadingItem] = Field(default_factory=list)
    unparsed: list[Segment] = Field(default_factory=list)
    pages_seen: list[int] = Field(default_factory=list)


class Job(BaseModel):
    id: str
    kind: str
    status: Literal["queued", "running", "done", "error", "cancelled"]
    progress: float = 0.0
    total: float | None = None
    message: str | None = None
    result: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class MoveProposal(BaseModel):
    doc_id: str
    from_path: str
    to_path: str
    reason: str | None = None


class MoveResult(BaseModel):
    doc_id: str
    from_path: str
    to_path: str
    applied: bool
    error: str | None = None


class ScanReport(BaseModel):
    scanned: int
    added: int
    updated: int
    unchanged: int
    removed: int
    errors: list[str] = Field(default_factory=list)
