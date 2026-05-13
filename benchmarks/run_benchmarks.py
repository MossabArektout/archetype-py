"""Manual performance benchmark runner for archetype-py."""

from __future__ import annotations

import ast
import platform
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from archetype.analysis.imports import build_import_graph
from archetype.dsl import query as query_module
from archetype.dsl.query import _current_graph, imports, load_project
from archetype.rule import registry, rule
from archetype.rules import layers, no_cycles

from benchmarks.fixtures import generate_layered_project


@dataclass(slots=True)
class BenchmarkResult:
    name: str
    file_count: int
    node_count: int
    edge_count: int
    parse_time_ms: float
    graph_build_time_ms: float
    rule_execution_time_ms: float
    total_time_ms: float


def run_single_benchmark(benchmark_name: str, scale_factor: int) -> BenchmarkResult:
    """Run one benchmark scenario and return collected timings and graph stats."""
    with tempfile.TemporaryDirectory(prefix="archetype-bench-") as temp_dir:
        root = Path(temp_dir)
        package_dir = generate_layered_project(root, scale_factor=scale_factor)

        python_files = sorted(root.rglob("*.py"))
        file_count = len(python_files)

        parse_start = time.perf_counter()
        for file_path in python_files:
            ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        parse_end = time.perf_counter()

        graph_start = time.perf_counter()
        graph = build_import_graph(root)
        graph_end = time.perf_counter()

        load_project(root)
        layer_paths = [
            f"{package_dir.name}.api",
            f"{package_dir.name}.services",
            f"{package_dir.name}.db",
        ]

        registry.clear()

        @rule(f"{benchmark_name}-no-cycles")
        def _no_cycles() -> None:
            no_cycles(package_dir.name)

        @rule(f"{benchmark_name}-layers")
        def _layers() -> None:
            layers(layer_paths).are_ordered()

        @rule(f"{benchmark_name}-api-must-not-import-db")
        def _must_not_import() -> None:
            imports(f"{package_dir.name}.api").must_not_import(f"{package_dir.name}.db")

        rules_start = time.perf_counter()
        registry.run_all()
        rules_end = time.perf_counter()

        # Imported for benchmarking internals; query module holds the live runtime value.
        runtime_graph = query_module._current_graph if query_module._current_graph is not None else _current_graph
        if runtime_graph is None:
            runtime_graph = graph

        parse_time_ms = (parse_end - parse_start) * 1000.0
        graph_build_time_ms = (graph_end - graph_start) * 1000.0
        rule_execution_time_ms = (rules_end - rules_start) * 1000.0
        total_time_ms = (
            parse_time_ms + graph_build_time_ms + rule_execution_time_ms
        )

        result = BenchmarkResult(
            name=benchmark_name,
            file_count=file_count,
            node_count=runtime_graph.number_of_nodes(),
            edge_count=runtime_graph.number_of_edges(),
            parse_time_ms=parse_time_ms,
            graph_build_time_ms=graph_build_time_ms,
            rule_execution_time_ms=rule_execution_time_ms,
            total_time_ms=total_time_ms,
        )

        registry.clear()
        return result


def format_benchmark_table(results: list[BenchmarkResult]) -> str:
    """Format benchmark results into a markdown table."""
    headers = ["name", "files", "nodes", "edges", "parse ms", "graph ms", "rules ms", "total ms"]
    rows = [
        [
            result.name,
            str(result.file_count),
            str(result.node_count),
            str(result.edge_count),
            f"{result.parse_time_ms:.2f}",
            f"{result.graph_build_time_ms:.2f}",
            f"{result.rule_execution_time_ms:.2f}",
            f"{result.total_time_ms:.2f}",
        ]
        for result in results
    ]

    table_lines = [
        "| " + " | ".join(headers) + " |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        table_lines.append("| " + " | ".join(row) + " |")
    return "\n".join(table_lines)


def write_benchmarks_md(results: list[BenchmarkResult]) -> None:
    """Write BENCHMARKS.md at project root with benchmark output and metadata."""
    repo_root = Path(__file__).resolve().parent.parent
    table = format_benchmark_table(results)

    content = "\n".join(
        [
            "# Benchmarks",
            "",
            "This document tracks `archetype check` performance across synthetic Python codebases of increasing size.",
            "Run benchmarks manually with:",
            "",
            "```bash",
            "python benchmarks/run_benchmarks.py",
            "```",
            "",
            "## Results",
            "",
            table,
            "",
            "## Timing Columns",
            "",
            "- `parse ms`: Time to parse all Python files with `ast.parse`.",
            "- `graph ms`: Time to build the import graph with `build_import_graph`.",
            "- `rules ms`: Time to execute `no_cycles`, `layers`, and `must_not_import` rules.",
            "- `total ms`: Sum of parse, graph, and rules timing.",
            "",
            "## Runtime Metadata",
            "",
            f"- Python: `{sys.version}`",
            f"- Platform: `{platform.platform()}`",
        ]
    )

    (repo_root / "BENCHMARKS.md").write_text(content + "\n", encoding="utf-8")


if __name__ == "__main__":
    scenarios = [
        ("scale-1", 1),
        ("scale-2", 2),
        ("scale-4", 4),
        ("scale-10", 10),
    ]

    benchmark_results: list[BenchmarkResult] = []
    for benchmark_name, scale in scenarios:
        print(f"Running benchmark '{benchmark_name}' (scale={scale})...")
        benchmark_results.append(run_single_benchmark(benchmark_name, scale))

    table = format_benchmark_table(benchmark_results)
    print("\n" + table)
    write_benchmarks_md(benchmark_results)
