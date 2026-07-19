"""Archetype rules for a layered FastAPI project.

Assumes a project layout like:

    myapp/
        api/            FastAPI routers and request/response schemas
        services/       business logic
        repositories/   data access built on the db layer
        db/             engine, session, and ORM models
        main.py         app factory and router wiring

Rename ``myapp`` to your package name and place this file in the project
root, then run ``archetype check .``.
"""

from archetype import group, imports, rule
from archetype.rules import layers, no_cycles

with group("Layering"):
    # Layers are listed top to bottom. A lower layer must never import an
    # upper one, so db cannot reach back into repositories, services, or api.
    @rule("layers-are-ordered")
    def layers_are_ordered() -> None:
        layers(
            [
                "myapp.api",
                "myapp.services",
                "myapp.repositories",
                "myapp.db",
            ]
        ).are_ordered()


with group("Boundaries"):
    # Layer ordering allows any downward import, including skipping layers.
    # These rules forbid the skips: each layer may only talk to the one
    # directly beneath it.
    @rule("api-must-not-import-repositories")
    def api_must_not_import_repositories() -> None:
        imports("myapp.api").must_not_import("myapp.repositories")

    @rule("api-must-not-import-db")
    def api_must_not_import_db() -> None:
        imports("myapp.api").must_not_import("myapp.db")

    @rule("services-must-not-import-db")
    def services_must_not_import_db() -> None:
        imports("myapp.services").must_not_import("myapp.db")


with group("Cycles"):
    @rule("no-import-cycles")
    def no_import_cycles() -> None:
        no_cycles("myapp")
