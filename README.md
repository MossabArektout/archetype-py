[![PyPI version](https://img.shields.io/pypi/v/archetype-py)](https://pypi.org/project/archetype-py/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://pypi.org/project/archetype-py/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/MossabArektout/archetype-py/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/MossabArektout/archetype-py/ci.yml?branch=main&label=ci)](https://github.com/MossabArektout/archetype-py/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/MossabArektout/archetype-py/badge)](https://securityscorecards.dev/viewer/?uri=github.com/MossabArektout/archetype-py)

# archetype-py

**Architecture tests for Python.** Write rules like "the API layer must not import the database" in plain Python, and fail CI the moment someone breaks one.

Archetype builds a static import graph of your project (your code is never imported or run), checks it against the rules in `architecture.py`, and points at the exact file and line of every violation.

## Why

Linters check style, type checkers check types, and tests check behavior. Nothing checks *structure*, so it erodes one reasonable-looking import at a time: the API reaches into the database, one feature package quietly starts depending on another, a circular import appears. The rules that would have prevented it live in team memory and code review comments. That doesn't scale, especially now that AI tools write code faster than anyone can review its shape.

Archetype turns those rules into checks that run in CI, in a pre-commit hook, and in pytest.

## Quick Start

Install the package (requires Python 3.11+):

```bash
pip install archetype-py
```

Rules live in an `architecture.py` file at your project root. A rule is a plain Python function:

```python
# architecture.py
from archetype import imports, rule

@rule("api-must-not-import-db")
def api_must_not_import_db() -> None:
    imports("myapp.api").must_not_import("myapp.db")
```

Run it:

```bash
archetype check .
```

When someone breaks the rule, the check names the exact file and line and exits `1`:

```text
General
=======
  ✗ api-must-not-import-db
    - myapp/api/routes.py:1
        imports myapp.db.session
  0 passed, 1 failed
Summary: 0 passed, 1 failed, 0 warned, 0 skipped, 1 total rules.
```

Don't want to write rules by hand? Generate them from the structure your code already has:

```bash
archetype init . --infer
```

```text
Analyzed shop: 25 modules, 22 internal imports, 8 top-level components.

  Layers        api → services → repositories → db → core
  Independent   billing, orders, shipping
  Protected     core.internal (already leaking)
  Cycles        found in 2 places (added as a warning)
  Likely leaks  db → api (1×)

Wrote ./architecture.py: 5 rules, no failures today, 3 warnings pointing at problems that already exist.
```

The inferred rules pass on today's code, so the first run is green and every later run catches new drift. Problems that already exist are added as warnings, with the evidence in comments, so nothing is hidden. See [how inference works](docs/rules.md#inferring-rules-from-your-code).

## What You Can Check

| Rule | Example |
|---|---|
| Forbidden imports | `imports("myapp.api").must_not_import("myapp.db")` |
| Forbidden indirect dependencies | `imports("myapp.api").must_not_depend_on("myapp.db")` |
| Allowlisted imports | `imports("myapp.domain").must_only_import_from("myapp.domain", "myapp.core")` |
| Layer order | `layers(["myapp.api", "myapp.services", "myapp.db"]).are_ordered()` |
| Strict layering (no skipping layers) | `layers([...]).are_adjacent()` |
| Independent feature packages | `independent(["myapp.billing", "myapp.orders", "myapp.shipping"])` |
| No import cycles | `no_cycles("myapp")` |
| Private internals | `module("myapp.core.internal").only_imported_within("myapp.core")` |
| Public API from `__all__` | `public_api("myapp.billing").enforce()` |
| Deprecated modules with a sunset date | `deprecated("myapp.legacy", sunset="2027-06-30")` |
| Import depth and coupling limits | `imports("myapp.api.*").fan_out_at_most(8)` |
| Naming conventions | `classes_in("myapp.services").all_match(r"[A-Z]\w*Service")` |

`imports` comes from `archetype`; the rest come from `archetype.rules`. Every check, the pattern syntax, and worked examples are in **[Writing Rules](docs/rules.md)**.

## A Fuller Example

Rules can be grouped, made warning-only, or scoped to new code:

```python
from archetype import group, imports, rule, since, warn
from archetype.rules import no_cycles

with group("Layer boundaries"):
    @rule("api-must-not-import-db")
    def api_must_not_import_db() -> None:
        imports("myapp.api").must_not_import("myapp.db")

@rule("services-should-not-use-db-internals")
@warn  # reported, but never fails the run
def services_should_not_use_db_internals() -> None:
    imports("myapp.services").must_not_import("myapp.db.internal")

@rule("recent-code-must-not-use-legacy")
@since("2026-01-01")  # only checks files changed after this date
def recent_code_must_not_use_legacy() -> None:
    imports("myapp.api").must_not_import("myapp.legacy")

@rule("no-import-cycles")
def no_import_cycles() -> None:
    no_cycles("myapp")
```

```text
General
=======
  ⚠ services-should-not-use-db-internals
    - myapp/services/reports.py:1
        imports myapp.db.internal.session
  ✓ recent-code-must-not-use-legacy (since 2026-01-01)
  ✓ no-import-cycles
  2 passed, 0 failed

Layer boundaries
================
  ✗ api-must-not-import-db
    - myapp/api/users.py:7
        imports myapp.db.internal.session
  0 passed, 1 failed
Summary: 2 passed, 1 failed, 1 warned, 0 skipped, 4 total rules.
```

If a rule's pattern matches no modules (usually a typo, or a rename the rule missed), it is reported as a warning with suggestions instead of passing silently.

For copy-paste rules covering the most common checks (API must not import the database, services must not import the API, no import cycles, and protected internal modules), see [Common Rule Recipes](docs/recipes.md).

For a complete rule file for a layered FastAPI project, see [`examples/fastapi/`](./examples/fastapi).

## Adopting It in an Existing Codebase

You don't have to fix everything before turning it on:

- **Start from what you have.** `archetype init . --infer` writes rules that already pass, and marks existing problems as warnings.
- **Freeze old violations.** `archetype check . --write-baseline archetype-baseline.json` records today's violations; `--baseline archetype-baseline.json` then fails only on new ones.
- **Check only what a PR touches.** `archetype check . --changed-from origin/main`.
- **Tighten gradually.** `@since("2026-01-01")` applies a rule to recently changed files only, and `@escalate(warn_until="2027-06-30")` turns a warning into a failure on a set date.
- **Show progress.** `--record-trend archetype-trend.jsonl` tracks the violation count over time, and `archetype trend` charts it.

Details in [Using the CLI](docs/usage.md).

## Run It Everywhere

**GitHub Actions**, in one step (checkout and Python setup included):

```yaml
- uses: MossabArektout/archetype-py@v0.6.0
```

Violations show up as inline annotations on the pull request. If a `CODEOWNERS` file exists, each violation is tagged with the team that owns the file.

**pre-commit**:

```yaml
repos:
  - repo: https://github.com/MossabArektout/archetype-py
    rev: v0.6.0
    hooks:
      - id: archetype
```

**pytest**: with Archetype installed, `pytest` picks up `architecture.py` and runs each rule as a test.

**Anywhere else**, run `archetype check .`. It exits `1` on failures, and `--format json` or `--format sarif` gives machine-readable output.

GitLab CI, Azure Pipelines, the built-in hook installer, and shell completion are covered in [CI and Integrations](docs/integrations.md).

## Documentation

- **[Writing Rules](docs/rules.md)**: every check, module patterns, decorators, inference, severity escalation, and shared rule packs
- **[Common Rule Recipes](docs/recipes.md)**: copy-paste rules for layer boundaries, import cycles, and protected internal modules
- **[Using the CLI](docs/usage.md)**: commands, configuration (`archetype.toml`), diagnostics, baselines, changed-files mode, trends, and troubleshooting
- **[CI and Integrations](docs/integrations.md)**: GitHub Actions, GitLab CI, Azure Pipelines, pre-commit, pytest, CODEOWNERS, and shell completion
- **[Report Formats](docs/reports.md)**: the JSON report contract, SARIF, and import graph export
- **[Changelog](CHANGELOG.md)**

## Security

Archetype makes no network calls and sends no telemetry. Note that `architecture.py` is ordinary Python and is executed when you run `archetype check`, so don't run it on untrusted changes (for example, from a fork's pull request) in a CI job that has secrets or write access. See [`SECURITY.md`](./SECURITY.md).

## Contributing

Contributions of every size are welcome: bug reports, rule ideas, docs, integrations, and performance work. Feedback counts too. If something here is confusing or missing, [open an issue](https://github.com/MossabArektout/archetype-py/issues).

New to open source? Start with an issue labeled
[`good first issue`](https://github.com/MossabArektout/archetype-py/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
Questions are welcome on any issue.

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the development setup.

## License

MIT. See [`LICENSE`](./LICENSE).
