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


def test_cli_warns_when_rule_pattern_matches_no_modules(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('misspelled-source')",
                "def _rule_misspelled_source() -> None:",
                "    imports('simple_project.mian').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    assert "⚠ misspelled-source" in result.output
    assert "Source pattern 'simple_project.mian' matched 0 modules." in result.output
    assert "simple_project.main" in result.output


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


def test_doctor_reports_detected_project_shape(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["doctor", str(project_path)])

    assert result.exit_code == 0
    assert "Archetype doctor" in result.output
    assert "architecture.py: missing" in result.output
    assert "Layout: unknown" in result.output
    assert "Package: not detected" in result.output
    assert "Modules discovered:" in result.output
    assert "Package roots:" in result.output


def test_graph_command_exports_mermaid_import_graph(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["graph", str(project_path), "--format", "mermaid"])

    assert result.exit_code == 0
    assert "graph LR" in result.output
    assert "simple_project.api" in result.output
    assert "-->" in result.output


def test_graph_command_exports_json_import_graph(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["graph", str(project_path), "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert "simple_project.api" in payload["nodes"]
    assert any(
        edge["source"] == "simple_project.api"
        and edge["target"] == "simple_project.db"
        and edge["line"] > 0
        for edge in payload["edges"]
    )


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

    captured: dict[str, str | int | None] = {"group_filter": None, "workers": None}

    def fake_run_all(
        *,
        group_filter: str | None = None,
        workers: int = 1,
        rule_policies=None,
    ):
        _ = rule_policies
        captured["group_filter"] = group_filter
        captured["workers"] = workers
        return []

    monkeypatch.setattr("archetype.check.registry.run_all", fake_run_all)
    runner = CliRunner()

    result = runner.invoke(
        cli, ["check", str(project_path), "--group", "Layer boundaries"]
    )

    assert result.exit_code == 0
    assert captured["group_filter"] == "Layer boundaries"
    assert captured["workers"] == 1


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
    assert "No rules matched group 'No such group'." in result.output
    assert "Summary: 0 passed, 0 failed, 0 warned, 0 skipped, 0 total rules." in result.output


def test_cli_no_cache_flag_passes_no_cache_to_load_project(
    tmp_path: Path, monkeypatch
) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text("from archetype import rule\n", encoding="utf-8")

    captured: dict[str, object | None] = {"no_cache": None, "exclude_patterns": None}

    def fake_load_project(
        _project_root: Path,
        src_root: Path | None = None,
        no_cache: bool = False,
        exclude_patterns=None,
    ) -> None:
        _ = src_root
        captured["no_cache"] = no_cache
        captured["exclude_patterns"] = exclude_patterns

    monkeypatch.setattr("archetype.check.load_project", fake_load_project)
    monkeypatch.setattr(
        "archetype.check.registry.run_all",
        lambda *, group_filter=None, workers=1, rule_policies=None: [],
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--no-cache"])

    assert result.exit_code == 0
    assert captured["no_cache"] is True
    assert captured["exclude_patterns"] == []


def test_cli_exclude_flag_is_repeatable_and_passes_patterns_to_load_project(
    tmp_path: Path, monkeypatch
) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text("from archetype import rule\n", encoding="utf-8")

    captured: dict[str, object | None] = {"exclude_patterns": None}

    def fake_load_project(
        _project_root: Path,
        src_root: Path | None = None,
        no_cache: bool = False,
        exclude_patterns=None,
    ) -> None:
        _ = src_root
        _ = no_cache
        captured["exclude_patterns"] = exclude_patterns

    monkeypatch.setattr("archetype.check.load_project", fake_load_project)
    monkeypatch.setattr(
        "archetype.check.registry.run_all",
        lambda *, group_filter=None, workers=1, rule_policies=None: [],
    )
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--exclude",
            "/vendor/",
            "--exclude",
            "/migrations/",
        ],
    )

    assert result.exit_code == 0
    assert captured["exclude_patterns"] == ["/vendor/", "/migrations/"]


def test_cli_exclude_patterns_from_pyproject_are_applied(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    vendor_pkg = project_path / "vendor"
    vendor_pkg.mkdir(parents=True)
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")
    (vendor_pkg / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")

    api_module = project_path / "simple_project" / "api.py"
    api_module.write_text(
        "\n".join(
            [
                "from simple_project import db",
                "from simple_project import services",
                "from simple_project.internal import tokens",
                "from vendor import helpers",
                "",
                "def handle() -> None:",
                "    return None",
            ]
        ),
        encoding="utf-8",
    )
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('api-must-not-import-vendor')",
                "def _rule_api_not_vendor() -> None:",
                "    imports('simple_project.api').must_not_import('vendor.*')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    without_config = runner.invoke(cli, ["check", str(project_path)])
    (project_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.archetype]",
                'exclude = ["/vendor/"]',
            ]
        ),
        encoding="utf-8",
    )
    with_config = runner.invoke(cli, ["check", str(project_path)])

    assert without_config.exit_code == 1
    assert with_config.exit_code == 0


def test_cli_exclude_patterns_from_archetype_toml_are_applied(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    vendor_pkg = project_path / "vendor"
    vendor_pkg.mkdir(parents=True)
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")
    (vendor_pkg / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")

    (project_path / "simple_project" / "api.py").write_text(
        "\n".join(
            [
                "from vendor import helpers",
                "",
                "def handle() -> None:",
                "    return None",
            ]
        ),
        encoding="utf-8",
    )
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('api-must-not-import-vendor')",
                "def _rule_api_not_vendor() -> None:",
                "    imports('simple_project.api').must_not_import('vendor.*')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_path / "archetype.toml").write_text(
        "\n".join(
            [
                'exclude = ["/vendor/"]',
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0


def test_cli_defaults_from_archetype_toml_are_applied(
    tmp_path: Path, monkeypatch
) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text("from archetype import rule\n", encoding="utf-8")
    (project_path / "archetype.toml").write_text(
        "\n".join(
            [
                'format = "json"',
                "quiet = true",
                'group = "core"',
                'exclude = ["/vendor/"]',
                "workers = 3",
                "cache = false",
                "",
                "[rules]",
                '"api-not-db" = "warning"',
            ]
        ),
        encoding="utf-8",
    )

    captured: dict[str, object | None] = {
        "group_filter": None,
        "workers": None,
        "no_cache": None,
        "exclude_patterns": None,
        "rule_policies": None,
    }

    def fake_load_project(
        _project_root: Path,
        src_root: Path | None = None,
        no_cache: bool = False,
        exclude_patterns=None,
    ) -> None:
        _ = src_root
        captured["no_cache"] = no_cache
        captured["exclude_patterns"] = exclude_patterns

    def fake_run_all(
        *,
        group_filter: str | None = None,
        workers: int = 1,
        rule_policies=None,
    ):
        captured["group_filter"] = group_filter
        captured["workers"] = workers
        captured["rule_policies"] = rule_policies
        return []

    monkeypatch.setattr("archetype.check.load_project", fake_load_project)
    monkeypatch.setattr("archetype.check.registry.run_all", fake_run_all)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["total"] == 0
    assert captured["group_filter"] == "core"
    assert captured["workers"] == 3
    assert captured["no_cache"] is True
    assert captured["exclude_patterns"] == ["/vendor/"]
    assert captured["rule_policies"] == {"api-not-db": "warning"}


def test_cli_flags_override_archetype_toml_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text("from archetype import rule\n", encoding="utf-8")
    (project_path / "archetype.toml").write_text(
        "\n".join(
            [
                'format = "json"',
                "quiet = true",
                'group = "core"',
                'exclude = ["/vendor/"]',
                "workers = 5",
                "cache = false",
            ]
        ),
        encoding="utf-8",
    )

    captured: dict[str, object | None] = {
        "group_filter": None,
        "workers": None,
        "no_cache": None,
        "exclude_patterns": None,
    }

    def fake_load_project(
        _project_root: Path,
        src_root: Path | None = None,
        no_cache: bool = False,
        exclude_patterns=None,
    ) -> None:
        _ = src_root
        captured["no_cache"] = no_cache
        captured["exclude_patterns"] = exclude_patterns

    def fake_run_all(
        *,
        group_filter: str | None = None,
        workers: int = 1,
        rule_policies=None,
    ):
        _ = rule_policies
        captured["group_filter"] = group_filter
        captured["workers"] = workers
        return []

    monkeypatch.setattr("archetype.check.load_project", fake_load_project)
    monkeypatch.setattr("archetype.check.registry.run_all", fake_run_all)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--format",
            "text",
            "--no-quiet",
            "--group",
            "override-group",
            "--exclude",
            "/migrations/",
            "--workers",
            "2",
            "--cache",
        ],
    )

    assert result.exit_code == 0
    assert "Summary: 0 passed, 0 failed, 0 warned, 0 skipped, 0 total rules." in result.output
    assert captured["group_filter"] == "override-group"
    assert captured["workers"] == 2
    assert captured["no_cache"] is False
    assert captured["exclude_patterns"] == ["/migrations/"]


def test_cli_rule_policy_warning_downgrades_failure_to_warning(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('api-not-db')",
                "def _rule_api_not_db() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_path / "archetype.toml").write_text(
        "\n".join(
            [
                'format = "json"',
                "",
                "[rules]",
                '"api-not-db" = "warning"',
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["warned"] == 1
    assert payload["rules"][0]["status"] == "warned"
    assert payload["rules"][0]["policy"] == "warning"


def test_cli_rule_policy_off_skips_rule_without_running_it(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import rule",
                "",
                "@rule('disabled-rule')",
                "def _disabled_rule() -> None:",
                "    raise RuntimeError('should not run')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_path / "archetype.toml").write_text(
        "\n".join(
            [
                'format = "json"',
                "",
                '[rules."disabled-rule"]',
                'policy = "off"',
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["skipped"] == 1
    assert payload["rules"][0]["status"] == "off"
    assert payload["rules"][0]["policy"] == "off"
    assert payload["rules"][0]["violations"] == []


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
    assert payload["schema_version"] == 2
    assert payload["summary"]["total"] == 1


def test_cli_format_json_outputs_parseable_json(tmp_path: Path) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--format", "json"])

    payload = json.loads(result.output)
    assert isinstance(payload, dict)
    assert payload["schema_version"] == 2
    assert "summary" in payload
    assert "violations" in payload
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
    assert payload["violations"] == {"total": 3, "new": 3, "suppressed": 0}


def test_cli_format_json_quiet_outputs_parseable_json_with_full_summary(
    tmp_path: Path,
) -> None:
    project_path = _make_project_copy(tmp_path)
    _write_quiet_mode_fixture(project_path)
    runner = CliRunner()

    result = runner.invoke(
        cli, ["check", str(project_path), "--format", "json", "--quiet"]
    )

    payload = json.loads(result.output)
    assert payload["summary"] == {
        "passed": 2,
        "failed": 1,
        "warned": 2,
        "skipped": 1,
        "total": 6,
    }
    assert payload["violations"] == {"total": 3, "new": 3, "suppressed": 0}
    assert isinstance(payload["rules"], list)
    assert len(payload["rules"]) == 6


def test_cli_write_baseline_creates_valid_json_file(tmp_path: Path) -> None:
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
    baseline_path = tmp_path / "archetype-baseline.json"
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--write-baseline",
            str(baseline_path),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert isinstance(payload["violations"], list)
    assert len(payload["violations"]) == 1
    violation = payload["violations"][0]
    assert violation["rule"] == "api-must-not-import-db"
    assert violation["module"] == "simple_project.api"
    assert violation["file"] == "simple_project/api.py"
    assert violation["line"] == 7


def test_cli_baseline_suppresses_existing_violations_and_exits_zero(tmp_path: Path) -> None:
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
    baseline_path = tmp_path / "archetype-baseline.json"
    runner = CliRunner()

    write_result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--write-baseline",
            str(baseline_path),
        ],
    )
    suppress_result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--baseline",
            str(baseline_path),
        ],
    )

    assert write_result.exit_code == 1
    assert suppress_result.exit_code == 0
    assert "Summary: 1 passed, 0 failed, 0 warned, 0 skipped, 1 total rules." in suppress_result.output


def test_cli_exit_code_is_non_zero_only_for_new_violations_with_baseline(
    tmp_path: Path,
) -> None:
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
                "@rule('main-must-not-import-db')",
                "def _rule_main_not_db() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    baseline_path = tmp_path / "archetype-baseline.json"
    runner = CliRunner()

    write_result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--write-baseline",
            str(baseline_path),
        ],
    )
    assert write_result.exit_code == 1

    (project_path / "simple_project" / "main.py").write_text(
        "\n".join(
            [
                '"""Entry module for the simple fixture project."""',
                "",
                "from simple_project import api",
                "from simple_project import db",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--baseline",
            str(baseline_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["summary"]["failed"] == 1
    assert payload["violations"] == {"total": 2, "new": 1, "suppressed": 1}


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


def test_cli_changed_from_accepts_branch_name_and_scopes_reporting(
    tmp_path: Path, monkeypatch
) -> None:
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
    changed_file = (project_path / "simple_project" / "api.py").resolve()

    captured: dict[str, str | None] = {"ref": None}

    def fake_changed_from(
        ref: str,
        _root: Path,
        *,
        exclude_patterns=None,
    ) -> set[Path]:
        _ = exclude_patterns
        captured["ref"] = ref
        return {changed_file}

    monkeypatch.setattr("archetype.check.get_files_changed_from", fake_changed_from)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--changed-from", "origin/main"])

    assert result.exit_code == 1
    assert captured["ref"] == "origin/main"
    assert "Scope: changed-files mode from 'origin/main' (1 changed Python files)" in result.output
    assert "✗ api-must-not-import-db" in result.output


def test_cli_changed_from_accepts_commit_sha_and_filters_out_of_scope_violations(
    tmp_path: Path, monkeypatch
) -> None:
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
    sha = "a1b2c3d4"

    monkeypatch.setattr(
        "archetype.check.get_files_changed_from",
        lambda *_args, **_kwargs: set(),
    )

    result = runner.invoke(cli, ["check", str(project_path), "--changed-from", sha])

    assert result.exit_code == 0
    assert f"Scope: changed-files mode from '{sha}' (0 changed Python files)" in result.output
    assert "✓ api-must-not-import-db" in result.output


def test_cli_changed_from_json_includes_scope_metadata(
    tmp_path: Path, monkeypatch
) -> None:
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
    changed_file = (project_path / "simple_project" / "api.py").resolve()
    runner = CliRunner()

    monkeypatch.setattr(
        "archetype.check.get_files_changed_from",
        lambda *_args, **_kwargs: {changed_file},
    )

    result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--changed-from",
            "origin/main",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["scope"] == {
        "mode": "changed-files",
        "changed_from": "origin/main",
        "changed_files_count": 1,
        "changed_files": ["simple_project/api.py"],
    }


def test_cli_changed_from_scope_ignores_excluded_paths(
    tmp_path: Path, monkeypatch
) -> None:
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
    changed_file = (project_path / "vendor" / "helpers.py").resolve()

    monkeypatch.setattr(
        "archetype.check.get_files_changed_from",
        lambda *_args, **_kwargs: {changed_file},
    )

    result = runner.invoke(
        cli,
        [
            "check",
            str(project_path),
            "--changed-from",
            "origin/main",
            "--exclude",
            "/vendor/",
        ],
    )

    assert result.exit_code == 0
    assert "Scope: changed-files mode from 'origin/main' (0 changed Python files)" in result.output


def test_cli_install_hook_creates_pre_commit_hook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    hook_path = tmp_path / ".git" / "hooks" / "pre-commit"

    monkeypatch.setattr(
        "archetype.check._resolve_git_hook_paths",
        lambda _path: (project_path, hook_path),
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["install-hook", str(project_path)])

    assert result.exit_code == 0
    content = hook_path.read_text(encoding="utf-8")
    assert content.startswith("#!/bin/sh")
    assert "# >>> archetype pre-commit hook >>>" in content
    assert 'archetype check "$repo_root"' in content
    assert hook_path.stat().st_mode & 0o111


def test_cli_install_hook_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    hook_path = tmp_path / ".git" / "hooks" / "pre-commit"

    monkeypatch.setattr(
        "archetype.check._resolve_git_hook_paths",
        lambda _path: (project_path, hook_path),
    )
    runner = CliRunner()

    first = runner.invoke(cli, ["install-hook", str(project_path)])
    second = runner.invoke(cli, ["install-hook", str(project_path)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    content = hook_path.read_text(encoding="utf-8")
    assert content.count("# >>> archetype pre-commit hook >>>") == 1
    assert "already installed" in second.output


def test_cli_install_hook_appends_to_existing_pre_commit_hook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    hook_path = tmp_path / ".git" / "hooks" / "pre-commit"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "echo \"existing pre-commit checks\"",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "archetype.check._resolve_git_hook_paths",
        lambda _path: (project_path, hook_path),
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["install-hook", str(project_path)])

    assert result.exit_code == 0
    content = hook_path.read_text(encoding="utf-8")
    assert "existing pre-commit checks" in content
    assert "# >>> archetype pre-commit hook >>>" in content
    assert "Appended Archetype block" in result.output


def test_cli_install_hook_errors_when_git_paths_cannot_be_resolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()

    def _raise(_path: Path) -> tuple[Path, Path]:
        raise ValueError("Unable to resolve git hooks path: fatal: not a git repository")

    monkeypatch.setattr("archetype.check._resolve_git_hook_paths", _raise)
    runner = CliRunner()

    result = runner.invoke(cli, ["install-hook", str(project_path)])

    assert result.exit_code == 1
    assert "not a git repository" in result.output


def test_cli_github_annotations_flag_emits_github_error_commands(
    tmp_path: Path,
) -> None:
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

    result = runner.invoke(
        cli,
        ["check", str(project_path), "--github-annotations"],
    )

    assert result.exit_code == 1
    assert "::error file=simple_project/api.py,line=7,title=archetype%3A api-must-not-import-db::" in result.output
