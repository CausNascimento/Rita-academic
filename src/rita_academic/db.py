"""Camada SQLite: schema, índice FTS5 e consultas."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  rel_path TEXT NOT NULL,
  type TEXT NOT NULL,
  title TEXT, authors TEXT NOT NULL DEFAULT '[]', year INTEGER,
  publisher TEXT, doi TEXT, isbn TEXT, language TEXT, pages INTEGER,
  size INTEGER NOT NULL DEFAULT 0, mtime REAL NOT NULL DEFAULT 0,
  added_at TEXT, indexed_at TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  has_text INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pages (
  doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_no INTEGER NOT NULL,
  text TEXT NOT NULL,
  PRIMARY KEY (doc_id, page_no)
);

CREATE TABLE IF NOT EXISTS annotations (
  id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_no INTEGER NOT NULL,
  kind TEXT NOT NULL,
  color_hex TEXT, color_name TEXT,
  text TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '',
  author TEXT, created TEXT
);

CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  doc_id TEXT,
  path TEXT NOT NULL UNIQUE,
  title TEXT, tags TEXT NOT NULL DEFAULT '[]',
  kind TEXT NOT NULL DEFAULT 'fichamento',
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS note_blocks (
  note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  heading TEXT, text TEXT NOT NULL,
  PRIMARY KEY (note_id, seq)
);

CREATE TABLE IF NOT EXISTS transcripts (
  doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  segment_no INTEGER NOT NULL,
  start_s REAL NOT NULL, end_s REAL NOT NULL,
  text TEXT NOT NULL,
  PRIMARY KEY (doc_id, segment_no)
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0, total REAL,
  message TEXT, result_json TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
  content,
  doc_id UNINDEXED,
  source_kind UNINDEXED,
  ref UNINDEXED,
  tokenize = 'unicode61 remove_diacritics 2'
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        # Uma conexão compartilhada entre a thread do servidor e a dos jobs: serializa o acesso.
        self._lock = threading.RLock()
        self._closed = False

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self.conn.close()

    # ---------- genérico ----------
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.conn.execute(sql, tuple(params))
            self.conn.commit()
            return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    def one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchone()

    # ---------- documentos ----------
    def upsert_document(self, doc: dict[str, Any]) -> None:
        cols = [
            "id", "path", "rel_path", "type", "title", "authors", "year", "publisher",
            "doi", "isbn", "language", "pages", "size", "mtime", "added_at", "indexed_at",
            "tags", "has_text",
        ]
        d = dict(doc)
        d["authors"] = json.dumps(d.get("authors") or [], ensure_ascii=False)
        d["tags"] = json.dumps(d.get("tags") or [], ensure_ascii=False)
        d["has_text"] = 1 if d.get("has_text", True) else 0
        values = [d.get(c) for c in cols]
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("id", "added_at"))
        self.execute(
            f"INSERT INTO documents ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            values,
        )

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        row = self.one("SELECT * FROM documents WHERE id=?", (doc_id,))
        return row_to_doc(row) if row else None

    def get_document_by_path(self, path: str) -> dict[str, Any] | None:
        row = self.one("SELECT * FROM documents WHERE path=?", (path,))
        return row_to_doc(row) if row else None

    def delete_document(self, doc_id: str) -> None:
        self.execute("DELETE FROM passages_fts WHERE doc_id=?", (doc_id,))
        self.execute("DELETE FROM documents WHERE id=?", (doc_id,))

    def list_documents(
        self,
        type_: str | None = None,
        tag: str | None = None,
        author: str | None = None,
        year: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where, params = [], []
        if type_:
            where.append("type=?")
            params.append(type_)
        if year:
            where.append("year=?")
            params.append(year)
        if author:
            where.append("lower(authors) LIKE ?")
            params.append(f"%{author.lower()}%")
        if tag:
            where.append("lower(tags) LIKE ?")
            params.append(f'%"{tag.lower()}"%')
        sql = "SELECT * FROM documents"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(title, rel_path) LIMIT ? OFFSET ?"
        params += [limit, offset]
        return [row_to_doc(r) for r in self.query(sql, params)]

    # ---------- páginas / FTS ----------
    def replace_pages(self, doc_id: str, pages: list[str]) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM pages WHERE doc_id=?", (doc_id,))
            self.conn.execute(
                "DELETE FROM passages_fts WHERE doc_id=? AND source_kind='page'", (doc_id,)
            )
            for i, text in enumerate(pages, start=1):
                if not text.strip():
                    continue
                self.conn.execute(
                    "INSERT INTO pages (doc_id, page_no, text) VALUES (?,?,?)", (doc_id, i, text)
                )
                self.conn.execute(
                    "INSERT INTO passages_fts (content, doc_id, source_kind, ref) VALUES (?,?,?,?)",
                    (text, doc_id, "page", str(i)),
                )
            self.conn.commit()

    def get_page(self, doc_id: str, page_no: int) -> str | None:
        row = self.one("SELECT text FROM pages WHERE doc_id=? AND page_no=?", (doc_id, page_no))
        return row["text"] if row else None

    def replace_annotations(self, doc_id: str, annots: list[dict[str, Any]]) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM annotations WHERE doc_id=?", (doc_id,))
            self.conn.execute(
                "DELETE FROM passages_fts WHERE doc_id=? AND source_kind='annotation'", (doc_id,)
            )
            for a in annots:
                self.conn.execute(
                    "INSERT INTO annotations (id, doc_id, page_no, kind, color_hex, color_name, text, "
                    "comment, author, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        a["id"], doc_id, a["page"], a["kind"], a.get("color_hex"), a.get("color_name"),
                        a.get("text", ""), a.get("comment", ""), a.get("author"), a.get("created"),
                    ),
                )
                content = (a.get("text", "") + "\n" + a.get("comment", "")).strip()
                if content:
                    self.conn.execute(
                        "INSERT INTO passages_fts (content, doc_id, source_kind, ref) VALUES (?,?,?,?)",
                        (content, doc_id, "annotation", str(a["page"])),
                    )
            self.conn.commit()

    def list_annotations(self, doc_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM annotations WHERE doc_id=? ORDER BY page_no, id", (doc_id,)
        )
        return [
            {
                "id": r["id"], "doc_id": r["doc_id"], "page": r["page_no"], "kind": r["kind"],
                "color_hex": r["color_hex"], "color_name": r["color_name"], "text": r["text"],
                "comment": r["comment"], "author": r["author"], "created": r["created"],
            }
            for r in rows
        ]

    def replace_transcript(self, doc_id: str, segments: list[dict[str, Any]]) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM transcripts WHERE doc_id=?", (doc_id,))
            self.conn.execute(
                "DELETE FROM passages_fts WHERE doc_id=? AND source_kind='transcript'", (doc_id,)
            )
            for i, s in enumerate(segments):
                self.conn.execute(
                    "INSERT INTO transcripts (doc_id, segment_no, start_s, end_s, text) VALUES (?,?,?,?,?)",
                    (doc_id, i, s["start"], s["end"], s["text"]),
                )
                self.conn.execute(
                    "INSERT INTO passages_fts (content, doc_id, source_kind, ref) VALUES (?,?,?,?)",
                    (s["text"], doc_id, "transcript", f"{s['start']:.1f}"),
                )
            self.conn.commit()

    def get_transcript(self, doc_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT start_s, end_s, text FROM transcripts WHERE doc_id=? ORDER BY segment_no",
            (doc_id,),
        )
        return [{"start": r["start_s"], "end": r["end_s"], "text": r["text"]} for r in rows]

    # ---------- notas ----------
    def upsert_note(self, note: dict[str, Any], blocks: list[dict[str, Any]]) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO notes (id, doc_id, path, title, tags, kind, updated_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET doc_id=excluded.doc_id, path=excluded.path, "
                "title=excluded.title, tags=excluded.tags, kind=excluded.kind, updated_at=excluded.updated_at",
                (
                    note["id"], note.get("doc_id"), note["path"], note.get("title"),
                    json.dumps(note.get("tags") or [], ensure_ascii=False),
                    note.get("kind", "fichamento"), note.get("updated_at"),
                ),
            )
            self.conn.execute("DELETE FROM note_blocks WHERE note_id=?", (note["id"],))
            self.conn.execute(
                "DELETE FROM passages_fts WHERE doc_id=? AND source_kind='note'", (note["id"],)
            )
            for i, b in enumerate(blocks):
                self.conn.execute(
                    "INSERT INTO note_blocks (note_id, seq, heading, text) VALUES (?,?,?,?)",
                    (note["id"], i, b.get("heading"), b["text"]),
                )
                self.conn.execute(
                    "INSERT INTO passages_fts (content, doc_id, source_kind, ref) VALUES (?,?,?,?)",
                    (b["text"], note["id"], "note", b.get("heading")),
                )
            self.conn.commit()

    def get_note(self, note_id: str) -> dict[str, Any] | None:
        row = self.one("SELECT * FROM notes WHERE id=?", (note_id,))
        return row_to_note(row) if row else None

    def list_notes(self, tag: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
        where, params = [], []
        if tag:
            where.append("lower(tags) LIKE ?")
            params.append(f'%"{tag.lower()}"%')
        if kind:
            where.append("kind=?")
            params.append(kind)
        sql = "SELECT * FROM notes"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC"
        return [row_to_note(r) for r in self.query(sql, params)]

    # ---------- busca ----------
    def search(
        self,
        query: str,
        kinds: list[str] | None = None,
        doc_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        where = ["passages_fts MATCH ?"]
        params: list[Any] = [fts_query(query)]
        if kinds:
            where.append(f"source_kind IN ({','.join('?' * len(kinds))})")
            params += kinds
        if doc_ids:
            where.append(f"doc_id IN ({','.join('?' * len(doc_ids))})")
            params += doc_ids
        sql = (
            "SELECT doc_id, source_kind, ref, bm25(passages_fts) AS score, "
            "snippet(passages_fts, 0, '[', ']', '…', 24) AS snippet "
            f"FROM passages_fts WHERE {' AND '.join(where)} ORDER BY score LIMIT ?"
        )
        params.append(limit)
        try:
            rows = self.query(sql, params)
        except sqlite3.OperationalError:
            # Consulta malformada para FTS: tenta como frase literal.
            params[0] = '"' + query.replace('"', '""') + '"'
            rows = self.query(sql, params)
        return [dict(r) for r in rows]

    # ---------- jobs ----------
    def upsert_job(self, job: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO jobs (id, kind, status, progress, total, message, result_json, created_at, "
            "updated_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, "
            "progress=excluded.progress, total=excluded.total, message=excluded.message, "
            "result_json=excluded.result_json, updated_at=excluded.updated_at",
            (
                job["id"], job["kind"], job["status"], job.get("progress", 0.0), job.get("total"),
                job.get("message"),
                json.dumps(job["result"], ensure_ascii=False) if job.get("result") is not None else None,
                job["created_at"], job["updated_at"],
            ),
        )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        return row_to_job(row) if row else None

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        return [row_to_job(r) for r in self.query(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        )]


def fts_query(query: str) -> str:
    """Converte uma consulta livre em sintaxe FTS5 tolerante.

    Mantém operadores explícitos (AND/OR/NOT, aspas, *). Caso contrário,
    cada termo vira um prefixo entre aspas, combinado implicitamente (AND).
    """
    q = query.strip()
    if not q:
        return '""'
    if any(tok in q for tok in ('"', " OR ", " AND ", " NOT ", "*", "NEAR(")):
        return q
    terms = [t for t in q.split() if t]
    return " ".join('"' + t.replace('"', '""') + '"*' for t in terms)


def row_to_doc(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["authors"] = json.loads(d.get("authors") or "[]")
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["has_text"] = bool(d.get("has_text", 1))
    return d


def row_to_note(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


def row_to_job(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["result"] = json.loads(d.pop("result_json")) if d.get("result_json") else None
    return d
