"""Archetype self-check rules for this repository."""

from archetype import imports, rule


@rule("analysis must not import dsl")
def analysis_not_import_dsl() -> None:
    imports("archetype.analysis").must_not_import("archetype.dsl")


@rule("plugin must not import rules")
def plugin_not_import_rules() -> None:
    imports("archetype.plugin").must_not_import("archetype.rules")


@rule("rules must not import plugin")
def rules_not_import_plugin() -> None:
    imports("archetype.rules").must_not_import("archetype.plugin")
