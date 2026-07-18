# FastAPI Example

A minimal FastAPI-style layout with layered architecture rules enforced by Archetype.

## Layout

```text
app/
├── api/            # HTTP routes (FastAPI routers)
├── services/       # Business logic
├── repositories/   # Data access
└── db/             # Database session
    └── internal/   # Internal engine details
```

Each layer only depends on the layer directly below it: `api` calls `services`, `services` calls `repositories`, `repositories` calls `db`.

## Rules enforced

See [`architecture.py`](./architecture.py):

- `app.api` must not import `app.repositories`.
- `app.api` must not import `app.db`.
- `app.services` must not import `app.api`.
- Layers are ordered top-down: `app.api` → `app.services` → `app.repositories` → `app.db`.
- No import cycles anywhere under `app`.

## Install and run

```bash
pip install archetype-py
archetype check .
```

From this directory, that produces:

```text
General
=======
  ✓ no-import-cycles
  1 passed, 0 failed

Layer boundaries
================
  ✓ api-must-not-import-repositories
  ✓ api-must-not-import-db
  ✓ services-must-not-import-api
  ✓ layer-order
  4 passed, 0 failed
Summary: 5 passed, 0 failed, 0 warned, 0 skipped, 5 total rules.
```

Introducing a forbidden import, such as importing `app.db.session` directly from `app/api/users.py`, causes `api-must-not-import-db` to fail with the offending file and line number.
