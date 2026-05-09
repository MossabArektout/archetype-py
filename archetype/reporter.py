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


def format_results(results: list[RuleResult]) -> str:
    """Build a complete plain-text report for rule execution results."""
    lines: list[str] = []
    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed

    for result in results:
        symbol = "✓" if result.passed else "✗"
        lines.append(f"{symbol} {result.name}")
        if not result.passed:
            for violation in result.violations:
                lines.append(f"  - {format_violation(violation)}")
            if result.error is not None:
                lines.append(f"  - Rule error: {result.error}")

    lines.append(
        f"Summary: {passed} passed, {failed} failed, {len(results)} total rules."
    )
    return "\n".join(lines)


def print_results(results: list[RuleResult]) -> None:
    """Print rule results using rich colors for pass/fail states."""
    console = Console()
    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed

    for result in results:
        if result.passed:
            console.print(f"[green]✓ {result.name}[/green]")
            continue

        console.print(f"[red]✗ {result.name}[/red]")
        for violation in result.violations:
            console.print(f"[red]  - {format_violation(violation)}[/red]")
        if result.error is not None:
            console.print(f"[red]  - Rule error: {result.error}[/red]")

    summary = f"Summary: {passed} passed, {failed} failed, {len(results)} total rules."
    summary_color = "green" if failed == 0 else "red"
    console.print(f"[{summary_color}]{summary}[/{summary_color}]")
