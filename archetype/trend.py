"""Trend history recording and reporting for violation counts over time.

`archetype check` already computes a violation count for a single run.
Trend reporting stores that same count (nothing new is calculated) once per
run, in a small JSON Lines file, so it can be reported on later: "we had
340 violations in January, 210 in June, 90 today."
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from archetype.analysis.models import RuleResult
from archetype.baseline import ViolationCounts

TREND_SCHEMA_VERSION = 1
_SPARKLINE_BLOCKS = "▁▂▃▄▅▆▇█"


@dataclass(frozen=True)
class TrendSummary:
    """A single trend record loaded from the trend history file."""

    recorded_at: str
    summary: Mapping[str, int]
    violations: Mapping[str, int]


def build_trend_entry(
    results: list[RuleResult],
    violation_counts: ViolationCounts,
    *,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Build one trend record from the same results and counts already
    computed for a check run — no new analysis is performed."""
    skipped = sum(1 for result in results if result.skipped)
    warned = sum(1 for result in results if result.warned)
    timed_out = sum(1 for result in results if result.timed_out)
    passed = sum(1 for result in results if result.passed and not result.skipped)
    failed = len(results) - passed - warned - skipped - timed_out

    return {
        "schema_version": TREND_SCHEMA_VERSION,
        "recorded_at": recorded_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "skipped": skipped,
            "total": len(results),
        },
        "violations": {
            "total": violation_counts.total,
            "new": violation_counts.new,
            "suppressed": violation_counts.suppressed,
        },
    }


def append_trend_entry(path: Path, entry: Mapping[str, Any]) -> None:
    """Append one trend record as a JSON line to `path`.

    Appending a line at a time (rather than rewriting a JSON array) means a
    CI job never needs to read the existing history just to add one more
    record. This does not guard against two jobs writing concurrently —
    record trend data from a single job per run if that matters to you.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False))
        handle.write("\n")


def load_trend_entries(path: Path) -> list[dict[str, Any]]:
    """Load all trend records from a JSON Lines trend file, in file order."""
    if not path.is_file():
        raise ValueError(f"Trend file not found: {path}")

    entries: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid trend record at {path}:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"Invalid trend record at {path}:{line_number}: expected a JSON object.")
        entries.append(record)
    return entries


def render_sparkline(values: list[int]) -> str:
    """Render a compact terminal sparkline for a series of values."""
    if not values:
        return ""
    lowest, highest = min(values), max(values)
    if highest == lowest:
        return _SPARKLINE_BLOCKS[0] * len(values)
    span = highest - lowest
    scale = len(_SPARKLINE_BLOCKS) - 1
    return "".join(
        _SPARKLINE_BLOCKS[round((value - lowest) / span * scale)] for value in values
    )


def format_trend_text(entries: list[Mapping[str, Any]]) -> str:
    """Build a plain-text trend report: a per-run table, a sparkline, and
    the overall change from the first recorded run to the latest one."""
    if not entries:
        return "No trend data recorded yet."

    header = f"{'Recorded at':<22}{'Violations':>12}{'Passed':>8}{'Failed':>8}{'Warned':>8}"
    lines = [header, "-" * len(header)]

    totals: list[int] = []
    for entry in entries:
        violations = entry.get("violations") or {}
        summary = entry.get("summary") or {}
        total = int(violations.get("total", 0))
        totals.append(total)
        lines.append(
            f"{str(entry.get('recorded_at', '?')):<22}"
            f"{total:>12}"
            f"{int(summary.get('passed', 0)):>8}"
            f"{int(summary.get('failed', 0)):>8}"
            f"{int(summary.get('warned', 0)):>8}"
        )

    lines.append("")
    lines.append(f"Trend ({len(entries)} runs): {render_sparkline(totals)}")

    first_total, last_total = totals[0], totals[-1]
    delta = last_total - first_total
    if delta == 0:
        lines.append(f"{first_total} -> {last_total} violations (no change)")
    elif first_total > 0:
        percent = abs(delta) / first_total * 100
        direction = "down" if delta < 0 else "up"
        lines.append(
            f"{first_total} -> {last_total} violations ({direction} {percent:.1f}%)"
        )
    else:
        lines.append(f"{first_total} -> {last_total} violations")

    return "\n".join(lines)
