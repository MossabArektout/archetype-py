"""Tests for `archetype init --infer` rule inference."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from archetype.analysis.imports import build_import_graph
from archetype.check import cli
from archetype.dsl.query import load_project
from archetype.infer import build_inferred_architecture, infer_architecture
from archetype.rules import independent, no_cycles
from archetype.rules.cycles import MAX_REPORTED_CYCLES


def _project(root: Path, files: dict[str, str]) -> Path:
    """Write a project from {relative path: source}, adding package __init__ files."""
    for relative, source in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    for relative in files:
        parent = (root / relative).parent
        while parent != root and not (parent / "__init__.py").exists():
            if parent.name == "src":
                break
            (parent / "__init__.py").write_text("", encoding="utf-8")
            parent = parent.parent
    return root


LAYERED_APP = {
    "myapp/api/routes.py": "from myapp.services import users\n",
    "myapp/services/users.py": "from myapp.repositories import user_repo\n",
    "myapp/repositories/user_repo.py": "from myapp.db import session\n",
    "myapp/db/session.py": "",
}

FEATURE_APP = {
    "shop/api/routes.py": (
        "from shop.billing import invoices\n"
        "from shop.orders import cart\n"
        "from shop.shipping import rates\n"
    ),
    "shop/billing/invoices.py": "from shop.core import money\n",
    "shop/orders/cart.py": "from shop.core import money\n",
    "shop/shipping/rates.py": "from shop.core import config\n",
    "shop/core/money.py": "",
    "shop/core/config.py": "",
}

# api -> services -> repositories -> db, plus one stray db -> api import.
LEAKY_APP = {
    "myapp/api/routes.py": "from myapp.services import users\nfrom myapp.services import orders\n",
    "myapp/api/deps.py": "",
    "myapp/services/users.py": "from myapp.repositories import user_repo\n",
    "myapp/services/orders.py": (
        "from myapp.repositories import order_repo\nfrom myapp.repositories import user_repo\n"
    ),
    "myapp/repositories/user_repo.py": "from myapp.db import session\n",
    "myapp/repositories/order_repo.py": "from myapp.db import session\nfrom myapp.db import models\n",
    "myapp/db/session.py": "",
    "myapp/db/models.py": "from myapp.api import deps\n",
}


def _infer(project: Path):
    return build_inferred_architecture(project, today=date(2026, 1, 1))


def _rule_names(inferred) -> dict[str, bool]:
    return {rule.name: rule.warn for rule in inferred.inference.rules}


def _run_check(project: Path) -> tuple[int, str]:
    result = CliRunner().invoke(cli, ["check", str(project), "--no-cache"])
    return result.exit_code, result.output


def _write_inferred(project: Path) -> None:
    result = CliRunner().invoke(cli, ["init", str(project), "--infer"])
    assert result.exit_code == 0, result.output


# --- inference ---------------------------------------------------------------


def test_infers_layer_chain_from_downward_imports(tmp_path: Path) -> None:
    inferred = _infer(_project(tmp_path, LAYERED_APP))

    assert inferred.inference.scope == "myapp"
    assert inferred.inference.layers == [
        "myapp.api",
        "myapp.services",
        "myapp.repositories",
        "myapp.db",
    ]
    assert inferred.inference.layers_adjacent is True
    assert _rule_names(inferred) == {"layers-flow-downward": False, "no-import-cycles": False}
    assert "are_adjacent()" in inferred.content


def test_every_generated_rule_passes_on_the_current_code(tmp_path: Path) -> None:
    for name, files in {"layered": LAYERED_APP, "features": FEATURE_APP, "leaky": LEAKY_APP}.items():
        inferred = _infer(_project(tmp_path / name, files))
        blocking = [
            result.name
            for result in inferred.results
            if result.error is not None or (not result.passed and not result.warned)
        ]
        assert blocking == [], name


def test_generated_file_is_green_under_archetype_check(tmp_path: Path) -> None:
    project = _project(tmp_path, FEATURE_APP)
    _write_inferred(project)

    exit_code, output = _run_check(project)

    assert exit_code == 0, output
    assert "0 failed" in output.splitlines()[-1]


def test_generated_layers_rule_catches_new_upward_import(tmp_path: Path) -> None:
    project = _project(tmp_path, LAYERED_APP)
    _write_inferred(project)

    (project / "myapp" / "db" / "session.py").write_text(
        "from myapp.services import users\n", encoding="utf-8"
    )
    exit_code, output = _run_check(project)

    assert exit_code == 1
    assert "layers-flow-downward" in output
    assert "myapp/db/session.py:1" in output


def test_infers_independent_feature_packages(tmp_path: Path) -> None:
    inferred = _infer(_project(tmp_path, FEATURE_APP))

    assert inferred.inference.independent == ["shop.billing", "shop.orders", "shop.shipping"]
    assert "independent(" in inferred.content


def test_generated_independence_rule_catches_new_cross_feature_import(tmp_path: Path) -> None:
    project = _project(tmp_path, FEATURE_APP)
    _write_inferred(project)

    (project / "shop" / "orders" / "cart.py").write_text(
        "from shop.core import money\nfrom shop.billing import invoices\n", encoding="utf-8"
    )
    exit_code, output = _run_check(project)

    assert exit_code == 1
    assert "independent-packages" in output


def test_shared_leaf_packages_are_not_declared_independent(tmp_path: Path) -> None:
    # core and config are imported by others but import nothing themselves:
    # they are shared utilities, not peers, so no independence rule is made.
    inferred = _infer(
        _project(
            tmp_path,
            {
                "myapp/api/routes.py": "from myapp.core import a\nfrom myapp.config import b\n",
                "myapp/core/a.py": "",
                "myapp/config/b.py": "",
            },
        )
    )

    assert inferred.inference.independent == []


def test_rare_upward_import_is_flagged_as_a_leak(tmp_path: Path) -> None:
    inferred = _infer(_project(tmp_path, LEAKY_APP))
    inference = inferred.inference

    assert inference.tangled == []
    assert [(leak.source, leak.target) for leak in inference.leaks] == [
        ("myapp.db", "myapp.api")
    ]
    assert inference.leaks[0].locations == ["myapp/db/models.py:1"]
    assert inference.layers == [
        "myapp.api",
        "myapp.services",
        "myapp.repositories",
        "myapp.db",
    ]
    # The full layering is a warning; everything below the reached layer is enforced.
    assert _rule_names(inferred) == {
        "layers-flow-downward": False,
        "all-layers-flow-downward": True,
        "no-import-cycles": False,
    }
    assert '"myapp.api",' not in inferred.content.split("all-layers-flow-downward")[0].split(
        "layers-flow-downward"
    )[1]
    assert "db -> api at myapp/db/models.py:1" in inferred.content


def test_cli_init_infer_shows_enforced_layers_after_a_leak(tmp_path: Path) -> None:
    project = _project(tmp_path, LEAKY_APP)

    result = CliRunner().invoke(cli, ["init", str(project), "--infer"])

    assert result.exit_code == 0
    assert "Layers" in result.output
    assert "api → services → repositories → db" in result.output
    assert "Enforced" in result.output
    assert "services → repositories → db" in result.output


def test_leak_between_non_chain_packages_gets_its_own_warning(tmp_path: Path) -> None:
    inferred = _infer(
        _project(
            tmp_path,
            {
                **LAYERED_APP,
                "myapp/web/a.py": "from myapp.util import x\nfrom myapp.util import y\n",
                "myapp/web/b.py": "from myapp.util import z\n",
                "myapp/util/x.py": "",
                "myapp/util/y.py": "",
                "myapp/util/z.py": "from myapp.web import b\n",
            },
        )
    )

    assert inferred.inference.layers[0] == "myapp.api"
    assert _rule_names(inferred)["util-must-not-import-web"] is True
    assert "closes a loop: web -> util -> web." in inferred.content
    assert "myapp/util/z.py:1" in inferred.content


def test_evenly_intertwined_packages_are_tangled_not_leaks(tmp_path: Path) -> None:
    inferred = _infer(
        _project(
            tmp_path,
            {
                "myapp/a/one.py": "from myapp.b import one\n",
                "myapp/a/two.py": "from myapp.b import two\n",
                "myapp/b/one.py": "from myapp.a import two\n",
                "myapp/b/two.py": "",
                "myapp/c/one.py": "from myapp.a import one\n",
            },
        )
    )

    assert inferred.inference.tangled == [["myapp.a", "myapp.b"]]
    assert inferred.inference.leaks == []
    assert "a <-> b" in inferred.content


def test_existing_cycles_become_a_warning_rule(tmp_path: Path) -> None:
    inferred = _infer(
        _project(
            tmp_path,
            {
                "myapp/core/a.py": "from myapp.core import b\n",
                "myapp/core/b.py": "from myapp.core import a\n",
                "myapp/api/c.py": "from myapp.core import a\n",
            },
        )
    )

    assert _rule_names(inferred)["no-import-cycles"] is True
    assert inferred.inference.cycles == [["myapp.core.a", "myapp.core.b", "myapp.core.a"]]
    assert "core.a -> core.b -> core.a" in inferred.content


def test_internal_package_used_only_by_its_parent_is_protected(tmp_path: Path) -> None:
    inferred = _infer(
        _project(
            tmp_path,
            {
                "myapp/auth/login.py": "from myapp.auth.internal import tokens\n",
                "myapp/auth/internal/tokens.py": "",
                "myapp/api/routes.py": "from myapp.auth import login\n",
            },
        )
    )

    assert inferred.inference.protected == [("myapp.auth.internal", "myapp.auth", False)]
    assert _rule_names(inferred)["protect-auth-internal"] is False
    assert 'module("myapp.auth.internal").only_imported_within("myapp.auth")' in inferred.content


def test_internal_package_already_imported_from_outside_is_a_warning(tmp_path: Path) -> None:
    inferred = _infer(
        _project(
            tmp_path,
            {
                "myapp/auth/internal/tokens.py": "",
                "myapp/api/routes.py": "from myapp.auth.internal import tokens\n",
            },
        )
    )

    assert inferred.inference.protected == [("myapp.auth.internal", "myapp.auth", True)]
    assert _rule_names(inferred)["protect-auth-internal"] is True


def test_private_package_used_only_by_its_parent_is_protected(tmp_path: Path) -> None:
    inferred = _infer(
        _project(
            tmp_path,
            {
                "myapp/billing/invoices.py": "from myapp.billing._engine import calc\n",
                "myapp/billing/_engine/calc.py": "",
                "myapp/api/routes.py": "from myapp.billing import invoices\n",
            },
        )
    )

    assert inferred.inference.protected == [("myapp.billing._engine", "myapp.billing", False)]


def test_rule_violated_only_by_tests_is_downgraded_with_its_location(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        {
            "myapp/auth/login.py": "from myapp.auth.internal import tokens\n",
            "myapp/auth/internal/tokens.py": "",
            "myapp/api/routes.py": "from myapp.auth import login\n",
            "tests/test_tokens.py": "from myapp.auth.internal import tokens\n",
        },
    )

    inferred = _infer(project)

    assert _rule_names(inferred)["protect-auth-internal"] is True
    assert "tests/test_tokens.py:1" in inferred.content
    assert all(result.passed or result.warned for result in inferred.results)


def test_test_and_example_code_is_left_out_of_inference(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        {
            **LAYERED_APP,
            "tests/test_api.py": "from myapp.api import routes\n",
            "examples/demo/src/demo/app.py": "",
        },
    )

    inferred = _infer(project)

    assert inferred.inference.scope == "myapp"
    assert all(component.startswith("myapp.") for component in inferred.inference.components)


def test_src_layout_is_analyzed_from_src(tmp_path: Path) -> None:
    project = _project(tmp_path, {f"src/{path}": source for path, source in LAYERED_APP.items()})
    (project / "src" / "__init__.py").unlink(missing_ok=True)

    inferred = _infer(project)

    assert inferred.inference.scope == "myapp"
    assert inferred.inference.layers[0] == "myapp.api"


def test_packages_importing_the_root_package_are_not_declared_independent(
    tmp_path: Path,
) -> None:
    files = dict(FEATURE_APP)
    files["shop/orders/cart.py"] = "import shop\nfrom shop.core import money\n"
    inferred = _infer(_project(tmp_path, files))

    assert inferred.inference.facade_importers == ["shop.orders.cart"]
    assert "shop.orders" not in inferred.inference.independent
    assert "`import shop`" in inferred.content


def test_multiple_top_level_packages_become_components(tmp_path: Path) -> None:
    inferred = _infer(
        _project(
            tmp_path,
            {
                "web/views.py": "from domain import models\n",
                "worker/jobs.py": "from domain import models\n",
                "domain/models.py": "",
            },
        )
    )

    assert inferred.inference.scope == ""
    assert inferred.inference.independent == ["web", "worker"]
    assert "no_cycles()" in inferred.content


def test_output_is_deterministic(tmp_path: Path) -> None:
    project = _project(tmp_path, LEAKY_APP)

    assert _infer(project).content == _infer(project).content


def test_generated_source_is_valid_python_with_minimal_imports(tmp_path: Path) -> None:
    inferred = _infer(_project(tmp_path, LAYERED_APP))

    compile(inferred.content, "architecture.py", "exec")
    assert "from archetype import group, rule\n" in inferred.content
    assert "from archetype.rules import layers, no_cycles\n" in inferred.content


def test_inference_does_not_leak_registry_or_loaded_project_state(tmp_path: Path) -> None:
    from archetype.rule import registry
    import archetype.dsl.query as query_module

    before_rules = list(registry._entries)
    before_graph = query_module._current_graph

    _infer(_project(tmp_path, LAYERED_APP))

    assert list(registry._entries) == before_rules
    assert query_module._current_graph is before_graph


def test_infer_architecture_handles_an_empty_graph(tmp_path: Path) -> None:
    import networkx as nx

    inference = infer_architecture(nx.DiGraph(), tmp_path)

    assert inference.module_count == 0
    assert [rule.name for rule in inference.rules] == ["no-import-cycles"]


# --- CLI -----------------------------------------------------------------------


def test_cli_init_infer_writes_file_and_prints_summary(tmp_path: Path) -> None:
    project = _project(tmp_path, LEAKY_APP)

    result = CliRunner().invoke(cli, ["init", str(project), "--infer"])

    assert result.exit_code == 0, result.output
    assert "Analyzed myapp: 13 modules" in result.output
    assert "api → services → repositories → db" in result.output
    assert "Likely leaks" in result.output
    assert "db → api (1×)" in result.output
    assert "3 rules, no failures today, 1 warning" in result.output
    assert (project / "architecture.py").is_file()


def test_cli_init_infer_dry_run_prints_without_writing(tmp_path: Path) -> None:
    project = _project(tmp_path, LAYERED_APP)

    result = CliRunner().invoke(cli, ["init", str(project), "--infer", "--dry-run"])

    assert result.exit_code == 0
    assert result.output.startswith('"""Architecture rules for myapp')
    assert not (project / "architecture.py").exists()


def test_cli_init_dry_run_without_infer_prints_starter_file(tmp_path: Path) -> None:
    project = _project(tmp_path, LAYERED_APP)

    result = CliRunner().invoke(cli, ["init", str(project), "--dry-run"])

    assert result.exit_code == 0
    assert "# Generated by archetype init" in result.output
    assert not (project / "architecture.py").exists()


def test_cli_init_infer_keeps_existing_file_when_declined(tmp_path: Path) -> None:
    project = _project(tmp_path, LAYERED_APP)
    (project / "architecture.py").write_text("# mine\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["init", str(project), "--infer"], input="n\n")

    assert result.exit_code == 0
    assert (project / "architecture.py").read_text(encoding="utf-8") == "# mine\n"
    assert "--infer --dry-run" in result.output


def test_cli_init_infer_overwrites_existing_file_when_confirmed(tmp_path: Path) -> None:
    project = _project(tmp_path, LAYERED_APP)
    (project / "architecture.py").write_text("# mine\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["init", str(project), "--infer"], input="y\n")

    assert result.exit_code == 0
    assert "layers-flow-downward" in (project / "architecture.py").read_text(encoding="utf-8")


def test_cli_init_infer_errors_on_project_without_python(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["init", str(tmp_path), "--infer"])

    assert result.exit_code == 1
    assert "no Python modules found" in result.output
    assert not (tmp_path / "architecture.py").exists()


def test_cli_init_without_infer_suggests_it(tmp_path: Path) -> None:
    project = _project(tmp_path, LAYERED_APP)

    result = CliRunner().invoke(cli, ["init", str(project)])

    assert result.exit_code == 0
    assert "--infer" in result.output


# --- independent() rule -------------------------------------------------------


def test_independent_passes_when_packages_do_not_import_each_other(tmp_path: Path) -> None:
    load_project(_project(tmp_path, FEATURE_APP), no_cache=True)

    independent(["shop.billing", "shop.orders", "shop.shipping"])


def test_independent_reports_every_cross_import(tmp_path: Path) -> None:
    files = dict(FEATURE_APP)
    files["shop/orders/cart.py"] = "from shop.billing import invoices\n"
    files["shop/shipping/rates.py"] = "from shop.orders import cart\n"
    load_project(_project(tmp_path, files), no_cache=True)

    with pytest.raises(AssertionError) as excinfo:
        independent(["shop.billing", "shop.orders", "shop.shipping"])

    violations = excinfo.value.violations
    assert sorted(violation.module for violation in violations) == [
        "shop.orders.cart",
        "shop.shipping.rates",
    ]
    assert "'shop.orders.cart' in 'shop.orders' imports 'shop.billing.invoices'" in (
        violations[0].message + violations[1].message
    )


def test_independent_allows_imports_within_one_package(tmp_path: Path) -> None:
    files = dict(FEATURE_APP)
    files["shop/billing/tax.py"] = "from shop.billing import invoices\n"
    load_project(_project(tmp_path, files), no_cache=True)

    independent(["shop.billing", "shop.orders"])


def test_independent_needs_at_least_two_patterns(tmp_path: Path) -> None:
    load_project(_project(tmp_path, FEATURE_APP), no_cache=True)

    with pytest.raises(ValueError):
        independent(["shop.billing"])


# --- no_cycles() on heavily tangled graphs ------------------------------------


def test_no_cycles_stops_enumerating_on_a_heavily_tangled_graph(tmp_path: Path) -> None:
    # Ten modules that all import each other contain ~1.1 million cycles.
    names = [f"m{index}" for index in range(10)]
    files = {
        f"tangle/{name}.py": "".join(f"from tangle import {other}\n" for other in names if other != name)
        for name in names
    }
    load_project(_project(tmp_path, files), no_cache=True)

    started = time.perf_counter()
    with pytest.raises(AssertionError) as excinfo:
        no_cycles("tangle")
    elapsed = time.perf_counter() - started

    assert elapsed < 10
    assert len(excinfo.value.violations) == MAX_REPORTED_CYCLES
    assert "Stopped after" in excinfo.value.violation_context[0]


def test_build_import_graph_used_for_inference_matches_check(tmp_path: Path) -> None:
    project = _project(tmp_path, LAYERED_APP)
    graph = build_import_graph(project)

    inference = infer_architecture(graph, project)

    assert inference.module_count == len(
        [node for node in graph.nodes if node.startswith("myapp.") or node == "myapp"]
    )
