"""Tests for reporter formatting and rendering behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from archetype.analysis.models import RuleResult, Violation
from archetype.reporter import (
    JSON_SCHEMA_VERSION,
    format_github_annotations,
    format_results,
    format_results_json,
    print_results,
)


def _violation() -> Violation:
    return Violation(
        module="simple_project.api",
        file=Path("simple_project/api.py"),
        line=1,
        message="Module 'simple_project.api' must not import 'simple_project.db'",
    )


def _results_fixture() -> list[RuleResult]:
    violation = _violation()
    return [
        RuleResult(name="pass-rule", passed=True),
        RuleResult(name="fail-rule", passed=False, violations=[violation]),
        RuleResult(
            name="warn-rule",
            passed=False,
            violations=[violation],
            warned=True,
            is_warning=True,
        ),
        RuleResult(
            name="skipped-rule",
            passed=False,
            skipped=True,
            skip_reason="Deferred",
        ),
        RuleResult(name="group-pass-rule", passed=True, group="All pass group"),
        RuleResult(
            name="group-warn-rule",
            passed=False,
            violations=[violation],
            warned=True,
            is_warning=True,
            group="Warning group",
        ),
    ]


def _render_output(
    renderer: str,
    results: list[RuleResult],
    quiet: bool,
    capsys: pytest.CaptureFixture[str],
) -> str:
    if renderer == "format":
        return format_results(results, quiet=quiet)
    print_results(results, quiet=quiet)
    return capsys.readouterr().out


@pytest.mark.parametrize("renderer", ["format", "print"])
def test_reporter_quiet_mode_hides_passing_rules(
    renderer: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _render_output(renderer, _results_fixture(), quiet=True, capsys=capsys)

    assert "pass-rule" not in output
    assert "group-pass-rule" not in output


@pytest.mark.parametrize("renderer", ["format", "print"])
def test_reporter_quiet_mode_shows_failing_rules(
    renderer: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _render_output(renderer, _results_fixture(), quiet=True, capsys=capsys)

    assert "✗ fail-rule" in output


@pytest.mark.parametrize("renderer", ["format", "print"])
def test_reporter_quiet_mode_shows_warned_rules(
    renderer: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _render_output(renderer, _results_fixture(), quiet=True, capsys=capsys)

    assert "⚠ warn-rule" in output
    assert "⚠ group-warn-rule" in output


@pytest.mark.parametrize("renderer", ["format", "print"])
def test_reporter_quiet_mode_hides_skipped_rules(
    renderer: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _render_output(renderer, _results_fixture(), quiet=True, capsys=capsys)

    assert "skipped-rule" not in output


@pytest.mark.parametrize("renderer", ["format", "print"])
def test_reporter_quiet_mode_summary_shows_full_counts(
    renderer: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _render_output(renderer, _results_fixture(), quiet=True, capsys=capsys)

    assert "Summary: 2 passed, 1 failed, 2 warned, 1 skipped, 6 total rules." in output


@pytest.mark.parametrize("renderer", ["format", "print"])
def test_reporter_quiet_mode_hides_all_passed_group_header(
    renderer: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _render_output(renderer, _results_fixture(), quiet=True, capsys=capsys)

    assert "All pass group" not in output


@pytest.mark.parametrize("renderer", ["format", "print"])
def test_reporter_quiet_mode_keeps_group_header_with_warning(
    renderer: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _render_output(renderer, _results_fixture(), quiet=True, capsys=capsys)

    assert "Warning group" in output


@pytest.mark.parametrize("renderer", ["format", "print"])
def test_reporter_default_mode_still_shows_passing_and_skipped(
    renderer: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _render_output(renderer, _results_fixture(), quiet=False, capsys=capsys)

    assert "pass-rule" in output
    assert "skipped-rule" in output


def test_format_results_json_includes_schema_version() -> None:
    payload = format_results_json(_results_fixture())

    assert payload["schema_version"] == JSON_SCHEMA_VERSION


def test_format_results_json_contract_shape_is_stable() -> None:
    results = [
        RuleResult(name="pass-rule", passed=True),
        RuleResult(
            name="fail-rule",
            passed=False,
            group="core",
            since_date="2026-01-01",
            violations=[_violation()],
        ),
    ]

    payload = format_results_json(results)

    assert payload == {
        "schema_version": JSON_SCHEMA_VERSION,
        "summary": {
            "passed": 1,
            "failed": 1,
            "warned": 0,
            "skipped": 0,
            "total": 2,
        },
        "violations": {
            "total": 1,
            "new": 1,
            "suppressed": 0,
        },
        "rules": [
            {
                "name": "pass-rule",
                "status": "passed",
                "group": None,
                "since_date": None,
                "violations": [],
            },
            {
                "name": "fail-rule",
                "status": "failed",
                "group": "core",
                "since_date": "2026-01-01",
                "violations": [
                    {
                        "module": "simple_project.api",
                        "message": "Module 'simple_project.api' must not import 'simple_project.db'",
                    }
                ],
            },
        ],
    }


def test_format_github_annotations_emits_error_and_warning_commands() -> None:
    violation = Violation(
        module="simple_project.api",
        file=Path("simple_project/api.py"),
        line=17,
        message="Module 'simple_project.api' must not import 'simple_project.db'",
    )
    results = [
        RuleResult(name="failing-rule", passed=False, violations=[violation]),
        RuleResult(
            name="warn-rule",
            passed=False,
            violations=[violation],
            warned=True,
            is_warning=True,
        ),
    ]

    annotations = format_github_annotations(results, project_root=Path.cwd())

    assert annotations[0].startswith(
        "::error file=simple_project/api.py,line=17,title=archetype%3A failing-rule::"
    )
    assert annotations[1].startswith(
        "::warning file=simple_project/api.py,line=17,title=archetype%3A warn-rule::"
    )


def test_format_github_annotations_escapes_reserved_characters() -> None:
    violation = Violation(
        module="simple_project.api",
        file=Path("simple_project/api.py"),
        line=3,
        message="invalid: one,two%three\nnext line",
    )
    result = RuleResult(name="rule:core,imports", passed=False, violations=[violation])

    annotations = format_github_annotations([result], project_root=Path.cwd())

    assert "title=archetype%3A rule%3Acore%2Cimports" in annotations[0]
    assert "::rule:core,imports: invalid: one,two%25three%0Anext line" in annotations[0]
