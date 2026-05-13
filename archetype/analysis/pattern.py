"""Pattern matching helpers for module selection in rules and DSL queries."""

from __future__ import annotations

import re
from functools import lru_cache
from re import Pattern


def validate_pattern(pattern: str) -> None:
    """Validate a module pattern and raise ValueError for invalid input."""
    if pattern == "":
        raise ValueError("Invalid module pattern: pattern cannot be empty.")
    if pattern.startswith("."):
        raise ValueError(
            f"Invalid module pattern '{pattern}': pattern cannot start with a dot."
        )
    if pattern.endswith("."):
        raise ValueError(
            f"Invalid module pattern '{pattern}': pattern cannot end with a dot."
        )
    if ".." in pattern:
        raise ValueError(
            f"Invalid module pattern '{pattern}': pattern cannot contain consecutive dots."
        )
    if re.search(r"\*{3,}", pattern):
        raise ValueError(
            f"Invalid module pattern '{pattern}': pattern cannot contain three or more consecutive '*'."
        )


def _segment_to_regex(segment: str) -> str:
    return "".join("[^.]*" if ch == "*" else re.escape(ch) for ch in segment)


def _collapse_globstar_segments(parts: list[str]) -> list[str]:
    collapsed: list[str] = []
    for part in parts:
        if part == "**" and collapsed and collapsed[-1] == "**":
            continue
        collapsed.append(part)
    return collapsed


def _wildcard_pattern_to_regex(pattern: str) -> str:
    parts = _collapse_globstar_segments(pattern.split("."))
    if parts == ["**"]:
        return r"[^.]+(?:\.[^.]+)*"

    chunks: list[str] = []
    last_index = len(parts) - 1

    for index, part in enumerate(parts):
        if part == "**":
            if index == 0:
                chunks.append(r"(?:[^.]+\.)*")
            elif index == last_index:
                chunks.append(r"(?:\.[^.]+)*")
            else:
                chunks.append(r"(?:\.[^.]+)*\.")
            continue

        segment_regex = _segment_to_regex(part)
        if index == 0:
            chunks.append(segment_regex)
            continue

        if parts[index - 1] == "**":
            chunks.append(segment_regex)
        else:
            chunks.append(r"\.")
            chunks.append(segment_regex)

    return "".join(chunks)


@lru_cache(maxsize=512)
def pattern_to_regex(pattern: str) -> Pattern[str]:
    """Compile a regex that matches the same module set as matches_pattern()."""
    validate_pattern(pattern)

    exact_regex = re.escape(pattern)
    prefix_regex = rf"{re.escape(pattern)}\..+"
    wildcard_regex = _wildcard_pattern_to_regex(pattern)
    combined = rf"^(?:{exact_regex}|{prefix_regex}|{wildcard_regex})$"
    return re.compile(combined)


def matches_pattern(module_name: str, pattern: str) -> bool:
    """Return True when a module name matches the provided module pattern."""
    if module_name == pattern:
        return True
    if module_name.startswith(f"{pattern}."):
        return True
    if "*" not in pattern:
        return False
    return bool(pattern_to_regex(pattern).fullmatch(module_name))


def find_matching_nodes(pattern: str, all_nodes: list[str]) -> list[str]:
    """Return all nodes that match the provided module pattern."""
    validate_pattern(pattern)
    regex = pattern_to_regex(pattern)
    return [node for node in all_nodes if regex.fullmatch(node)]
