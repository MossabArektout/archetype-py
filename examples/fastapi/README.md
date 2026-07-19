# FastAPI Example

A realistic `architecture.py` for a layered FastAPI project.

## Project Layout

The rules in [`architecture.py`](./architecture.py) assume a common four-layer
FastAPI structure:

```text
myapp/
    api/            FastAPI routers and request/response schemas
    services/       business logic
    repositories/   data access built on the db layer
    db/             engine, session, and ORM models
    main.py         app factory and router wiring
architecture.py     the rules in this example
```

Dependencies flow one direction, each layer talking only to the layer directly
beneath it:

```text
api -> services -> repositories -> db
```

## The Rules

| Rule | What it enforces |
|---|---|
| `layers-are-ordered` | `layers([...]).are_ordered()` forbids upward imports: `db` cannot reach back into `repositories`, `services`, or `api`. |
| `api-must-not-import-repositories` | Routers go through services, never straight to data access. |
| `api-must-not-import-db` | Routers never touch the engine, session, or ORM models. |
| `services-must-not-import-db` | Business logic depends on repositories, not raw database internals. |
| `no-import-cycles` | `no_cycles("myapp")` fails on any circular import inside the package. |

The layering rule and the `must_not_import` rules are complementary: layer
ordering only forbids upward imports, so the boundary rules add "no layer
skipping" on the way down.

## Run It

Install Archetype:

```bash
pip install archetype-py
```

Copy `architecture.py` into your project root (next to your package), rename
`myapp` to your package name, then run:

```bash
archetype check .
```

Example failure when a router imports the session directly:

```text
FAILED
======
  x api-must-not-import-db
    - myapp/api/users.py:7
        imports myapp.db.session

Summary: 4 passed, 1 failed, 0 warned, 0 skipped
```

With the package installed, pytest also collects the rules from
`architecture.py` as test items:

```bash
pytest
```

If a rule reports a `pattern matched 0 modules` diagnostic, run
`archetype doctor .` to see the package roots and modules Archetype detected.
