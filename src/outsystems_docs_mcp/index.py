"""Markdown parsing and the SQLite FTS5 search index."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags TEXT NOT NULL,
    url TEXT NOT NULL,
    body TEXT NOT NULL,
    UNIQUE (source, path)
);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
    title, summary, tags, body,
    content='docs', content_rowid='id',
    tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.M)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


@dataclass
class Doc:
    path: str
    title: str
    summary: str
    tags: str
    body: str


def parse_markdown(text: str, rel_path: str) -> Doc:
    meta: dict = {}
    m = _FRONT_MATTER.match(text)
    if m:
        try:
            loaded = yaml.safe_load(m.group(1))
            if isinstance(loaded, dict):
                meta = loaded
        except yaml.YAMLError:
            pass
        text = text[m.end():]
    body = _HTML_COMMENT.sub("", text).strip()

    h1 = _H1.search(body)
    if h1:
        title = h1.group(1).strip()
    else:
        title = Path(rel_path).stem.replace("-", " ").replace("_", " ").capitalize()

    tags = meta.get("tags") or ""
    if isinstance(tags, list):
        tags = ", ".join(map(str, tags))
    return Doc(
        path=rel_path,
        title=title,
        summary=str(meta.get("summary") or "").strip(),
        tags=str(tags),
        body=body,
    )


def connect(db_file: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def insert_docs(conn: sqlite3.Connection, source: str, docs: list[tuple[Doc, str]]) -> None:
    """Insert (doc, url) pairs for one source, keeping the FTS table in sync."""
    for doc, url in docs:
        cur = conn.execute(
            "INSERT INTO docs (source, path, title, summary, tags, url, body) VALUES (?,?,?,?,?,?,?)",
            (source, doc.path, doc.title, doc.summary, doc.tags, url, doc.body),
        )
        conn.execute(
            "INSERT INTO docs_fts (rowid, title, summary, tags, body) VALUES (?,?,?,?,?)",
            (cur.lastrowid, doc.title, doc.summary, doc.tags, doc.body),
        )


_TOKEN = re.compile(r"[\w.]+", re.UNICODE)


def to_fts_queries(query: str) -> list[str]:
    """Turn free text into FTS5 queries, strictest first.

    Quoted phrases are kept and other words are quoted individually. Returns an
    all-terms (AND) query followed by an any-term (OR) query, so pages matching
    everything rank first and partial matches still fill the remaining slots.
    Users can pass raw FTS5 syntax by prefixing the query with `fts:`.
    """
    if query.startswith("fts:"):
        raw = query[4:].strip()
        return [raw] if raw else []
    phrases = re.findall(r'"([^"]+)"', query)
    rest = re.sub(r'"[^"]*"', " ", query)
    terms = [f'"{p}"' for p in phrases]
    terms += [f'"{t}"' for t in _TOKEN.findall(rest) if t.strip(".")]
    if not terms:
        return []
    if len(terms) == 1:
        return terms
    return [" AND ".join(terms), " OR ".join(terms)]


def search(
    conn: sqlite3.Connection, query: str, source: str | None = None, limit: int = 10
) -> list[sqlite3.Row]:
    # bm25 weights: title, summary, tags, body (lower = better).
    sql = """
        SELECT d.id, d.source, d.path, d.title, d.summary, d.url,
               snippet(docs_fts, 3, '**', '**', ' … ', 32) AS snippet,
               bm25(docs_fts, 10.0, 5.0, 3.0, 1.0) AS score
        FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid
        WHERE docs_fts MATCH ?
    """
    if source:
        sql += " AND d.source = ?"
    sql += " ORDER BY score LIMIT ?"

    results: list[sqlite3.Row] = []
    seen: set[int] = set()
    for fts in to_fts_queries(query):
        params: list = [fts, *([source] if source else []), limit]
        for row in conn.execute(sql, params):
            if row["id"] not in seen and len(results) < limit:
                seen.add(row["id"])
                results.append(row)
        if len(results) >= limit:
            break
    return results
