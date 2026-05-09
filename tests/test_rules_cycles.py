"""Tests for the built-in circular import detection rule."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archetype.dsl.query import load_project
from archetype.rules import no_cycles


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


def _make_project_copy(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    shutil.copytree(_fixture_root() / "simple_project", project_path / "simple_project")
    return project_path


def _add_simple_project_cycle(project_path: Path) -> None:
    db_file = project_path / "simple_project" / "db.py"
    db_file.write_text(
        db_file.read_text(encoding="utf-8") + "\nfrom simple_project import api\n",
        encoding="utf-8",
    )


def test_no_cycles_passes_on_original_simple_project(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    no_cycles()


def test_no_cycles_raises_on_modified_fixture_with_cycle(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _add_simple_project_cycle(project_path)
    load_project(project_path)

    with pytest.raises(AssertionError):
        no_cycles()


def test_no_cycles_violation_message_shows_full_human_readable_chain(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _add_simple_project_cycle(project_path)
    load_project(project_path)

    with pytest.raises(AssertionError) as excinfo:
        no_cycles()

    violations = getattr(excinfo.value, "violations", [])
    assert violations
    message = violations[0].message
    assert " imports " in message
    parts = message.split(" imports ")
    assert len(parts) >= 3
    assert parts[0] == parts[-1]


def test_no_cycles_with_pattern_ignores_cycles_outside_pattern(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)

    other_pkg = project_path / "other"
    other_pkg.mkdir(parents=True, exist_ok=True)
    (other_pkg / "__init__.py").write_text("", encoding="utf-8")
    (other_pkg / "a.py").write_text("from other import b\n", encoding="utf-8")
    (other_pkg / "b.py").write_text("from other import a\n", encoding="utf-8")

    load_project(project_path)

    no_cycles("simple_project")
