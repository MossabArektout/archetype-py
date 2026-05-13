"""Opt-in benchmark regression tests (run with `pytest -m benchmark`)."""

from __future__ import annotations

import time

import pytest

from archetype.analysis.imports import build_import_graph
from archetype.dsl.query import imports, load_project
from archetype.rule import registry, rule
from archetype.rules import layers, no_cycles

from benchmarks.fixtures import generate_layered_project


@pytest.mark.benchmark
def test_build_import_graph_scale_1_under_2_seconds(tmp_path) -> None:
    generate_layered_project(tmp_path, scale_factor=1)

    start = time.perf_counter()
    build_import_graph(tmp_path)
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0


@pytest.mark.benchmark
def test_build_import_graph_scale_2_under_5_seconds(tmp_path) -> None:
    generate_layered_project(tmp_path, scale_factor=2)

    start = time.perf_counter()
    build_import_graph(tmp_path)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0


@pytest.mark.benchmark
def test_three_rules_scale_1_under_1_second(tmp_path) -> None:
    package_dir = generate_layered_project(tmp_path, scale_factor=1)
    load_project(tmp_path)

    registry.clear()

    layer_paths = [
        f"{package_dir.name}.api",
        f"{package_dir.name}.services",
        f"{package_dir.name}.db",
    ]

    @rule("benchmark-test-no-cycles")
    def _no_cycles() -> None:
        no_cycles(package_dir.name)

    @rule("benchmark-test-layers")
    def _layers() -> None:
        layers(layer_paths).are_ordered()

    @rule("benchmark-test-must-not-import")
    def _must_not_import() -> None:
        imports(f"{package_dir.name}.api").must_not_import(f"{package_dir.name}.db")

    start = time.perf_counter()
    registry.run_all()
    elapsed = time.perf_counter() - start

    registry.clear()

    assert elapsed < 1.0
