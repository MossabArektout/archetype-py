"""Tests for import graph construction."""

import os
from pathlib import Path

import archetype.dsl.query as query_module
from archetype.analysis.cache import ensure_gitignore_entry, get_cache_path
from archetype.analysis.imports import (
    ImportGraphBuildError,
    build_import_graph,
    discover_package_roots,
)


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "simple_project"


def _namespace_fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "namespace_project"


def _monorepo_fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "monorepo_project"


def test_graph_contains_expected_module_nodes() -> None:
    graph = build_import_graph(_fixture_root())
    expected_nodes = {
        "simple_project.main",
        "simple_project.api",
        "simple_project.services",
        "simple_project.db",
    }
    assert expected_nodes.issubset(set(graph.nodes))


def test_graph_contains_deliberate_api_to_db_violation_edge() -> None:
    graph = build_import_graph(_fixture_root())
    assert graph.has_edge("simple_project.api", "simple_project.db")


def test_db_module_has_no_outgoing_edges() -> None:
    graph = build_import_graph(_fixture_root())
    assert graph.out_degree("simple_project.db") == 0


def test_graph_excludes_stdlib_and_third_party_modules() -> None:
    graph = build_import_graph(_fixture_root())
    assert all(node.split(".", maxsplit=1)[0] == "simple_project" for node in graph.nodes)


def test_graph_stores_import_line_number_on_edge() -> None:
    graph = build_import_graph(_fixture_root())

    edge_data = graph.get_edge_data("simple_project.api", "simple_project.db")

    assert edge_data is not None
    assert edge_data["line"] == 7


def test_graph_excludes_paths_by_directory_pattern(tmp_path: Path) -> None:
    app_pkg = tmp_path / "app"
    vendor_pkg = tmp_path / "vendor"
    migrations_pkg = app_pkg / "migrations"
    app_pkg.mkdir(parents=True)
    vendor_pkg.mkdir(parents=True)
    migrations_pkg.mkdir(parents=True)
    (app_pkg / "__init__.py").write_text("", encoding="utf-8")
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")
    (migrations_pkg / "__init__.py").write_text("", encoding="utf-8")
    (vendor_pkg / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    (migrations_pkg / "seed.py").write_text("from app import db\n", encoding="utf-8")
    (app_pkg / "db.py").write_text("", encoding="utf-8")
    (app_pkg / "api.py").write_text("from vendor import helpers\n", encoding="utf-8")

    included_graph = build_import_graph(tmp_path)
    excluded_graph = build_import_graph(
        tmp_path,
        exclude_patterns=("/vendor/", "/migrations/"),
    )

    assert "vendor.helpers" in included_graph.nodes
    assert "app.migrations.seed" in included_graph.nodes
    assert "vendor.helpers" not in excluded_graph.nodes
    assert "app.migrations.seed" not in excluded_graph.nodes


def test_graph_stores_absolute_source_file_path_on_edge() -> None:
    graph = build_import_graph(_fixture_root())

    edge_data = graph.get_edge_data("simple_project.api", "simple_project.db")
    expected_file = (_fixture_root() / "simple_project" / "api.py").resolve()

    assert edge_data is not None
    assert Path(edge_data["file"]).is_absolute()
    assert Path(edge_data["file"]) == expected_file


def test_build_import_graph_reports_invalid_python_source(tmp_path: Path) -> None:
    package = tmp_path / "app"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    invalid_file = package / "broken.py"
    invalid_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

    try:
        build_import_graph(tmp_path)
    except ImportGraphBuildError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected invalid Python source to fail graph building.")

    assert f"failed to parse {invalid_file}" in message
    assert "invalid syntax" in message
    assert "line 1" in message


def test_build_import_graph_reports_invalid_file_encoding(tmp_path: Path) -> None:
    package = tmp_path / "app"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    unreadable_file = package / "bad_encoding.py"
    unreadable_file.write_bytes(b"\xff")

    try:
        build_import_graph(tmp_path)
    except ImportGraphBuildError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected invalid file encoding to fail graph building.")

    assert f"failed to read {unreadable_file}" in message
    assert "utf-8" in message


def test_graph_supports_namespace_package_without_init_files() -> None:
    graph = build_import_graph(_namespace_fixture_root())

    assert "company.payments.api" in graph.nodes
    assert "company.shared.utils" in graph.nodes
    assert graph.has_edge("company.payments.api", "company.shared.utils")


def test_discover_package_roots_supports_monorepo_nested_src_layout() -> None:
    roots = discover_package_roots(_monorepo_fixture_root())
    root_paths = {root.resolve() for root in roots}
    monorepo_root = _monorepo_fixture_root().resolve()

    assert monorepo_root / "services" / "billing" / "src" in root_paths
    assert monorepo_root / "libs" / "shared" / "src" in root_paths


def test_graph_supports_monorepo_multi_root_package_detection() -> None:
    graph = build_import_graph(_monorepo_fixture_root())

    assert "acme.billing.api" in graph.nodes
    assert "acme.shared.utils" in graph.nodes
    assert graph.has_edge("acme.billing.api", "acme.shared.utils")


def test_discover_package_roots_preserves_flat_layout_behavior() -> None:
    roots = discover_package_roots(_fixture_root())

    assert roots == [_fixture_root().resolve()]


def test_discover_package_roots_preserves_src_layout_behavior(tmp_path: Path) -> None:
    src_pkg = tmp_path / "src" / "myapp"
    src_pkg.mkdir(parents=True)
    (src_pkg / "__init__.py").write_text("", encoding="utf-8")
    (src_pkg / "api.py").write_text("from myapp import services\n", encoding="utf-8")
    (src_pkg / "services.py").write_text("", encoding="utf-8")

    roots = discover_package_roots(tmp_path)

    assert roots == [(tmp_path / "src").resolve()]


def _make_tmp_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    package = project_root / "app"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "api.py").write_text("from app import services\n", encoding="utf-8")
    (package / "services.py").write_text("from app import db\n", encoding="utf-8")
    (package / "db.py").write_text("", encoding="utf-8")
    return project_root


def test_load_project_uses_cached_graph_when_files_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = _make_tmp_project(tmp_path)
    build_calls = 0
    original = query_module.build_import_graph

    def counting_build(root: Path, *, exclude_patterns=None):
        nonlocal build_calls
        build_calls += 1
        return original(root, exclude_patterns=exclude_patterns)

    monkeypatch.setattr(query_module, "build_import_graph", counting_build)

    query_module.load_project(project_root)
    query_module.load_project(project_root)

    assert build_calls == 1


def test_load_project_rebuilds_when_file_timestamp_changes(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = _make_tmp_project(tmp_path)
    target_file = project_root / "app" / "services.py"
    build_calls = 0
    original = query_module.build_import_graph

    def counting_build(root: Path, *, exclude_patterns=None):
        nonlocal build_calls
        build_calls += 1
        return original(root, exclude_patterns=exclude_patterns)

    monkeypatch.setattr(query_module, "build_import_graph", counting_build)

    query_module.load_project(project_root)

    current_mtime = target_file.stat().st_mtime
    os.utime(target_file, (current_mtime + 10.0, current_mtime + 10.0))
    query_module.load_project(project_root)

    assert build_calls == 2


def test_load_project_rebuilds_when_new_python_file_is_added(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = _make_tmp_project(tmp_path)
    build_calls = 0
    original = query_module.build_import_graph

    def counting_build(root: Path, *, exclude_patterns=None):
        nonlocal build_calls
        build_calls += 1
        return original(root, exclude_patterns=exclude_patterns)

    monkeypatch.setattr(query_module, "build_import_graph", counting_build)

    query_module.load_project(project_root)
    (project_root / "app" / "new_module.py").write_text("VALUE = 1\n", encoding="utf-8")
    query_module.load_project(project_root)

    assert build_calls == 2


def test_load_project_ignores_corrupted_cache_and_rebuilds(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = _make_tmp_project(tmp_path)
    get_cache_path(project_root).write_bytes(b"corrupted")

    build_calls = 0
    original = query_module.build_import_graph

    def counting_build(root: Path, *, exclude_patterns=None):
        nonlocal build_calls
        build_calls += 1
        return original(root, exclude_patterns=exclude_patterns)

    monkeypatch.setattr(query_module, "build_import_graph", counting_build)

    query_module.load_project(project_root)

    assert build_calls == 1


def test_load_project_no_cache_always_rebuilds(tmp_path: Path, monkeypatch) -> None:
    project_root = _make_tmp_project(tmp_path)
    build_calls = 0
    original = query_module.build_import_graph

    def counting_build(root: Path, *, exclude_patterns=None):
        nonlocal build_calls
        build_calls += 1
        return original(root, exclude_patterns=exclude_patterns)

    monkeypatch.setattr(query_module, "build_import_graph", counting_build)

    query_module.load_project(project_root)
    query_module.load_project(project_root, no_cache=True)

    assert build_calls == 2


def test_load_project_rebuilds_when_exclusion_patterns_change(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = _make_tmp_project(tmp_path)
    build_calls = 0
    original = query_module.build_import_graph

    def counting_build(root: Path, *, exclude_patterns=None):
        nonlocal build_calls
        build_calls += 1
        return original(root, exclude_patterns=exclude_patterns)

    monkeypatch.setattr(query_module, "build_import_graph", counting_build)

    query_module.load_project(project_root, exclude_patterns=("/vendor/",))
    query_module.load_project(project_root, exclude_patterns=("/migrations/",))

    assert build_calls == 2


def test_ensure_gitignore_entry_creates_gitignore_when_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)

    ensure_gitignore_entry(project_root)

    gitignore = project_root / ".gitignore"
    assert gitignore.exists()
    assert gitignore.read_text(encoding="utf-8") == ".archetype_cache\n"


def test_ensure_gitignore_entry_appends_when_missing_entry(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    gitignore = project_root / ".gitignore"
    gitignore.write_text("node_modules/\n", encoding="utf-8")

    ensure_gitignore_entry(project_root)

    content = gitignore.read_text(encoding="utf-8")
    assert "node_modules/" in content
    assert ".archetype_cache" in content


def test_ensure_gitignore_entry_does_not_duplicate_existing_entry(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    gitignore = project_root / ".gitignore"
    gitignore.write_text(".archetype_cache\n", encoding="utf-8")

    ensure_gitignore_entry(project_root)
    ensure_gitignore_entry(project_root)

    content = gitignore.read_text(encoding="utf-8")
    assert content.count(".archetype_cache") == 1


def test_ensure_gitignore_entry_preserves_content_without_duplicate_cache_entry(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    gitignore = project_root / ".gitignore"
    gitignore.write_text("# local files\nnode_modules/\n", encoding="utf-8")

    ensure_gitignore_entry(project_root)
    ensure_gitignore_entry(project_root)

    assert gitignore.read_text(encoding="utf-8") == (
        "# local files\nnode_modules/\n.archetype_cache\n"
    )
