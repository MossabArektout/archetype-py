"""Tests for project initialization helpers and CLI init command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from archetype.check import cli
from archetype.init import detect_project_structure, generate_architecture_py


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_package(project_root: Path, name: str = "myapp") -> Path:
    package = project_root / name
    _write(package / "__init__.py")
    return package


def test_detect_project_structure_identifies_top_level_package(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path, "myapp")
    _write(myapp / "main.py")

    docs = tmp_path / "docs"
    _write(docs / "__init__.py")
    _write(docs / "ignored.py")

    structure = detect_project_structure(tmp_path)

    assert structure["top_level_package"] == "myapp"


def test_detect_project_structure_detects_layers_in_order(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path)
    _write(myapp / "api" / "__init__.py")
    _write(myapp / "services" / "__init__.py")
    _write(myapp / "db" / "__init__.py")

    structure = detect_project_structure(tmp_path)

    assert structure["detected_layers"] == ["myapp.api", "myapp.services", "myapp.db"]


def test_detect_project_structure_returns_empty_layers_when_unknown(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path)
    _write(myapp / "controllers" / "__init__.py")
    _write(myapp / "store" / "__init__.py")

    structure = detect_project_structure(tmp_path)

    assert structure["detected_layers"] == []


def test_detect_project_structure_detects_internal_subpackages(tmp_path: Path) -> None:
    myapp = _make_package(tmp_path)
    _write(myapp / "auth" / "internal" / "__init__.py")
    _write(myapp / "billing" / "internal" / "__init__.py")

    structure = detect_project_structure(tmp_path)

    assert structure["has_internal"] is True
    assert structure["internal_paths"] == [
        "myapp.auth.internal",
        "myapp.billing.internal",
    ]


def test_generate_architecture_py_includes_layers_rule_for_two_or_more_layers() -> None:
    structure = {
        "top_level_package": "myapp",
        "detected_layers": ["myapp.api", "myapp.services", "myapp.db"],
        "has_internal": False,
        "internal_paths": [],
        "total_python_files": 5,
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
    }

    content = generate_architecture_py(structure)

    assert "shop.routes" in content
    assert "shop.business" in content
    assert "shop.repositories" in content
    assert "your_project" not in content


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
