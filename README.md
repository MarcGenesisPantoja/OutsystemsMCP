# OutSystems Documentation MCP

An [MCP](https://modelcontextprotocol.io) server that lets AI assistants (Claude Code, Claude Desktop, Cursor, …) search and read the official OutSystems documentation offline.

It indexes the public Markdown sources OutSystems publishes on GitHub:

| Source key | Content | Repository |
|---|---|---|
| `o11` | OutSystems 11 | [OutSystems/docs-product](https://github.com/OutSystems/docs-product) |
| `odc` | OutSystems Developer Cloud | [OutSystems/docs-odc](https://github.com/OutSystems/docs-odc) |
| `howtos` | How-to guides | [OutSystems/docs-howtos](https://github.com/OutSystems/docs-howtos) |

## Setup

Requires [uv](https://docs.astral.sh/uv/) and `git`.

```bash
git clone <your-repo-url> outsystems-documentation-mcp
cd outsystems-documentation-mcp
uv sync
uv run sync
```

`uv run sync` makes a shallow, Markdown-only clone of each repository into `data/repos/` (~30 MB) and builds a SQLite full-text index at `data/docs.db`. It takes a few seconds. Run it again at any time to pull the latest docs.

Options:

- `uv run sync --source odc` – fetch only some sources (repeatable); the index is always rebuilt from everything already downloaded.
- `uv run sync --skip-fetch` – rebuild the index without network access.
- Set `OUTSYSTEMS_DOCS_DATA_DIR` to store data somewhere other than `./data` (set it for both `sync` and the server).

## Connect it to your MCP client

The server talks over stdio. Replace `/path/to/outsystems-documentation-mcp` with the absolute path of your checkout.

**Claude Code**

```bash
claude mcp add outsystems-docs -- uv --directory /path/to/outsystems-documentation-mcp run outsystems-docs-mcp
```

**Claude Desktop / Cursor / other clients** (`claude_desktop_config.json`, `.cursor/mcp.json`, …)

```json
{
  "mcpServers": {
    "outsystems-docs": {
      "command": "uv",
      "args": ["--directory", "/path/to/outsystems-documentation-mcp", "run", "outsystems-docs-mcp"]
    }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `search_docs(query, source?, limit?)` | Ranked full-text search. Pages matching all terms come first; use `"quoted phrases"`, or prefix with `fts:` for raw [FTS5 syntax](https://www.sqlite.org/fts5.html#full_text_query_syntax). |
| `get_doc(path, offset?, max_chars?)` | Read a page as Markdown, e.g. `o11:building-apps/timers/timer-create-run.md`. Long pages are paged with `offset`. |
| `list_docs(source, prefix?)` | Browse sections, or list the pages under a folder. |
| `index_info()` | When the index was last synced and how many pages it has. |

## Development

```bash
uv run pytest
```
