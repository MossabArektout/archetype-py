"""Tests for the built-in module boundary rule."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archetype.dsl.query import load_project
from archetype.rules import module


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


def _make_project_copy(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    shutil.copytree(_fixture_root() / "simple_project", project_path / "simple_project")
    return project_path


def test_only_imported_within_raises_for_outside_api_access(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    with pytest.raises(AssertionError):
        module("simple_project.internal").only_imported_within("simple_project.services")


def test_only_imported_within_passes_for_allowed_services_access(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    api_file = project_path / "simple_project" / "api.py"
    original = api_file.read_text(encoding="utf-8")
    filtered = "\n".join(
        line
        for line in original.splitlines()
        if "simple_project.internal" not in line
    )
    api_file.write_text(filtered + "\n", encoding="utf-8")

    load_project(project_path)
    module("simple_project.internal").only_imported_within("simple_project.services")


def test_boundary_violation_message_names_source_and_protected_target(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    with pytest.raises(AssertionError) as excinfo:
        module("simple_project.internal").only_imported_within("simple_project.services")

    violations = getattr(excinfo.value, "violations", [])
    assert violations
    assert "simple_project.api" in violations[0].message
    assert "simple_project.internal.tokens" in violations[0].message
    assert "outside" in violations[0].message
