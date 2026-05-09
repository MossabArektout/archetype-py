"""Tests for the Archetype CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner

from archetype.check import cli


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


def _make_project_copy(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    shutil.copytree(_fixture_root() / "simple_project", project_path / "simple_project")
    return project_path


def test_cli_exits_one_when_architecture_file_missing(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 1
    assert "architecture.py not found" in result.output
    assert str(project_path / "architecture.py") in result.output


def test_cli_exits_zero_when_all_rules_pass(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('main-does-not-import-db')",
                "def _rule_main_not_db() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    assert "Summary: 1 passed, 0 failed, 1 total" in result.output


def test_cli_exits_one_when_any_rule_fails(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('api-must-not-import-db')",
                "def _rule_api_not_db() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 1
    assert "Summary: 0 passed, 1 failed, 1 total" in result.output


def test_cli_prints_violation_messages_for_failing_rules(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('api-must-not-import-db')",
                "def _rule_api_not_db() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 1
    assert "must not import" in result.output
