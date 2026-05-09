"""AST traversal helpers used by Archetype static analysis."""

from __future__ import annotations

import ast


def get_class_names(tree: ast.AST) -> list[str]:
    """Return all class names defined anywhere in the AST."""
    return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def get_top_level_function_names(tree: ast.AST) -> list[str]:
    """Return names of module-level functions only (excluding class methods)."""
    return [
        node.name
        for node in getattr(tree, "body", [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
