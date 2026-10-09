"""Shared configuration: documentation sources and where local data lives."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    key: str
    label: str
    repo: str
    branch: str
    content_dir: str = "src"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.repo}.git"

    def github_url(self, rel_path: str) -> str:
        return f"https://github.com/{self.repo}/blob/{self.branch}/{self.content_dir}/{rel_path}"


SOURCES: dict[str, Source] = {
    s.key: s
    for s in (
        Source("o11", "OutSystems 11 (O11)", "OutSystems/docs-product", "master"),
        Source("odc", "OutSystems Developer Cloud (ODC)", "OutSystems/docs-odc", "main"),
        Source("howtos", "OutSystems How-to guides", "OutSystems/docs-howtos", "master"),
    )
}


def data_dir() -> Path:
    """Directory holding cloned repos and the search index.

    Override with OUTSYSTEMS_DOCS_DATA_DIR. Defaults to `data/` in the project
    checkout so `uv run sync` and the server agree regardless of the cwd an MCP
    client launches us from; falls back to the user data dir when installed
    as a regular (non-editable) package.
    """
    env = os.environ.get("OUTSYSTEMS_DOCS_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    project_root = Path(__file__).resolve().parents[2]
    if (project_root / "pyproject.toml").is_file():
        return project_root / "data"
    xdg = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(xdg) / "outsystems-docs-mcp"


def repos_dir() -> Path:
    return data_dir() / "repos"


def db_path() -> Path:
    return data_dir() / "docs.db"
