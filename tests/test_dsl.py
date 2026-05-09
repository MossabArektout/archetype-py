"""Tests for the Archetype query DSL."""

from pathlib import Path

import pytest

import archetype.dsl.query as query_module
from archetype.dsl.query import imports, load_project


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


@pytest.fixture(autouse=True)
def clear_loaded_graph() -> None:
    query_module._current_graph = None
    yield
    query_module._current_graph = None


def test_must_not_import_raises_for_direct_api_to_db_dependency() -> None:
    load_project(_fixture_root())

    with pytest.raises(AssertionError):
        imports("simple_project.api").must_not_import("simple_project.db")


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

    with pytest.raises(AssertionError):
        imports("simple_project.api").must_only_import_from("simple_project.services")

    imports("simple_project.services").must_only_import_from("simple_project.db")


def test_imports_without_load_project_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="Call load_project\\(path\\)"):
        imports("simple_project.api")
