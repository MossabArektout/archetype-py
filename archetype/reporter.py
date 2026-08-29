"""Shared formatting and output utilities for Archetype rule results."""

from __future__ import annotations

from collections.abc import Mapping
import re
from collections import OrderedDict
from pathlib import Path
from urllib.parse import quote

from rich.console import Console

from archetype.baseline import ViolationCounts
from archetype.analysis.codeowners import Codeowners
from archetype.analysis.models import RuleResult, Violation

JSON_SCHEMA_VERSION = 2
SARIF_SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"


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


def _relative_violation_path(
    violation: Violation,
    *,
    project_root: Path | None = None,
) -> Path | None:
    file_value = str(violation.file)
    if file_value in {"", "<unknown>"}:
        return None

    raw_file = Path(file_value)
    file_path = raw_file.resolve() if raw_file.is_absolute() else raw_file
    display_path = file_path

    resolved_root = project_root
    if resolved_root is None:
        try:
            import archetype.dsl.query as query_module

            resolved_root = (
                getattr(query_module, "_project_root", None)
                or getattr(query_module, "_current_root", None)
            )
        except Exception:  # noqa: BLE001
            resolved_root = None

    try:
        if resolved_root is not None:
            display_path = file_path.relative_to(Path(resolved_root).resolve())
        elif file_path.is_absolute():
            display_path = file_path.relative_to(Path.cwd().resolve())
    except Exception:  # noqa: BLE001
        display_path = raw_file

    return display_path


def _violation_location(violation: Violation) -> str | None:
    if violation.line <= 0 or str(violation.file) in {"", "<unknown>"}:
        return None

    display_path = _relative_violation_path(violation)
    if display_path is None:
        return None

    return f"{display_path.as_posix()}:{violation.line}"


def _violation_owners(
    violation: Violation,
    codeowners: Codeowners | None,
    *,
    project_root: Path | None = None,
) -> tuple[str, ...]:
    if codeowners is None or codeowners.is_empty:
        return ()
    relative_path = _relative_violation_path(violation, project_root=project_root)
    if relative_path is None:
        return ()
    return codeowners.owners_for(relative_path.as_posix())


def _format_rule_name(result: RuleResult) -> str:
    if result.since_date:
        return f"{result.name} (since {result.since_date})"
    if result.escalate_date:
        return f"{result.name} (warn until {result.escalate_date})"
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


def _violation_lines(
    result: RuleResult,
    codeowners: Codeowners | None = None,
) -> list[str]:
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
        owners = _violation_owners(violation, codeowners)
        if owners:
            lines.append(f"        owner: {', '.join(owners)}")
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


def format_results(
    results: list[RuleResult],
    quiet: bool = False,
    *,
    codeowners: Codeowners | None = None,
) -> str:
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
                lines.extend(_violation_lines(result, codeowners))
                if result.error is not None:
                    lines.append(f"    - Rule error: {result.error}")
            elif not result.passed:
                lines.extend(_violation_lines(result, codeowners))
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
    if result.policy == "off":
        return "off"
    if result.skipped:
        return "skipped"
    if getattr(result, "timed_out", False):
        return "timeout"
    if result.warned:
        return "warned"
    if result.passed:
        return "passed"
    return "failed"


def _violation_counts(results: list[RuleResult]) -> ViolationCounts:
    total = 0
    suppressed = 0
    for result in results:
        if result.skipped or result.error is not None:
            continue
        total += len(result.violations) + len(result.suppressed_violations)
        suppressed += len(result.suppressed_violations)
    return ViolationCounts(total=total, new=total - suppressed, suppressed=suppressed)


def format_results_json(
    results: list[RuleResult],
    *,
    violation_counts: ViolationCounts | None = None,
    scope: Mapping[str, object] | None = None,
    codeowners: Codeowners | None = None,
) -> Mapping[str, object]:
    """Build a JSON-serializable report for rule execution results."""
    skipped = sum(1 for result in results if result.skipped)
    warned = sum(1 for result in results if result.warned)
    timed_out = sum(1 for result in results if result.timed_out)
    passed = sum(1 for result in results if result.passed and not result.skipped)
    failed = len(results) - passed - warned - skipped - timed_out
    counts = violation_counts or _violation_counts(results)

    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "summary": {
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "skipped": skipped,
            "total": len(results),
        },
        "violations": {
            "total": counts.total,
            "new": counts.new,
            "suppressed": counts.suppressed,
        },
        "rules": [
            {
                "name": result.name,
                "status": _result_status(result),
                "group": result.group,
                "since_date": result.since_date,
                "escalate_date": result.escalate_date,
                "policy": result.policy,
                "violations": [
                    {
                        "module": violation.module,
                        "file": None
                        if str(violation.file) in {"", "<unknown>"}
                        else str(violation.file),
                        "line": violation.line,
                        "target": _extract_target(violation),
                        "message": violation.message,
                        "owners": list(_violation_owners(violation, codeowners)),
                    }
                    for violation in result.violations
                ],
                "diagnostics": list(result.violation_context),
            }
            for result in results
        ],
    }
    if scope is not None:
        payload["scope"] = dict(scope)
    return payload


def _sarif_level(result: RuleResult) -> str:
    if result.policy == "off" or result.skipped:
        return "none"
    if result.warned or result.is_warning or result.policy == "warning":
        return "warning"
    return "error"


def _sarif_rule_properties(result: RuleResult) -> dict[str, object]:
    properties: dict[str, object] = {
        "severity": _sarif_level(result),
        "policy": result.policy,
        "tags": ["architecture"],
    }
    if result.group is not None:
        properties["group"] = result.group
    if result.since_date is not None:
        properties["since_date"] = result.since_date
    if result.escalate_date is not None:
        properties["escalate_date"] = result.escalate_date
    return properties


def _sarif_rule(result: RuleResult) -> dict[str, object]:
    description = f"Archetype architecture rule '{result.name}'."
    if result.group is not None:
        description += f" Group: {result.group}."

    return {
        "id": result.name,
        "name": result.name,
        "shortDescription": {"text": result.name},
        "fullDescription": {"text": description},
        "defaultConfiguration": {"level": _sarif_level(result)},
        "properties": _sarif_rule_properties(result),
    }


def _sarif_artifact_uri(violation: Violation, project_root: Path) -> str | None:
    if str(violation.file) in {"", "<unknown>"}:
        return None

    raw_file = Path(violation.file)
    file_path = raw_file.resolve() if raw_file.is_absolute() else raw_file
    resolved_root = project_root.resolve()

    if file_path.is_absolute():
        try:
            file_path = file_path.relative_to(resolved_root)
        except ValueError:
            pass

    return quote(file_path.as_posix(), safe="/._-~")


def _sarif_location(
    violation: Violation,
    *,
    project_root: Path,
) -> dict[str, object] | None:
    artifact_uri = _sarif_artifact_uri(violation, project_root)
    if artifact_uri is None:
        return None

    physical_location: dict[str, object] = {
        "artifactLocation": {"uri": artifact_uri},
    }
    if violation.line > 0:
        physical_location["region"] = {"startLine": violation.line}

    return {
        "physicalLocation": physical_location,
        "logicalLocations": [
            {
                "fullyQualifiedName": violation.module,
                "kind": "module",
            }
        ],
    }


def _sarif_result_properties(
    result: RuleResult,
    violation: Violation,
    *,
    codeowners: Codeowners | None = None,
    project_root: Path | None = None,
) -> dict[str, object]:
    properties: dict[str, object] = {
        "module": violation.module,
        "target": _extract_target(violation),
    }
    if result.group is not None:
        properties["group"] = result.group
    owners = _violation_owners(violation, codeowners, project_root=project_root)
    if owners:
        properties["owners"] = list(owners)
    return properties


def format_results_sarif(
    results: list[RuleResult],
    *,
    project_root: Path,
    scope: Mapping[str, object] | None = None,
    codeowners: Codeowners | None = None,
) -> Mapping[str, object]:
    """Build a SARIF 2.1.0 report for rule execution results."""
    rule_index_by_id: dict[str, int] = {}
    rules: list[dict[str, object]] = []

    for result in results:
        if result.name in rule_index_by_id:
            continue
        rule_index_by_id[result.name] = len(rules)
        rules.append(_sarif_rule(result))

    sarif_results: list[dict[str, object]] = []
    for result in results:
        if result.skipped or result.passed:
            continue

        for violation in result.violations:
            sarif_result: dict[str, object] = {
                "ruleId": result.name,
                "ruleIndex": rule_index_by_id[result.name],
                "level": _sarif_level(result),
                "kind": "fail",
                "message": {"text": f"{result.name}: {violation.message}"},
                "properties": _sarif_result_properties(
                    result,
                    violation,
                    codeowners=codeowners,
                    project_root=project_root,
                ),
            }
            location = _sarif_location(violation, project_root=project_root)
            if location is not None:
                sarif_result["locations"] = [location]
            sarif_results.append(sarif_result)

    run: dict[str, object] = {
        "tool": {
            "driver": {
                "name": "archetype-py",
                "informationUri": "https://github.com/MossabArektout/archetype-py",
                "rules": rules,
            }
        },
        "results": sarif_results,
    }
    if scope is not None:
        run["properties"] = {"scope": dict(scope)}

    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [run],
    }


def _github_escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _github_escape_property(value: str) -> str:
    escaped = _github_escape_data(value)
    return escaped.replace(":", "%3A").replace(",", "%2C")


def format_github_annotations(
    results: list[RuleResult],
    *,
    project_root: Path,
    codeowners: Codeowners | None = None,
) -> list[str]:
    """Build GitHub Actions workflow annotation commands for rule violations."""
    annotations: list[str] = []
    resolved_root = project_root.resolve()

    for result in results:
        if result.skipped or result.passed:
            continue
        if not result.violations and result.error is None:
            continue

        level = "warning" if result.warned else "error"
        title = _github_escape_property(f"archetype: {result.name}")

        if result.error is not None and not result.violations:
            message = _github_escape_data(f"{result.name}: Rule error: {result.error}")
            annotations.append(f"::{level} title={title}::{message}")
            continue

        for violation in result.violations:
            file_value = str(violation.file)
            file_path = Path(file_value)
            if file_path.is_absolute():
                try:
                    file_path = file_path.resolve().relative_to(resolved_root)
                except ValueError:
                    file_path = file_path.resolve()
            line = violation.line if violation.line > 0 else 1
            file_prop = _github_escape_property(file_path.as_posix())
            owners = _violation_owners(violation, codeowners, project_root=project_root)
            owner_prefix = f"{', '.join(owners)}: " if owners else ""
            message = _github_escape_data(
                f"{owner_prefix}{result.name}: {violation.message}"
            )
            annotations.append(
                f"::{level} file={file_prop},line={line},title={title}::{message}"
            )

    return annotations


def print_results(
    results: list[RuleResult],
    quiet: bool = False,
    *,
    codeowners: Codeowners | None = None,
) -> None:
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
                        owners = _violation_owners(violation, codeowners)
                        if owners:
                            console.print(f"[yellow]        owner: {', '.join(owners)}[/yellow]")
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
                owners = _violation_owners(violation, codeowners)
                if owners:
                    console.print(f"[red]        owner: {', '.join(owners)}[/red]")
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
