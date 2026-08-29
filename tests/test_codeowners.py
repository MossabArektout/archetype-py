"""Tests for CODEOWNERS parsing and path-to-owner lookup."""

from __future__ import annotations

from pathlib import Path

from archetype.analysis.codeowners import Codeowners, load_codeowners, parse_codeowners_text


def test_parse_ignores_comments_and_blank_lines() -> None:
    codeowners = parse_codeowners_text(
        "\n".join(
            [
                "# top comment",
                "",
                "myapp/db/ @acme/data-team  # trailing comment",
                "   ",
            ]
        )
    )
    assert codeowners.owners_for("myapp/db/session.py") == ("@acme/data-team",)


def test_exact_file_match() -> None:
    codeowners = parse_codeowners_text("myapp/api/users.py @acme/api-team")
    assert codeowners.owners_for("myapp/api/users.py") == ("@acme/api-team",)
    assert codeowners.owners_for("myapp/api/other.py") == ()


def test_directory_pattern_matches_nested_files() -> None:
    codeowners = parse_codeowners_text("myapp/db/ @acme/data-team")
    assert codeowners.owners_for("myapp/db/session.py") == ("@acme/data-team",)
    assert codeowners.owners_for("myapp/db/internal/engine.py") == ("@acme/data-team",)
    assert codeowners.owners_for("myapp/api/users.py") == ()


def test_anchored_pattern_only_matches_from_root() -> None:
    codeowners = parse_codeowners_text("/myapp/db/ @acme/data-team")
    assert codeowners.owners_for("myapp/db/session.py") == ("@acme/data-team",)
    assert codeowners.owners_for("vendor/myapp/db/session.py") == ()


def test_unanchored_pattern_matches_at_any_depth() -> None:
    codeowners = parse_codeowners_text("db/ @acme/data-team")
    assert codeowners.owners_for("myapp/db/session.py") == ("@acme/data-team",)
    assert codeowners.owners_for("db/session.py") == ("@acme/data-team",)


def test_glob_pattern_matches_by_extension() -> None:
    codeowners = parse_codeowners_text("*.sql @acme/data-team")
    assert codeowners.owners_for("myapp/db/migrations/001.sql") == ("@acme/data-team",)
    assert codeowners.owners_for("myapp/api/users.py") == ()


def test_wildcard_star_is_a_catch_all_default_owner() -> None:
    codeowners = parse_codeowners_text("* @acme/platform-team")
    assert codeowners.owners_for("anything/at/all.py") == ("@acme/platform-team",)


def test_last_matching_pattern_wins() -> None:
    codeowners = parse_codeowners_text(
        "\n".join(
            [
                "* @acme/platform-team",
                "myapp/db/ @acme/data-team",
            ]
        )
    )
    assert codeowners.owners_for("myapp/db/session.py") == ("@acme/data-team",)
    assert codeowners.owners_for("myapp/api/users.py") == ("@acme/platform-team",)


def test_multiple_owners_on_one_line() -> None:
    codeowners = parse_codeowners_text("myapp/db/ @acme/data-team @acme/platform-team")
    assert codeowners.owners_for("myapp/db/session.py") == (
        "@acme/data-team",
        "@acme/platform-team",
    )


def test_no_match_returns_empty_tuple() -> None:
    codeowners = parse_codeowners_text("myapp/db/ @acme/data-team")
    assert codeowners.owners_for("unrelated/path.py") == ()


def test_empty_codeowners_is_empty() -> None:
    assert Codeowners().is_empty is True
    assert parse_codeowners_text("myapp/db/ @acme/data-team").is_empty is False


def test_load_codeowners_prefers_github_directory(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("myapp/db/ @acme/data-team", encoding="utf-8")
    (tmp_path / "CODEOWNERS").write_text("myapp/db/ @acme/root-team", encoding="utf-8")

    codeowners = load_codeowners(tmp_path)

    assert codeowners.owners_for("myapp/db/session.py") == ("@acme/data-team",)


def test_load_codeowners_falls_back_to_root(tmp_path: Path) -> None:
    (tmp_path / "CODEOWNERS").write_text("myapp/db/ @acme/root-team", encoding="utf-8")

    codeowners = load_codeowners(tmp_path)

    assert codeowners.owners_for("myapp/db/session.py") == ("@acme/root-team",)


def test_load_codeowners_falls_back_to_docs(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "CODEOWNERS").write_text("myapp/db/ @acme/docs-team", encoding="utf-8")

    codeowners = load_codeowners(tmp_path)

    assert codeowners.owners_for("myapp/db/session.py") == ("@acme/docs-team",)


def test_load_codeowners_returns_empty_when_no_file_exists(tmp_path: Path) -> None:
    codeowners = load_codeowners(tmp_path)

    assert codeowners.is_empty is True
    assert codeowners.owners_for("myapp/db/session.py") == ()
