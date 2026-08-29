"""Built-in rule for enforcing a package's declared public API as its import boundary."""

from __future__ import annotations

import ast
from pathlib import Path

import archetype.dsl.query as query_module
from archetype.analysis.ast_utils import read_source
from archetype.analysis.imports import discover_package_roots
from archetype.analysis.models import Violation
from archetype.analysis.pattern import find_matching_nodes, validate_pattern

_INIT_FILENAMES = ("__init__.py", "init.py")


def _implied_module_names(all_nodes: list[str]) -> set[str]:
    """Return every graph node plus its ancestor package names.

    A package without an __init__.py/init.py never gets a graph node for
    itself -- only its submodules do (e.g. "pkg.widget" exists but "pkg"
    does not). Deriving package roots from ancestor prefixes, not just
    literal nodes, lets that package still be identified as "pkg" so
    _check_package() can report the missing __init__.py clearly, instead of
    silently matching one of its submodules instead.
    """
    known: set[str] = set(all_nodes)
    for node in all_nodes:
        parts = node.split(".")
        for index in range(1, len(parts)):
            known.add(".".join(parts[:index]))
    return known


def _find_package_roots(pattern: str, all_nodes: list[str]) -> list[str]:
    """Return the topmost names matching pattern, excluding matched descendants.

    matches_pattern() treats a pattern like "myapp.billing" as matching both
    the package itself and every module beneath it, so a plain
    find_matching_nodes() call returns the whole subtree. Public API
    enforcement needs just the package root(s) -- the names whose parent
    did not also match.
    """
    candidates = list(_implied_module_names(all_nodes))
    matched = set(find_matching_nodes(pattern, candidates))
    roots = [
        node
        for node in matched
        if "." not in node or node.rsplit(".", 1)[0] not in matched
    ]
    return sorted(roots)


def _find_init_file(package: str) -> Path | None:
    for package_root in discover_package_roots(
        query_module._current_root,
        exclude_patterns=query_module._exclude_patterns,
    ):
        package_dir = package_root.joinpath(*package.split("."))
        for filename in _INIT_FILENAMES:
            candidate = package_dir / filename
            if candidate.is_file():
                return candidate
    return None


def _read_declared_all(init_file: Path) -> list[str] | None:
    """Return the string literals assigned to __all__, or None if __all__
    isn't declared as a literal list/tuple of string constants."""
    tree = ast.parse(read_source(init_file), filename=str(init_file))

    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue

        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
            continue

        if not isinstance(value, (ast.List, ast.Tuple)):
            return None

        names: list[str] = []
        for element in value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                return None
            names.append(element.value)
        return names

    return None


class PublicApiRule:
    """Rule object for enforcing a package's declared public API boundary."""

    def __init__(self, package_pattern: str) -> None:
        graph = query_module._current_graph
        if graph is None:
            raise RuntimeError(query_module._not_loaded_project_message())
        self.graph = graph
        self.package_pattern = package_pattern

    def enforce(self) -> None:
        """Assert outside modules only reach submodules declared in __all__."""
        all_nodes = list(self.graph.nodes)
        package_roots = _find_package_roots(self.package_pattern, all_nodes)
        if not package_roots:
            query_module._record_unmatched_pattern(self.package_pattern, all_nodes, role="Package")
            return

        violations: list[Violation] = []
        for package in package_roots:
            # A node with no submodules in the graph is a plain module, not a
            # package -- there is no interface boundary to enforce, and no
            # __init__.py is expected. This matters for wildcard patterns
            # (e.g. public_api("*")) that also match such leaf modules.
            if not any(node.startswith(f"{package}.") for node in all_nodes):
                continue
            violations.extend(self._check_package(package))

        if violations:
            exc = AssertionError(
                f"Public API violated by {len(violations)} import(s) reaching past "
                f"the declared interface of '{self.package_pattern}'."
            )
            setattr(exc, "violations", violations)
            raise exc

    def _check_package(self, package: str) -> list[Violation]:
        init_file = _find_init_file(package)
        if init_file is None:
            raise RuntimeError(
                f"public_api('{self.package_pattern}') could not find an "
                f"__init__.py for package '{package}'.\n\n"
                "Public API enforcement reads __all__ from a package's "
                "__init__.py. Namespace packages (PEP 420, no __init__.py) "
                "are not supported."
            )

        declared = _read_declared_all(init_file)
        if declared is None:
            raise RuntimeError(
                f"public_api('{self.package_pattern}') requires package "
                f"'{package}' to declare __all__ as a literal list or tuple "
                f"of strings in {init_file}.\n\n"
                'Add, for example, __all__ = ["PublicThing"] to declare what '
                "outside code may depend on."
            )

        public_children = set(declared)
        prefix = f"{package}."
        violations: list[Violation] = []

        for source, target in self.graph.edges:
            if source == package or source.startswith(prefix):
                continue  # traffic within the package itself, including re-exports
            if not target.startswith(prefix):
                continue  # importing the package root, or an unrelated module

            child = target[len(prefix):].split(".", 1)[0]
            if child in public_children:
                continue  # this submodule subtree is explicitly public

            violation_file, violation_line = query_module._edge_violation_location(
                self.graph, source, target
            )
            violations.append(
                Violation(
                    module=source,
                    file=violation_file,
                    line=violation_line,
                    message=(
                        f"Public API violation: '{source}' imports '{target}' "
                        f"directly, bypassing the declared public interface of "
                        f"'{package}' (__all__ = {sorted(public_children)!r})."
                    ),
                )
            )

        return violations


def public_api(package_pattern: str) -> PublicApiRule:
    """Create a rule enforcing a package's declared __all__ as its import boundary."""
    validate_pattern(package_pattern)
    return PublicApiRule(package_pattern)
