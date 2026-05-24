"""Path exclusion helpers shared by graph building and reporting."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable


def normalize_exclude_patterns(patterns: Iterable[str] | None) -> tuple[str, ...]:
    """Normalize exclusion patterns and preserve declaration order."""
    if patterns is None:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_pattern in patterns:
        pattern = raw_pattern.strip().replace("\\", "/")
        if not pattern:
            continue
        while pattern.startswith("./"):
            pattern = pattern[2:]
        if not pattern:
            continue
        if pattern not in seen:
            normalized.append(pattern)
            seen.add(pattern)
    return tuple(normalized)


def is_path_excluded(path: Path, project_root: Path, exclude_patterns: Iterable[str]) -> bool:
    """Return whether path matches any configured exclusion pattern."""
    try:
        relative_path = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return False

    posix_path = relative_path.as_posix()
    parts = relative_path.parts
    wrapped_path = f"/{posix_path}/"

    for pattern in normalize_exclude_patterns(exclude_patterns):
        has_glob = any(char in pattern for char in "*?[]")
        anchored = pattern.startswith("/")
        directory_hint = pattern.endswith("/")
        core = pattern.strip("/")

        if not core:
            continue

        if has_glob:
            if anchored:
                if fnmatch(posix_path, core):
                    return True
            else:
                if fnmatch(posix_path, pattern) or fnmatch(posix_path, f"**/{pattern}"):
                    return True
            continue

        if directory_hint:
            if core in parts[:-1]:
                return True
            if anchored and (posix_path == core or posix_path.startswith(f"{core}/")):
                return True
            if f"/{core}/" in wrapped_path:
                return True
            continue

        if anchored:
            if posix_path == core or posix_path.startswith(f"{core}/"):
                return True
            continue

        if posix_path == core or posix_path.endswith(f"/{core}") or f"/{core}/" in wrapped_path:
            return True

    return False


def filter_excluded_paths(
    paths: Iterable[Path],
    *,
    project_root: Path,
    exclude_patterns: Iterable[str],
) -> set[Path]:
    """Return the subset of paths not matched by exclusions."""
    normalized = normalize_exclude_patterns(exclude_patterns)
    return {
        path.resolve()
        for path in paths
        if not is_path_excluded(path, project_root, normalized)
    }
