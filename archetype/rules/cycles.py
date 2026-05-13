"""Built-in rule for detecting circular imports in the project graph."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

import archetype.dsl.query as query_module
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes


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
        target_graph = graph.subgraph(matched_nodes).copy()

    raw_cycles = list(nx.simple_cycles(target_graph))
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
        violations.append(
            Violation(
                module=normalized[0],
                file=Path("<unknown>"),
                line=0,
                message=chain,
            )
        )

    exc = AssertionError(f"Detected {len(violations)} circular import cycle(s).")
    setattr(exc, "violations", violations)
    raise exc
