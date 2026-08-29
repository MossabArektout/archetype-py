"""Tests for the built-in deprecated-module import rule."""

from __future__ import annotations

import importlib
import shutil
from datetime import date
from pathlib import Path

import pytest

import archetype.dsl.query as query_module
from archetype.dsl.query import load_project
from archetype.rules import deprecated

# archetype/rules/__init__.py does `from archetype.rules.deprecated import
# deprecated`, which rebinds the `deprecated` attribute on the `archetype.rules`
# package from the submodule to the function of the same name (a standard
# Python footgun for a submodule whose name matches its main export). Fetch
# the real submodule through sys.modules via import_module() instead of
# `import archetype.rules.deprecated as ...`, which would bind to the function.
deprecated_module = importlib.import_module("archetype.rules.deprecated")


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


def _make_project_copy(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    shutil.copytree(_fixture_root() / "simple_project", project_path / "simple_project")
    return project_path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _set_today(monkeypatch: pytest.MonkeyPatch, value: date) -> None:
    monkeypatch.setattr(deprecated_module, "_today", lambda: value)


def test_deprecated_raises_when_imported_from_outside(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    with pytest.raises(AssertionError) as excinfo:
        deprecated("simple_project.internal")

    violations = getattr(excinfo.value, "violations", [])
    assert {v.module for v in violations} == {"simple_project.api", "simple_project.services"}
    assert all("deprecated" in v.message for v in violations)


def test_deprecated_is_a_no_op_when_pattern_matches_nothing(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    deprecated("does_not_exist")


def test_deprecated_does_not_flag_imports_within_its_own_subtree(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    _write(project_path / "legacy" / "helpers.py", "VALUE = 1\n")
    _write(
        project_path / "legacy" / "__init__.py",
        "from .helpers import VALUE\n",
    )
    _write(project_path / "consumer.py", "VALUE = 2\n")
    load_project(project_path)

    deprecated("legacy")


def test_deprecated_message_counts_down_to_a_future_sunset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)
    _set_today(monkeypatch, date(2026, 10, 1))

    with pytest.raises(AssertionError) as excinfo:
        deprecated("simple_project.internal", sunset="2026-11-01")

    violations = getattr(excinfo.value, "violations", [])
    assert violations
    assert "Scheduled for removal on 2026-11-01 (31 day(s) remaining)" in violations[0].message


def test_deprecated_message_reports_today_on_the_sunset_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)
    _set_today(monkeypatch, date(2026, 11, 1))

    with pytest.raises(AssertionError) as excinfo:
        deprecated("simple_project.internal", sunset="2026-11-01")

    violations = getattr(excinfo.value, "violations", [])
    assert "Scheduled for removal on 2026-11-01 (today)" in violations[0].message


def test_deprecated_message_reports_overdue_after_the_sunset_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)
    _set_today(monkeypatch, date(2026, 11, 4))

    with pytest.raises(AssertionError) as excinfo:
        deprecated("simple_project.internal", sunset="2026-11-01")

    violations = getattr(excinfo.value, "violations", [])
    assert "Was scheduled for removal on 2026-11-01 (3 day(s) overdue)" in violations[0].message


def test_deprecated_message_includes_reason_when_given(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    with pytest.raises(AssertionError) as excinfo:
        deprecated("simple_project.internal", reason="replaced by simple_project.services")

    violations = getattr(excinfo.value, "violations", [])
    assert "(replaced by simple_project.services)" in violations[0].message


def test_deprecated_without_sunset_has_no_date_framing(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    with pytest.raises(AssertionError) as excinfo:
        deprecated("simple_project.internal")

    violations = getattr(excinfo.value, "violations", [])
    assert "No removal date is set." in violations[0].message


def test_deprecated_rejects_invalid_sunset_date(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    with pytest.raises(ValueError, match="Invalid date"):
        deprecated("simple_project.internal", sunset="not-a-date")


def test_deprecated_without_load_project_raises_runtime_error() -> None:
    # Other test modules load a project and never reset this module-level
    # state, so it cannot be assumed to already be None here.
    query_module._current_graph = None

    with pytest.raises(RuntimeError) as excinfo:
        deprecated("simple_project.internal")
    assert "archetype check" in str(excinfo.value)
