"""Tests for project initialization helpers and CLI init command."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

from click.testing import CliRunner

from archetype.check import cli
from archetype.dsl.query import load_project
from archetype.init import detect_project_structure, generate_architecture_py
from archetype.rule import registry


EXPECTED_STRUCTURE_KEYS = {
    "top_level_package",
    "detected_layers",
    "has_internal",
    "internal_paths",
    "total_python_files",
    "layout",
}


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_package(project_root: Path, name: str = "myapp") -> Path:
    package = project_root / name
    _write(package / "__init__.py")
    return package


def _make_src_package(project_root: Path, name: str = "myapp") -> Path:
    package = project_root / "src" / name
    _write(package / "__init__.py")
    return package


def test_detect_project_structure_identifies_top_level_package(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path, "myapp")
    _write(myapp / "main.py")

    docs = tmp_path / "docs"
    _write(docs / "__init__.py")
    _write(docs / "ignored.py")

    structure = detect_project_structure(tmp_path)

    assert set(structure) == EXPECTED_STRUCTURE_KEYS
    assert structure["top_level_package"] == "myapp"
    assert structure["layout"] == "flat"


def test_detect_project_structure_detects_layers_in_order(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path)
    _write(myapp / "api" / "__init__.py")
    _write(myapp / "services" / "__init__.py")
    _write(myapp / "db" / "__init__.py")

    structure = detect_project_structure(tmp_path)

    assert set(structure) == EXPECTED_STRUCTURE_KEYS
    assert structure["detected_layers"] == ["myapp.api", "myapp.services", "myapp.db"]
    assert structure["layout"] == "flat"


def test_detect_project_structure_returns_empty_layers_when_unknown(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path)
    _write(myapp / "controllers" / "__init__.py")
    _write(myapp / "store" / "__init__.py")

    structure = detect_project_structure(tmp_path)

    assert set(structure) == EXPECTED_STRUCTURE_KEYS
    assert structure["detected_layers"] == []
    assert structure["layout"] == "flat"


def test_detect_project_structure_detects_internal_subpackages(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path)
    _write(myapp / "auth" / "internal" / "__init__.py")
    _write(myapp / "billing" / "internal" / "__init__.py")

    structure = detect_project_structure(tmp_path)

    assert set(structure) == EXPECTED_STRUCTURE_KEYS
    assert structure["has_internal"] is True
    assert structure["layout"] == "flat"
    assert structure["internal_paths"] == [
        "myapp.auth.internal",
        "myapp.billing.internal",
    ]


def test_detect_project_structure_identifies_src_layout(tmp_path: Path) -> None:
    myapp = _make_src_package(tmp_path, "myapp")
    _write(myapp / "api" / "__init__.py")

    structure = detect_project_structure(tmp_path)

    assert set(structure) == EXPECTED_STRUCTURE_KEYS
    assert structure["layout"] == "src"
    assert structure["top_level_package"] == "myapp"


def test_detect_project_structure_identifies_flat_layout(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path, "myapp")
    _write(myapp / "api" / "__init__.py")

    structure = detect_project_structure(tmp_path)

    assert set(structure) == EXPECTED_STRUCTURE_KEYS
    assert structure["layout"] == "flat"
    assert structure["top_level_package"] == "myapp"


def test_detect_project_structure_returns_unknown_layout_when_no_package_found(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "tests" / "test_example.py", "def test_x():\n    pass\n")

    structure = detect_project_structure(tmp_path)

    assert structure == {
        "top_level_package": None,
        "detected_layers": [],
        "has_internal": False,
        "internal_paths": [],
        "total_python_files": 0,
        "layout": "unknown",
    }


def test_detect_project_structure_selects_largest_src_package_when_multiple_exist(
    tmp_path: Path,
) -> None:
    alpha = _make_src_package(tmp_path, "alpha")
    _write(alpha / "a.py")

    beta = _make_src_package(tmp_path, "beta")
    _write(beta / "a.py")
    _write(beta / "b.py")
    _write(beta / "c.py")

    structure = detect_project_structure(tmp_path)

    assert structure["layout"] == "src"
    assert structure["top_level_package"] == "beta"


def test_generate_architecture_py_includes_layers_rule_for_two_or_more_layers() -> None:
    structure = {
        "top_level_package": "myapp",
        "detected_layers": ["myapp.api", "myapp.services", "myapp.db"],
        "has_internal": False,
        "internal_paths": [],
        "total_python_files": 5,
        "layout": "flat",
    }

    content = generate_architecture_py(structure)

    assert "layers(['myapp.api', 'myapp.services', 'myapp.db']).are_ordered()" in content


def test_generate_architecture_py_always_includes_no_cycles_rule() -> None:
    structure = {
        "top_level_package": None,
        "detected_layers": [],
        "has_internal": False,
        "internal_paths": [],
        "total_python_files": 0,
        "layout": "unknown",
    }

    content = generate_architecture_py(structure)

    assert "@rule('no-import-cycles')" in content
    assert "no_cycles()" in content


def test_generate_architecture_py_includes_boundary_rules_for_each_internal_path() -> None:
    structure = {
        "top_level_package": "myapp",
        "detected_layers": ["myapp.api", "myapp.services", "myapp.db"],
        "has_internal": True,
        "internal_paths": ["myapp.auth.internal", "myapp.billing.internal"],
        "total_python_files": 8,
        "layout": "flat",
    }

    content = generate_architecture_py(structure)

    assert "module('myapp.auth.internal').only_imported_within('myapp.auth')" in content
    assert "module('myapp.billing.internal').only_imported_within('myapp.billing')" in content


def test_generate_architecture_py_uses_actual_detected_module_paths() -> None:
    structure = {
        "top_level_package": "shop",
        "detected_layers": ["shop.routes", "shop.business", "shop.repositories"],
        "has_internal": False,
        "internal_paths": [],
        "total_python_files": 4,
        "layout": "flat",
    }

    content = generate_architecture_py(structure)

    assert "shop.routes" in content
    assert "shop.business" in content
    assert "shop.repositories" in content
    assert "your_project" not in content


def test_generate_architecture_py_includes_src_layout_comment() -> None:
    structure = {
        "top_level_package": "myapp",
        "detected_layers": ["myapp.api", "myapp.services", "myapp.db"],
        "has_internal": False,
        "internal_paths": [],
        "total_python_files": 5,
        "layout": "src",
    }

    content = generate_architecture_py(structure)

    assert "# Generated by archetype init" in content
    assert "# Detected layout: src (package found at src/myapp)" in content
    assert "# Customize these rules for your project" in content


def test_generate_architecture_py_includes_flat_layout_comment() -> None:
    structure = {
        "top_level_package": "myapp",
        "detected_layers": ["myapp.api", "myapp.services", "myapp.db"],
        "has_internal": False,
        "internal_paths": [],
        "total_python_files": 5,
        "layout": "flat",
    }

    content = generate_architecture_py(structure)

    assert "# Generated by archetype init" in content
    assert "# Detected layout: flat (package found at myapp/)" in content
    assert "# Customize these rules for your project" in content


def test_generate_architecture_py_uses_package_paths_for_src_layout() -> None:
    structure = {
        "top_level_package": "myapp",
        "detected_layers": ["myapp.api", "myapp.services", "myapp.db"],
        "has_internal": False,
        "internal_paths": [],
        "total_python_files": 5,
        "layout": "src",
    }

    content = generate_architecture_py(structure)

    assert "myapp.api" in content
    assert "src.myapp.api" not in content


def test_init_cli_creates_architecture_py_when_missing(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path)
    _write(myapp / "api" / "__init__.py")
    _write(myapp / "services" / "__init__.py")
    _write(myapp / "db" / "__init__.py")

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / "architecture.py").is_file()
    assert "architecture.py created at" in result.output


def test_init_cli_prints_detected_layout_line_for_src_and_flat(tmp_path: Path) -> None:
    src_project = tmp_path / "src_project"
    src_myapp = _make_src_package(src_project)
    _write(src_myapp / "api" / "__init__.py")
    _write(src_myapp / "services" / "__init__.py")
    _write(src_myapp / "db" / "__init__.py")

    flat_project = tmp_path / "flat_project"
    flat_myapp = _make_package(flat_project)
    _write(flat_myapp / "api" / "__init__.py")
    _write(flat_myapp / "services" / "__init__.py")
    _write(flat_myapp / "db" / "__init__.py")

    runner = CliRunner()
    src_result = runner.invoke(cli, ["init", str(src_project)])
    flat_result = runner.invoke(cli, ["init", str(flat_project)])

    assert src_result.exit_code == 0
    assert "  Layout:  src (src/myapp)" in src_result.output

    assert flat_result.exit_code == 0
    assert "  Layout:  flat (myapp/)" in flat_result.output


def test_init_cli_generates_working_architecture_py_for_src_layout(tmp_path: Path) -> None:
    myapp = _make_src_package(tmp_path)
    _write(myapp / "api" / "__init__.py", "from myapp import services\n")
    _write(myapp / "services" / "__init__.py", "from myapp import db\n")
    _write(myapp / "db" / "__init__.py")

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(tmp_path)])

    assert result.exit_code == 0

    architecture_path = tmp_path / "architecture.py"
    assert architecture_path.is_file()
    content = architecture_path.read_text(encoding="utf-8")
    assert "myapp.api" in content
    assert "myapp.services" in content
    assert "myapp.db" in content
    assert "src.myapp.api" not in content

    registry.clear()
    load_project(tmp_path, src_root=tmp_path / "src")

    module_name = f"_archetype_generated_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, architecture_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    original_sys_path = list(sys.path)
    try:
        sys.path.insert(0, str(tmp_path))
        spec.loader.exec_module(module)
    finally:
        sys.path = original_sys_path

    results = registry.run_all()
    assert results
    assert all(result.passed for result in results)
    registry.clear()


def test_init_cli_does_not_overwrite_when_user_declines(tmp_path: Path) -> None:
    _make_package(tmp_path)
    architecture = tmp_path / "architecture.py"
    architecture.write_text("ORIGINAL", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(tmp_path)], input="n\n")

    assert result.exit_code == 0
    assert architecture.read_text(encoding="utf-8") == "ORIGINAL"
    assert "already exists" in result.output
    assert "Existing file kept unchanged." in result.output


def test_init_cli_overwrites_when_user_confirms(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path)
    _write(myapp / "api" / "__init__.py")
    _write(myapp / "services" / "__init__.py")
    _write(myapp / "db" / "__init__.py")

    architecture = tmp_path / "architecture.py"
    architecture.write_text("ORIGINAL", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(tmp_path)], input="y\n")

    assert result.exit_code == 0
    assert architecture.read_text(encoding="utf-8") != "ORIGINAL"
    assert "Overwrite?" in result.output
    assert "architecture.py created at" in result.output


def test_init_cli_exits_zero_in_all_normal_scenarios(tmp_path: Path) -> None:
    runner = CliRunner()

    project_create = tmp_path / "create"
    _make_package(project_create)
    result_create = runner.invoke(cli, ["init", str(project_create)])

    project_keep = tmp_path / "keep"
    _make_package(project_keep)
    (project_keep / "architecture.py").write_text("ORIGINAL", encoding="utf-8")
    result_keep = runner.invoke(cli, ["init", str(project_keep)], input="n\n")

    project_overwrite = tmp_path / "overwrite"
    _make_package(project_overwrite)
    (project_overwrite / "architecture.py").write_text("ORIGINAL", encoding="utf-8")
    result_overwrite = runner.invoke(cli, ["init", str(project_overwrite)], input="y\n")

    assert result_create.exit_code == 0
    assert result_keep.exit_code == 0
    assert result_overwrite.exit_code == 0
