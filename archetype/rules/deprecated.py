"""Built-in rule for flagging imports of a deprecated module or package."""

from __future__ import annotations

from datetime import date

import archetype.dsl.query as query_module
from archetype.analysis.git_utils import parse_date_string
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes, validate_pattern


def _today() -> date:
    return date.today()


def _sunset_status(sunset: str | None) -> str:
    if sunset is None:
        return "No removal date is set."
    deadline = parse_date_string(sunset)
    days = (deadline - _today()).days
    if days > 0:
        return f"Scheduled for removal on {sunset} ({days} day(s) remaining)."
    if days == 0:
        return f"Scheduled for removal on {sunset} (today)."
    return f"Was scheduled for removal on {sunset} ({-days} day(s) overdue)."


def deprecated(
    pattern: str,
    *,
    sunset: str | None = None,
    reason: str | None = None,
) -> None:
    """Assert that a deprecated module or package is not imported from
    outside itself.

    Every import edge that reaches a module matching `pattern`, from a
    source that does not itself match `pattern`, is reported as a
    violation -- imports from one part of the deprecated subtree into
    another (for example its own `__init__.py` importing a sibling
    submodule) are not flagged. Each violation message names the sunset
    date and how many days remain or have passed, and the reason when
    given.

    Unlike @escalate, deprecated() does not decide pass/fail based on the
    date by itself -- it always reports a violation when the module is
    imported, keeping severity policy in one place. Combine it with
    @escalate to make it warn now and start failing exactly on `sunset`:

        @rule("legacy-billing-removed")
        @escalate(warn_until="2026-11-01")
        def legacy_billing_removed() -> None:
            deprecated(
                "myapp.legacy_billing",
                sunset="2026-11-01",
                reason="replaced by myapp.billing_v2",
            )

    `sunset`, if given, must be an ISO `YYYY-MM-DD` date string.
    """
    validate_pattern(pattern)
    if sunset is not None:
        parse_date_string(sunset)

    graph = query_module._current_graph
    if graph is None:
        raise RuntimeError(query_module._not_loaded_project_message())

    all_nodes = list(graph.nodes)
    matched_nodes = set(find_matching_nodes(pattern, all_nodes))
    if not matched_nodes:
        query_module._record_unmatched_pattern(pattern, all_nodes, role="Deprecated")
        return

    status = _sunset_status(sunset)
    reason_suffix = f" ({reason})" if reason else ""
    violations: list[Violation] = []

    for source, target in graph.edges:
        if source in matched_nodes or target not in matched_nodes:
            continue

        violation_file, violation_line = query_module._edge_violation_location(
            graph, source, target
        )
        violations.append(
            Violation(
                module=source,
                file=violation_file,
                line=violation_line,
                message=(
                    f"Deprecated module import: '{source}' imports '{target}', "
                    f"which is deprecated{reason_suffix}. {status}"
                ),
            )
        )

    if violations:
        exc = AssertionError(
            f"Deprecated module '{pattern}' imported by {len(violations)} module(s)."
        )
        setattr(exc, "violations", violations)
        raise exc
