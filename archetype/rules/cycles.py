"""Built-in rule for detecting circular imports in the project graph."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

import archetype.dsl.query as query_module
from archetype.analysis.models import Violation


def _matches_pattern(module_name: str, pattern: str) -> bool:
    return module_name == pattern or module_name.startswith(f"{pattern}.")


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
            "No project graph is loaded. Call load_project(path) before evaluating no_cycles()."
        )

    if module_pattern is None:
        target_graph = graph
    else:
        matched_nodes = [
            node for node in graph.nodes if _matches_pattern(node, module_pattern)
        ]
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
