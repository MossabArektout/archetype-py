"""Cache helpers for persisting and reusing built import graphs."""

from __future__ import annotations

import pickle
from pathlib import Path

import networkx as nx


def get_cache_path(project_root: Path) -> Path:
    """Return the cache file path for a project."""
    return project_root.resolve() / ".archetype_cache"


def compute_file_signatures(project_root: Path) -> dict[str, float]:
    """Compute mtime signatures for Python files under project_root."""
    signatures: dict[str, float] = {}
    root = project_root.resolve()

    for file_path in root.rglob("*.py"):
        parts = file_path.parts
        if "__pycache__" in parts:
            continue
        if ".venv" in parts or "venv" in parts or "site-packages" in parts:
            continue
        signatures[str(file_path.resolve())] = file_path.stat().st_mtime

    return signatures


def load_cached_graph(
    project_root: Path,
) -> tuple[nx.DiGraph | None, dict[str, float] | None]:
    """Load a cached graph and signatures if available and validly readable."""
    cache_path = get_cache_path(project_root)
    if not cache_path.exists():
        return None, None

    try:
        payload = pickle.loads(cache_path.read_bytes())
        graph, signatures = payload
        if not isinstance(graph, nx.DiGraph):
            return None, None
        if not isinstance(signatures, dict):
            return None, None
        return graph, signatures
    except Exception:  # noqa: BLE001
        return None, None


def is_cache_valid(
    cached_signatures: dict[str, float] | None,
    current_signatures: dict[str, float],
) -> bool:
    """Return whether cached file signatures exactly match current signatures."""
    if cached_signatures is None:
        return False
    return cached_signatures == current_signatures


def save_cached_graph(
    project_root: Path,
    graph: nx.DiGraph,
    signatures: dict[str, float],
) -> None:
    """Persist graph/signatures cache, ignoring any write failures."""
    cache_path = get_cache_path(project_root)
    try:
        cache_path.write_bytes(pickle.dumps((graph, signatures)))
    except Exception:  # noqa: BLE001
        return


def ensure_gitignore_entry(project_root: Path) -> None:
    """Ensure .archetype_cache is present in project .gitignore."""
    gitignore_path = project_root.resolve() / ".gitignore"
    entry = ".archetype_cache"

    try:
        if not gitignore_path.exists():
            gitignore_path.write_text(f"{entry}\n", encoding="utf-8")
            return

        content = gitignore_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        if entry in lines:
            return

        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{entry}\n"
        gitignore_path.write_text(content, encoding="utf-8")
    except Exception:  # noqa: BLE001
        return
