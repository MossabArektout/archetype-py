"""Query API for selecting modules and asserting dependency constraints."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from archetype.analysis.imports import build_import_graph
from archetype.analysis.models import Violation

_current_graph: nx.DiGraph | None = None
_current_root: Path | None = None


def _matches_pattern(module_name: str, pattern: str) -> bool:
    return module_name == pattern or module_name.startswith(f"{pattern}.")


def load_project(project_root: Path) -> None:
    """Load a project's import graph into DSL runtime state."""
    global _current_graph, _current_root
    resolved_root = project_root.resolve()
    _current_graph = build_import_graph(resolved_root)
    _current_root = resolved_root


class ImportQuery:
    """Query object for evaluating import constraints on matched modules."""

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        if _current_graph is None:
            raise RuntimeError(
                "No project graph is loaded. Call load_project(path) before using imports()."
            )
        self.graph = _current_graph
        self.matched_nodes = [
            node for node in self.graph.nodes if _matches_pattern(node, pattern)
        ]

    def must_not_import(self, target_pattern: str) -> None:
        """Assert that matched source modules do not import modules matching target."""
        violations: list[Violation] = []

        for source in self.matched_nodes:
            for target in self.graph.successors(source):
                if _matches_pattern(target, target_pattern):
                    violations.append(
                        Violation(
                            module=source,
                            file=Path("<unknown>"),
                            line=0,
                            message=(
                                f"Module '{source}' must not import '{target_pattern}' "
                                f"(found import to '{target}')."
                            ),
                        )
                    )

        if violations:
            exc = AssertionError(
                f"Forbidden imports found: {len(violations)} edge(s) from "
                f"'{self.pattern}' to '{target_pattern}'."
            )
            setattr(exc, "violations", violations)
            raise exc

    def has_no_cycles(self) -> None:
        """Assert that the matched module set has no directed import cycles."""
        subgraph = self.graph.subgraph(self.matched_nodes)
        try:
            cycle_edges = nx.find_cycle(subgraph, orientation="original")
        except nx.NetworkXNoCycle:
            return

        cycle_nodes = [edge[0] for edge in cycle_edges]
        cycle_nodes.append(cycle_edges[0][0])
        chain = " -> ".join(cycle_nodes)
        raise AssertionError(f"Import cycle detected: {chain}")

    def must_only_import_from(self, *allowed_patterns: str) -> None:
        """Assert that matched source modules import only from allowed targets."""
        violations: list[Violation] = []

        for source in self.matched_nodes:
            for target in self.graph.successors(source):
                if not any(
                    _matches_pattern(target, allowed_pattern)
                    for allowed_pattern in allowed_patterns
                ):
                    violations.append(
                        Violation(
                            module=source,
                            file=Path("<unknown>"),
                            line=0,
                            message=(
                                f"Module '{source}' imports '{target}', which is outside "
                                f"the allowed set: {allowed_patterns}."
                            ),
                        )
                    )

        if violations:
            exc = AssertionError(
                f"Disallowed imports found for '{self.pattern}': {len(violations)} edge(s)."
            )
            setattr(exc, "violations", violations)
            raise exc


def imports(pattern: str) -> ImportQuery:
    """Create an import query rooted at the provided module/package pattern."""
    return ImportQuery(pattern)
