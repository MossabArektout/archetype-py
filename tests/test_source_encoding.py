"""Tests for reading Python sources whose encoding is not plain UTF-8."""

from __future__ import annotations

from pathlib import Path

import pytest

from archetype.analysis.imports import build_import_graph
from archetype.dsl.query import load_project
from archetype.rules import classes_in, functions_in

BOM = b"\xef\xbb\xbf"
LATIN_1_HEADER = b"# -*- coding: latin-1 -*-\n# caf\xe9\n"


def _make_project(tmp_path: Path, *, api_source: bytes) -> Path:
    project_path = tmp_path / "project"
    package_path = project_path / "myapp"
    package_path.mkdir(parents=True)
    (package_path / "__init__.py").write_bytes(b"")
    (package_path / "db.py").write_bytes(b"value = 1\n")
    (package_path / "api.py").write_bytes(api_source)
    return project_path


def test_build_import_graph_accepts_utf8_bom(tmp_path: Path) -> None:
    project_path = _make_project(tmp_path, api_source=BOM + b"import myapp.db\n")

    graph = build_import_graph(project_path)

    assert ("myapp.api", "myapp.db") in graph.edges()


def test_build_import_graph_accepts_pep263_encoding_declaration(tmp_path: Path) -> None:
    project_path = _make_project(
        tmp_path,
        api_source=LATIN_1_HEADER + b"import myapp.db\n",
    )

    graph = build_import_graph(project_path)

    assert ("myapp.api", "myapp.db") in graph.edges()


def test_build_import_graph_still_reads_plain_utf8(tmp_path: Path) -> None:
    project_path = _make_project(
        tmp_path,
        api_source=b"# caf\xc3\xa9\nimport myapp.db\n",
    )

    graph = build_import_graph(project_path)

    assert ("myapp.api", "myapp.db") in graph.edges()


def test_classes_in_accepts_utf8_bom(tmp_path: Path) -> None:
    project_path = _make_project(
        tmp_path,
        api_source=BOM + b"class UserService:\n    pass\n",
    )
    load_project(project_path)

    classes_in("myapp.api").all_match(r".*Service$")


def test_classes_in_accepts_pep263_encoding_declaration(tmp_path: Path) -> None:
    project_path = _make_project(
        tmp_path,
        api_source=LATIN_1_HEADER + b"class UserService:\n    pass\n",
    )
    load_project(project_path)

    classes_in("myapp.api").all_match(r".*Service$")


def test_classes_in_still_reports_violations_in_bom_source(tmp_path: Path) -> None:
    project_path = _make_project(
        tmp_path,
        api_source=BOM + b"class Helper:\n    pass\n",
    )
    load_project(project_path)

    with pytest.raises(AssertionError):
        classes_in("myapp.api").all_match(r".*Service$")


def test_functions_in_accepts_utf8_bom(tmp_path: Path) -> None:
    project_path = _make_project(
        tmp_path,
        api_source=BOM + b"def handle():\n    return None\n",
    )
    load_project(project_path)

    functions_in("myapp.api").must_include("handle")


def test_functions_in_accepts_pep263_encoding_declaration(tmp_path: Path) -> None:
    project_path = _make_project(
        tmp_path,
        api_source=LATIN_1_HEADER + b"def handle():\n    return None\n",
    )
    load_project(project_path)

    functions_in("myapp.api").must_include("handle")
