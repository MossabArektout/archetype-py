"""Built-in naming convention rules based on static AST inspection."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import archetype.dsl.query as query_module
from archetype.analysis.ast_utils import (
    get_class_names,
    get_top_level_function_names,
)
from archetype.analysis.imports import path_to_module
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes


def _matched_python_files(module_pattern: str) -> list[Path]:
    root = query_module._current_root
    graph = query_module._current_graph
    if root is None or graph is None:
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

    matched_modules = set(find_matching_nodes(module_pattern, list(graph.nodes)))
    matched: list[Path] = []
    for file_path in sorted(root.rglob("*.py")):
        module_name = path_to_module(file_path, root)
        if module_name and module_name in matched_modules:
            matched.append(file_path)
    return matched


class ClassesInQuery:
    """Naming query for class definitions in matched modules."""

    def __init__(self, module_pattern: str) -> None:
        self.module_pattern = module_pattern
        self.files = _matched_python_files(module_pattern)

    def all_match(self, name_pattern: str) -> None:
        """Assert all class names in matched files satisfy a regex."""
        violations: list[Violation] = []
        regex = re.compile(name_pattern)

        for file_path in self.files:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
            for class_name in get_class_names(tree):
                if not regex.fullmatch(class_name):
                    violations.append(
                        Violation(
                            module=self.module_pattern,
                            file=file_path,
                            line=0,
                            message=(
                                f"Class '{class_name}' in '{file_path}' does not match "
                                f"required pattern '{name_pattern}'."
                            ),
                        )
                    )

        if violations:
            exc = AssertionError(
                f"Naming rule failed: {len(violations)} class name violation(s)."
            )
            setattr(exc, "violations", violations)
            raise exc


class FunctionsInQuery:
    """Naming query for required module-level function presence."""

    def __init__(self, module_pattern: str) -> None:
        self.module_pattern = module_pattern
        self.files = _matched_python_files(module_pattern)

    def must_include(self, function_name: str) -> None:
        """Assert each matched file defines the required top-level function."""
        violations: list[Violation] = []

        for file_path in self.files:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
            top_level_functions = get_top_level_function_names(tree)
            if function_name not in top_level_functions:
                violations.append(
                    Violation(
                        module=self.module_pattern,
                        file=file_path,
                        line=0,
                        message=(
                            f"File '{file_path}' is missing required top-level function "
                            f"'{function_name}'."
                        ),
                    )
                )

        if violations:
            exc = AssertionError(
                f"Naming rule failed: required function '{function_name}' missing in "
                f"{len(violations)} file(s)."
            )
            setattr(exc, "violations", violations)
            raise exc


def classes_in(module_pattern: str) -> ClassesInQuery:
    """Create a class-naming query for modules matching module_pattern."""
    return ClassesInQuery(module_pattern)


def functions_in(module_pattern: str) -> FunctionsInQuery:
    """Create a function-presence query for modules matching module_pattern."""
    return FunctionsInQuery(module_pattern)
