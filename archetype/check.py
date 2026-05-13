"""Command-line entry points and orchestration for running architecture checks."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import click

from archetype.dsl.query import load_project
from archetype.reporter import print_results
from archetype.rule import registry


@click.group()
def cli() -> None:
    """Archetype CLI."""


@cli.command("check")
@click.argument(
    "path",
    required=False,
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--group",
    "group_filter",
    type=str,
    default=None,
    help="Run only rules in the specified group name (exact match).",
)
def check(path: Path, group_filter: str | None) -> None:
    """Run architecture rules against a Python project."""
    project_path = path.resolve()
    architecture_file = project_path / "architecture.py"

    if not architecture_file.is_file():
        click.echo(
            f"Error: architecture.py not found. Looked for: {architecture_file}",
            err=True,
        )
        raise SystemExit(1)

    registry.clear()
    load_project(project_path)

    module_name = f"_archetype_user_architecture_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, architecture_file)
    if spec is None or spec.loader is None:
        click.echo(
            f"Error: could not load architecture module from: {architecture_file}",
            err=True,
        )
        raise SystemExit(1)

    module = importlib.util.module_from_spec(spec)
    original_sys_path = list(sys.path)
    try:
        sys.path.insert(0, str(project_path))
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        click.echo(
            f"Error: failed to import architecture.py from {architecture_file}: {exc}",
            err=True,
        )
        raise SystemExit(1) from exc
    finally:
        sys.path = original_sys_path

    results = registry.run_all(group_filter=group_filter)
    failed = sum(1 for result in results if not result.passed and not result.warned)
    print_results(results)
    raise SystemExit(0 if failed == 0 else 1)
