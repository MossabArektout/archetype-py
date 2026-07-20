# Changelog

## Unreleased

### Added
- Added per-rule `error`, `warning`, and `off` policies via `archetype.toml`
  for gradual rule adoption and rollout control. (#64)

### Documentation
- Documented current `archetype check` flags, including `--group`,
  `--format json`, `--quiet`, and `--no-cache` examples. (#42)
- Added a FastAPI example under `examples/fastapi/` with a realistic
  `architecture.py` covering layer ordering, forbidden imports, and cycle
  detection. (#71)
- Added an Example Output section showing passing, failing, and unmatched
  pattern warning runs, and corrected the stale sample output in the Minimal
  Example section. (#77)

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
