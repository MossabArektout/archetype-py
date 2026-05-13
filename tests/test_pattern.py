"""Tests for module pattern matching helpers."""

from __future__ import annotations

import pytest

from archetype.analysis.pattern import (
    find_matching_nodes,
    matches_pattern,
    validate_pattern,
)


def test_exact_matching_still_supports_descendant_modules() -> None:
    nodes = ["myapp.api", "myapp.api.routes", "myapp.services"]
    assert find_matching_nodes("myapp.api", nodes) == ["myapp.api", "myapp.api.routes"]


def test_single_star_matches_within_one_dot_segment_only() -> None:
    nodes = [
        "myapp.user_service",
        "myapp.auth_service",
        "myapp.payments.user_service",
        "myapp.service_utils",
    ]
    assert find_matching_nodes("myapp.*_service", nodes) == [
        "myapp.user_service",
        "myapp.auth_service",
    ]


def test_double_star_matches_zero_or_more_segments() -> None:
    nodes = [
        "myapp.auth.internal",
        "myapp.payments.processing.internal",
        "myapp.internal",
    ]
    assert find_matching_nodes("myapp.**.internal", nodes) == [
        "myapp.auth.internal",
        "myapp.payments.processing.internal",
        "myapp.internal",
    ]


def test_find_matching_nodes_returns_empty_list_for_non_matching_pattern() -> None:
    nodes = ["myapp.api", "myapp.services"]
    assert find_matching_nodes("myapp.unknown.*", nodes) == []


@pytest.mark.parametrize(
    "pattern",
    ["", ".myapp", "myapp.", "myapp..api", "myapp.***.api"],
)
def test_validate_pattern_raises_for_invalid_patterns(pattern: str) -> None:
    with pytest.raises(ValueError):
        validate_pattern(pattern)


def test_dot_prefix_behavior_still_matches_nested_descendants() -> None:
    assert matches_pattern("myapp.api.routes.handler", "myapp.api")
