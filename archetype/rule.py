"""Rule decorator and rule registration primitives for architecture checks."""

from __future__ import annotations

from functools import wraps
from typing import Callable

from archetype.analysis.models import RuleResult


RuleFn = Callable[[], None | RuleResult]


class RuleRegistry:
    """In-memory registry for architecture rule callables."""

    def __init__(self) -> None:
        self._rules: list[RuleFn] = []

    def register(self, func: RuleFn) -> None:
        """Register a rule function."""
        self._rules.append(func)

    def clear(self) -> None:
        """Remove all registered rule functions."""
        self._rules.clear()

    def run_all(self) -> list[RuleResult]:
        """Execute all registered rules and collect results."""
        results: list[RuleResult] = []
        for func in self._rules:
            rule_name = getattr(func, "_rule_name", func.__name__)
            try:
                outcome = func()
                if isinstance(outcome, RuleResult):
                    results.append(outcome)
                else:
                    results.append(RuleResult(name=rule_name, passed=True))
            except AssertionError as exc:
                violations = getattr(exc, "violations", [])
                results.append(
                    RuleResult(name=rule_name, passed=False, violations=violations)
                )
            except Exception as exc:  # noqa: BLE001
                results.append(RuleResult(name=rule_name, passed=False, error=exc))
        return results


registry = RuleRegistry()


def rule(name: str) -> Callable[[RuleFn], RuleFn]:
    """Decorator for registering architecture rules with a display name."""

    def decorator(func: RuleFn) -> RuleFn:
        setattr(func, "_rule_name", name)

        @wraps(func)
        def wrapped() -> None | RuleResult:
            return func()

        setattr(wrapped, "_rule_name", name)
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
