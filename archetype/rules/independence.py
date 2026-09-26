"""Built-in rule for keeping sibling packages from importing one another."""

from __future__ import annotations

import archetype.dsl.query as query_module
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes, validate_pattern


def independent(module_patterns: list[str]) -> None:
    """Assert that no module in one pattern imports a module in another.

    Typical use is a set of feature packages that should only meet through
    shared lower layers, never by importing each other directly:

        independent(["myapp.billing", "myapp.orders", "myapp.shipping"])

    Imports within a single pattern are allowed. If patterns overlap, a
    module belongs to the first pattern it matches.
    """
    graph = query_module._current_graph
    if graph is None:
        raise RuntimeError(query_module._not_loaded_project_message())
    if len(module_patterns) < 2:
        raise ValueError("independent() needs at least two module patterns.")
    for pattern in module_patterns:
        validate_pattern(pattern)

    all_nodes = list(graph.nodes)
    node_owner: dict[str, str] = {}
    for pattern in module_patterns:
        matched = find_matching_nodes(pattern, all_nodes)
        if not matched:
            query_module._record_unmatched_pattern(pattern, all_nodes, role="Independent")
        for node in matched:
            node_owner.setdefault(node, pattern)

    violations: list[Violation] = []
    for source, target in graph.edges:
        source_owner = node_owner.get(source)
        target_owner = node_owner.get(target)
        if source_owner is None or target_owner is None or source_owner == target_owner:
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
                    f"Independence violation: '{source}' in '{source_owner}' imports "
                    f"'{target}' in '{target_owner}'."
                ),
            )
        )

    if violations:
        exc = AssertionError(
            f"Independent modules import each other in {len(violations)} place(s)."
        )
        setattr(exc, "violations", violations)
        raise exc
