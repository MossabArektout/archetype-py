"""Tests for the @escalate decorator (time-based severity scheduling)."""

from __future__ import annotations

import importlib
from datetime import date

import pytest

from archetype.analysis.models import Violation
from archetype.rule import escalate, registry, rule

rule_module = importlib.import_module("archetype.rule")


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    registry.clear()
    yield
    registry.clear()


def _set_today(monkeypatch: pytest.MonkeyPatch, value: date) -> None:
    monkeypatch.setattr(rule_module, "_today", lambda: value)


def _failing_violation() -> list[Violation]:
    return [
        Violation(
            module="myapp.api",
            file="myapp/api.py",
            line=1,
            message="must not import myapp.legacy",
        )
    ]


def test_invalid_deadline_format_raises_at_decoration_time() -> None:
    with pytest.raises(ValueError, match="Invalid date"):

        @rule("bad-deadline")
        @escalate(warn_until="11/01/2026")
        def bad_deadline() -> None:
            return None


def test_violation_before_deadline_is_reported_as_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_today(monkeypatch, date(2026, 10, 1))

    @rule("no-legacy-imports")
    @escalate(warn_until="2026-11-01")
    def no_legacy_imports() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", _failing_violation())
        raise exc

    results = registry.run_all()

    assert len(results) == 1
    result = results[0]
    assert result.passed is False
    assert result.warned is True
    assert result.is_warning is True
    assert result.escalate_date == "2026-11-01"


def test_violation_on_deadline_date_is_still_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warn_until is inclusive: the deadline day itself is still grace period."""
    _set_today(monkeypatch, date(2026, 11, 1))

    @rule("no-legacy-imports")
    @escalate(warn_until="2026-11-01")
    def no_legacy_imports() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", _failing_violation())
        raise exc

    results = registry.run_all()

    assert results[0].warned is True
    assert results[0].passed is False


def test_violation_after_deadline_is_a_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_today(monkeypatch, date(2026, 11, 2))

    @rule("no-legacy-imports")
    @escalate(warn_until="2026-11-01")
    def no_legacy_imports() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", _failing_violation())
        raise exc

    results = registry.run_all()

    assert len(results) == 1
    result = results[0]
    assert result.passed is False
    assert result.warned is False
    assert result.is_warning is False


def test_hard_failures_after_deadline_count_toward_ci_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_today(monkeypatch, date(2026, 11, 2))

    @rule("no-legacy-imports")
    @escalate(warn_until="2026-11-01")
    def no_legacy_imports() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", _failing_violation())
        raise exc

    results = registry.run_all()
    hard_failures = sum(1 for result in results if not result.passed and not result.warned)

    assert hard_failures == 1


def test_warnings_before_deadline_do_not_count_toward_ci_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_today(monkeypatch, date(2026, 10, 1))

    @rule("no-legacy-imports")
    @escalate(warn_until="2026-11-01")
    def no_legacy_imports() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", _failing_violation())
        raise exc

    results = registry.run_all()
    hard_failures = sum(1 for result in results if not result.passed and not result.warned)

    assert hard_failures == 0


def test_passing_rule_is_unaffected_before_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_today(monkeypatch, date(2026, 10, 1))

    @rule("no-legacy-imports")
    @escalate(warn_until="2026-11-01")
    def no_legacy_imports() -> None:
        return None

    results = registry.run_all()

    assert results[0].passed is True
    assert results[0].warned is False


def test_passing_rule_is_unaffected_after_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_today(monkeypatch, date(2026, 11, 2))

    @rule("no-legacy-imports")
    @escalate(warn_until="2026-11-01")
    def no_legacy_imports() -> None:
        return None

    results = registry.run_all()

    assert results[0].passed is True
    assert results[0].warned is False
