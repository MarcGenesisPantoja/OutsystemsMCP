"""`uv run sync`: fetch the OutSystems docs repositories and rebuild the search index."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config, index


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def fetch_source(source: config.Source, dest: Path) -> None:
    """Shallow, sparse clone of the source's content dir; fast-forward if present."""
    if (dest / ".git").is_dir():
        print(f"[{source.key}] updating {source.repo} ...", flush=True)
        _git("fetch", "--depth", "1", "origin", source.branch, cwd=dest)
        _git("reset", "--hard", "FETCH_HEAD", cwd=dest)
        return
    print(f"[{source.key}] cloning {source.repo} ...", flush=True)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(
        "clone", "--depth", "1", "--filter=blob:none", "--sparse",
        "--no-checkout", "--branch", source.branch, source.clone_url, str(dest),
    )
    # Only Markdown is needed; with --filter=blob:none, images are never downloaded.
    _git("sparse-checkout", "set", "--no-cone", f"/{source.content_dir}/**/*.md", cwd=dest)
    _git("checkout", source.branch, cwd=dest)


def collect_docs(source: config.Source, repo: Path) -> list[tuple[index.Doc, str]]:
    root = repo / source.content_dir
    docs = []
    for md in sorted(root.rglob("*.md")):
        rel = md.relative_to(root).as_posix()
        text = md.read_text(encoding="utf-8", errors="replace")
        doc = index.parse_markdown(text, rel)
        if doc.body:
            docs.append((doc, source.github_url(rel)))
    return docs


def build_index(sources: list[config.Source], db_file: Path) -> dict[str, int]:
    tmp = db_file.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)
    counts: dict[str, int] = {}
    conn = index.connect(tmp)
    try:
        index.create_schema(conn)
        for source in sources:
            docs = collect_docs(source, config.repos_dir() / source.key)
            index.insert_docs(conn, source.key, docs)
            counts[source.key] = len(docs)
            print(f"[{source.key}] indexed {len(docs)} pages", flush=True)
        conn.execute(
            "INSERT OR REPLACE INTO meta VALUES ('synced_at', ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
        )
        conn.execute("INSERT INTO docs_fts(docs_fts) VALUES ('optimize')")
        conn.commit()
    finally:
        conn.close()
    tmp.replace(db_file)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sync", description="Download OutSystems documentation and build the local search index."
    )
    parser.add_argument(
        "--source", action="append", choices=sorted(config.SOURCES),
        help="Only sync these sources (repeatable). Defaults to all.",
    )
    parser.add_argument(
        "--skip-fetch", action="store_true",
        help="Rebuild the index from already-downloaded repos without hitting the network.",
    )
    args = parser.parse_args(argv)

    if shutil.which("git") is None:
        print("error: git is required but was not found on PATH", file=sys.stderr)
        return 1

    # The index is rebuilt from scratch, so it always covers every source;
    # --source only limits which repos are fetched.
    to_fetch = [config.SOURCES[k] for k in (args.source or config.SOURCES)]
    config.data_dir().mkdir(parents=True, exist_ok=True)

    if not args.skip_fetch:
        for source in to_fetch:
            try:
                fetch_source(source, config.repos_dir() / source.key)
            except subprocess.CalledProcessError as e:
                print(f"error: failed to fetch {source.repo}: {e}", file=sys.stderr)
                return 1

    available = [s for s in config.SOURCES.values() if (config.repos_dir() / s.key / s.content_dir).is_dir()]
    if not available:
        print("error: no documentation downloaded yet; run `uv run sync` without --skip-fetch", file=sys.stderr)
        return 1

    counts = build_index(available, config.db_path())
    print(f"Done: {sum(counts.values())} pages indexed into {config.db_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
