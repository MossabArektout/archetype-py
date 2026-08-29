"""AST traversal helpers used by Archetype static analysis."""

from __future__ import annotations

import ast
from pathlib import Path


def read_source(file_path: Path) -> bytes:
    """Read a Python source file as bytes, ready for ast.parse.

    Returning bytes lets CPython apply its own BOM handling and PEP 263
    encoding detection, matching what a real import does. Decoding as utf-8
    first would reject valid sources that carry a BOM or declare a different
    encoding.
    """
    return file_path.read_bytes()


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
