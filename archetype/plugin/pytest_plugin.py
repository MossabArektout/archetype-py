"""Pytest plugin hooks for auto-discovering and executing architecture rules."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from archetype.dsl.query import load_project
from archetype.reporter import format_violation
from archetype.rule import registry


def pytest_collect_file(file_path: Path, parent: pytest.Collector):  # type: ignore[override]
    """Collect only architecture.py files as Archetype rule containers."""
    if file_path.name == "architecture.py":
        return ArchetypeFile.from_parent(parent, path=file_path)
    return None


class ArchetypeFile(pytest.File):
    """Custom collector for architecture.py files."""

    def collect(self):
        registry.clear()
        project_root = self.path.parent
        load_project(project_root)

        module_name = f"_archetype_pytest_architecture_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, self.path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load architecture module at {self.path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for rule_func in registry._rules:
            rule_name = getattr(rule_func, "_rule_name", rule_func.__name__)
            yield ArchetypeItem.from_parent(
                self, name=rule_name, rule_func=rule_func, file_path=self.path
            )


class ArchetypeItem(pytest.Item):
    """Custom pytest test item wrapping a single architecture rule callable."""

    def __init__(
        self,
        *,
        name: str,
        parent: pytest.Collector,
        rule_func,
        file_path: Path,
    ) -> None:
        super().__init__(name=name, parent=parent)
        self.rule_func = rule_func
        self.file_path = file_path

    def runtest(self) -> None:
        self.rule_func()

    def repr_failure(self, excinfo, style=None):  # type: ignore[override]
        err = excinfo.value
        if isinstance(err, AssertionError):
            violations = getattr(err, "violations", None)
            if violations:
                lines = [f"Rule '{self.name}' violations:"]
                lines.extend(f"  - {format_violation(violation)}" for violation in violations)
                return "\n".join(lines)
        return super().repr_failure(excinfo, style=style)

    def reportinfo(self):
        return self.file_path, None, self.name
