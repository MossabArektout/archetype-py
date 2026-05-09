"""Built-in module boundary rule for protecting internal module access."""

from __future__ import annotations

from pathlib import Path

import archetype.dsl.query as query_module
from archetype.analysis.models import Violation


def _matches_pattern(module_name: str, pattern: str) -> bool:
    return module_name == pattern or module_name.startswith(f"{pattern}.")


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

        for source, target in self.graph.edges:
            source_in_parent = _matches_pattern(source, parent_pattern)
            target_is_protected = _matches_pattern(target, self.protected_pattern)
            if not source_in_parent and target_is_protected:
                violations.append(
                    Violation(
                        module=source,
                        file=Path("<unknown>"),
                        line=0,
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
    return ModuleBoundaryRule(protected_pattern)
