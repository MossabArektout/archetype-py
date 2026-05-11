"""Data models representing modules, imports, and analysis results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Violation:
    """Represents a single architectural rule violation."""

    module: str
    file: Path
    line: int
    message: str


@dataclass
class RuleResult:
    """Represents the execution outcome for a single architecture rule."""

    name: str
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    error: Exception | None = None
    warned: bool = False
    is_warning: bool = False
    skipped: bool = False
    skip_reason: str | None = None
