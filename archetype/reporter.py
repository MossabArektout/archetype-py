"""Shared formatting and output utilities for Archetype rule results."""

from __future__ import annotations

import re
from collections import OrderedDict

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
    return f"{violation.module} -> {target}: {violation.message}"


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
    return sum(1 for result in results if not result.passed and not result.warned)


def _violation_lines(result: RuleResult) -> list[str]:
    lines: list[str] = []
    for context_line in result.violation_context:
        lines.append(f"    {context_line}")
    for violation in result.violations:
        lines.append(f"    - {format_violation(violation)}")
    return lines


def format_results(results: list[RuleResult]) -> str:
    """Build a complete plain-text report for rule execution results."""
    lines: list[str] = []
    skipped = sum(1 for result in results if result.skipped)
    warned = sum(1 for result in results if result.warned)
    passed = sum(1 for result in results if result.passed and not result.skipped)
    failed = len(results) - passed - warned - skipped

    for idx, (group_name, group_results) in enumerate(_group_results(results)):
        if idx > 0:
            lines.append("")
        section_name = "General" if group_name is None else group_name
        lines.append(section_name)
        lines.append("=" * len(section_name))

        for result in group_results:
            if result.skipped:
                line = f"  — {result.name}"
                if result.skip_reason:
                    line += f" ({result.skip_reason})"
                lines.append(line)
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

        lines.append(
            f"  {_group_passed(group_results)} passed, {_group_failed(group_results)} failed"
        )

    lines.append(
        f"Summary: {passed} passed, {failed} failed, {warned} warned, {skipped} skipped, {len(results)} total rules."
    )
    return "\n".join(lines)


def print_results(results: list[RuleResult]) -> None:
    """Print rule results using rich colors for pass/fail states."""
    console = Console()
    skipped = sum(1 for result in results if result.skipped)
    warned = sum(1 for result in results if result.warned)
    passed = sum(1 for result in results if result.passed and not result.skipped)
    failed = len(results) - passed - warned - skipped

    for idx, (group_name, group_results) in enumerate(_group_results(results)):
        if idx > 0:
            console.print("")

        section_name = "General" if group_name is None else group_name
        console.print(f"[bold]{section_name}[/bold]")
        console.print(f"[bold]{'=' * len(section_name)}[/bold]")

        for result in group_results:
            if result.skipped:
                line = f"  — {result.name}"
                if result.skip_reason:
                    line += f" ({result.skip_reason})"
                console.print(f"[dim]{line}[/dim]")
                continue

            if result.is_warning:
                console.print(f"[yellow]  ⚠ {_format_rule_name(result)}[/yellow]")
                if result.warned:
                    for context_line in result.violation_context:
                        console.print(f"[yellow]    {context_line}[/yellow]")
                    for violation in result.violations:
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
                console.print(f"[red]    - {format_violation(violation)}[/red]")
            if result.error is not None:
                console.print(f"[red]    - Rule error: {result.error}[/red]")

        console.print(
            f"[bold]  {_group_passed(group_results)} passed, {_group_failed(group_results)} failed[/bold]"
        )

    summary = f"Summary: {passed} passed, {failed} failed, {warned} warned, {skipped} skipped, {len(results)} total rules."
    if failed > 0:
        summary_color = "red"
    elif warned > 0:
        summary_color = "yellow"
    else:
        summary_color = "green"
    console.print(f"[{summary_color}]{summary}[/{summary_color}]")
