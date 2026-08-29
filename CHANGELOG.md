# Changelog

## Unreleased

### Fixed
- `archetype check --format json` now always emits forward-slash paths in
  the `file` field, matching the documented contract. Previously, running
  on native Windows Python emitted backslash paths instead.
- Fixed a `UnicodeEncodeError` crash on Windows when `archetype check` runs
  without a real console attached (for example, under a pre-commit hook, or
  with output redirected/piped) and the process falls back to a legacy
  codepage such as cp1252 that cannot represent report symbols like `✓`.
  The CLI now forces UTF-8 stdout/stderr on Windows.

### Changed
- Raised the PyPI `Development Status` classifier from `3 - Alpha` to
  `4 - Beta`, and added explicit `Programming Language :: Python :: 3.11`
  / `3.12` classifiers matching the versions actually tested in CI.
- Expanded CI to run the full test suite on Windows and macOS in addition
  to Linux, and added Python 3.13 and 3.14 to the version matrix (12
  OS/version combinations total). Also added `Programming Language ::
  Python :: 3.13` / `3.14` classifiers now that those versions are
  covered. Previously CI only ran on `ubuntu-latest` with Python 3.11 and
  3.12, which is how a Windows-only crash (see Fixed, above) went
  undetected until it was found manually.

### Added
- Added a `py.typed` marker and the `Typing :: Typed` classifier, so type
  checkers (mypy, pyright) treat Archetype as a typed package instead of
  falling back to `Any` for everything it exports.
- Added `layers([...]).are_adjacent()`, a strict variant of `are_ordered()`
  that also rejects layer-skipping imports (e.g. an API layer reaching
  straight past a services layer into the DB layer), requiring every
  cross-layer import to route through the layer directly below it.
- Added `imports(...).max_depth(n)` to cap how many dotted segments deep an
  import target may reach.
- Added `imports(...).fan_in_at_most(n)` and `imports(...).fan_out_at_most(n)`
  to flag modules with too many importers or too many dependencies, pointing
  the violation at the module's own defining file.
- Added `deprecated(pattern, sunset=..., reason=...)` for flagging imports of
  a deprecated module or package from outside itself, with a message that
  counts down to (or reports overdue past) the sunset date. Combine with
  `@escalate(warn_until=...)` to turn a warning into a hard failure exactly
  on the sunset date.
- Added `public_api(pattern).enforce()` for declaring and enforcing a
  package's public interface from its `__all__`. Any import that reaches
  past a package's declared `__all__` into an internal submodule is a
  violation, regardless of which module does the reaching. A submodule can
  itself be declared public by listing its name in `__all__`.
- Added `archetype completion [bash|zsh|fish]` for generating shell
  tab-completion scripts (auto-detects the shell from `$SHELL` when omitted).
- Added a `.pre-commit-hooks.yaml` manifest so Archetype can be added to
  `.pre-commit-config.yaml` like any other pre-commit tool, instead of only
  through the built-in `archetype install-hook` installer.
- Added per-rule `error`, `warning`, and `off` policies via `archetype.toml`
  for gradual rule adoption and rollout control. (#64)
- Added `archetype.rule.use()` for adopting shared, installable rule
  packages across multiple repositories without copy-pasting
  `architecture.py` rules. Registering two different rules under the same
  name now raises a clear error instead of silently shadowing one of them.
- Added `@escalate(warn_until="YYYY-MM-DD")` for scheduling a rule to
  transition from warning-only to a hard failure automatically on a given
  date, for rolling out new org-wide rules without a flag day. Added an
  `escalate_date` field to the JSON and SARIF report contracts.
- Added CODEOWNERS-aware violation routing: when a `.github/CODEOWNERS`,
  `CODEOWNERS`, or `docs/CODEOWNERS` file is present, violations are
  annotated with the owning team/user in text, JSON, SARIF, and GitHub
  Actions inline annotation output. No configuration required.
- Added trend reporting: `archetype check --record-trend <file>` appends
  each run's violation counts to a JSON Lines history file, and
  `archetype trend <file>` renders it as a table with a sparkline and the
  overall change from first to latest run (or `--format json` for raw
  series data). No new analysis — reuses the count already computed for
  the JSON report contract.

### Documentation
- Added GitLab CI and Azure Pipelines examples alongside the existing
  GitHub Actions one, so teams on those platforms don't have to translate
  the job syntax themselves.
- Documented current `archetype check` flags, including `--group`,
  `--format json`, `--quiet`, and `--no-cache` examples. (#42)
- Added a FastAPI example under `examples/fastapi/` with a realistic
  `architecture.py` covering layer ordering, forbidden imports, and cycle
  detection. (#71)
- Documented the built-in `archetype install-hook` pre-commit hook, including
  verification steps, `PATH` requirements, and coexistence with existing
  hooks. (#76)
- Added an `examples/shared-rules/` walkthrough for publishing an
  installable, shared rule package and adopting it across repositories.

## 0.4.0 - 2026-07-05

### Added
- `archetype doctor` command for inspecting detected layout, package roots,
  modules, import edges, config source, excludes, cache status, layers, and
  internal packages.
- `archetype graph` command for exporting the discovered import graph as
  Mermaid or JSON.
- Unmatched pattern diagnostics for rule source, target, allowed, layer,
  boundary, cycle, and naming patterns.
- Pattern suggestions for likely misspellings when a rule pattern matches no
  modules.
- JSON report schema v2 with violation `file`, `line`, `target`, and per-rule
  `diagnostics` fields.

### Changed
- Transitive dependency violations now point to the first import statement in
  the forbidden dependency path.
- Layering violations now include the source file and line for the offending
  import.
- Circular import violations now include a source file and line instead of
  reporting `<unknown>`.
- Rules with unmatched patterns now report as warnings instead of silently
  passing.

## 0.3.0 - 2026-05-26

### Added
- Git pre-commit hook integration via `archetype install-hook`.
- GitHub PR inline annotations support with `--github-annotations`.
- Baseline mode for legacy repositories via `--write-baseline` and `--baseline`.
- Project config defaults through `archetype.toml`.
- Exclude paths support via CLI (`--exclude`) and config.
- Versioned JSON contract with explicit `schema_version`.
- Namespace package and monorepo layout support improvements.
- Changed-files mode with `--changed-from <git-ref>`.

### Changed
- CI/release workflows expanded to cover new check and packaging behaviors.

## 0.1.0 - 2026-05-09

### Added
- Introduced static import graph analysis that maps module dependencies without executing application code.
- Added a rule authoring model using `@rule` decorators and a central registry so architectural checks are defined as plain Python.
- Shipped a readable query DSL with project loading, import constraints, and cycle checks for writing architecture policies.
- Added a CLI command (`archetype check`) that discovers `architecture.py`, executes rules, and returns CI-friendly exit codes.
- Added a pytest plugin that auto-collects `architecture.py` rules as native pytest test items with readable failure output.
- Added a shared reporting layer for consistent violation formatting across CLI and pytest execution paths.
- Added built-in rule packs for layering constraints, module boundaries, naming conventions, and circular import detection.
- Added test fixtures and comprehensive pytest coverage for graph construction, DSL behavior, CLI behavior, plugin collection, and built-in rules.
- Added GitHub Actions workflows for reusable architecture checks in downstream projects and matrix CI for Archetype development.
- Added packaging and release automation for PyPI publication using GitHub Actions Trusted Publishing.


## 0.1.1 — 2026-05-09

### Fixed
- Updated contributing link to correct GitHub repository URL
- Fixed badge URLs to point to correct repository
- Updated project links in pyproject.toml

## 0.2.0 — 2026-05-13

### Added
- @warn decorator for non-blocking rule violations that report
  without failing CI
- @skip decorator to temporarily disable a rule with an optional
  reason string
- @since decorator to enforce rules only on files modified after
  a given date using git history
- Glob pattern support for module matching with single star and
  double star wildcards
- Rule grouping with group context manager and --group CLI flag
- archetype init command to scaffold architecture.py by detecting
  project structure automatically
- Performance benchmarking suite in benchmarks/ folder
- Improved error messages when load_project has not been called

### Changed
- Summary line now includes warned and skipped counts
- Reporter output organized by group when rules use group context manager
- pytest plugin node IDs include group name when present


## 0.2.3 — 2026-05-16

### Added
- archetype init command for scaffolding
- --quiet flag to show only failures and warnings
- --format json flag for machine-readable output
- --no-cache flag to force fresh graph rebuild
- --group flag to run specific rule groups only
- must_not_depend_on for transitive dependency checking
- Import graph caching for faster repeat runs
- File path and line number in violation messages

### Fixed
- src layout detection in archetype init
- Verbose violation messages now concise and scannable
- --quiet flag correctly filters JSON output
- Naming convention violation message format cleaned up
