"""Tests for the built-in layers rule."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archetype.dsl.query import load_project
from archetype.rules import layers


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


def _make_project_copy(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    shutil.copytree(_fixture_root() / "simple_project", project_path / "simple_project")
    return project_path


def test_are_ordered_raises_when_lower_layer_imports_upper_layer(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    db_file = project_path / "simple_project" / "db.py"
    original = db_file.read_text(encoding="utf-8")
    db_file.write_text(
        original + "\nfrom simple_project import api\n",
        encoding="utf-8",
    )

    load_project(project_path)

    with pytest.raises(AssertionError):
        layers(["simple_project.api", "simple_project.services", "simple_project.db"]).are_ordered()

    db_file.write_text(original, encoding="utf-8")


def test_are_ordered_passes_when_imports_flow_downward_only(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    # Future enhancement: catch layer-skipping imports such as API -> DB.
    layers(["simple_project.api", "simple_project.services", "simple_project.db"]).are_ordered()


def test_violation_message_includes_source_target_and_direction(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    db_file = project_path / "simple_project" / "db.py"
    original = db_file.read_text(encoding="utf-8")
    db_file.write_text(
        original + "\nfrom simple_project import api\n",
        encoding="utf-8",
    )

    load_project(project_path)

    with pytest.raises(AssertionError) as excinfo:
        layers(["simple_project.api", "simple_project.services", "simple_project.db"]).are_ordered()

    violations = getattr(excinfo.value, "violations", [])
    assert violations
    assert "simple_project.db" in violations[0].message
    assert "simple_project.api" in violations[0].message
    assert "upward" in violations[0].message

    db_file.write_text(original, encoding="utf-8")


def test_are_ordered_supports_wildcard_layer_patterns(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    db_file = project_path / "simple_project" / "db.py"
    original = db_file.read_text(encoding="utf-8")
    db_file.write_text(
        original + "\nfrom simple_project import api\n",
        encoding="utf-8",
    )

    load_project(project_path)

    with pytest.raises(AssertionError):
        layers(["simple_project.a*", "simple_project.services", "simple_project.db"]).are_ordered()

    db_file.write_text(original, encoding="utf-8")
