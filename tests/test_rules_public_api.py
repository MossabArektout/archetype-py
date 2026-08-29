"""Tests for the built-in public API (declared __all__) boundary rule."""

from __future__ import annotations

from pathlib import Path

import pytest

from archetype.dsl.query import load_project
from archetype.rules import public_api


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_project(tmp_path: Path, *, package_all: str | None) -> Path:
    """Build a minimal project with a `pkg` package and a `consumer` module.

    `pkg/__init__.py` re-exports `Widget` from `pkg/widget.py`. `pkg_all`
    controls what, if anything, `pkg/__init__.py` declares as `__all__`.
    """
    project_path = tmp_path / "project"
    _write(
        project_path / "pkg" / "widget.py",
        "class Widget:\n    pass\n",
    )
    init_body = "from .widget import Widget\n"
    if package_all is not None:
        init_body += f"\n__all__ = {package_all}\n"
    _write(project_path / "pkg" / "__init__.py", init_body)
    _write(project_path / "consumer.py", "from pkg import Widget\n")
    return project_path


def test_public_api_passes_when_only_the_package_root_is_imported(tmp_path: Path) -> None:
    project_path = _build_project(tmp_path, package_all='["Widget"]')
    load_project(project_path)

    public_api("pkg").enforce()


def test_public_api_flags_deep_import_into_undeclared_submodule(tmp_path: Path) -> None:
    project_path = _build_project(tmp_path, package_all='["Widget"]')
    (project_path / "consumer.py").write_text(
        "from pkg.widget import Widget\n", encoding="utf-8"
    )
    load_project(project_path)

    with pytest.raises(AssertionError) as excinfo:
        public_api("pkg").enforce()

    violations = getattr(excinfo.value, "violations", [])
    assert len(violations) == 1
    assert violations[0].module == "consumer"
    assert "consumer" in violations[0].message
    assert "pkg.widget" in violations[0].message
    assert "bypassing the declared public interface of 'pkg'" in violations[0].message


def test_public_api_allows_submodule_explicitly_declared_public(tmp_path: Path) -> None:
    project_path = _build_project(tmp_path, package_all='["widget"]')
    (project_path / "consumer.py").write_text("import pkg.widget\n", encoding="utf-8")
    load_project(project_path)

    public_api("pkg").enforce()


def test_public_api_raises_when_all_not_declared(tmp_path: Path) -> None:
    project_path = _build_project(tmp_path, package_all=None)
    load_project(project_path)

    with pytest.raises(RuntimeError, match="declare __all__"):
        public_api("pkg").enforce()


def test_public_api_raises_when_all_is_not_a_literal_list(tmp_path: Path) -> None:
    project_path = _build_project(tmp_path, package_all="_compute_all()")
    load_project(project_path)

    with pytest.raises(RuntimeError, match="declare __all__"):
        public_api("pkg").enforce()


def test_public_api_raises_when_package_has_no_init_file(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    _write(project_path / "pkg" / "widget.py", "class Widget:\n    pass\n")
    _write(project_path / "consumer.py", "from pkg import widget\n")
    load_project(project_path)

    with pytest.raises(RuntimeError, match="could not find an __init__.py"):
        public_api("pkg").enforce()


def test_public_api_is_a_no_op_when_pattern_matches_nothing(tmp_path: Path) -> None:
    project_path = _build_project(tmp_path, package_all='["Widget"]')
    load_project(project_path)

    public_api("does_not_exist").enforce()


def test_public_api_enforces_every_package_matched_by_a_wildcard_pattern(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    _write(project_path / "billing" / "__init__.py", '__all__ = ["Invoice"]\n')
    _write(project_path / "billing" / "internal.py", "class Invoice:\n    pass\n")
    _write(project_path / "orders" / "__init__.py", '__all__ = ["Order"]\n')
    _write(project_path / "orders" / "internal.py", "class Order:\n    pass\n")
    _write(
        project_path / "consumer.py",
        "from billing.internal import Invoice\nfrom orders.internal import Order\n",
    )
    load_project(project_path)

    with pytest.raises(AssertionError) as excinfo:
        public_api("*").enforce()

    violations = getattr(excinfo.value, "violations", [])
    assert len(violations) == 2
    violated_targets = {v.message for v in violations}
    assert any("billing.internal" in message for message in violated_targets)
    assert any("orders.internal" in message for message in violated_targets)
