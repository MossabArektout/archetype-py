# Changelog

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
