"""Top-level package metadata and public exports for Archetype."""

from archetype.dsl.query import imports, load_project
from archetype.rule import registry, rule

module = None

__all__ = ["rule", "registry", "imports", "load_project", "module"]
