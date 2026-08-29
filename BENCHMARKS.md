# Benchmarks

This document tracks `archetype check` performance across synthetic Python codebases of increasing size.
Run benchmarks manually with:

```bash
python benchmarks/run_benchmarks.py
```

## Results

| name | files | nodes | edges | parse ms | graph ms | rules ms | total ms |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| scale-1 | 54 | 54 | 144 | 12.63 | 61.99 | 3.22 | 77.84 |
| scale-2 | 154 | 154 | 735 | 30.20 | 212.20 | 5.27 | 247.66 |
| scale-4 | 504 | 504 | 3964 | 112.84 | 1032.35 | 23.75 | 1168.95 |
| scale-10 | 1004 | 1004 | 9945 | 344.70 | 2504.77 | 58.48 | 2907.95 |

## Timing Columns

- `parse ms`: Time to parse all Python files with `ast.parse`.
- `graph ms`: Time to build the import graph with `build_import_graph`.
- `rules ms`: Time to execute `no_cycles`, `layers`, and `must_not_import` rules.
- `total ms`: Sum of parse, graph, and rules timing.

## Notes

- These numbers measure a **cold** run: `graph ms` calls `build_import_graph` directly, bypassing the import graph cache (see `archetype check --no-cache`). A real `archetype check` run on an unchanged project reuses the cached graph and is substantially faster than the `graph ms` figure above suggests; these results represent the worst case (first run, or after any file changes).
- Numbers vary run-to-run (background load, disk I/O for the synthetic project's temp files) by roughly 10-15% at this scale; treat this as an order-of-magnitude reference, not a precise regression baseline. Exact regression tracking is handled separately by `pytest -m benchmark` (`benchmarks/test_performance_regression.py`).

## Runtime Metadata

- Python: `3.14.4 (tags/v3.14.4:23116f9, Apr  7 2026, 14:10:54) [MSC v.1944 64 bit (AMD64)]`
- Platform: `Windows-11-10.0.26200-SP0`
