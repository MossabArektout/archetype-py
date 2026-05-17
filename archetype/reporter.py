"""Shared formatting and output utilities for Archetype rule results."""

from __future__ import annotations

from collections.abc import Mapping
import re
from collections import OrderedDict
from pathlib import Path

from rich.console import Console

from archetype.analysis.models import RuleResult, Violation


def _extract_target(violation: Violation) -> str:
    for pattern in (
        r"found import to '([^']+)'",
        r"imports protected module '([^']+)'",
        r"imports disallowed module '([^']+)'",
        r"imports '([^']+)'",
    ):
        match = re.search(pattern, violation.message)
        if match:
            return match.group(1)
    quoted = re.findall(r"'([^']+)'", violation.message)
    if quoted:
        return quoted[-1]
    return "<unknown>"


def format_violation(violation: Violation) -> str:
    """Format a violation into a concise, actionable message."""
    target = _extract_target(violation)
    location = _violation_location(violation)
    if location is not None:
        return f"{location} {violation.module} -> {target}: {violation.message}"
    return f"{violation.module} -> {target}: {violation.message}"


def _violation_location(violation: Violation) -> str | None:
    if violation.line <= 0 or str(violation.file) in {"", "<unknown>"}:
        return None

    raw_file = Path(violation.file)
    file_path = raw_file.resolve() if raw_file.is_absolute() else raw_file
    display_path = file_path

    try:
        import archetype.dsl.query as query_module

        project_root = (
            getattr(query_module, "_project_root", None)
            or getattr(query_module, "_current_root", None)
        )
        if project_root is not None:
            display_path = file_path.relative_to(Path(project_root).resolve())
        elif file_path.is_absolute():
            display_path = file_path.relative_to(Path.cwd().resolve())
    except Exception:  # noqa: BLE001
        display_path = raw_file

    return f"{display_path.as_posix()}:{violation.line}"


def _format_rule_name(result: RuleResult) -> str:
    if result.since_date:
        return f"{result.name} (since {result.since_date})"
    return result.name


def _group_results(results: list[RuleResult]) -> list[tuple[str | None, list[RuleResult]]]:
    grouped: OrderedDict[str | None, list[RuleResult]] = OrderedDict()
    for result in results:
        grouped.setdefault(result.group, []).append(result)

    ordered_keys: list[str | None] = []
    if None in grouped:
        ordered_keys.append(None)
    ordered_keys.extend(key for key in grouped if key is not None)
    return [(key, grouped[key]) for key in ordered_keys]


def _group_passed(results: list[RuleResult]) -> int:
    return sum(1 for result in results if result.passed and not result.skipped)


def _group_failed(results: list[RuleResult]) -> int:
    return sum(
        1 for result in results if not result.passed and not result.warned and not result.timed_out
    )


def _group_timed_out(results: list[RuleResult]) -> int:
    return sum(1 for result in results if result.timed_out)


def _format_timeout_seconds(timeout_seconds: float | None) -> str:
    if timeout_seconds is None:
        return "<unknown>s"
    numeric = float(timeout_seconds)
    if numeric.is_integer():
        return f"{int(numeric)}s"
    return f"{numeric:g}s"


def _violation_lines(result: RuleResult) -> list[str]:
    lines: list[str] = []
    for context_line in result.violation_context:
        lines.append(f"    {context_line}")
    for violation in result.violations:
        location = _violation_location(violation)
        if location is not None:
            lines.append(f"    - {location}")
            lines.append(f"        imports {_extract_target(violation)}")
        else:
            lines.append(f"    - {format_violation(violation)}")
    return lines


def _should_render_result(result: RuleResult, quiet: bool) -> bool:
    if not quiet:
        return True
    if result.skipped:
        return False
    return not (result.passed and not result.warned)


def _filtered_group_results(
    group_results: list[RuleResult],
    quiet: bool,
) -> list[RuleResult]:
    if not quiet:
        return group_results
    return [result for result in group_results if _should_render_result(result, quiet=True)]


def format_results(results: list[RuleResult], quiet: bool = False) -> str:
    """Build a complete plain-text report for rule execution results."""
    lines: list[str] = []
    skipped = sum(1 for result in results if result.skipped)
    warned = sum(1 for result in results if result.warned)
    timed_out = sum(1 for result in results if result.timed_out)
    passed = sum(1 for result in results if result.passed and not result.skipped)
    failed = len(results) - passed - warned - skipped - timed_out

    rendered_sections = 0
    for group_name, group_results in _group_results(results):
        visible_group_results = _filtered_group_results(group_results, quiet)
        if quiet and group_name is not None and not visible_group_results:
            continue

        if rendered_sections > 0:
            lines.append("")
        section_name = "General" if group_name is None else group_name
        lines.append(section_name)
        lines.append("=" * len(section_name))

        for result in visible_group_results:
            if result.skipped:
                line = f"  — {result.name}"
                if result.skip_reason:
                    line += f" ({result.skip_reason})"
                lines.append(line)
                continue
            if result.timed_out:
                lines.append(
                    f"  ⏱ {_format_rule_name(result)} "
                    f"(timed out after {_format_timeout_seconds(result.timeout_seconds)})"
                )
                continue

            if result.is_warning:
                symbol = "⚠"
            else:
                symbol = "✓" if result.passed else "✗"
            lines.append(f"  {symbol} {_format_rule_name(result)}")
            if result.warned:
                lines.extend(_violation_lines(result))
                if result.error is not None:
                    lines.append(f"    - Rule error: {result.error}")
            elif not result.passed:
                lines.extend(_violation_lines(result))
                if result.error is not None:
                    lines.append(f"    - Rule error: {result.error}")

        timeout_segment = ""
        group_timed_out = _group_timed_out(visible_group_results)
        if group_timed_out > 0:
            label = "timeout" if group_timed_out == 1 else "timeouts"
            timeout_segment = f", {group_timed_out} {label}"
        lines.append(
            f"  {_group_passed(visible_group_results)} passed, "
            f"{_group_failed(visible_group_results)} failed{timeout_segment}"
        )
        rendered_sections += 1

    timeout_summary = ""
    if timed_out > 0:
        label = "timeout" if timed_out == 1 else "timeouts"
        timeout_summary = f", {timed_out} {label}"
    lines.append(
        f"Summary: {passed} passed, {failed} failed, {warned} warned, {skipped} skipped"
        f"{timeout_summary}, {len(results)} total rules."
    )
    return "\n".join(lines)


def _result_status(result: RuleResult) -> str:
    if result.skipped:
        return "skipped"
    if getattr(result, "timed_out", False):
        return "timeout"
    if result.warned:
        return "warned"
    if result.passed:
        return "passed"
    return "failed"


def format_results_json(results: list[RuleResult]) -> Mapping[str, object]:
    """Build a JSON-serializable report for rule execution results."""
    skipped = sum(1 for result in results if result.skipped)
    warned = sum(1 for result in results if result.warned)
    timed_out = sum(1 for result in results if result.timed_out)
    passed = sum(1 for result in results if result.passed and not result.skipped)
    failed = len(results) - passed - warned - skipped - timed_out

    return {
        "summary": {
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "skipped": skipped,
            "total": len(results),
        },
        "rules": [
            {
                "name": result.name,
                "status": _result_status(result),
                "group": result.group,
                "since_date": result.since_date,
                "violations": [
                    {"module": violation.module, "message": violation.message}
                    for violation in result.violations
                ],
            }
            for result in results
        ],
    }


def print_results(results: list[RuleResult], quiet: bool = False) -> None:
    """Print rule results using rich colors for pass/fail states."""
    console = Console()
    skipped = sum(1 for result in results if result.skipped)
    warned = sum(1 for result in results if result.warned)
    timed_out = sum(1 for result in results if result.timed_out)
    passed = sum(1 for result in results if result.passed and not result.skipped)
    failed = len(results) - passed - warned - skipped - timed_out

    rendered_sections = 0
    for group_name, group_results in _group_results(results):
        visible_group_results = _filtered_group_results(group_results, quiet)
        if quiet and group_name is not None and not visible_group_results:
            continue

        if rendered_sections > 0:
            console.print("")

        section_name = "General" if group_name is None else group_name
        console.print(f"[bold]{section_name}[/bold]")
        console.print(f"[bold]{'=' * len(section_name)}[/bold]")

        for result in visible_group_results:
            if result.skipped:
                line = f"  — {result.name}"
                if result.skip_reason:
                    line += f" ({result.skip_reason})"
                console.print(f"[dim]{line}[/dim]")
                continue
            if result.timed_out:
                console.print(
                    "[yellow]"
                    f"  ⏱ {_format_rule_name(result)} "
                    f"(timed out after {_format_timeout_seconds(result.timeout_seconds)})"
                    "[/yellow]"
                )
                continue

            if result.is_warning:
                console.print(f"[yellow]  ⚠ {_format_rule_name(result)}[/yellow]")
                if result.warned:
                    for context_line in result.violation_context:
                        console.print(f"[yellow]    {context_line}[/yellow]")
                    for violation in result.violations:
                        location = _violation_location(violation)
                        if location is not None:
                            console.print(f"[yellow]    - {location}[/yellow]")
                            console.print(
                                f"[yellow]        imports {_extract_target(violation)}[/yellow]"
                            )
                        else:
                            console.print(f"[yellow]    - {format_violation(violation)}[/yellow]")
                    if result.error is not None:
                        console.print(f"[yellow]    - Rule error: {result.error}[/yellow]")
                continue

            if result.passed:
                console.print(f"[green]  ✓ {_format_rule_name(result)}[/green]")
                continue

            console.print(f"[red]  ✗ {_format_rule_name(result)}[/red]")
            for context_line in result.violation_context:
                console.print(f"[red]    {context_line}[/red]")
            for violation in result.violations:
                location = _violation_location(violation)
                if location is not None:
                    console.print(f"[red]    - {location}[/red]")
                    console.print(f"[red]        imports {_extract_target(violation)}[/red]")
                else:
                    console.print(f"[red]    - {format_violation(violation)}[/red]")
            if result.error is not None:
                console.print(f"[red]    - Rule error: {result.error}[/red]")

        timeout_segment = ""
        group_timed_out = _group_timed_out(visible_group_results)
        if group_timed_out > 0:
            label = "timeout" if group_timed_out == 1 else "timeouts"
            timeout_segment = f", {group_timed_out} {label}"
        console.print(
            "[bold]"
            f"  {_group_passed(visible_group_results)} passed, "
            f"{_group_failed(visible_group_results)} failed{timeout_segment}"
            "[/bold]"
        )
        rendered_sections += 1

    timeout_summary = ""
    if timed_out > 0:
        label = "timeout" if timed_out == 1 else "timeouts"
        timeout_summary = f", {timed_out} {label}"
    summary = (
        f"Summary: {passed} passed, {failed} failed, {warned} warned, {skipped} skipped"
        f"{timeout_summary}, {len(results)} total rules."
    )
    if failed > 0:
        summary_color = "red"
    elif warned > 0 or timed_out > 0:
        summary_color = "yellow"
    else:
        summary_color = "green"
    console.print(f"[{summary_color}]{summary}[/{summary_color}]")
