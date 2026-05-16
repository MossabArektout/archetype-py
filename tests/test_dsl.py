"""Tests for the Archetype query DSL."""

from pathlib import Path

import pytest

import archetype.dsl.query as query_module
from archetype.dsl.query import imports, load_project
from archetype.rules import no_cycles


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


@pytest.fixture(autouse=True)
def clear_loaded_graph() -> None:
    query_module._current_graph = None
    query_module._project_root = None
    yield
    query_module._current_graph = None
    query_module._project_root = None


def test_must_not_import_raises_for_direct_api_to_db_dependency() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError):
        imports("simple_project.api").must_not_import("simple_project.db")


def test_must_not_import_violation_includes_non_empty_file_and_line() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError) as excinfo:
        imports("simple_project.api").must_not_import("simple_project.db")

    violations = getattr(excinfo.value, "violations", [])
    assert violations
    assert violations[0].file is not None
    assert violations[0].line != 0


def test_must_not_import_violation_file_points_to_source_module_file() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError) as excinfo:
        imports("simple_project.api").must_not_import("simple_project.db")

    violations = getattr(excinfo.value, "violations", [])
    expected_file = (_fixture_root() / "simple_project" / "api.py").resolve()
    assert violations
    assert Path(violations[0].file).resolve() == expected_file


def test_must_not_import_passes_when_dependency_does_not_exist() -> None:
    load_project(_fixture_root())

    imports("simple_project.main").must_not_import("simple_project.db")


def test_has_no_cycles_raises_when_cycle_exists_and_passes_when_none() -> None:
    load_project(_fixture_root())
    imports("simple_project").has_no_cycles()

    assert query_module._current_graph is not None
    query_module._current_graph.add_edge("simple_project.db", "simple_project.api")

    with pytest.raises(AssertionError):
        imports("simple_project").has_no_cycles()


def test_must_only_import_from_raises_and_passes_for_valid_edges() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError) as excinfo:
        imports("simple_project.api").must_only_import_from("simple_project.services")
    violations = getattr(excinfo.value, "violations", [])
    assert violations
    assert "outside the allowed set" not in violations[0].message
    assert getattr(excinfo.value, "violation_context", []) == [
        "Allowed imports for 'simple_project.api': simple_project.services."
    ]

    imports("simple_project.services").must_only_import_from(
        "simple_project.db",
        "simple_project.internal",
    )


def test_must_not_import_supports_single_star_wildcard_source_pattern() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError):
        imports("simple_project.*").must_not_import("simple_project.db")


def test_must_not_depend_on_raises_for_transitive_dependency() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError):
        imports("simple_project.main").must_not_depend_on("simple_project.db")


def test_must_not_depend_on_passes_when_no_transitive_dependency_exists() -> None:
    load_project(_fixture_root())

    imports("simple_project.db").must_not_depend_on("simple_project.api")


def test_must_not_depend_on_catches_direct_dependencies_too() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError):
        imports("simple_project.api").must_not_depend_on("simple_project.db")


def test_must_not_depend_on_violation_message_shows_full_dependency_path() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError) as excinfo:
        imports("simple_project.main").must_not_depend_on("simple_project.db")

    violations = getattr(excinfo.value, "violations", [])
    assert violations
    assert "→" in violations[0].message
    assert "simple_project.main → simple_project.api → simple_project.db" in violations[0].message


def test_must_not_depend_on_without_load_project_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        imports("simple_project.api").must_not_depend_on("simple_project.db")
    assert "archetype check" in str(excinfo.value)


def test_must_only_import_from_supports_double_star_allowed_pattern() -> None:
    load_project(_fixture_root())

    imports("simple_project.services").must_only_import_from(
        "simple_project.db",
        "simple_project.**.tokens",
    )


def test_imports_without_load_project_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        imports("simple_project.api")
    assert "archetype check" in str(excinfo.value)


def test_builtin_rule_without_load_project_raises_runtime_error_with_helpful_message() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        no_cycles()
    assert "archetype check" in str(excinfo.value)
