"""MCP server exposing search over the locally indexed OutSystems documentation."""

from __future__ import annotations

import sqlite3
from typing import Literal

from mcp.server.mcpserver import MCPServer

from . import config, index

mcp = MCPServer(
    "outsystems-docs",
    instructions=(
        "Search and read the official OutSystems documentation. Sources: "
        "'o11' (OutSystems 11), 'odc' (OutSystems Developer Cloud) and 'howtos' "
        "(How-to guides). Use search_docs to find pages, then get_doc to read one. "
        "O11 and ODC differ significantly; filter by source when the user's platform is known."
    ),
)

SourceKey = Literal["o11", "odc", "howtos"]


class IndexMissing(RuntimeError):
    pass


def _connect() -> sqlite3.Connection:
    db = config.db_path()
    if not db.is_file():
        raise IndexMissing(
            f"Documentation index not found at {db}. Run `uv run sync` in the project directory first."
        )
    return index.connect(db)


@mcp.tool()
def search_docs(query: str, source: SourceKey | None = None, limit: int = 10) -> str:
    """Full-text search across OutSystems documentation.

    Args:
        query: Keywords or a "quoted phrase". Prefix with `fts:` to pass raw SQLite FTS5 syntax.
        source: Restrict to 'o11', 'odc' or 'howtos'. Omit to search all.
        limit: Maximum number of results (1-50).
    """
    limit = max(1, min(limit, 50))
    with _connect() as conn:
        try:
            rows = index.search(conn, query, source, limit)
        except sqlite3.OperationalError as e:
            return f"Invalid search query: {e}"
    if not rows:
        return f"No results for {query!r}."
    out = []
    for i, r in enumerate(rows, 1):
        lines = [f"{i}. [{r['source']}] {r['title']}", f"   path: {r['source']}:{r['path']}"]
        if r["summary"]:
            lines.append(f"   summary: {r['summary']}")
        lines.append(f"   excerpt: {' '.join(r['snippet'].split())}")
        out.append("\n".join(lines))
    return "\n\n".join(out)


@mcp.tool()
def get_doc(path: str, offset: int = 0, max_chars: int = 20000) -> str:
    """Read a documentation page as Markdown.

    Args:
        path: Page identifier as returned by search_docs, e.g. 'o11:building-apps/data/intro.md'.
        offset: Character offset to start from, for paging through long pages.
        max_chars: Maximum characters to return.
    """
    source, sep, rel = path.partition(":")
    if not sep or source not in config.SOURCES:
        return "Path must look like '<source>:<path>' where source is one of: " + ", ".join(config.SOURCES)
    with _connect() as conn:
        row = conn.execute(
            "SELECT title, summary, url, body FROM docs WHERE source = ? AND path = ?", (source, rel)
        ).fetchone()
    if row is None:
        return f"No page found for {path!r}. Use search_docs or list_docs to find valid paths."
    body = row["body"]
    offset = max(0, offset)
    chunk = body[offset : offset + max(1, max_chars)]
    header = [f"Title: {row['title']}", f"Source: {config.SOURCES[source].label}", f"URL: {row['url']}"]
    if row["summary"]:
        header.append(f"Summary: {row['summary']}")
    end = offset + len(chunk)
    if offset or end < len(body):
        header.append(f"Showing characters {offset}-{end} of {len(body)}.")
        if end < len(body):
            header.append(f"Call get_doc again with offset={end} for more.")
    return "\n".join(header) + "\n\n---\n\n" + chunk


@mcp.tool()
def list_docs(source: SourceKey, prefix: str = "", limit: int = 200) -> str:
    """Browse the documentation tree.

    Without a prefix, returns the top-level sections and their page counts. With a
    prefix (e.g. 'building-apps/data'), lists pages under that folder.

    Args:
        source: 'o11', 'odc' or 'howtos'.
        prefix: Folder path to list pages under.
        limit: Maximum number of pages to list.
    """
    with _connect() as conn:
        if not prefix:
            rows = conn.execute(
                """SELECT CASE WHEN instr(path, '/') > 0 THEN substr(path, 1, instr(path, '/') - 1)
                               ELSE path END AS section, count(*) AS n
                   FROM docs WHERE source = ? GROUP BY section ORDER BY section""",
                (source,),
            ).fetchall()
            return "\n".join(f"{r['section']} ({r['n']} pages)" for r in rows) or "No pages indexed."
        prefix = prefix.strip("/") + "/"
        rows = conn.execute(
            "SELECT path, title FROM docs WHERE source = ? AND substr(path, 1, ?) = ? ORDER BY path LIMIT ?",
            (source, len(prefix), prefix, max(1, limit)),
        ).fetchall()
    if not rows:
        return f"No pages under {prefix!r}."
    return "\n".join(f"{source}:{r['path']} — {r['title']}" for r in rows)


@mcp.tool()
def index_info() -> str:
    """Report when the documentation index was last synced and how many pages it holds."""
    with _connect() as conn:
        synced = conn.execute("SELECT value FROM meta WHERE key = 'synced_at'").fetchone()
        counts = conn.execute("SELECT source, count(*) AS n FROM docs GROUP BY source").fetchall()
    lines = [f"Last synced: {synced['value'] if synced else 'unknown'}"]
    lines += [f"{config.SOURCES[r['source']].label}: {r['n']} pages" for r in counts]
    return "\n".join(lines)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
