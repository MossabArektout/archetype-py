"""Built-in layering rule for enforcing top-down architectural dependencies."""

from __future__ import annotations

import archetype.dsl.query as query_module
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes


class LayerOrderRule:
    """Rule object that validates import directions across declared layers."""

    def __init__(self, layer_patterns: list[str]) -> None:
        self.layer_patterns = layer_patterns

    def _require_graph(self):
        graph = query_module._current_graph
        if graph is None:
            raise RuntimeError(query_module._not_loaded_project_message())
        return graph

    def are_ordered(self) -> None:
        """Assert that lower layers do not import upper layers."""
        graph = self._require_graph()

        violations: list[Violation] = []
        all_nodes = list(graph.nodes)
        for upper_index, upper_pattern in enumerate(self.layer_patterns):
            for lower_pattern in self.layer_patterns[upper_index + 1 :]:
                lower_nodes = find_matching_nodes(lower_pattern, all_nodes)
                upper_nodes = set(find_matching_nodes(upper_pattern, all_nodes))
                if not lower_nodes:
                    query_module._record_unmatched_pattern(
                        lower_pattern,
                        all_nodes,
                        role="Layer",
                    )
                if not upper_nodes:
                    query_module._record_unmatched_pattern(
                        upper_pattern,
                        all_nodes,
                        role="Layer",
                    )

                for source in lower_nodes:
                    for target in graph.successors(source):
                        if target in upper_nodes:
                            violation_file, violation_line = (
                                query_module._edge_violation_location(
                                    graph,
                                    source,
                                    target,
                                )
                            )
                            violations.append(
                                Violation(
                                    module=source,
                                    file=violation_file,
                                    line=violation_line,
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

    def are_adjacent(self) -> None:
        """Assert that cross-layer imports only reach the immediately next
        layer -- no upward imports, and no skipping over a layer.

        `are_ordered()` allows a top layer to reach straight past a middle
        layer into the bottom one; `are_adjacent()` additionally requires
        every cross-layer import to route through the layer directly below
        it, which is what "layered architecture" usually means in review.
        It is a strict superset of `are_ordered()` -- call one or the
        other, not both, to avoid the same edge being reported twice.
        """
        graph = self._require_graph()
        all_nodes = list(graph.nodes)

        layer_node_sets: list[set[str]] = []
        for pattern in self.layer_patterns:
            nodes = set(find_matching_nodes(pattern, all_nodes))
            if not nodes:
                query_module._record_unmatched_pattern(pattern, all_nodes, role="Layer")
            layer_node_sets.append(nodes)

        # A node's layer index is the first pattern it matches. Layers are
        # expected not to overlap; if they do, the earliest-listed layer
        # wins, matching how are_ordered() treats each pair independently.
        node_layer_index: dict[str, int] = {}
        for index, nodes in enumerate(layer_node_sets):
            for node in nodes:
                node_layer_index.setdefault(node, index)

        violations: list[Violation] = []
        for source, target in graph.edges:
            source_index = node_layer_index.get(source)
            target_index = node_layer_index.get(target)
            if source_index is None or target_index is None:
                continue  # not part of the declared layering
            distance = target_index - source_index
            if distance in (0, 1):
                continue  # same layer, or the adjacent layer below: fine

            violation_file, violation_line = query_module._edge_violation_location(
                graph, source, target
            )
            source_layer = self.layer_patterns[source_index]
            target_layer = self.layer_patterns[target_index]
            if distance < 0:
                message = (
                    f"Layering violation (upward dependency): '{source}' in layer "
                    f"'{source_layer}' imports '{target}' in layer '{target_layer}'."
                )
            else:
                skipped = self.layer_patterns[source_index + 1 : target_index]
                message = (
                    f"Layering violation (skipped layer): '{source}' in layer "
                    f"'{source_layer}' imports '{target}' in layer '{target_layer}', "
                    f"skipping {skipped!r}. Imports must route through the adjacent "
                    f"layer."
                )
            violations.append(
                Violation(module=source, file=violation_file, line=violation_line, message=message)
            )

        if violations:
            exc = AssertionError(
                f"Layer adjacency violated by {len(violations)} import(s)."
            )
            setattr(exc, "violations", violations)
            raise exc


def layers(layer_patterns: list[str]) -> LayerOrderRule:
    """Create a layer-order rule for modules listed top-to-bottom."""
    return LayerOrderRule(layer_patterns)
