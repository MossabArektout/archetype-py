"""Tests for trend history recording and reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from archetype.analysis.models import RuleResult
from archetype.baseline import ViolationCounts
from archetype.trend import (
    TREND_SCHEMA_VERSION,
    append_trend_entry,
    build_trend_entry,
    format_trend_text,
    load_trend_entries,
    render_sparkline,
)


def _results() -> list[RuleResult]:
    return [
        RuleResult(name="pass-rule", passed=True),
        RuleResult(name="fail-rule", passed=False),
        RuleResult(name="warn-rule", passed=False, warned=True, is_warning=True),
        RuleResult(name="skipped-rule", passed=True, skipped=True),
    ]


def test_build_trend_entry_reuses_already_computed_counts() -> None:
    entry = build_trend_entry(
        _results(),
        ViolationCounts(total=90, new=90, suppressed=0),
        recorded_at="2026-08-29T00:00:00Z",
    )

    assert entry == {
        "schema_version": TREND_SCHEMA_VERSION,
        "recorded_at": "2026-08-29T00:00:00Z",
        "summary": {"passed": 1, "failed": 1, "warned": 1, "skipped": 1, "total": 4},
        "violations": {"total": 90, "new": 90, "suppressed": 0},
    }


def test_build_trend_entry_defaults_recorded_at_to_now() -> None:
    entry = build_trend_entry(_results(), ViolationCounts(total=0, new=0, suppressed=0))

    assert entry["recorded_at"].endswith("Z")
    assert "T" in entry["recorded_at"]


def test_append_trend_entry_creates_file_and_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "trend.jsonl"

    append_trend_entry(path, {"recorded_at": "2026-01-01T00:00:00Z", "violations": {"total": 1}})

    assert path.is_file()
    assert path.read_text(encoding="utf-8").strip().endswith("}")


def test_append_trend_entry_appends_one_line_per_call(tmp_path: Path) -> None:
    path = tmp_path / "trend.jsonl"

    append_trend_entry(path, {"recorded_at": "2026-01-01T00:00:00Z", "violations": {"total": 340}})
    append_trend_entry(path, {"recorded_at": "2026-06-01T00:00:00Z", "violations": {"total": 210}})
    append_trend_entry(path, {"recorded_at": "2026-08-29T00:00:00Z", "violations": {"total": 90}})

    entries = load_trend_entries(path)

    assert len(entries) == 3
    assert [entry["violations"]["total"] for entry in entries] == [340, 210, 90]


def test_load_trend_entries_ignores_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "trend.jsonl"
    path.write_text(
        '{"recorded_at": "2026-01-01T00:00:00Z", "violations": {"total": 1}}\n'
        "\n"
        '{"recorded_at": "2026-01-02T00:00:00Z", "violations": {"total": 2}}\n',
        encoding="utf-8",
    )

    entries = load_trend_entries(path)

    assert len(entries) == 2


def test_load_trend_entries_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        load_trend_entries(tmp_path / "does-not-exist.jsonl")


def test_load_trend_entries_raises_on_invalid_json_line(tmp_path: Path) -> None:
    path = tmp_path / "trend.jsonl"
    path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid trend record"):
        load_trend_entries(path)


def test_load_trend_entries_raises_when_line_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "trend.jsonl"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected a JSON object"):
        load_trend_entries(path)


def test_render_sparkline_empty_series() -> None:
    assert render_sparkline([]) == ""


def test_render_sparkline_flat_series_uses_lowest_block() -> None:
    assert render_sparkline([5, 5, 5]) == "▁▁▁"


def test_render_sparkline_scales_between_min_and_max() -> None:
    spark = render_sparkline([340, 210, 90])
    assert len(spark) == 3
    assert spark[0] == "█"  # highest value
    assert spark[-1] == "▁"  # lowest value


def test_format_trend_text_reports_no_data() -> None:
    assert format_trend_text([]) == "No trend data recorded yet."


def test_format_trend_text_shows_downward_trend_percentage() -> None:
    entries = [
        {
            "recorded_at": "2026-01-01T00:00:00Z",
            "summary": {"passed": 1, "failed": 1, "warned": 0, "skipped": 0},
            "violations": {"total": 340},
        },
        {
            "recorded_at": "2026-08-29T00:00:00Z",
            "summary": {"passed": 2, "failed": 0, "warned": 0, "skipped": 0},
            "violations": {"total": 90},
        },
    ]

    output = format_trend_text(entries)

    assert "340 -> 90 violations (down 73.5%)" in output
    assert "2026-01-01T00:00:00Z" in output
    assert "2026-08-29T00:00:00Z" in output


def test_format_trend_text_reports_no_change() -> None:
    entries = [
        {"recorded_at": "a", "summary": {}, "violations": {"total": 10}},
        {"recorded_at": "b", "summary": {}, "violations": {"total": 10}},
    ]

    assert "no change" in format_trend_text(entries)
