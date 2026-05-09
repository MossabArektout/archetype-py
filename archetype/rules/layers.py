"""Built-in layering rule for enforcing top-down architectural dependencies."""

from __future__ import annotations

from pathlib import Path

import archetype.dsl.query as query_module
from archetype.analysis.models import Violation


def _matches_pattern(module_name: str, pattern: str) -> bool:
    return module_name == pattern or module_name.startswith(f"{pattern}.")


class LayerOrderRule:
    """Rule object that validates import directions across declared layers."""

    def __init__(self, layer_patterns: list[str]) -> None:
        self.layer_patterns = layer_patterns

    def are_ordered(self) -> None:
        """Assert that lower layers do not import upper layers."""
        graph = query_module._current_graph
        if graph is None:
            raise RuntimeError(
                "No project graph is loaded. Call load_project(path) before evaluating layers()."
            )

        violations: list[Violation] = []
        for upper_index, upper_pattern in enumerate(self.layer_patterns):
            for lower_pattern in self.layer_patterns[upper_index + 1 :]:
                lower_nodes = [
                    node
                    for node in graph.nodes
                    if _matches_pattern(node, lower_pattern)
                ]
                upper_nodes = {
                    node
                    for node in graph.nodes
                    if _matches_pattern(node, upper_pattern)
                }

                for source in lower_nodes:
                    for target in graph.successors(source):
                        if target in upper_nodes:
                            violations.append(
                                Violation(
                                    module=source,
                                    file=Path("<unknown>"),
                                    line=0,
                                    message=(
                                        f"Layering violation (upward dependency): lower layer "
                                        f"'{lower_pattern}' module '{source}' imports upper layer "
                                        f"'{upper_pattern}' module '{target}'."
                                    ),
                                )
                            )

        if violations:
            exc = AssertionError(
                f"Layer ordering violated by {len(violations)} upward import(s)."
            )
            setattr(exc, "violations", violations)
            raise exc


def layers(layer_patterns: list[str]) -> LayerOrderRule:
    """Create a layer-order rule for modules listed top-to-bottom."""
    return LayerOrderRule(layer_patterns)
