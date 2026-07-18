"""Archetype architecture rules for the FastAPI example layout."""

from archetype import group, imports, rule
from archetype.rules import layers, no_cycles

with group("Layer boundaries"):

    @rule("api-must-not-import-repositories")
    def api_must_not_import_repositories() -> None:
        imports("app.api").must_not_import("app.repositories")

    @rule("api-must-not-import-db")
    def api_must_not_import_db() -> None:
        imports("app.api").must_not_import("app.db")

    @rule("services-must-not-import-api")
    def services_must_not_import_api() -> None:
        imports("app.services").must_not_import("app.api")

    @rule("layer-order")
    def layer_order() -> None:
        layers(["app.api", "app.services", "app.repositories", "app.db"]).are_ordered()


@rule("no-import-cycles")
def no_import_cycles() -> None:
    no_cycles("app")
