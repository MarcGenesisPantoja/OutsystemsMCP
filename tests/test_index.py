from outsystems_docs_mcp import index

PAGE = """---
tags: timers, batch
summary: Learn how to create Timers.
---

<!-- internal note -->
# Create and Run Timers

Timers run **batch jobs** in the background.
"""


def test_parse_markdown_reads_front_matter_and_title():
    doc = index.parse_markdown(PAGE, "building-apps/timers/create.md")
    assert doc.title == "Create and Run Timers"
    assert doc.summary == "Learn how to create Timers."
    assert doc.tags == "timers, batch"
    assert "internal note" not in doc.body


def test_parse_markdown_without_front_matter_falls_back_to_filename():
    doc = index.parse_markdown("Just text.", "data/site-properties.md")
    assert doc.title == "Site properties"
    assert doc.summary == ""


def test_to_fts_queries():
    assert index.to_fts_queries('rest "site property"') == [
        '"site property" AND "rest"',
        '"site property" OR "rest"',
    ]
    assert index.to_fts_queries("timer") == ['"timer"']
    assert index.to_fts_queries("fts:a NEAR b") == ["a NEAR b"]
    assert index.to_fts_queries("  ") == []


def test_search_ranks_full_matches_first(tmp_path):
    conn = index.connect(tmp_path / "t.db")
    index.create_schema(conn)
    docs = [
        index.parse_markdown(PAGE, "timers.md"),
        index.parse_markdown("# Background tasks\n\nAll about background work.", "bg.md"),
    ]
    index.insert_docs(conn, "o11", [(d, "u") for d in docs])
    rows = index.search(conn, "timers background")
    assert [r["path"] for r in rows] == ["timers.md", "bg.md"]
    assert index.search(conn, "timers", source="odc") == []
