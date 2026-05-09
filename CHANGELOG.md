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
