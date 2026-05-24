"""Git and filesystem date utilities for date-scoped rule execution."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from archetype.analysis.path_filters import is_path_excluded, normalize_exclude_patterns

_IGNORED_DIRS = {"__pycache__", "venv", ".venv", "env", ".env"}


def parse_date_string(date_str: str) -> date:
    """Parse an ISO date string in YYYY-MM-DD format."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise ValueError(
            f"Invalid date '{date_str}'. Expected format: YYYY-MM-DD."
        )
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            f"Invalid date '{date_str}'. Expected format: YYYY-MM-DD."
        ) from exc


def get_file_last_modified_date(file_path: Path, project_root: Path) -> date:
    """Return the most recent modification date for a file using git or filesystem."""
    resolved_root = project_root.resolve()
    resolved_file = file_path.resolve()

    try:
        rel_path = resolved_file.relative_to(resolved_root)
    except ValueError:
        rel_path = resolved_file

    try:
        completed = subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--format=%cd",
                "--date=short",
                str(rel_path),
            ],
            cwd=resolved_root,
            capture_output=True,
            text=True,
            check=True,
        )
        output = completed.stdout.strip()
        if output:
            return parse_date_string(output)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        pass

    try:
        return datetime.fromtimestamp(resolved_file.stat().st_mtime).date()
    except OSError:
        return date.today()


def get_files_modified_after(
    date_str: str,
    project_root: Path,
    *,
    exclude_patterns: Iterable[str] | None = None,
) -> set[Path]:
    """Return Python files under project_root modified strictly after date_str."""
    threshold = parse_date_string(date_str)
    resolved_root = project_root.resolve()
    normalized_excludes = normalize_exclude_patterns(exclude_patterns)
    modified_files: set[Path] = set()

    for root, dirs, files in os.walk(resolved_root):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
        root_path = Path(root)

        for filename in files:
            if not filename.endswith(".py"):
                continue
            file_path = (root_path / filename).resolve()
            if is_path_excluded(file_path, resolved_root, normalized_excludes):
                continue
            if get_file_last_modified_date(file_path, resolved_root) > threshold:
                modified_files.add(file_path)

    return modified_files


def get_files_changed_from(
    ref: str,
    project_root: Path,
    *,
    exclude_patterns: Iterable[str] | None = None,
) -> set[Path]:
    """Return Python files changed from ref...HEAD."""
    resolved_root = project_root.resolve()
    normalized_excludes = normalize_exclude_patterns(exclude_patterns)
    completed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{ref}...HEAD", "--", "*.py"],
        cwd=resolved_root,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_files: set[Path] = set()
    for line in completed.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        changed_file = (resolved_root / rel).resolve()
        if is_path_excluded(changed_file, resolved_root, normalized_excludes):
            continue
        changed_files.add(changed_file)
    return changed_files
