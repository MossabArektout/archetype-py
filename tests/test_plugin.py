"""Tests for the Archetype pytest plugin."""

from __future__ import annotations

from pathlib import Path

pytest_plugins = ("pytester",)


def _write_simple_project(root: Path) -> None:
    package = root / "simple_project"
    package.mkdir(parents=True, exist_ok=True)

    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "main.py").write_text(
        "from simple_project import api\n",
        encoding="utf-8",
    )
    (package / "api.py").write_text(
        "from simple_project import services\nfrom simple_project import db\n",
        encoding="utf-8",
    )
    (package / "services.py").write_text(
        "from simple_project import db\n",
        encoding="utf-8",
    )
    (package / "db.py").write_text("", encoding="utf-8")


def test_plugin_collects_rules_as_individual_test_items(pytester) -> None:
    _write_simple_project(pytester.path)
    (pytester.path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('rule-one')",
                "def _rule_one() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
                "@rule('rule-two')",
                "def _rule_two() -> None:",
                "    imports('simple_project.services').must_not_import('simple_project.main')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = pytester.runpytest_inprocess("--collect-only", "-q")

    result.stdout.fnmatch_lines(["*rule-one*", "*rule-two*", "*2 tests collected*"])


def test_plugin_rule_pass_is_reported_as_passing_test(pytester) -> None:
    _write_simple_project(pytester.path)
    (pytester.path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('main-not-db')",
                "def _rule_main_not_db() -> None:",
                "    imports('simple_project.main').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = pytester.runpytest_inprocess("-q")

    result.stdout.fnmatch_lines(["*1 passed*"])


def test_plugin_rule_failure_shows_violation_message(pytester) -> None:
    _write_simple_project(pytester.path)
    (pytester.path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('api-not-db')",
                "def _rule_api_not_db() -> None:",
                "    imports('simple_project.api').must_not_import('simple_project.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = pytester.runpytest_inprocess("-q")

    result.stdout.fnmatch_lines(
        [
            "*Rule 'api-not-db' violations:*",
            "*simple_project.api -> simple_project.db*",
            "*1 failed*",
        ]
    )
