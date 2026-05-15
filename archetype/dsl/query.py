"""Query API for selecting modules and asserting dependency constraints."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from archetype.analysis.imports import build_import_graph
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes, validate_pattern

_current_graph: nx.DiGraph | None = None
_current_root: Path | None = None

def load_project(project_root: Path, src_root: Path | None = None) -> None:
    """Load a project's import graph into DSL runtime state."""
    global _current_graph, _current_root
    resolved_project_root = project_root.resolve()
    analysis_root = src_root.resolve() if src_root is not None else resolved_project_root
    _current_graph = build_import_graph(analysis_root)
    _current_root = analysis_root


class ImportQuery:
    """Query object for evaluating import constraints on matched modules."""

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        if _current_graph is None:
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
        self.graph = _current_graph
        self.matched_nodes = find_matching_nodes(pattern, list(self.graph.nodes))

    def must_not_import(self, target_pattern: str) -> None:
        """Assert that matched source modules do not import modules matching target."""
        violations: list[Violation] = []
        target_nodes = set(find_matching_nodes(target_pattern, list(self.graph.nodes)))

        for source in self.matched_nodes:
            for target in self.graph.successors(source):
                if target in target_nodes:
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
        allowed_nodes: set[str] = set()
        graph_nodes = list(self.graph.nodes)
        for allowed_pattern in allowed_patterns:
            allowed_nodes.update(find_matching_nodes(allowed_pattern, graph_nodes))

        for source in self.matched_nodes:
            for target in self.graph.successors(source):
                if target not in allowed_nodes:
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
    validate_pattern(pattern)
    return ImportQuery(pattern)
