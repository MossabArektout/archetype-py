# Benchmarks

This file records `archetype check` performance on synthetic projects of varying sizes.
Run `python benchmarks/run_benchmarks.py` to generate real measurements.

## Results

| name | files | nodes | edges | parse ms | graph ms | rules ms | total ms |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| scale-1 | - | - | - | - | - | - | - |
| scale-2 | - | - | - | - | - | - | - |
| scale-4 | - | - | - | - | - | - | - |
| scale-10 | - | - | - | - | - | - | - |

## Timing Columns

- `parse ms`: AST parsing time for all Python files.
- `graph ms`: Import graph build time.
- `rules ms`: Time to execute benchmark rules.
- `total ms`: Combined benchmark timing.
