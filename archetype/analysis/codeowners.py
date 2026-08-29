"""CODEOWNERS parsing and path-to-owner lookup for violation routing."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

_CODEOWNERS_LOCATIONS = (
    Path(".github/CODEOWNERS"),
    Path("CODEOWNERS"),
    Path("docs/CODEOWNERS"),
)


@dataclass(frozen=True)
class _CodeownersRule:
    pattern: str
    owners: tuple[str, ...]


class Codeowners:
    """Path-to-owner lookup parsed from a CODEOWNERS file.

    Matching follows GitHub's own CODEOWNERS precedence: patterns are
    checked in file order, and the last matching pattern wins, same as
    ``.gitignore``.
    """

    def __init__(self, rules: Iterable[_CodeownersRule] = ()) -> None:
        self._rules = tuple(rules)

    def owners_for(self, path: Path | str) -> tuple[str, ...]:
        """Return the owners of `path` (relative to the project root)."""
        posix_path = Path(path).as_posix().lstrip("/")
        matched: tuple[str, ...] = ()
        for rule in self._rules:
            if _matches(rule.pattern, posix_path):
                matched = rule.owners
        return matched

    @property
    def is_empty(self) -> bool:
        return not self._rules


def _matches(pattern: str, posix_path: str) -> bool:
    if pattern == "*":
        return True

    anchored = pattern.startswith("/")
    directory_hint = pattern.endswith("/")
    core = pattern.strip("/")
    if not core:
        return False

    has_glob = any(char in core for char in "*?[]")
    wrapped_path = f"/{posix_path}/"

    if directory_hint:
        if anchored:
            return posix_path == core or posix_path.startswith(f"{core}/")
        return posix_path.startswith(f"{core}/") or f"/{core}/" in wrapped_path

    if has_glob:
        if anchored:
            return fnmatch(posix_path, core)
        return (
            fnmatch(posix_path, core)
            or fnmatch(posix_path, f"*/{core}")
            or fnmatch(posix_path, f"**/{core}")
        )

    if anchored:
        return posix_path == core or posix_path.startswith(f"{core}/")

    return (
        posix_path == core
        or posix_path.endswith(f"/{core}")
        or f"/{core}/" in wrapped_path
    )


def parse_codeowners_text(text: str) -> Codeowners:
    """Parse CODEOWNERS file contents into a lookup."""
    rules: list[_CodeownersRule] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        pattern = parts[0]
        owners = tuple(parts[1:])
        if not owners:
            continue
        rules.append(_CodeownersRule(pattern=pattern, owners=owners))
    return Codeowners(rules)


def load_codeowners(project_root: Path) -> Codeowners:
    """Load CODEOWNERS from the first standard location GitHub recognizes.

    Checked in order: ``.github/CODEOWNERS``, ``CODEOWNERS``,
    ``docs/CODEOWNERS`` — the same order and locations GitHub itself looks
    in. Returns an empty lookup (matching nothing) if none is found.
    """
    for relative in _CODEOWNERS_LOCATIONS:
        candidate = project_root / relative
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            return parse_codeowners_text(text)
    return Codeowners()
