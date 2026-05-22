"""Import parsing and dependency graph construction from Python source files."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Iterable

import networkx as nx

from archetype.analysis.path_filters import is_path_excluded, normalize_exclude_patterns

_IGNORED_DIRS = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    ".env",
    ".tox",
    "node_modules",
}


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


def _has_python_files(
    path: Path,
    *,
    project_root: Path,
    exclude_patterns: Iterable[str] | None = None,
) -> bool:
    normalized_excludes = normalize_exclude_patterns(exclude_patterns)
    if not path.is_dir():
        return False
    for root, dirs, files in os.walk(path):
        dirs[:] = [directory for directory in dirs if directory not in _IGNORED_DIRS]
        if normalized_excludes and is_path_excluded(
            Path(root), project_root, normalized_excludes
        ):
            continue
        for filename in files:
            file_path = Path(root) / filename
            if (
                filename.endswith(".py")
                and not is_path_excluded(file_path, project_root, normalized_excludes)
            ):
                return True
    return False


def _has_top_level_python_package(project_root: Path) -> bool:
    for child in project_root.iterdir():
        if not child.is_dir() or child.name in _IGNORED_DIRS:
            continue
        if (child / "__init__.py").is_file():
            return True
    return False


def discover_package_roots(
    project_root: Path,
    *,
    exclude_patterns: Iterable[str] | None = None,
) -> list[Path]:
    """Discover candidate package roots for flat, src, and monorepo layouts."""
    resolved_root = project_root.resolve()
    normalized_excludes = normalize_exclude_patterns(exclude_patterns)
    discovered: list[Path] = []
    seen: set[Path] = set()

    def add_candidate(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        if _has_python_files(
            resolved,
            project_root=resolved_root,
            exclude_patterns=normalized_excludes,
        ):
            seen.add(resolved)
            discovered.append(resolved)

    if _has_top_level_python_package(resolved_root):
        add_candidate(resolved_root)

    top_level_src = resolved_root / "src"
    if top_level_src.is_dir():
        add_candidate(top_level_src)

    for path in sorted(resolved_root.rglob("src")):
        if not path.is_dir():
            continue
        if path == top_level_src:
            continue
        if any(part in _IGNORED_DIRS for part in path.parts):
            continue
        if is_path_excluded(path, resolved_root, normalized_excludes):
            continue
        add_candidate(path)

    if discovered:
        return discovered
    return [resolved_root]


def build_import_graph(
    project_root: Path,
    *,
    exclude_patterns: Iterable[str] | None = None,
) -> nx.DiGraph:
    """Build a directed import graph for local Python modules under project_root."""
    graph = nx.DiGraph()
    root = project_root.resolve()
    normalized_excludes = normalize_exclude_patterns(exclude_patterns)
    package_roots = discover_package_roots(root, exclude_patterns=normalized_excludes)
    python_files: list[tuple[Path, Path]] = []

    for package_root in package_roots:
        for file_path in sorted(package_root.rglob("*.py")):
            if any(part in _IGNORED_DIRS for part in file_path.parts):
                continue
            if is_path_excluded(file_path, root, normalized_excludes):
                continue
            python_files.append((package_root, file_path))

    local_modules: set[str] = set()
    for package_root, file_path in python_files:
        module_name = path_to_module(file_path, package_root)
        if module_name:
            local_modules.add(module_name)

    local_prefixes: set[str] = set()
    for module_name in local_modules:
        parts = module_name.split(".")
        for index in range(1, len(parts)):
            local_prefixes.add(".".join(parts[:index]))

    def is_local_module(module_name: str) -> bool:
        return module_name in local_modules or module_name in local_prefixes

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

    for package_root, file_path in python_files:
        current_module = path_to_module(file_path, package_root)
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
