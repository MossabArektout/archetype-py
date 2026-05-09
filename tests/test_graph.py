"""Tests for import graph construction."""

from pathlib import Path

from archetype.analysis.imports import build_import_graph


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


def test_graph_contains_expected_module_nodes() -> None:
    graph = build_import_graph(_fixture_root())
    expected_nodes = {
        "simple_project.main",
        "simple_project.api",
        "simple_project.services",
        "simple_project.db",
    }
    assert expected_nodes.issubset(set(graph.nodes))


def test_graph_contains_deliberate_api_to_db_violation_edge() -> None:
    graph = build_import_graph(_fixture_root())
    assert graph.has_edge("simple_project.api", "simple_project.db")


def test_db_module_has_no_outgoing_edges() -> None:
    graph = build_import_graph(_fixture_root())
    assert graph.out_degree("simple_project.db") == 0


def test_graph_excludes_stdlib_and_third_party_modules() -> None:
    graph = build_import_graph(_fixture_root())
    assert all(node.split(".", maxsplit=1)[0] == "simple_project" for node in graph.nodes)
