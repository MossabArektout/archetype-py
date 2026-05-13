"""Tests for rule grouping and namespacing behavior."""

from __future__ import annotations

import importlib

import pytest

from archetype.rule import group, registry, rule

rule_module = importlib.import_module("archetype.rule")


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    registry.clear()
    setattr(rule_module._current_group, "name", None)
    yield
    registry.clear()
    setattr(rule_module._current_group, "name", None)


def test_rules_inside_group_have_group_attribute() -> None:
    with group("Layer boundaries"):

        @rule("grouped-rule")
        def grouped_rule() -> None:
            return None

    assert getattr(grouped_rule, "_group", None) == "Layer boundaries"


def test_rules_outside_group_have_no_group_attribute_value() -> None:
    @rule("ungrouped-rule")
    def ungrouped_rule() -> None:
        return None

    assert getattr(ungrouped_rule, "_group", None) is None


def test_nested_groups_raise_value_error() -> None:
    with pytest.raises(ValueError, match=r"cannot be nested"):
        with group("Outer"):
            with group("Inner"):
                pass


def test_run_all_group_filter_runs_only_matching_group() -> None:
    with group("Layer boundaries"):

        @rule("layer-rule")
        def layer_rule() -> None:
            return None

    with group("Naming conventions"):

        @rule("naming-rule")
        def naming_rule() -> None:
            return None

    results = registry.run_all(group_filter="Layer boundaries")

    assert [result.name for result in results] == ["layer-rule"]
    assert [result.group for result in results] == ["Layer boundaries"]


def test_run_all_group_filter_returns_empty_when_no_match() -> None:
    with group("Layer boundaries"):

        @rule("layer-rule")
        def layer_rule() -> None:
            return None

    results = registry.run_all(group_filter="No such group")

    assert results == []


def test_current_group_resets_after_exception_in_with_block() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with group("Layer boundaries"):
            raise RuntimeError("boom")

    assert getattr(rule_module._current_group, "name", None) is None


def test_sequential_group_blocks_do_not_bleed() -> None:
    with group("Group A"):

        @rule("rule-a")
        def rule_a() -> None:
            return None

    with group("Group B"):

        @rule("rule-b")
        def rule_b() -> None:
            return None

    @rule("rule-c")
    def rule_c() -> None:
        return None

    assert getattr(rule_a, "_group", None) == "Group A"
    assert getattr(rule_b, "_group", None) == "Group B"
    assert getattr(rule_c, "_group", None) is None
