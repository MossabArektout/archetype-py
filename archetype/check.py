"""Command-line entry points and orchestration for running architecture checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

import click

from archetype.dsl.query import load_project
from archetype.init import (
    detect_project_structure,
    find_existing_architecture_py,
    generate_architecture_py,
    write_architecture_py,
)
from archetype.reporter import format_results_json, print_results
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
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Show only failures and warnings, suppress passing and skipped rules.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Force a fresh import graph rebuild and ignore any cached graph.",
)
def check(
    path: Path,
    group_filter: str | None,
    quiet: bool,
    output_format: str,
    no_cache: bool,
) -> None:
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
    structure = detect_project_structure(project_path)
    src_root = project_path / "src" if structure.get("layout") == "src" else None
    load_project(project_path, src_root=src_root, no_cache=no_cache)

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
    if output_format == "json":
        click.echo(json.dumps(format_results_json(results), ensure_ascii=False, indent=2))
    else:
        print_results(results, quiet=quiet)
    raise SystemExit(0 if failed == 0 else 1)


@cli.command("init")
@click.argument(
    "path",
    required=False,
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def init(path: Path) -> None:
    """Detect project structure and generate a starter architecture.py file."""
    project_path = path.resolve()
    display_path = str(path)
    display_arch_path = (
        "./architecture.py"
        if display_path in {".", ""}
        else f"{display_path.rstrip('/')}/architecture.py"
    )

    existing_file = find_existing_architecture_py(project_path)
    if existing_file is not None:
        click.echo(f"architecture.py already exists at {display_arch_path}")
        if not click.confirm("Overwrite?", default=False):
            click.echo("\nExisting file kept unchanged.")
            raise SystemExit(0)
        existing_file.unlink()

    structure = detect_project_structure(project_path)

    click.echo("\nDetected project structure:")
    layout = structure.get("layout")
    package_name = structure.get("top_level_package")
    if layout == "src" and isinstance(package_name, str):
        click.echo(f"  Layout:  src (src/{package_name})")
    elif layout == "flat" and isinstance(package_name, str):
        click.echo(f"  Layout:  flat ({package_name}/)")
    else:
        click.echo("  Layout:  unknown")
    click.echo(f"  Package: {package_name if package_name is not None else 'not detected'}")

    detected_layers = list(structure.get("detected_layers", []))
    if detected_layers:
        click.echo(f"  Layers:  {' → '.join(detected_layers)}")
    else:
        click.echo("  Layers:  none detected")

    internal_paths = list(structure.get("internal_paths", []))
    if internal_paths:
        click.echo(f"  Internal packages: {', '.join(internal_paths)}")
    else:
        click.echo("  Internal packages: none detected")

    if package_name is None:
        click.echo(
            "\nWarning: project structure could not be auto-detected; "
            "the generated file will contain placeholder rules."
        )

    click.echo("\nGenerating architecture.py...\n")

    content = generate_architecture_py(structure)
    write_architecture_py(project_path, content)

    click.echo(f"architecture.py created at {display_arch_path}")
    click.echo(f"Run archetype check {path} to see results.")
    raise SystemExit(0)
