"""Tests for the Archetype CLI."""

from __future__ import annotations

import json
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


def _write_quiet_mode_fixture(project_path: Path) -> None:
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import group, imports, rule, skip, warn",
                "",
                "@rule('pass-rule')",
                "def _pass_rule() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
                "@rule('fail-rule')",
                "def _fail_rule() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
                "@rule('warn-rule')",
                "@warn",
                "def _warn_rule() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
                "@rule('skipped-rule')",
                "@skip(reason='Deferred')",
                "def _skipped_rule() -> None:",
                "    raise AssertionError('must never execute')",
                "",
                "with group('All pass group'):",
                "    @rule('group-pass-rule')",
                "    def _group_pass_rule() -> None:",
                "        imports('simple_project.main').must_not_import('simple_project.db')",
                "",
                "with group('Warning group'):",
                "    @rule('group-warn-rule')",
                "    @warn",
                "    def _group_warn_rule() -> None:",
                "        imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )


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
    assert "Summary: 1 passed, 0 failed, 0 warned, 0 skipped, 1 total rules." in result.output


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
    assert "Summary: 0 passed, 1 failed, 0 warned, 0 skipped, 1 total rules." in result.output


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
    assert "✗ api-must-not-import-db" in result.output
    assert "simple_project/api.py:7" in result.output
    assert "imports simple_project.db" in result.output


def test_cli_shows_allowed_set_once_for_must_only_import_from(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('api-only-services')",
                "def _rule_api_only_services() -> None:",
                "    imports('simple_project.api').must_only_import_from('simple_project.services')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 1
    assert "Allowed imports for 'simple_project.api': simple_project.services." in result.output
    assert result.output.count(
        "Allowed imports for 'simple_project.api': simple_project.services."
    ) == 1
    assert "simple_project/api.py:7" in result.output
    assert "imports simple_project.db" in result.output
    assert "outside the allowed set" not in result.output


def test_cli_summary_reflects_passing_and_failing_counts(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('pass-rule')",
                "def _pass_rule() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
                "@rule('fail-rule')",
                "def _fail_rule() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 1
    assert "✓ pass-rule" in result.output
    assert "✗ fail-rule" in result.output
    assert "Summary: 1 passed, 1 failed, 0 warned, 0 skipped, 2 total rules." in result.output


def test_cli_exits_zero_when_only_warned_rules_have_violations(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule, warn",
                "",
                "@rule('warn-only-rule')",
                "@warn",
                "def _warn_only_rule() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    assert "⚠ warn-only-rule" in result.output
    assert "Summary: 0 passed, 0 failed, 1 warned, 0 skipped, 1 total rules." in result.output


def test_cli_summary_includes_warned_count(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule, warn",
                "",
                "@rule('pass-rule')",
                "def _pass_rule() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
                "@rule('warn-rule')",
                "@warn",
                "def _warn_rule() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    assert "Summary: 1 passed, 0 failed, 1 warned, 0 skipped, 2 total rules." in result.output


def test_cli_exits_zero_when_all_rules_are_skipped(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import rule, skip",
                "",
                "@rule('skipped-rule')",
                "@skip",
                "def _skipped_rule() -> None:",
                "    raise AssertionError('must never execute')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    assert "— skipped-rule" in result.output
    assert "Summary: 0 passed, 0 failed, 0 warned, 1 skipped, 1 total rules." in result.output


def test_cli_summary_includes_skipped_count(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule, skip",
                "",
                "@rule('pass-rule')",
                "def _pass_rule() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
                "@rule('skipped-rule')",
                "@skip",
                "def _skipped_rule() -> None:",
                "    raise AssertionError('must never execute')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    assert "Summary: 1 passed, 0 failed, 0 warned, 1 skipped, 2 total rules." in result.output


def test_cli_outputs_skip_reason_when_provided(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import rule, skip",
                "",
                "@rule('skipped-rule')",
                "@skip(reason='Fixing in refactor-auth branch')",
                "def _skipped_rule() -> None:",
                "    raise AssertionError('must never execute')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    assert "— skipped-rule (Fixing in refactor-auth branch)" in result.output


def test_cli_exits_zero_when_since_filters_out_all_violations(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule, since",
                "",
                "@rule('api-must-not-import-db')",
                "@since('2999-01-01')",
                "def _rule_api_not_db() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    assert "✓ api-must-not-import-db (since 2999-01-01)" in result.output
    assert "Summary: 1 passed, 0 failed, 0 warned, 0 skipped, 1 total rules." in result.output


def test_cli_outputs_since_date_next_to_rule_name(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule, since",
                "",
                "@rule('api-must-not-import-db')",
                "@since('2000-01-01')",
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
    assert "✗ api-must-not-import-db (since 2000-01-01)" in result.output


def test_cli_group_flag_passes_group_filter_to_registry_run_all(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import rule",
                "",
                "@rule('simple-rule')",
                "def _simple_rule() -> None:",
                "    return None",
                "",
            ]
        ),
        encoding="utf-8",
    )

    captured: dict[str, str | None] = {"group_filter": None}

    def fake_run_all(*, group_filter: str | None = None):
        captured["group_filter"] = group_filter
        return []

    monkeypatch.setattr("archetype.check.registry.run_all", fake_run_all)
    runner = CliRunner()

    result = runner.invoke(
        cli, ["check", str(project_path), "--group", "Layer boundaries"]
    )

    assert result.exit_code == 0
    assert captured["group_filter"] == "Layer boundaries"


def test_cli_group_flag_with_unknown_group_returns_zero_rules(
    tmp_path: Path,
) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import group, imports, rule",
                "",
                "with group('Layer boundaries'):",
                "    @rule('api-not-db')",
                "    def _rule_api_not_db() -> None:",
                "        imports('simple_project.main').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--group", "No such group"])

    assert result.exit_code == 0
    assert "Summary: 0 passed, 0 failed, 0 warned, 0 skipped, 0 total rules." in result.output


def test_cli_quiet_flag_is_accepted(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('pass-rule')",
                "def _pass_rule() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert result.exit_code == 0
    assert "No such option" not in result.output


def test_cli_format_flag_is_accepted(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('pass-rule')",
                "def _pass_rule() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--format", "json"])

    assert result.exit_code == 0
    assert "No such option" not in result.output
    payload = json.loads(result.output)
    assert payload["summary"]["total"] == 1


def test_cli_format_json_outputs_parseable_json(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--format", "json"])

    payload = json.loads(result.output)
    assert isinstance(payload, dict)
    assert "summary" in payload
    assert "rules" in payload


def test_cli_format_json_summary_counts_are_correct(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--format", "json"])

    payload = json.loads(result.output)
    assert payload["summary"] == {
        "passed": 2,
        "failed": 1,
        "warned": 2,
        "skipped": 1,
        "total": 6,
    }


def test_cli_format_text_behavior_is_unchanged(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    default_result = runner.invoke(cli, ["check", str(project_path)])
    text_result = runner.invoke(cli, ["check", str(project_path), "--format", "text"])

    assert default_result.exit_code == text_result.exit_code
    assert default_result.output == text_result.output


def test_cli_exit_code_is_identical_for_text_and_json_formats(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    text_result = runner.invoke(cli, ["check", str(project_path), "--format", "text"])
    json_result = runner.invoke(cli, ["check", str(project_path), "--format", "json"])

    assert text_result.exit_code == json_result.exit_code


def test_cli_quiet_mode_hides_passing_rules(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert "pass-rule" not in result.output
    assert "group-pass-rule" not in result.output


def test_cli_quiet_mode_shows_failing_rules(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert "✗ fail-rule" in result.output


def test_cli_quiet_mode_shows_warned_rules(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert "⚠ warn-rule" in result.output
    assert "⚠ group-warn-rule" in result.output


def test_cli_quiet_mode_hides_skipped_rules(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert "skipped-rule" not in result.output


def test_cli_quiet_mode_summary_shows_full_counts(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert (
        "Summary: 2 passed, 1 failed, 2 warned, 1 skipped, 6 total rules."
        in result.output
    )


def test_cli_quiet_mode_hides_group_headers_when_all_rules_passed(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert "All pass group" not in result.output


def test_cli_quiet_mode_keeps_group_header_with_warning_or_failure(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert "Warning group" in result.output


def test_cli_exit_code_is_identical_with_and_without_quiet(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    normal_result = runner.invoke(cli, ["check", str(project_path)])
    quiet_result = runner.invoke(cli, ["check", str(project_path), "--quiet"])

    assert normal_result.exit_code == quiet_result.exit_code


def test_cli_quiet_short_flag_matches_long_flag_behavior(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    long_result = runner.invoke(cli, ["check", str(project_path), "--quiet"])
    short_result = runner.invoke(cli, ["check", str(project_path), "-q"])

    assert long_result.exit_code == short_result.exit_code
    assert long_result.output == short_result.output
