# Shared, inheritable rule packs

Without this pattern, every repository in an organization that wants the
same architecture rules (for example, "API code must never import the
database layer directly") ends up copy-pasting the same `architecture.py`
rules into every project. When the rule needs to change, someone has to
edit every copy by hand.

Instead, publish the shared rules as a normal, installable Python package,
and have each repository's `architecture.py` register them with
[`archetype.rule.use`](../../README.md#rule-helpers).

## Layout of this example

- [`acme_archetype_rules/`](./acme_archetype_rules/) — a minimal example of
  a shared rule package. In a real org this would be its own repository,
  published to PyPI or a private index (e.g. as `acme-archetype-rules`).
- [`acme_archetype_rules_pyproject.toml`](./acme_archetype_rules_pyproject.toml) —
  what that package's `pyproject.toml` would look like. It's named without
  the leading dot here so it doesn't participate in this repository's own
  build; rename it to `pyproject.toml` when you copy `acme_archetype_rules/`
  out into its own project.
- [`consuming_project_architecture.py`](./consuming_project_architecture.py) —
  what a project's own `architecture.py` looks like once it depends on the
  published shared package (`pip install acme-archetype-rules`).

## The pattern

In the shared package, define rules exactly as you would locally:

```python
# acme_archetype_rules/__init__.py
from archetype import group, imports, rule

with group("Org baseline"):
    @rule("no-direct-db-access-from-api")
    def no_direct_db_access_from_api() -> None:
        imports("api").must_not_import("db")
```

In each consuming repository's `architecture.py`:

```python
import acme_archetype_rules
from archetype.rule import use

use(acme_archetype_rules)
```

`use()` registers every `@rule`-decorated function it finds in the module
(or accepts individual rule functions, or an iterable of them, if you only
want to adopt some of the shared rules). Add repo-specific rules alongside
it as usual — there's no conflict as long as rule names are unique across
both the shared package and the local file.

## Why not a bare `import acme_archetype_rules`?

Python only executes a module's top-level code — including `@rule`
decorators — the first time that module is imported in a process. A bare
import relies on that first-time execution as its registration mechanism,
which breaks the moment something reloads or re-collects rules without a
fresh Python process: for example, a monorepo where the pytest plugin
collects several `architecture.py` files that all depend on the same
shared package. The first file's collection imports the shared module and
its rules register; the registry is then cleared before the second file is
collected, but the shared module is already cached by Python, so a bare
import does *not* re-run its decorators — its rules would silently vanish
for every file after the first.

`use()` avoids this: it re-registers the already-decorated functions
directly out of the module's namespace, independent of whether Python
actually re-executed it.

## Overriding a shared rule's severity locally

A repository can relax or disable one inherited rule without touching the
shared package, using the normal per-rule policy in `archetype.toml`,
matched by the rule's registered name:

```toml
[rules."no-services-in-tests"]
policy = "warning"
```
