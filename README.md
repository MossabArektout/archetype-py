![PyPI](https://img.shields.io/pypi/v/archetype) ![Python](https://img.shields.io/pypi/pyversions/archetype) ![License](https://img.shields.io/badge/license-MIT-green) ![CI](https://img.shields.io/github/actions/workflow/status/your-org/your-repo/ci.yml?branch=main)

## Architectural rules should not live in people’s heads
Architectural rules usually exist in engineers’ heads but nowhere in the codebase.
Archetype turns those rules into executable Python checks that run in `archetype check` and `pytest`.

```python
# architecture.py
from archetype import imports, rule

@rule("api does not import db")
def api_not_db() -> None:
    imports("myapp.api").must_not_import("myapp.db")

@rule("services only import db")
def services_only_db() -> None:
    imports("myapp.services").must_only_import_from("myapp.db")
```

```text
$ archetype check .
✓ api does not import db
✗ services only import db
  - myapp.services.user -> myapp.cache: Module 'myapp.services.user' imports 'myapp.cache', which is outside the allowed set: ('myapp.db',).
Summary: 1 passed, 1 failed, 2 total rules.
```

## Installation
```bash
pip install archetype
```

## Quickstart
1. Install Archetype.

```bash
pip install archetype
```

2. Create `architecture.py` in your project root.

```bash
touch architecture.py
```

3. Add your first rule with the imports DSL.

```python
# architecture.py
from archetype import imports, rule

@rule("api does not import db")
def api_not_db() -> None:
    imports("myapp.api").must_not_import("myapp.db")
```

4. Run the checker.

```bash
archetype check .
```

5. Read the output and fix violations.

```text
✓ api does not import db
Summary: 1 passed, 0 failed, 1 total rules.
```

If your project already runs `pytest`, running `pytest` is sufficient because Archetype rules are collected and executed by the pytest plugin.

## Why Archetype exists
Style tools enforce how code looks. Type tools enforce what values can flow through code. Architectural tools enforce which parts of the system are allowed to depend on which other parts.

Pylint and similar linters are strong at local code quality checks, and Mypy is strong at static type correctness. Neither is designed to express team-level dependency contracts like “API cannot import DB” or “internal modules are private outside their package boundary.”

Archetype keeps rules in `architecture.py` as normal Python functions, not static YAML declarations. That makes rules executable, reviewable, testable, and easy to evolve with the codebase using the same language and tooling your team already uses.

## Built-in rules reference
### `layers`
Enforces that lower layers do not import upper layers.

```python
from archetype import rule
from archetype.rules import layers

@rule("layers are ordered")
def layer_order() -> None:
    layers(["myapp.api", "myapp.services", "myapp.db"]).are_ordered()
```

### `module` (module boundaries)
Enforces that a protected internal module is only imported from an allowed parent scope.

```python
from archetype import rule
from archetype.rules import module

@rule("internal auth is private")
def auth_boundary() -> None:
    module("myapp.auth.internal").only_imported_within("myapp.auth")
```

### `classes_in` and `functions_in` (naming conventions)
Enforces class naming patterns and required top-level functions in matched modules.

```python
from archetype import rule
from archetype.rules import classes_in, functions_in

@rule("service classes end with Service")
def class_names() -> None:
    classes_in("myapp.services").all_match(r".*Service$")

@rule("api modules expose handle")
def api_handle_exists() -> None:
    functions_in("myapp.api").must_include("handle")
```

### `no_cycles`
Enforces that there are no import cycles in the whole project or in a selected module scope.

```python
from archetype import rule
from archetype.rules import no_cycles

@rule("no cycles in services")
def services_no_cycles() -> None:
    no_cycles("myapp.services")
```

## Writing custom rules
```python
from archetype import imports, rule

@rule("custom architecture policy")
def custom_policy() -> None:
    imports("myapp.api").must_not_import("myapp.db")
    imports("myapp.services").has_no_cycles()
    imports("myapp.services").must_only_import_from("myapp.db", "myapp.shared")
```

Any Python function decorated with `@rule` that returns without raising is a passing rule. Rules can use the full Python language, so you can encode architecture constraints that do not fit generic linters or static config.

## CI integration
```yaml
name: Archetype Check

on:
  push:
    branches: [main]
  pull_request:

jobs:
  archetype:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: |
          python -m pip install --upgrade pip
          pip install archetype
      - run: archetype check .
```

If your CI already runs `pytest`, no additional CI configuration is required.

## Contributing
Source code and issue tracking are in the GitHub repository: `https://github.com/your-org/your-repo`.
Contributions are welcome; open an issue first to discuss scope before submitting a pull request.
