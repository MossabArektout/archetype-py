"""Built-in module boundary rule for protecting internal module access."""

from __future__ import annotations

from pathlib import Path

import archetype.dsl.query as query_module
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes, validate_pattern


class ModuleBoundaryRule:
    """Rule object for enforcing module import boundaries."""

    def __init__(self, protected_pattern: str) -> None:
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
        self.graph = graph
        self.protected_pattern = protected_pattern

    def only_imported_within(self, parent_pattern: str) -> None:
        """Assert protected modules are imported only from inside parent_pattern."""
        violations: list[Violation] = []
        all_nodes = list(self.graph.nodes)
        parent_nodes = set(find_matching_nodes(parent_pattern, all_nodes))
        protected_nodes = set(find_matching_nodes(self.protected_pattern, all_nodes))

        for source, target in self.graph.edges:
            source_in_parent = source in parent_nodes
            target_is_protected = target in protected_nodes
            if not source_in_parent and target_is_protected:
                edge_data = self.graph.get_edge_data(source, target, default={})
                file_attr = edge_data.get("file")
                line_attr = edge_data.get("line")
                violation_file = Path(str(file_attr)) if file_attr else Path("<unknown>")
                try:
                    violation_line = int(line_attr or 0)
                except (TypeError, ValueError):
                    violation_line = 0
                violations.append(
                    Violation(
                        module=source,
                        file=violation_file,
                        line=violation_line,
                        message=(
                            f"Boundary violation: outside module '{source}' imports protected "
                            f"module '{target}' (allowed only within '{parent_pattern}')."
                        ),
                    )
                )

        if violations:
            exc = AssertionError(
                f"Module boundary violated by {len(violations)} import(s) into '{self.protected_pattern}'."
            )
            setattr(exc, "violations", violations)
            raise exc


def module(protected_pattern: str) -> ModuleBoundaryRule:
    """Create a module boundary rule for a protected module pattern."""
    validate_pattern(protected_pattern)
    return ModuleBoundaryRule(protected_pattern)
