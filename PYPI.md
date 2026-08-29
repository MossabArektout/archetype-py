# archetype-py

Enforce architectural rules as code. Catch structural violations before they merge.

[GitHub Repository](https://github.com/MossabArektout/archetype-py)  
[Documentation](https://github.com/MossabArektout/archetype-py#readme)

## Why archetype-py

Most tooling checks formatting, typing, and tests, but not architecture drift.  
`archetype-py` lets you codify structural boundaries and enforce them in local runs, CI, and pytest.

## When to use / When not to use

Use archetype-py when:
- You want architecture rules to run automatically in CI and pytest.
- You need to prevent forbidden imports, layer violations, or import cycles.
- You are adopting architecture checks incrementally in a legacy codebase (baseline mode).

Do not use archetype-py when:
- You only need style/type checks (linters and type checkers are enough).
- Your project is a very small script with no meaningful module boundaries.
- You are looking for runtime policy enforcement instead of static import-graph checks.

## Install

```bash
pip install archetype-py
```

## Quick Start

```bash
archetype init .
archetype check .
```

Create an `architecture.py` file and define your rules:

```python
from archetype import rule
from archetype.rules import layers

@rule("layers are ordered")
def layer_order() -> None:
    layers(["myapp.api", "myapp.services", "myapp.db"]).are_ordered()
```

## Core Features

- Architecture rules for forbidden imports, allowlisted imports, and protected boundaries
- Transitive dependency checks with `must_not_depend_on`
- Layer order enforcement with `layers(...).are_ordered()`
- Import cycle detection with `no_cycles(...)`
- Public API enforcement from a package's declared `__all__` with `public_api(...).enforce()`
- Rule decorators: `@rule`, `@warn`, `@skip`, `@since`
- Rule grouping via `group("...")` and targeted execution with `--group`
- `archetype init` scaffolding for starter `architecture.py`
- JSON and text reporting (`--format json|text`) with stable JSON contract versioning
- Quiet output mode (`--quiet`) for CI-friendly logs
- Import graph caching for faster repeated runs (`--cache`, `--no-cache`)
- Parallel execution control with `--workers`
- Baseline adoption for legacy codebases (`--write-baseline`, `--baseline`)
- Changed-files scope mode (`--changed-from <git-ref>`)
- GitHub Actions inline PR annotations (`--github-annotations`)
- Project diagnostics with `archetype doctor`
- Import graph export with `archetype graph --format mermaid|json`
- Unmatched pattern warnings with suggestions for likely misspellings
- Path exclusions via CLI (`--exclude`) and config
- Project config defaults through `archetype.toml`
- Git pre-commit hook installer (`archetype install-hook`)
- Project layout support for flat, `src/`, namespace packages (PEP 420), and monorepos
- CLI command and pytest plugin support for local and CI enforcement

## CI Example

```yaml
- run: archetype check .
```

For full guides, examples, and release notes, use the GitHub README and changelog.
