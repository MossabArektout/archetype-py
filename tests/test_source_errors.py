"""Tests for graceful handling of unreadable or unparsable Python sources."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from archetype.analysis.cache import compute_file_signatures
from archetype.analysis.imports import SourceReadError, build_import_graph
from archetype.check import cli


def _make_project(tmp_path: Path, *, source: str) -> Path:
    project_path = tmp_path / "project"
    package_path = project_path / "myapp"
    package_path.mkdir(parents=True)
    (package_path / "__init__.py").write_text("", encoding="utf-8")
    (package_path / "api.py").write_text("import myapp.broken\n", encoding="utf-8")
    (package_path / "broken.py").write_text(source, encoding="utf-8")
    (project_path / "architecture.py").write_text(
        "\n".join(
            [
                "from archetype import imports, rule",
                "",
                "@rule('api-must-not-import-db')",
                "def _rule() -> None:",
                "    imports('myapp.api').must_not_import('myapp.db')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return project_path


def test_build_import_graph_raises_source_read_error_on_syntax_error(tmp_path: Path) -> None:
    project_path = _make_project(tmp_path, source="def broken(:\n    pass\n")

    with pytest.raises(SourceReadError) as exc_info:
        build_import_graph(project_path)

    message = str(exc_info.value)
    assert "failed to parse" in message
    assert "myapp/broken.py" in message
    assert "invalid syntax" in message


def test_build_import_graph_raises_source_read_error_on_invalid_encoding(
    tmp_path: Path,
) -> None:
    project_path = _make_project(tmp_path, source="")
    (project_path / "myapp" / "broken.py").write_bytes(b"\xff\xfe\x00invalid\n")

    with pytest.raises(SourceReadError) as exc_info:
        build_import_graph(project_path)

    message = str(exc_info.value)
    assert "failed to read" in message
    assert "myapp/broken.py" in message
    assert "not valid UTF-8" in message


def test_build_import_graph_reports_null_bytes_without_line_noise(tmp_path: Path) -> None:
    project_path = _make_project(tmp_path, source="value = 1\x00\n")

    with pytest.raises(SourceReadError) as exc_info:
        build_import_graph(project_path)

    message = str(exc_info.value)
    assert "null bytes" in message
    assert "unknown line" not in message


def test_build_import_graph_reports_path_relative_to_project_root(tmp_path: Path) -> None:
    project_path = _make_project(tmp_path, source="def broken(:\n    pass\n")

    with pytest.raises(SourceReadError) as exc_info:
        build_import_graph(project_path)

    assert str(project_path) not in str(exc_info.value)


@pytest.mark.parametrize("command", ["check", "doctor", "graph"])
def test_cli_reports_syntax_error_without_traceback(tmp_path: Path, command: str) -> None:
    project_path = _make_project(tmp_path, source="def broken(:\n    pass\n")
    runner = CliRunner()

    result = runner.invoke(cli, [command, str(project_path)])

    assert result.exit_code == 1
    assert "Error: failed to parse" in result.output
    assert "myapp/broken.py" in result.output
    assert "Traceback" not in result.output


def test_cli_check_reports_unreadable_file_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = _make_project(tmp_path, source="value = 1\n")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "broken.py":
            raise PermissionError(13, "Permission denied")
        return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    runner = CliRunner()

    result = runner.invoke(cli, ["check", str(project_path), "--no-cache"])

    assert result.exit_code == 1
    assert "Error: failed to read" in result.output
    assert "myapp/broken.py" in result.output
    assert "Traceback" not in result.output


def test_file_signatures_change_when_permissions_change(tmp_path: Path) -> None:
    """A file becoming unreadable must invalidate the cache even if mtime is unchanged.

    Regression test: signatures used to record mtime only, so a cached graph could
    silently hide a file that had become unreadable since the cache was written.
    """
    project_path = _make_project(tmp_path, source="value = 1\n")
    broken_path = project_path / "myapp" / "broken.py"

    before = compute_file_signatures(project_path)
    mtime_before = broken_path.stat().st_mtime
    os.chmod(broken_path, 0o444)
    try:
        after = compute_file_signatures(project_path)

        assert broken_path.stat().st_mtime == mtime_before
        assert before != after
    finally:
        os.chmod(broken_path, 0o644)


def test_file_signatures_tolerate_unstatable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file that cannot be stat'ed must not raise out of the cache layer."""
    project_path = _make_project(tmp_path, source="value = 1\n")
    original_stat = Path.stat

    # Compared by name rather than resolve(), which would call stat() recursively.
    def fake_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        if self.name == "broken.py":
            raise OSError(2, "No such file or directory")
        return original_stat(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "stat", fake_stat)

    signatures = compute_file_signatures(project_path)

    assert signatures[str(project_path / "myapp" / "broken.py")] == (-1.0, -1)
