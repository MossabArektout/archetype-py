"""Tests for built-in naming convention rules."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archetype.dsl.query import load_project
from archetype.rules import classes_in, functions_in


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


def _make_project_copy(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    shutil.copytree(_fixture_root() / "simple_project", project_path / "simple_project")
    return project_path


def test_classes_all_match_raises_for_badly_named_class(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    with pytest.raises(AssertionError):
        classes_in("simple_project.services").all_match(r".*Service$")


def test_classes_all_match_passes_when_only_user_service_exists(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    services_file = project_path / "simple_project" / "services.py"
    services_file.write_text(
        "\n".join(
            [
                '"""Service layer for the simple fixture project."""',
                "",
                "from simple_project import db",
                "from simple_project.internal import tokens",
                "",
                "class UserService:",
                '    """Service class following the expected naming convention."""',
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    load_project(project_path)
    classes_in("simple_project.services").all_match(r".*Service$")


def test_functions_must_include_passes_when_handle_exists(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    functions_in("simple_project.api").must_include("handle")


def test_functions_must_include_raises_when_function_missing(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    load_project(project_path)

    with pytest.raises(AssertionError):
        functions_in("simple_project.services").must_include("handle")
