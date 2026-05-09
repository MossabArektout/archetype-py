"""Tests for rule registration and execution behavior."""

from pathlib import Path

import pytest

from archetype.analysis.models import Violation
from archetype.rule import registry, rule


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    registry.clear()
    yield
    registry.clear()


def test_decorated_function_is_registered() -> None:
    @rule("registered_rule")
    def sample_rule() -> None:
        return None

    assert registry._rules == [sample_rule]


def test_run_all_returns_passing_result_when_rule_succeeds() -> None:
    @rule("passing_rule")
    def passing_rule() -> None:
        return None

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "passing_rule"
    assert results[0].passed is True
    assert results[0].violations == []
    assert results[0].error is None


def test_run_all_captures_assertion_error_violations() -> None:
    violations = [
        Violation(
            module="simple_project.api",
            file=Path("simple_project/api.py"),
            line=1,
            message="API must not import DB directly.",
        )
    ]

    @rule("failing_rule")
    def failing_rule() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", violations)
        raise exc

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "failing_rule"
    assert results[0].passed is False
    assert results[0].violations == violations
    assert results[0].error is None


def test_run_all_captures_non_assertion_error() -> None:
    @rule("broken_rule")
    def broken_rule() -> None:
        raise RuntimeError("unexpected error")

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "broken_rule"
    assert results[0].passed is False
    assert isinstance(results[0].error, RuntimeError)


def test_clear_removes_all_registered_rules() -> None:
    @rule("rule_one")
    def rule_one() -> None:
        return None

    @rule("rule_two")
    def rule_two() -> None:
        return None

    assert len(registry._rules) == 2
    registry.clear()
    assert registry._rules == []
