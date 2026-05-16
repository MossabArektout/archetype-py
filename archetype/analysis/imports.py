"""Import parsing and dependency graph construction from Python source files."""

from __future__ import annotations

import ast
from pathlib import Path

import networkx as nx


def path_to_module(file_path: Path, project_root: Path) -> str:
    """Convert a Python file path to its fully-qualified module path."""
    relative = file_path.relative_to(project_root).with_suffix("")
    parts = list(relative.parts)

    if parts and parts[-1] in {"__init__", "init"}:
        parts = parts[:-1]

    return ".".join(parts)


def resolve_relative_import(
    current_module: str, imported_module: str | None, level: int
) -> str:
    """Resolve a relative import into an absolute module path."""
    if level <= 0:
        return imported_module or current_module

    current_parts = [part for part in current_module.split(".") if part]
    drop_count = min(level, len(current_parts))
    base_parts = current_parts[:-drop_count]

    if imported_module:
        return ".".join(base_parts + imported_module.split("."))
    return ".".join(base_parts)


def build_import_graph(project_root: Path) -> nx.DiGraph:
    """Build a directed import graph for local Python modules under project_root."""
    graph = nx.DiGraph()
    root = project_root.resolve()

    def is_local_module(module_name: str) -> bool:
        top_level = module_name.split(".", maxsplit=1)[0]
        return (root / top_level).is_dir()

    def add_import_edge(
        current_module: str,
        imported_module: str,
        *,
        line: int | None,
        file_path: Path,
    ) -> None:
        if imported_module and is_local_module(imported_module):
            graph.add_node(imported_module)
            if graph.has_edge(current_module, imported_module):
                # Keep first-seen import location if multiple statements import
                # the same source->target pair.
                return
            graph.add_edge(
                current_module,
                imported_module,
                line=line or 0,
                file=str(file_path.resolve()),
            )

    for file_path in sorted(root.rglob("*.py")):
        current_module = path_to_module(file_path, root)
        if not current_module:
            continue

        graph.add_node(current_module)

        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    add_import_edge(
                        current_module,
                        alias.name,
                        line=getattr(node, "lineno", 0),
                        file_path=file_path,
                    )

            if isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    resolution_context = current_module
                    if file_path.stem in {"__init__", "init"}:
                        resolution_context = f"{current_module}.__init__"
                    base_module = resolve_relative_import(
                        resolution_context,
                        node.module,
                        node.level,
                    )
                else:
                    base_module = node.module or ""

                # Resolve imported names as potential submodules first.
                # Example: `from simple_project import db` -> `simple_project.db`
                # Example: `from . import utils` -> `<current_pkg>.utils`
                resolved_submodule = False
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    candidate = f"{base_module}.{alias.name}" if base_module else alias.name
                    if candidate and is_local_module(candidate):
                        resolved_submodule = True
                        add_import_edge(
                            current_module,
                            candidate,
                            line=getattr(node, "lineno", 0),
                            file_path=file_path,
                        )

                # Fall back to base module dependency when no concrete local
                # submodule candidates were found (or for star imports).
                if not resolved_submodule or any(alias.name == "*" for alias in node.names):
                    add_import_edge(
                        current_module,
                        base_module,
                        line=getattr(node, "lineno", 0),
                        file_path=file_path,
                    )

    return graph
