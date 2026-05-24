"""Baseline snapshot and suppression helpers for legacy violations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from archetype.analysis.models import RuleResult, Violation

BASELINE_VERSION = 1


@dataclass(frozen=True)
class ViolationCounts:
    """Counts describing baseline suppression outcome."""

    total: int
    new: int
    suppressed: int


def _normalize_violation_file(file: Path, project_root: Path) -> str:
    resolved_root = project_root.resolve()
    resolved_file = (project_root / file).resolve() if not file.is_absolute() else file.resolve()
    try:
        return resolved_file.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_file.as_posix()


def _rule_violation_key(
    *,
    result: RuleResult,
    violation: Violation,
    project_root: Path,
) -> tuple[str | int | None, ...]:
    return (
        result.name,
        result.group,
        result.since_date,
        violation.module,
        _normalize_violation_file(violation.file, project_root),
        violation.line,
        violation.message,
    )


def build_baseline_payload(results: list[RuleResult], project_root: Path) -> Mapping[str, Any]:
    """Build a JSON-serializable baseline payload from current violations."""
    entries: list[dict[str, Any]] = []
    for result in results:
        if result.skipped or result.error is not None:
            continue
        for violation in result.violations:
            entries.append(
                {
                    "rule": result.name,
                    "group": result.group,
                    "since_date": result.since_date,
                    "module": violation.module,
                    "file": _normalize_violation_file(violation.file, project_root),
                    "line": violation.line,
                    "message": violation.message,
                }
            )

    entries.sort(
        key=lambda item: (
            item["rule"],
            item["group"] or "",
            item["since_date"] or "",
            item["module"],
            item["file"],
            item["line"],
            item["message"],
        )
    )
    return {"version": BASELINE_VERSION, "violations": entries}


def write_baseline(path: Path, payload: Mapping[str, Any]) -> None:
    """Write baseline JSON to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _coerce_str(value: Any, field_name: str, index: int) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid baseline violation at index {index}: '{field_name}' must be a string."
        )
    return value


def _coerce_optional_str(value: Any, field_name: str, index: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid baseline violation at index {index}: '{field_name}' must be a string or null."
        )
    return value


def _coerce_int(value: Any, field_name: str, index: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"Invalid baseline violation at index {index}: '{field_name}' must be an integer."
        )
    return value


def load_baseline(path: Path) -> Counter[tuple[str | int | None, ...]]:
    """Load baseline JSON and return a counter keyed by normalized violations."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid baseline JSON at {path}: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise ValueError(f"Invalid baseline format at {path}: expected JSON object.")

    violations = raw.get("violations")
    if not isinstance(violations, list):
        raise ValueError(
            f"Invalid baseline format at {path}: missing or invalid 'violations' array."
        )

    counter: Counter[tuple[str | int | None, ...]] = Counter()
    for index, entry in enumerate(violations):
        if not isinstance(entry, Mapping):
            raise ValueError(f"Invalid baseline violation at index {index}: expected object.")
        key = (
            _coerce_str(entry.get("rule"), "rule", index),
            _coerce_optional_str(entry.get("group"), "group", index),
            _coerce_optional_str(entry.get("since_date"), "since_date", index),
            _coerce_str(entry.get("module"), "module", index),
            _coerce_str(entry.get("file"), "file", index),
            _coerce_int(entry.get("line"), "line", index),
            _coerce_str(entry.get("message"), "message", index),
        )
        counter[key] += 1
    return counter


def apply_baseline(
    results: list[RuleResult],
    baseline_counter: Counter[tuple[str | int | None, ...]],
    project_root: Path,
) -> ViolationCounts:
    """Suppress baseline violations in-place and return violation counts."""
    total = 0
    new = 0
    suppressed = 0

    for result in results:
        if result.skipped or result.error is not None:
            continue
        if not result.violations:
            continue

        remaining: list[Violation] = []
        hidden: list[Violation] = []
        for violation in result.violations:
            total += 1
            key = _rule_violation_key(result=result, violation=violation, project_root=project_root)
            if baseline_counter[key] > 0:
                baseline_counter[key] -= 1
                suppressed += 1
                hidden.append(violation)
            else:
                new += 1
                remaining.append(violation)

        result.violations = remaining
        if hidden:
            result.suppressed_violations.extend(hidden)
        if not remaining:
            result.passed = True
            result.warned = False

    return ViolationCounts(total=total, new=new, suppressed=suppressed)
