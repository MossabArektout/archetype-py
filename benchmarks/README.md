# Benchmark Suite

This folder contains opt-in performance benchmarks for `archetype-py`.

## What It Measures

- AST parsing time for synthetic Python projects.
- Import graph build time via `build_import_graph`.
- Rule execution time for `no_cycles`, `layers`, and `must_not_import`.

## Run Benchmarks

```bash
python benchmarks/run_benchmarks.py
```

The script prints a markdown table and writes `BENCHMARKS.md` at repo root.

## Regression Tests

```bash
pytest -m benchmark
```

Benchmark tests are excluded from default pytest runs.

## Adding Scenarios

- Add fixture patterns in `benchmarks/fixtures.py`.
- Add scenario entries in `benchmarks/run_benchmarks.py`.
- Keep scenarios deterministic and parseable by `ast`.
