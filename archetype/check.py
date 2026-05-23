"""Command-line entry points and orchestration for running architecture checks."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import TypeVar

import click
from click.core import ParameterSource

from archetype.baseline import (
    ViolationCounts,
    apply_baseline,
    build_baseline_payload,
    load_baseline,
    write_baseline,
)
from archetype.analysis.git_utils import get_files_changed_from
from archetype.analysis.path_filters import filter_excluded_paths
from archetype.config import load_check_config
from archetype.dsl.query import load_project
from archetype.init import (
    detect_project_structure,
    find_existing_architecture_py,
    generate_architecture_py,
    write_architecture_py,
)
from archetype.analysis.models import RuleResult
from archetype.reporter import (
    format_github_annotations,
    format_results_json,
    print_results,
)
from archetype.rule import registry

T = TypeVar("T")
_HOOK_BEGIN_MARKER = "# >>> archetype pre-commit hook >>>"
_HOOK_END_MARKER = "# <<< archetype pre-commit hook <<<"


def _run_git(project_path: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(project_path), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ValueError("Git executable not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise ValueError(details) from exc
    return completed.stdout.strip()


def _resolve_git_hook_paths(project_path: Path) -> tuple[Path, Path]:
    try:
        repo_root = Path(_run_git(project_path, "rev-parse", "--show-toplevel")).resolve()
        hook_path_raw = Path(
            _run_git(project_path, "rev-parse", "--git-path", "hooks/pre-commit")
        )
    except ValueError as exc:
        raise ValueError(f"Unable to resolve git hooks path: {exc}") from exc
    hook_path = (
        hook_path_raw
        if hook_path_raw.is_absolute()
        else (repo_root / hook_path_raw).resolve()
    )
    return repo_root, hook_path


def _managed_pre_commit_block() -> str:
    return "\n".join(
        [
            _HOOK_BEGIN_MARKER,
            "if ! command -v archetype >/dev/null 2>&1; then",
            "  echo \"archetype: CLI not found on PATH. Install archetype to run checks.\" >&2",
            "  exit 1",
            "fi",
            "",
            "repo_root=\"$(git rev-parse --show-toplevel 2>/dev/null)\"",
            "if [ -z \"$repo_root\" ]; then",
            "  echo \"archetype: unable to resolve repository root.\" >&2",
            "  exit 1",
            "fi",
            "",
            "archetype check \"$repo_root\"",
            _HOOK_END_MARKER,
            "",
        ]
    )


def _render_pre_commit_hook(existing: str | None) -> tuple[str, str]:
    block = _managed_pre_commit_block()
    if existing is None or not existing.strip():
        return ("#!/bin/sh\n\n" + block, "created")

    if _HOOK_BEGIN_MARKER in existing and _HOOK_END_MARKER in existing:
        pattern = (
            rf"{re.escape(_HOOK_BEGIN_MARKER)}.*?{re.escape(_HOOK_END_MARKER)}\n?"
        )
        updated = re.sub(pattern, block, existing, flags=re.DOTALL)
        if updated == existing:
            return (existing, "unchanged")
        return (updated, "updated")

    updated = existing.rstrip("\n") + "\n\n" + block
    return (updated, "appended")


def _scope_results_to_changed_files(
    results: list[RuleResult],
    *,
    changed_files: set[Path],
    project_root: Path,
) -> None:
    resolved_root = project_root.resolve()
    for result in results:
        if result.skipped or result.error is not None:
            continue
        if not result.violations:
            continue

        scoped = []
        for violation in result.violations:
            violation_file = Path(violation.file)
            violation_path = (
                (resolved_root / violation_file).resolve()
                if not violation_file.is_absolute()
                else violation_file.resolve()
            )
            if violation_path in changed_files:
                scoped.append(violation)

        result.violations = scoped
        if not scoped:
            result.passed = True
            result.warned = False


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
    "quiet",
    flag_value=True,
    default=None,
    help="Show only failures and warnings, suppress passing and skipped rules.",
)
@click.option(
    "--no-quiet",
    "quiet",
    flag_value=False,
    default=None,
    help="Show full output including passing and skipped rules.",
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
    "--cache",
    "cache",
    flag_value=True,
    default=None,
    help="Use import graph cache.",
)
@click.option(
    "--no-cache",
    "cache",
    flag_value=False,
    default=None,
    help="Force a fresh import graph rebuild and ignore any cached graph.",
)
@click.option(
    "--write-baseline",
    "write_baseline_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write current violations to a baseline JSON file.",
)
@click.option(
    "--baseline",
    "baseline_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Load baseline JSON and suppress matching existing violations.",
)
@click.option(
    "--exclude",
    "exclude_patterns",
    type=str,
    multiple=True,
    help="Exclude path pattern from analysis (repeatable). Example: --exclude /vendor/",
)
@click.option(
    "--workers",
    type=click.IntRange(1),
    default=None,
    help="Number of worker threads for running rules.",
)
@click.option(
    "--changed-from",
    "changed_from",
    type=str,
    default=None,
    help="Limit reported violations to files changed from the given ref (branch or SHA).",
)
@click.option(
    "--github-annotations",
    is_flag=True,
    default=False,
    help="Emit GitHub Actions inline PR annotations for violations.",
)
@click.pass_context
def check(
    ctx: click.Context,
    path: Path,
    group_filter: str | None,
    quiet: bool | None,
    output_format: str,
    cache: bool | None,
    write_baseline_path: Path | None,
    baseline_path: Path | None,
    exclude_patterns: tuple[str, ...],
    workers: int | None,
    changed_from: str | None,
    github_annotations: bool,
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
    try:
        config = load_check_config(project_path)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    def _resolved_value(name: str, cli_value: T, config_value: T | None) -> T:
        if (
            ctx.get_parameter_source(name) == ParameterSource.DEFAULT
            and config_value is not None
        ):
            return config_value
        return cli_value

    effective_output_format = _resolved_value("output_format", output_format, config.output_format)
    effective_quiet = _resolved_value("quiet", quiet, config.quiet)
    effective_group_filter = _resolved_value("group_filter", group_filter, config.group_filter)
    effective_cache = _resolved_value("cache", cache, config.cache)
    effective_workers = _resolved_value("workers", workers, config.workers)

    effective_excludes: list[str]
    if (
        ctx.get_parameter_source("exclude_patterns") == ParameterSource.DEFAULT
        and config.exclude_patterns is not None
    ):
        effective_excludes = list(config.exclude_patterns)
    else:
        effective_excludes = list(exclude_patterns)

    use_cache = True if effective_cache is None else effective_cache
    load_project(
        project_path,
        src_root=src_root,
        no_cache=not use_cache,
        exclude_patterns=effective_excludes,
    )

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

    results = registry.run_all(
        group_filter=effective_group_filter,
        workers=effective_workers or 1,
    )
    violation_counts = ViolationCounts(
        total=sum(len(result.violations) for result in results),
        new=sum(len(result.violations) for result in results),
        suppressed=0,
    )

    if write_baseline_path is not None:
        payload = build_baseline_payload(results, project_root=project_path)
        try:
            write_baseline(write_baseline_path.resolve(), payload)
        except OSError as exc:
            click.echo(f"Error: failed to write baseline {write_baseline_path}: {exc}", err=True)
            raise SystemExit(1) from exc

    if baseline_path is not None:
        try:
            baseline_counter = load_baseline(baseline_path.resolve())
        except (OSError, ValueError) as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1) from exc
        violation_counts = apply_baseline(
            results,
            baseline_counter=baseline_counter,
            project_root=project_path,
        )

    scope_metadata: dict[str, object] | None = None
    if changed_from is not None:
        try:
            changed_files = get_files_changed_from(
                changed_from,
                project_path,
                exclude_patterns=effective_excludes,
            )
        except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
            click.echo(f"Error: unable to run git diff for --changed-from '{changed_from}': {exc}", err=True)
            raise SystemExit(1) from exc
        changed_files = filter_excluded_paths(
            changed_files,
            project_root=project_path,
            exclude_patterns=effective_excludes,
        )

        _scope_results_to_changed_files(
            results,
            changed_files=changed_files,
            project_root=project_path,
        )
        scope_metadata = {
            "mode": "changed-files",
            "changed_from": changed_from,
            "changed_files_count": len(changed_files),
            "changed_files": sorted(
                changed_path.relative_to(project_path.resolve()).as_posix()
                if changed_path.is_relative_to(project_path.resolve())
                else changed_path.as_posix()
                for changed_path in changed_files
            ),
        }
    if effective_group_filter is not None and not results and effective_output_format == "text":
        click.echo(f"No rules matched group '{effective_group_filter}'.")
    failed = sum(1 for result in results if not result.passed and not result.warned)
    if effective_output_format == "json":
        click.echo(
            json.dumps(
                format_results_json(
                    results,
                    violation_counts=violation_counts,
                    scope=scope_metadata,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if scope_metadata is not None:
            click.echo(
                f"Scope: changed-files mode from '{changed_from}' "
                f"({scope_metadata['changed_files_count']} changed Python files)"
            )
        print_results(results, quiet=bool(effective_quiet))

    if github_annotations:
        for annotation in format_github_annotations(results, project_root=project_path):
            click.echo(annotation, err=True)
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


@cli.command("install-hook")
@click.argument(
    "path",
    required=False,
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def install_hook(path: Path) -> None:
    """Install an Archetype-managed git pre-commit hook."""
    target = path.resolve()
    try:
        repo_root, hook_path = _resolve_git_hook_paths(target)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    try:
        hook_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        click.echo(f"Error: unable to create hooks directory '{hook_path.parent}': {exc}", err=True)
        raise SystemExit(1) from exc

    existing: str | None = None
    if hook_path.exists():
        try:
            existing = hook_path.read_text(encoding="utf-8")
        except OSError as exc:
            click.echo(f"Error: unable to read existing hook '{hook_path}': {exc}", err=True)
            raise SystemExit(1) from exc

    content, status = _render_pre_commit_hook(existing)
    if status != "unchanged":
        try:
            hook_path.write_text(content, encoding="utf-8")
            hook_path.chmod(hook_path.stat().st_mode | 0o111)
        except OSError as exc:
            click.echo(f"Error: unable to write hook '{hook_path}': {exc}", err=True)
            raise SystemExit(1) from exc

    if status == "created":
        click.echo(f"Installed pre-commit hook at {hook_path}")
    elif status == "updated":
        click.echo(f"Updated Archetype block in pre-commit hook at {hook_path}")
    elif status == "appended":
        click.echo(f"Appended Archetype block to existing pre-commit hook at {hook_path}")
    else:
        click.echo(f"Archetype pre-commit hook already installed at {hook_path}")
    click.echo(f"Hook command: archetype check {repo_root}")
    raise SystemExit(0)
