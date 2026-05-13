"""Rule decorator and rule registration primitives for architecture checks."""

from __future__ import annotations

import threading
from functools import wraps
from pathlib import Path
from typing import Callable

from archetype.analysis.git_utils import get_files_modified_after, parse_date_string
from archetype.analysis.models import RuleResult
from archetype.dsl import query as query_module


RuleFn = Callable[[], None | RuleResult]
RuleEntry = tuple[RuleFn, str | None]
_current_group = threading.local()


def _get_current_group() -> str | None:
    return getattr(_current_group, "name", None)


class _RuleGroupContext:
    def __init__(self, name: str) -> None:
        self._name = name

    def __enter__(self) -> _RuleGroupContext:
        if _get_current_group() is not None:
            raise ValueError("Rule groups cannot be nested.")
        setattr(_current_group, "name", self._name)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        setattr(_current_group, "name", None)
        return False


def group(name: str) -> _RuleGroupContext:
    """Context manager that assigns a group name to rules defined inside it."""
    return _RuleGroupContext(name)


class RuleRegistry:
    """In-memory registry for architecture rule callables."""

    def __init__(self) -> None:
        self._rules: list[RuleFn] = []
        self._entries: list[RuleEntry] = []

    def register(self, func: RuleFn) -> None:
        """Register a rule function."""
        group_name = getattr(func, "_group", None)
        self._rules.append(func)
        self._entries.append((func, group_name))

    def clear(self) -> None:
        """Remove all registered rule functions."""
        self._rules.clear()
        self._entries.clear()

    def run_all(self, group_filter: str | None = None) -> list[RuleResult]:
        """Execute all registered rules and collect results."""
        results: list[RuleResult] = []
        for func, group_name in self._entries:
            if group_filter is not None and group_name != group_filter:
                continue
            rule_name = getattr(func, "_rule_name", func.__name__)
            since_date = getattr(func, "_since_date", None)
            if getattr(func, "_skipped", False):
                results.append(
                    RuleResult(
                        name=rule_name,
                        passed=True,
                        skipped=True,
                        skip_reason=getattr(func, "_skip_reason", None),
                        group=group_name,
                        since_date=since_date,
                    )
                )
                continue
            try:
                outcome = func()
                if isinstance(outcome, RuleResult):
                    if outcome.group is None:
                        outcome.group = group_name
                    if outcome.since_date is None:
                        outcome.since_date = since_date
                    results.append(outcome)
                else:
                    results.append(
                        RuleResult(
                            name=rule_name,
                            passed=True,
                            group=group_name,
                            since_date=since_date,
                        )
                    )
            except AssertionError as exc:
                violations = getattr(exc, "violations", [])
                filtered_violations = getattr(exc, "filtered_violations", [])
                results.append(
                    RuleResult(
                        name=rule_name,
                        passed=False,
                        violations=violations,
                        group=group_name,
                        since_date=getattr(exc, "since_date", since_date),
                        filtered_violations=filtered_violations,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    RuleResult(
                        name=rule_name,
                        passed=False,
                        error=exc,
                        group=group_name,
                        since_date=since_date,
                    )
                )
        return results


registry = RuleRegistry()


def rule(name: str) -> Callable[[RuleFn], RuleFn]:
    """Decorator for registering architecture rules with a display name."""

    def decorator(func: RuleFn) -> RuleFn:
        group_name = _get_current_group()
        setattr(func, "_rule_name", name)
        setattr(func, "_group", group_name)

        @wraps(func)
        def wrapped() -> None | RuleResult:
            return func()

        setattr(wrapped, "_rule_name", name)
        setattr(wrapped, "_group", group_name)
        if getattr(func, "_skipped", False):
            setattr(wrapped, "_skipped", True)
            setattr(wrapped, "_skip_reason", getattr(func, "_skip_reason", None))
        if getattr(func, "_since_date", None) is not None:
            setattr(wrapped, "_since_date", getattr(func, "_since_date"))
        registry.register(wrapped)
        return wrapped

    return decorator


def warn(func: RuleFn) -> RuleFn:
    """Decorator that turns assertion violations into non-blocking warnings."""

    @wraps(func)
    def wrapped() -> None | RuleResult:
        rule_name = getattr(
            wrapped,
            "_rule_name",
            getattr(func, "_rule_name", func.__name__),
        )
        try:
            func()
            return RuleResult(name=rule_name, passed=True, is_warning=True)
        except AssertionError as exc:
            violations = getattr(exc, "violations", [])
            return RuleResult(
                name=rule_name,
                passed=False,
                violations=violations,
                warned=True,
                is_warning=True,
            )

    return wrapped


def skip(
    func: RuleFn | str | None = None,
    *,
    reason: str | None = None,
) -> RuleFn | Callable[[RuleFn], RuleFn]:
    """Decorator that marks a rule as temporarily skipped."""

    skip_reason = reason
    if isinstance(func, str) and reason is None:
        skip_reason = func

    def decorator(rule_func: RuleFn) -> RuleFn:
        @wraps(rule_func)
        def wrapped() -> RuleResult:
            rule_name = getattr(
                wrapped,
                "_rule_name",
                getattr(rule_func, "_rule_name", rule_func.__name__),
            )
            return RuleResult(
                name=rule_name,
                passed=True,
                skipped=True,
                skip_reason=skip_reason,
                violations=[],
            )

        setattr(wrapped, "_skipped", True)
        setattr(wrapped, "_skip_reason", skip_reason)
        return wrapped

    if callable(func):
        return decorator(func)
    return decorator


def since(date_str: str) -> Callable[[RuleFn], RuleFn]:
    """Decorator that scopes rule violations to files modified after date_str."""
    parse_date_string(date_str)

    def decorator(func: RuleFn) -> RuleFn:
        setattr(func, "_since_date", date_str)

        @wraps(func)
        def wrapped() -> None | RuleResult:
            rule_name = getattr(
                wrapped,
                "_rule_name",
                getattr(func, "_rule_name", func.__name__),
            )
            try:
                outcome = func()
            except AssertionError as exc:
                violations = getattr(exc, "violations", [])
                project_root = query_module._current_root

                recent_files = (
                    get_files_modified_after(date_str, project_root)
                    if project_root is not None
                    else None
                )

                scoped_violations = []
                filtered_violations = []
                for violation in violations:
                    violation_file = Path(violation.file)
                    if not violation_file.is_absolute() and project_root is not None:
                        violation_path = (project_root / violation_file).resolve()
                    else:
                        violation_path = violation_file.resolve()

                    if recent_files is None or violation_path in recent_files:
                        scoped_violations.append(violation)
                    else:
                        filtered_violations.append(violation)

                if not scoped_violations:
                    return RuleResult(
                        name=rule_name,
                        passed=True,
                        since_date=date_str,
                        filtered_violations=filtered_violations,
                    )

                filtered_exc = AssertionError(str(exc))
                setattr(filtered_exc, "violations", scoped_violations)
                setattr(filtered_exc, "since_date", date_str)
                setattr(filtered_exc, "filtered_violations", filtered_violations)
                raise filtered_exc from None

            if isinstance(outcome, RuleResult):
                if outcome.since_date is None:
                    outcome.since_date = date_str
                return outcome

            return RuleResult(name=rule_name, passed=True, since_date=date_str)

        setattr(wrapped, "_since_date", date_str)
        return wrapped

    return decorator
