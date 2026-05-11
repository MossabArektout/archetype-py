"""Shared formatting and output utilities for Archetype rule results."""

from __future__ import annotations

import re

from rich.console import Console

from archetype.analysis.models import RuleResult, Violation


def _extract_target(violation: Violation) -> str:
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


def format_results(results: list[RuleResult]) -> str:
    """Build a complete plain-text report for rule execution results."""
    lines: list[str] = []
    skipped = sum(1 for result in results if result.skipped)
    warned = sum(1 for result in results if result.warned)
    passed = sum(1 for result in results if result.passed and not result.skipped)
    failed = len(results) - passed - warned - skipped

    for result in results:
        if result.skipped:
            line = f"— {result.name}"
            if result.skip_reason:
                line += f" ({result.skip_reason})"
            lines.append(line)
            continue

        if result.is_warning:
            symbol = "⚠"
        else:
            symbol = "✓" if result.passed else "✗"
        lines.append(f"{symbol} {_format_rule_name(result)}")
        if result.warned:
            for violation in result.violations:
                lines.append(f"  - {format_violation(violation)}")
            if result.error is not None:
                lines.append(f"  - Rule error: {result.error}")
        elif not result.passed:
            for violation in result.violations:
                lines.append(f"  - {format_violation(violation)}")
            if result.error is not None:
                lines.append(f"  - Rule error: {result.error}")

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

    for result in results:
        if result.skipped:
            line = f"— {result.name}"
            if result.skip_reason:
                line += f" ({result.skip_reason})"
            console.print(f"[dim]{line}[/dim]")
            continue

        if result.is_warning:
            console.print(f"[yellow]⚠ {_format_rule_name(result)}[/yellow]")
            if result.warned:
                for violation in result.violations:
                    console.print(f"[yellow]  - {format_violation(violation)}[/yellow]")
                if result.error is not None:
                    console.print(f"[yellow]  - Rule error: {result.error}[/yellow]")
            continue

        if result.passed:
            console.print(f"[green]✓ {_format_rule_name(result)}[/green]")
            continue

        console.print(f"[red]✗ {_format_rule_name(result)}[/red]")
        for violation in result.violations:
            console.print(f"[red]  - {format_violation(violation)}[/red]")
        if result.error is not None:
            console.print(f"[red]  - Rule error: {result.error}[/red]")

    summary = f"Summary: {passed} passed, {failed} failed, {warned} warned, {skipped} skipped, {len(results)} total rules."
    if failed > 0:
        summary_color = "red"
    elif warned > 0:
        summary_color = "yellow"
    else:
        summary_color = "green"
    console.print(f"[{summary_color}]{summary}[/{summary_color}]")
