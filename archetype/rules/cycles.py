"""Built-in rule for detecting circular imports in the project graph."""

from __future__ import annotations

from itertools import islice

import networkx as nx

import archetype.dsl.query as query_module
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes

# The number of distinct cycles grows exponentially in a tangled graph (a
# 100-module package can have millions), so enumeration stops here instead of
# hanging. Projects below the cap get exactly the full list, as before.
MAX_REPORTED_CYCLES = 1000


def _normalize_cycle(cycle: list[str]) -> tuple[str, ...]:
    """Normalize a cycle by rotating to its alphabetically first module."""
    if not cycle:
        return ()
    min_module = min(cycle)
    min_index = cycle.index(min_module)
    rotated = cycle[min_index:] + cycle[:min_index]
    return tuple(rotated)


def no_cycles(module_pattern: str | None = None) -> None:
    """Assert that no import cycles exist globally or inside a module pattern."""
    graph = query_module._current_graph
    if graph is None:
        raise RuntimeError(
            "Archetype has not loaded a project yet.\n\n"
            "This usually means one of the following:\n"
            "  - You are calling imports() or module() outside of a @rule function\n"
            "  - You are running architecture.py directly with python architecture.py\n"
            "    instead of through archetype check or pytest\n\n"
            "To fix this, run your rules using one of these commands:\n"
            "  archetype check .\n"
            "  pytest\n\n"
            "If you need to load a project programmatically use:\n"
            "  from archetype import load_project\n"
            "  from pathlib import Path\n"
            "  load_project(Path(\".\"))"
        )

    if module_pattern is None:
        target_graph = graph
    else:
        matched_nodes = find_matching_nodes(module_pattern, list(graph.nodes))
        if not matched_nodes:
            query_module._record_unmatched_pattern(
                module_pattern,
                list(graph.nodes),
                role="Cycle",
            )
        target_graph = graph.subgraph(matched_nodes).copy()

    raw_cycles = list(islice(nx.simple_cycles(target_graph), MAX_REPORTED_CYCLES + 1))
    truncated = len(raw_cycles) > MAX_REPORTED_CYCLES
    raw_cycles = raw_cycles[:MAX_REPORTED_CYCLES]
    if not raw_cycles:
        return

    seen: set[tuple[str, ...]] = set()
    violations: list[Violation] = []

    for cycle in raw_cycles:
        normalized = _normalize_cycle(cycle)
        if normalized in seen:
            continue
        seen.add(normalized)

        chain_nodes = list(normalized) + [normalized[0]]
        chain = " imports ".join(chain_nodes)
        violation_file, violation_line = query_module._edge_violation_location(
            graph,
            chain_nodes[0],
            chain_nodes[1],
        )
        violations.append(
            Violation(
                module=normalized[0],
                file=violation_file,
                line=violation_line,
                message=chain,
            )
        )

    if truncated:
        exc = AssertionError(
            f"Detected more than {MAX_REPORTED_CYCLES} circular import cycles; "
            f"showing the first {len(violations)}."
        )
        setattr(
            exc,
            "violation_context",
            [
                f"Stopped after {MAX_REPORTED_CYCLES} cycles: this graph has too many to "
                "list. Breaking a few of the modules that appear most often usually "
                "removes most of them."
            ],
        )
    else:
        exc = AssertionError(f"Detected {len(violations)} circular import cycle(s).")
    setattr(exc, "violations", violations)
    raise exc
