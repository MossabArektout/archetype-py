"""Cache helpers for persisting and reusing built import graphs."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Iterable

import networkx as nx

from archetype.analysis.path_filters import is_path_excluded, normalize_exclude_patterns


def get_cache_path(project_root: Path) -> Path:
    """Return the cache file path for a project."""
    return project_root.resolve() / ".archetype_cache"


# Signature recorded when a file cannot be stat'ed at all, for example a
# broken symlink. It never equals a real signature, so the cache is rebuilt
# and the rebuild surfaces the underlying read error instead of crashing here.
_UNREADABLE_SIGNATURE = (-1.0, -1)
_EXCLUDE_SIGNATURE = (-1.0, 0)


def compute_file_signatures(
    project_root: Path,
    *,
    exclude_patterns: Iterable[str] | None = None,
) -> dict[str, tuple[float, int]]:
    """Compute mtime and permission signatures for Python files under project_root."""
    signatures: dict[str, tuple[float, int]] = {}
    root = project_root.resolve()
    normalized_excludes = normalize_exclude_patterns(exclude_patterns)

    for file_path in root.rglob("*.py"):
        parts = file_path.parts
        if "__pycache__" in parts:
            continue
        if ".venv" in parts or "venv" in parts or "site-packages" in parts:
            continue
        if is_path_excluded(file_path, root, normalized_excludes):
            continue
        try:
            stat_result = file_path.stat()
        except OSError:
            # Keyed on the unresolved path because resolve() may itself need a
            # working stat() for this entry.
            signatures[str(file_path)] = _UNREADABLE_SIGNATURE
            continue
        # Mode is part of the signature so that a file becoming unreadable
        # invalidates the cache even when its mtime is unchanged. Without this
        # a cached graph would silently hide the unreadable file.
        signatures[str(file_path.resolve())] = (stat_result.st_mtime, stat_result.st_mode)
    for excluded in normalized_excludes:
        signatures[f"__archetype_exclude__:{excluded}"] = _EXCLUDE_SIGNATURE

    return signatures


def load_cached_graph(
    project_root: Path,
) -> tuple[nx.DiGraph | None, dict[str, tuple[float, int]] | None]:
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
    cached_signatures: dict[str, tuple[float, int]] | None,
    current_signatures: dict[str, tuple[float, int]],
) -> bool:
    """Return whether cached file signatures exactly match current signatures."""
    if cached_signatures is None:
        return False
    return cached_signatures == current_signatures


def save_cached_graph(
    project_root: Path,
    graph: nx.DiGraph,
    signatures: dict[str, tuple[float, int]],
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
