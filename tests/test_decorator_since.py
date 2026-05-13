"""Tests for the @since decorator and git date utilities."""

from __future__ import annotations

import os
import importlib
from datetime import date, datetime
from pathlib import Path

import pytest

from archetype.analysis.git_utils import get_file_last_modified_date, parse_date_string
from archetype.analysis.models import Violation
from archetype.dsl import query as query_module
from archetype.rule import registry, rule, since

rule_module = importlib.import_module("archetype.rule")


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    registry.clear()
    yield
    registry.clear()


@pytest.fixture(autouse=True)
def restore_current_root() -> None:
    original_root = query_module._current_root
    yield
    query_module._current_root = original_root


def test_since_passes_when_all_violations_are_before_since_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_module._current_root = tmp_path
    old_file = (tmp_path / "old.py").resolve()
    old_file.write_text("print('old')\n", encoding="utf-8")

    monkeypatch.setattr(rule_module, "get_files_modified_after", lambda *_: set())

    violations = [
        Violation(
            module="app.api",
            file=old_file,
            line=1,
            message="must not import db",
        )
    ]

    @rule("old-violations-only")
    @since("2026-01-01")
    def scoped_rule() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", violations)
        raise exc

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].violations == []
    assert results[0].filtered_violations == violations


def test_since_fails_with_only_violations_in_recent_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_module._current_root = tmp_path
    recent_file = (tmp_path / "recent.py").resolve()
    old_file = (tmp_path / "old.py").resolve()
    recent_file.write_text("print('recent')\n", encoding="utf-8")
    old_file.write_text("print('old')\n", encoding="utf-8")

    monkeypatch.setattr(rule_module, "get_files_modified_after", lambda *_: {recent_file})

    recent_violation = Violation(
        module="app.api",
        file=recent_file,
        line=2,
        message="recent violation",
    )
    old_violation = Violation(
        module="app.api",
        file=old_file,
        line=1,
        message="old violation",
    )

    @rule("mixed-violations")
    @since("2026-01-01")
    def scoped_rule() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", [recent_violation, old_violation])
        raise exc

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].violations == [recent_violation]
    assert results[0].filtered_violations == [old_violation]


def test_since_date_is_stored_in_rule_result() -> None:
    @rule("scoped-pass")
    @since("2026-01-01")
    def scoped_pass() -> None:
        return None

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].since_date == "2026-01-01"


def test_parse_date_string_invalid_format_raises_clear_error() -> None:
    with pytest.raises(ValueError, match=r"Expected format: YYYY-MM-DD"):
        parse_date_string("01-01-2026")


def test_get_file_last_modified_date_falls_back_to_filesystem_time_when_git_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_file = tmp_path / "module.py"
    test_file.write_text("print('hello')\n", encoding="utf-8")

    fallback_dt = datetime(2025, 6, 15, 12, 30, 0)
    os.utime(test_file, (fallback_dt.timestamp(), fallback_dt.timestamp()))

    def raise_git_missing(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("git not found")

    monkeypatch.setattr("archetype.analysis.git_utils.subprocess.run", raise_git_missing)

    last_modified = get_file_last_modified_date(test_file, tmp_path)

    assert last_modified == date(2025, 6, 15)


def test_passing_rule_still_passes_with_since_applied() -> None:
    @rule("always-pass")
    @since("2099-01-01")
    def always_pass() -> None:
        return None

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].violations == []
    assert results[0].since_date == "2099-01-01"
