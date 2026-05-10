"""Tests for rule registration and execution behavior."""

from pathlib import Path

import pytest

from archetype.analysis.models import Violation
from archetype.rule import registry, rule, warn


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


def test_warned_rule_returns_warned_result_on_assertion() -> None:
    violations = [
        Violation(
            module="simple_project.api",
            file=Path("simple_project/api.py"),
            line=1,
            message="API must not import DB directly.",
        )
    ]

    @rule("warned-failing-rule")
    @warn
    def warned_failing_rule() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", violations)
        raise exc

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "warned-failing-rule"
    assert results[0].passed is False
    assert results[0].warned is True
    assert results[0].is_warning is True
    assert results[0].violations == violations
    assert results[0].error is None


def test_warned_rule_that_passes_is_marked_as_warning_rule() -> None:
    @rule("warned-passing-rule")
    @warn
    def warned_passing_rule() -> None:
        return None

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "warned-passing-rule"
    assert results[0].passed is True
    assert results[0].warned is False
    assert results[0].is_warning is True


def test_registry_run_all_includes_warned_and_normal_results() -> None:
    @rule("normal-pass")
    def normal_pass() -> None:
        return None

    @rule("warned-fail")
    @warn
    def warned_fail() -> None:
        exc = AssertionError("warn-only failure")
        setattr(exc, "violations", [])
        raise exc

    results = registry.run_all()

    assert len(results) == 2
    by_name = {result.name: result for result in results}
    assert by_name["normal-pass"].passed is True
    assert by_name["normal-pass"].warned is False
    assert by_name["warned-fail"].passed is False
    assert by_name["warned-fail"].warned is True
    assert by_name["warned-fail"].is_warning is True


def test_warned_rules_do_not_count_as_hard_failures_for_ci() -> None:
    @rule("warned-fail")
    @warn
    def warned_fail() -> None:
        exc = AssertionError("warn-only failure")
        setattr(exc, "violations", [])
        raise exc

    results = registry.run_all()
    hard_failures = sum(1 for result in results if not result.passed and not result.warned)

    assert hard_failures == 0
