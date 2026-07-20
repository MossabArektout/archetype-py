# Common Rule Recipes

Copy-paste rules for the architecture checks teams reach for first. Each one
is a complete, working rule — drop it into `architecture.py`, rename `myapp`
to your package, and run `archetype check .`.

All examples assume a layered project:

```
myapp/
    api/            HTTP routes and request/response schemas
    services/       business logic
    repositories/   data access
    db/             engine, session, and ORM models
    core/
        internal/   implementation details private to core
```

For a full rule file built around this layout, see
[`examples/fastapi/`](../examples/fastapi).

## API must not import the database

The most common architectural rule: HTTP handlers talk to services, never
directly to the database. This keeps query logic out of route functions and
lets you change the persistence layer without touching the API.

```python
from archetype import group, imports, rule

with group("Boundaries"):
    @rule("api-must-not-import-db")
    def api_must_not_import_db() -> None:
        imports("myapp.api").must_not_import("myapp.db")
```

A violation reports the exact import:

```text
  ✗ api-must-not-import-db
    - myapp/api/routes.py:2
        imports myapp.db.session
```

`must_not_import` catches **direct** imports only. To also catch the case
where `api` reaches the database through an intermediate module, use
`must_not_depend_on`, which follows the full dependency chain:

```python
@rule("api-must-not-depend-on-db")
def api_must_not_depend_on_db() -> None:
    imports("myapp.api").must_not_depend_on("myapp.db")
```

## Services must not import the API

The mirror of the rule above, and the one that actually prevents cycles.
Business logic should not know how it was invoked — a service importing a
route handler means the layers have started to fuse.

```python
with group("Boundaries"):
    @rule("services-must-not-import-api")
    def services_must_not_import_api() -> None:
        imports("myapp.services").must_not_import("myapp.api")
```

If you want to state the whole layer order at once rather than writing a rule
per pair, use `layers(...).are_ordered()`:

```python
from archetype.rules import layers

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
```

Layers are listed top to bottom, and a lower layer may never import an upper
one. Note that ordering still permits a layer to skip past its neighbour —
`api` importing `repositories` is downward, so it passes. Pair it with
explicit `must_not_import` rules when you want each layer to talk only to the
one directly beneath it.

## No import cycles

Circular imports cause import-order bugs, break refactoring, and make modules
impossible to test in isolation. This rule fails if any cycle exists anywhere
in the package:

```python
from archetype.rules import no_cycles

with group("Cycles"):
    @rule("no-import-cycles")
    def no_import_cycles() -> None:
        no_cycles("myapp")
```

Scope it to a subtree when adopting Archetype in a large codebase that is not
cycle-free yet:

```python
@rule("no-cycles-in-services")
def no_cycles_in_services() -> None:
    no_cycles("myapp.services")
```

For an existing project with known cycles, prefer
[baseline mode](../README.md#baseline-mode) so current violations are
recorded and only new ones fail.

## Protecting internal modules

Python has no `private` keyword, so anything importable gets imported. Use
`module(...).only_imported_within(...)` to declare that a subpackage is an
implementation detail of its parent — usable inside it, off limits everywhere
else:

```python
from archetype.rules import module

with group("Internals"):
    @rule("internal-helpers-stay-private")
    def internal_helpers_stay_private() -> None:
        module("myapp.core.internal.*").only_imported_within("myapp.core.*")
```

`myapp.core.engine` may import `myapp.core.internal.helpers`, but any module
outside `myapp.core` fails:

```text
  ✗ internal-helpers-stay-private
    - myapp/services/reports.py:1
        imports myapp.core.internal.helpers
```

The inverse — restricting what a module is allowed to import, rather than who
may import it — is `must_only_import_from`. Anything not listed is a
violation, which makes it a good fit for a module you want to keep dependency
free:

```python
@rule("domain-imports-nothing-else")
def domain_imports_nothing_else() -> None:
    imports("myapp.domain").must_only_import_from("myapp.domain.*")
```

## Putting it together

The four recipes as a single `architecture.py`:

```python
from archetype import group, imports, rule
from archetype.rules import module, no_cycles

with group("Boundaries"):
    @rule("api-must-not-import-db")
    def api_must_not_import_db() -> None:
        imports("myapp.api").must_not_import("myapp.db")

    @rule("services-must-not-import-api")
    def services_must_not_import_api() -> None:
        imports("myapp.services").must_not_import("myapp.api")


with group("Cycles"):
    @rule("no-import-cycles")
    def no_import_cycles() -> None:
        no_cycles("myapp")


with group("Internals"):
    @rule("internal-helpers-stay-private")
    def internal_helpers_stay_private() -> None:
        module("myapp.core.internal.*").only_imported_within("myapp.core.*")
```

On a project that satisfies all four:

```text
Boundaries
==========
  ✓ api-must-not-import-db
  ✓ services-must-not-import-api
  2 passed, 0 failed

Cycles
======
  ✓ no-import-cycles
  1 passed, 0 failed

Internals
=========
  ✓ internal-helpers-stay-private
  1 passed, 0 failed
Summary: 4 passed, 0 failed, 0 warned, 0 skipped, 4 total rules.
```

## Adopting a recipe gradually

Rules do not have to block CI on day one. Add `@warn` to report violations
without failing the run:

```python
@rule("api-must-not-import-db")
@warn
def api_must_not_import_db() -> None:
    imports("myapp.api").must_not_import("myapp.db")
```

`@rule(...)` stays on top. See [Rule Helpers](../README.md#rule-helpers) for
`@skip` and `@since`, and [Baseline Mode](../README.md#baseline-mode) for
freezing existing violations while failing on new ones.

## If a rule always passes

A rule whose pattern matches nothing is reported as a warning, not a silent
pass:

```text
  ⚠ controllers-must-not-import-db
    Source pattern 'myapp.controllers' matched 0 modules. Did you mean: myapp.core, myapp.core.internal.helpers, myapp.core.internal?
```

Usually the package name still says `myapp`, or the pattern was left behind
after a rename. Run `archetype doctor .` to list the modules Archetype
actually discovered.
