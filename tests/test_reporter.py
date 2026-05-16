"""Tests for reporter formatting and rendering behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from archetype.analysis.models import RuleResult, Violation
from archetype.reporter import format_results, print_results


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
