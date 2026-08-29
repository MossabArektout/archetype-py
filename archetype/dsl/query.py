"""Query API for selecting modules and asserting dependency constraints."""

from __future__ import annotations

import threading
from pathlib import Path

import networkx as nx

from archetype.analysis.cache import (
    compute_file_signatures,
    ensure_gitignore_entry,
    is_cache_valid,
    load_cached_graph,
    save_cached_graph,
)
from archetype.analysis.imports import build_import_graph, resolve_module_file
from archetype.analysis.models import Violation
from archetype.analysis.path_filters import normalize_exclude_patterns
from archetype.analysis.pattern import find_matching_nodes, suggest_patterns, validate_pattern

_current_graph: nx.DiGraph | None = None
_current_root: Path | None = None
_project_root: Path | None = None
_exclude_patterns: tuple[str, ...] = ()
_pattern_state = threading.local()


def _not_loaded_project_message() -> str:
    return (
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


def clear_pattern_diagnostics() -> None:
    """Clear pattern diagnostics recorded while evaluating one rule."""
    setattr(_pattern_state, "diagnostics", [])


def get_pattern_diagnostics() -> list[str]:
    """Return pattern diagnostics recorded while evaluating one rule."""
    return list(getattr(_pattern_state, "diagnostics", []))


def _record_unmatched_pattern(
    pattern: str,
    all_nodes: list[str],
    *,
    role: str,
) -> None:
    suggestions = suggest_patterns(pattern, all_nodes)
    message = f"{role} pattern '{pattern}' matched 0 modules."
    if suggestions:
        message += f" Did you mean: {', '.join(suggestions)}?"
    diagnostics = getattr(_pattern_state, "diagnostics", [])
    if message not in diagnostics:
        diagnostics.append(message)
        setattr(_pattern_state, "diagnostics", diagnostics)


def load_project(
    project_root: Path,
    src_root: Path | None = None,
    no_cache: bool = False,
    exclude_patterns: tuple[str, ...] | list[str] | None = None,
) -> None:
    """Load a project's import graph into DSL runtime state."""
    global _current_graph, _current_root, _project_root, _exclude_patterns
    resolved_project_root = project_root.resolve()
    analysis_root = src_root.resolve() if src_root is not None else resolved_project_root
    normalized_excludes = normalize_exclude_patterns(exclude_patterns)

    if no_cache:
        graph = build_import_graph(analysis_root, exclude_patterns=normalized_excludes)
    else:
        current_signatures = compute_file_signatures(
            resolved_project_root,
            exclude_patterns=normalized_excludes,
        )
        cached_graph, cached_signatures = load_cached_graph(resolved_project_root)
        if is_cache_valid(cached_signatures, current_signatures):
            graph = cached_graph
        else:
            graph = build_import_graph(analysis_root, exclude_patterns=normalized_excludes)
            save_cached_graph(resolved_project_root, graph, current_signatures)
            ensure_gitignore_entry(resolved_project_root)

    _current_graph = graph
    _current_root = analysis_root
    _project_root = resolved_project_root
    _exclude_patterns = normalized_excludes


def _edge_violation_location(
    graph: nx.DiGraph, source: str, target: str
) -> tuple[Path, int]:
    edge_data = graph.get_edge_data(source, target, default={})
    file_attr = edge_data.get("file")
    line_attr = edge_data.get("line")

    if file_attr:
        file_path = Path(str(file_attr))
    else:
        file_path = Path("<unknown>")

    try:
        line = int(line_attr or 0)
    except (TypeError, ValueError):
        line = 0

    return file_path, line


def _module_violation_location(module_name: str) -> tuple[Path, int]:
    """Resolve a module-level (not edge-level) violation to its defining file.

    Used by checks like fan_in_at_most()/fan_out_at_most() that flag a
    module for its overall shape rather than one specific import
    statement, so there is no single edge to point at. Line 0 signals a
    whole-file violation, the same convention _edge_violation_location()
    falls back to when an edge has no recorded line.
    """
    if _current_root is not None:
        file_path = resolve_module_file(module_name, _current_root, exclude_patterns=_exclude_patterns)
        if file_path is not None:
            return file_path, 0
    return Path("<unknown>"), 0


def _format_module_list(names: list[str], *, limit: int = 5) -> str:
    """Render a bounded, human-readable list of module names for messages."""
    ordered = sorted(names)
    if len(ordered) <= limit:
        return ", ".join(ordered)
    shown = ", ".join(ordered[:limit])
    return f"{shown}, and {len(ordered) - limit} more"


class ImportQuery:
    """Query object for evaluating import constraints on matched modules."""

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        if _current_graph is None:
            raise RuntimeError(_not_loaded_project_message())
        self.graph = _current_graph
        graph_nodes = list(self.graph.nodes)
        self.matched_nodes = find_matching_nodes(pattern, graph_nodes)
        if not self.matched_nodes:
            _record_unmatched_pattern(pattern, graph_nodes, role="Source")

    def must_not_import(self, target_pattern: str) -> None:
        """Assert that matched source modules do not import modules matching target."""
        violations: list[Violation] = []
        graph_nodes = list(self.graph.nodes)
        target_nodes = set(find_matching_nodes(target_pattern, graph_nodes))
        if not target_nodes:
            _record_unmatched_pattern(target_pattern, graph_nodes, role="Target")

        for source in self.matched_nodes:
            for target in self.graph.successors(source):
                if target in target_nodes:
                    violation_file, violation_line = _edge_violation_location(
                        self.graph, source, target
                    )
                    violations.append(
                        Violation(
                            module=source,
                            file=violation_file,
                            line=violation_line,
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

    def must_not_depend_on(self, target_pattern: str) -> None:
        """Assert that matched source modules do not transitively depend on target.

        Example:
            # Fails only on direct edge source -> target.
            imports("myapp.api").must_not_import("myapp.db")

            # Fails when target is reachable through any dependency chain.
            imports("myapp.api").must_not_depend_on("myapp.db")
        """
        if _current_graph is None or self.graph is None:
            raise RuntimeError(_not_loaded_project_message())

        violations: list[Violation] = []
        graph_nodes = list(self.graph.nodes)
        target_nodes = find_matching_nodes(target_pattern, graph_nodes)
        if not target_nodes:
            _record_unmatched_pattern(target_pattern, graph_nodes, role="Target")

        for source in self.matched_nodes:
            reachable = nx.descendants(self.graph, source)
            for target in target_nodes:
                if target not in reachable:
                    continue
                path = nx.shortest_path(self.graph, source=source, target=target)
                violation_file, violation_line = _edge_violation_location(
                    self.graph,
                    path[0],
                    path[1],
                )
                violations.append(
                    Violation(
                        module=source,
                        file=violation_file,
                        line=violation_line,
                        message=" → ".join(path),
                    )
                )

        if violations:
            exc = AssertionError(
                f"Forbidden transitive dependencies found: {len(violations)} path(s) from "
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
        violation_file, violation_line = _edge_violation_location(
            self.graph,
            cycle_edges[0][0],
            cycle_edges[0][1],
        )
        exc = AssertionError(f"Import cycle detected: {chain}")
        setattr(
            exc,
            "violations",
            [
                Violation(
                    module=cycle_edges[0][0],
                    file=violation_file,
                    line=violation_line,
                    message=chain,
                )
            ],
        )
        raise exc

    def must_only_import_from(self, *allowed_patterns: str) -> None:
        """Assert that matched source modules import only from allowed targets."""
        violations: list[Violation] = []
        allowed_nodes: set[str] = set()
        graph_nodes = list(self.graph.nodes)
        for allowed_pattern in allowed_patterns:
            matches = find_matching_nodes(allowed_pattern, graph_nodes)
            if not matches:
                _record_unmatched_pattern(allowed_pattern, graph_nodes, role="Allowed")
            allowed_nodes.update(matches)

        for source in self.matched_nodes:
            for target in self.graph.successors(source):
                if target not in allowed_nodes:
                    violation_file, violation_line = _edge_violation_location(
                        self.graph, source, target
                    )
                    violations.append(
                        Violation(
                            module=source,
                            file=violation_file,
                            line=violation_line,
                            message=f"Module '{source}' imports disallowed module '{target}'.",
                        )
                    )

        if violations:
            exc = AssertionError(
                f"Disallowed imports found for '{self.pattern}': {len(violations)} edge(s)."
            )
            allowed_summary = ", ".join(allowed_patterns) if allowed_patterns else "<none>"
            setattr(
                exc,
                "violation_context",
                [f"Allowed imports for '{self.pattern}': {allowed_summary}."],
            )
            setattr(exc, "violations", violations)
            raise exc

    def max_depth(self, max_segments: int) -> None:
        """Assert that matched source modules import nothing nested deeper
        than max_segments dotted segments.

        Example:
            # Forbid reaching more than 3 packages deep from anywhere.
            imports("**").max_depth(3)

        A target's depth is its dotted-name segment count, so
        "myapp.billing" is depth 2 and "myapp.billing.internal.db" is
        depth 4. Use public_api(...) instead when the allowed depth
        should vary per package based on a declared __all__.
        """
        if max_segments < 1:
            raise ValueError("max_depth() requires max_segments >= 1.")

        violations: list[Violation] = []
        for source in self.matched_nodes:
            for target in self.graph.successors(source):
                depth = target.count(".") + 1
                if depth <= max_segments:
                    continue
                violation_file, violation_line = _edge_violation_location(
                    self.graph, source, target
                )
                violations.append(
                    Violation(
                        module=source,
                        file=violation_file,
                        line=violation_line,
                        message=(
                            f"Import depth violation: '{source}' imports '{target}' "
                            f"({depth} segments deep), exceeding the maximum of "
                            f"{max_segments}."
                        ),
                    )
                )

        if violations:
            exc = AssertionError(
                f"Import depth exceeded by {len(violations)} import(s) from '{self.pattern}'."
            )
            setattr(exc, "violations", violations)
            raise exc

    def fan_in_at_most(self, max_count: int) -> None:
        """Assert that no matched module is imported by more than max_count
        other modules (its fan-in).

        A high fan-in on a low-level utility is normal; a high fan-in on a
        module that is supposed to be an implementation detail is often a
        sign it has quietly become a hidden hub everything depends on.
        """
        if max_count < 0:
            raise ValueError("fan_in_at_most() requires max_count >= 0.")

        violations: list[Violation] = []
        for node in self.matched_nodes:
            importers = list(self.graph.predecessors(node))
            count = len(importers)
            if count <= max_count:
                continue
            violation_file, violation_line = _module_violation_location(node)
            violations.append(
                Violation(
                    module=node,
                    file=violation_file,
                    line=violation_line,
                    message=(
                        f"Fan-in violation: '{node}' is imported by {count} module(s) "
                        f"({_format_module_list(importers)}), exceeding the maximum "
                        f"of {max_count}."
                    ),
                )
            )

        if violations:
            exc = AssertionError(
                f"Fan-in exceeded for {len(violations)} module(s) matching '{self.pattern}'."
            )
            setattr(exc, "violations", violations)
            raise exc

    def fan_out_at_most(self, max_count: int) -> None:
        """Assert that no matched module imports more than max_count other
        modules (its fan-out).

        A high fan-out often means a module is doing too much and is
        coupled to more of the system than it should be.
        """
        if max_count < 0:
            raise ValueError("fan_out_at_most() requires max_count >= 0.")

        violations: list[Violation] = []
        for node in self.matched_nodes:
            dependencies = list(self.graph.successors(node))
            count = len(dependencies)
            if count <= max_count:
                continue
            violation_file, violation_line = _module_violation_location(node)
            violations.append(
                Violation(
                    module=node,
                    file=violation_file,
                    line=violation_line,
                    message=(
                        f"Fan-out violation: '{node}' imports {count} module(s) "
                        f"({_format_module_list(dependencies)}), exceeding the "
                        f"maximum of {max_count}."
                    ),
                )
            )

        if violations:
            exc = AssertionError(
                f"Fan-out exceeded for {len(violations)} module(s) matching '{self.pattern}'."
            )
            setattr(exc, "violations", violations)
            raise exc


def imports(pattern: str) -> ImportQuery:
    """Create an import query rooted at the provided module/package pattern."""
    validate_pattern(pattern)
    return ImportQuery(pattern)
