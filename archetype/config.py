"""Configuration loading for CLI behavior."""

from __future__ import annotations

import tomllib
from pathlib import Path


def load_exclude_patterns(project_root: Path) -> list[str]:
    """Load exclusion patterns from pyproject.toml [tool.archetype]."""
    config_path = project_root.resolve() / "pyproject.toml"
    if not config_path.is_file():
        return []

    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid pyproject.toml: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to read pyproject.toml: {exc}") from exc

    tool = payload.get("tool")
    if not isinstance(tool, dict):
        return []
    archetype = tool.get("archetype")
    if not isinstance(archetype, dict):
        return []

    raw_patterns = archetype.get("exclude")
    if raw_patterns is None:
        raw_patterns = archetype.get("excludes")
    if raw_patterns is None:
        return []

    if isinstance(raw_patterns, str):
        return [raw_patterns]
    if not isinstance(raw_patterns, list) or not all(
        isinstance(pattern, str) for pattern in raw_patterns
    ):
        raise ValueError(
            "Invalid [tool.archetype] exclude value. Expected a string or array of strings."
        )
    return list(raw_patterns)
