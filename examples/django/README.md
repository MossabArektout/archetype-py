# Django Example

A worked example of using Archetype on a Django-shaped codebase: two apps
(`users`, `billing`), each split into `models.py`, `internal.py`,
`services.py`, and `views.py`, with rules in [`architecture.py`](./architecture.py)
that keep them that way.

## Layout

```
examples/django/
├── architecture.py      # the rules
├── users/
│   ├── models.py         # ORM models -- schema only
│   ├── internal.py       # raw ORM/SQL access -- private to this app
│   ├── services.py       # public API -- the only sanctioned entry point
│   └── views.py          # HTTP layer -- calls services.py only
└── billing/
    └── (same shape as users/)
```

`billing` depends on `users` the way one app depending on another normally
should: `billing/services.py` calls `users/services.py`, never
`users/internal.py`.

## The rules

| Rule | What it catches |
|---|---|
| `views must not import internal modules directly` | Any `*.views` module importing any `*.internal` module -- the HTTP layer reaching past the service layer straight into raw ORM/SQL code. |
| `users internal is private to the users app` | Anything outside `users/` importing `users.internal` -- e.g. `billing` reaching into another app's internals instead of calling `users.services`. |
| `billing internal is private to the billing app` | The mirror of the rule above, scoped to `billing.internal`. |
| `views, services, and models stay in order` | `models.py` importing `services.py`/`views.py`, or `services.py` importing `views.py` -- dependencies flowing the wrong way up the stack. |
| `no import cycles between apps` | `users` and `billing` (or any apps you add later) ending up in an import cycle. |

## Running it

```bash
pip install archetype-py
archetype check examples/django
```

On the code as committed, that prints:

```
General
=======
  ✓ views must not import internal modules directly
  ✓ users internal is private to the users app
  ✓ billing internal is private to the billing app
  ✓ views, services, and models stay in order
  ✓ no import cycles between apps
  5 passed, 0 failed
Summary: 5 passed, 0 failed, 0 warned, 0 skipped, 5 total rules.
```

`archetype check examples/django --format json` gives the same result as a
machine-readable report, for wiring into CI.

## What a violation looks like

If `billing/services.py` reached into `users/internal.py` directly instead
of going through `users/services.py`:

```python
# billing/services.py
from users import internal as users_internal   # <- boundary violation

def get_billing_summary(user_email: str) -> BillingSummary | None:
    user_row = users_internal.fetch_user_row_by_email(user_email)
    ...
```

`archetype check examples/django` would fail with:

```
General
=======
  ✓ views must not import internal modules directly
  ✗ users internal is private to the users app
    - billing/services.py:15
        imports users.internal
  ✓ billing internal is private to the billing app
  ✓ views, services, and models stay in order
  ✓ no import cycles between apps
  4 passed, 1 failed
Summary: 4 passed, 1 failed, 0 warned, 0 skipped, 5 total rules.
```

And if `users/views.py` imported `users/internal.py` directly instead of
going through `users/services.py`, the other rule would catch it the same
way, pointing at `users/views.py:11` and failing
`views must not import internal modules directly` instead.

Both outputs above are real `archetype check` output, captured against a
deliberately broken copy of this example -- not hand-written.

## Adapting this to your own project

- Rename `users`/`billing` to your real app names; the rules use wildcard
  patterns (`*.views`, `*.internal`, `*.services`, `*.models`) for the
  views/layering/cycle checks, so any app matching that shape is covered
  automatically. Only the two boundary rules (`module(...).only_imported_within(...)`)
  are per-app and need one line added per new app.
- If your "internal" layer is a package rather than a single file (e.g.
  `internal/queries.py`, `internal/raw_sql.py`), keep the boundary rules
  written without a wildcard on the app name (`module("users.internal")`,
  not `module("*.internal")`) -- non-wildcard patterns match a package and
  everything inside it, so submodules stay protected too. A wildcarded
  target pattern like `*.internal` only matches a single path segment and
  will not reach into a package's submodules.
- See the root [`README.md`](../../README.md#rule-helpers) for the full
  rule-helper reference (`@warn`, `@skip`, `@since`, `group(...)`), and
  [`README.md#minimal-example`](../../README.md#minimal-example) for the
  smallest possible `architecture.py`.
