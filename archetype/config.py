"""Configuration loading for CLI behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class CheckConfig:
    """Resolved defaults for `archetype check`."""

    output_format: str | None = None
    quiet: bool | None = None
    group_filter: str | None = None
    exclude_patterns: list[str] | None = None
    workers: int | None = None
    cache: bool | None = None
    rule_policies: dict[str, str] | None = None


def _read_toml(path: Path) -> dict[str, object]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid {path.name}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid {path.name}: expected a TOML table/object.")
    return payload


def _ensure_bool(raw: object, *, field: str, source: str) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"Invalid {source} '{field}': expected a boolean.")
    return raw


def _ensure_str(raw: object, *, field: str, source: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Invalid {source} '{field}': expected a non-empty string.")
    return raw


def _ensure_str_list(raw: object, *, field: str, source: str) -> list[str]:
    if isinstance(raw, str):
        return [raw]
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(
            f"Invalid {source} '{field}': expected a string or array of strings."
        )
    return list(raw)


def _ensure_workers(raw: object, *, source: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError(f"Invalid {source} 'workers': expected an integer >= 1.")
    return raw


def _ensure_policy(raw: object, *, field: str, source: str) -> str:
    policy = _ensure_str(raw, field=field, source=source)
    if policy not in {"error", "warning", "off"}:
        raise ValueError(
            f"Invalid {source} '{field}': expected 'error', 'warning', or 'off'."
        )
    return policy


def _parse_rule_policies(raw: object, *, source: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid {source} 'rules': expected a TOML table.")

    policies: dict[str, str] = {}
    for rule_name, raw_rule_cfg in raw.items():
        if not isinstance(rule_name, str) or not rule_name.strip():
            raise ValueError(f"Invalid {source} 'rules': expected non-empty rule names.")

        if isinstance(raw_rule_cfg, str):
            policies[rule_name] = _ensure_policy(
                raw_rule_cfg,
                field=f"rules.{rule_name}",
                source=source,
            )
            continue

        if isinstance(raw_rule_cfg, dict):
            if "policy" not in raw_rule_cfg:
                raise ValueError(
                    f"Invalid {source} 'rules.{rule_name}': missing 'policy'."
                )
            policies[rule_name] = _ensure_policy(
                raw_rule_cfg["policy"],
                field=f"rules.{rule_name}.policy",
                source=source,
            )
            continue

        raise ValueError(
            f"Invalid {source} 'rules.{rule_name}': expected a policy string or table."
        )
    return policies


def _parse_check_config(
    payload: dict[str, object],
    *,
    scope: str,
) -> CheckConfig:
    check_cfg: dict[str, object] = {}
    raw_defaults = payload.get("defaults")
    if isinstance(raw_defaults, dict):
        check_cfg = raw_defaults
    else:
        check_cfg = payload

    output_format: str | None = None
    quiet: bool | None = None
    group_filter: str | None = None
    exclude_patterns: list[str] | None = None
    workers: int | None = None
    cache: bool | None = None
    rule_policies = _parse_rule_policies(payload.get("rules"), source=scope)

    if "format" in check_cfg:
        format_value = _ensure_str(check_cfg["format"], field="format", source=scope)
        if format_value not in {"text", "json", "sarif"}:
            raise ValueError(
                f"Invalid {scope} 'format': expected 'text', 'json', or 'sarif'."
            )
        output_format = format_value

    if "quiet" in check_cfg:
        quiet = _ensure_bool(check_cfg["quiet"], field="quiet", source=scope)

    if "group" in check_cfg:
        group_filter = _ensure_str(check_cfg["group"], field="group", source=scope)

    if "exclude" in check_cfg:
        exclude_patterns = _ensure_str_list(
            check_cfg["exclude"], field="exclude", source=scope
        )
    elif "excludes" in check_cfg:
        exclude_patterns = _ensure_str_list(
            check_cfg["excludes"], field="excludes", source=scope
        )

    if "workers" in check_cfg:
        workers = _ensure_workers(check_cfg["workers"], source=scope)

    if "cache" in check_cfg:
        cache = _ensure_bool(check_cfg["cache"], field="cache", source=scope)

    return CheckConfig(
        output_format=output_format,
        quiet=quiet,
        group_filter=group_filter,
        exclude_patterns=exclude_patterns,
        workers=workers,
        cache=cache,
        rule_policies=rule_policies,
    )


def load_check_config(project_root: Path) -> CheckConfig:
    """Load check defaults from archetype.toml, falling back to pyproject.toml."""
    root = project_root.resolve()

    archetype_config_path = root / "archetype.toml"
    if archetype_config_path.is_file():
        payload = _read_toml(archetype_config_path)
        return _parse_check_config(payload, scope="archetype.toml")

    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        return CheckConfig(exclude_patterns=[])

    pyproject_payload = _read_toml(pyproject_path)
    tool = pyproject_payload.get("tool")
    if not isinstance(tool, dict):
        return CheckConfig(exclude_patterns=[])
    archetype = tool.get("archetype")
    if not isinstance(archetype, dict):
        return CheckConfig(exclude_patterns=[])
    return _parse_check_config(archetype, scope="[tool.archetype]")


def load_exclude_patterns(project_root: Path) -> list[str]:
    """Backward-compatible helper for exclusion-only lookups."""
    return list(load_check_config(project_root).exclude_patterns or [])
