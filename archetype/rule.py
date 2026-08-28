"""Rule decorator and rule registration primitives for architecture checks."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterable

from archetype.analysis.git_utils import get_files_modified_after, parse_date_string
from archetype.analysis.models import RuleResult
from archetype.dsl import query as query_module


RuleFn = Callable[[], None | RuleResult]
RuleEntry = tuple[RuleFn, str | None]
_current_group = threading.local()
RulePolicy = str


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
        self._by_name: dict[str, RuleFn] = {}

    def register(self, func: RuleFn) -> None:
        """Register a rule function.

        Registering the same function object under a name that is already
        registered is a no-op. This happens naturally when a shared rule
        module's already-decorated functions are re-registered through
        :func:`use` — for example when a monorepo's pytest plugin collects
        several ``architecture.py`` files that each depend on the same
        shared rule package, or when ``use`` runs right after the first
        import already triggered the decorator's own registration.

        Registering two *different* functions under the same name raises,
        since two rules silently sharing one name would be indistinguishable
        in reports.
        """
        rule_name = getattr(func, "_rule_name", func.__name__)
        existing = self._by_name.get(rule_name)
        if existing is not None:
            if existing is func:
                return
            raise ValueError(
                f"Rule name {rule_name!r} is already registered by a "
                "different function. Rule names must be unique within a "
                "project, including rules pulled in from shared rule "
                "packages via archetype.rule.use() — rename one of the "
                "conflicting rules."
            )
        group_name = getattr(func, "_group", None)
        self._rules.append(func)
        self._entries.append((func, group_name))
        self._by_name[rule_name] = func

    def clear(self) -> None:
        """Remove all registered rule functions."""
        self._rules.clear()
        self._entries.clear()
        self._by_name.clear()

    def _apply_policy(self, result: RuleResult, policy: RulePolicy) -> RuleResult:
        result.policy = policy
        if (
            policy == "warning"
            and not result.skipped
            and not result.passed
            and not result.timed_out
        ):
            result.warned = True
            result.is_warning = True
        return result

    def _run_entry(
        self,
        func: RuleFn,
        group_name: str | None,
        policy: RulePolicy = "error",
    ) -> RuleResult:
        rule_name = getattr(func, "_rule_name", func.__name__)
        since_date = getattr(func, "_since_date", None)
        if policy == "off":
            return RuleResult(
                name=rule_name,
                passed=True,
                skipped=True,
                skip_reason="Disabled by policy",
                group=group_name,
                since_date=since_date,
                policy=policy,
            )
        if getattr(func, "_skipped", False):
            return RuleResult(
                name=rule_name,
                passed=True,
                skipped=True,
                skip_reason=getattr(func, "_skip_reason", None),
                group=group_name,
                since_date=since_date,
                policy=policy,
            )
        query_module.clear_pattern_diagnostics()

        def with_pattern_diagnostics(result: RuleResult) -> RuleResult:
            diagnostics = collected_pattern_diagnostics()
            if not diagnostics:
                return result
            result.violation_context = [*diagnostics, *result.violation_context]
            if result.passed and not result.warned:
                result.passed = False
                result.warned = True
                result.is_warning = True
            return result

        timeout = getattr(func, "_timeout", None)
        captured_diagnostics: list[str] | None = None

        def collected_pattern_diagnostics() -> list[str]:
            if captured_diagnostics is not None:
                return captured_diagnostics
            return query_module.get_pattern_diagnostics()

        def run_func() -> None | RuleResult:
            nonlocal captured_diagnostics
            if timeout is None:
                return func()

            outcome: None | RuleResult = None
            caught_error: BaseException | None = None

            def run_rule() -> None:
                nonlocal outcome, caught_error, captured_diagnostics
                query_module.clear_pattern_diagnostics()
                try:
                    outcome = func()
                except BaseException as exc:  # noqa: BLE001
                    caught_error = exc
                finally:
                    captured_diagnostics = query_module.get_pattern_diagnostics()

            timeout_seconds = float(timeout)
            thread = threading.Thread(target=run_rule, daemon=True)
            thread.start()
            thread.join(timeout_seconds)
            if thread.is_alive():
                return RuleResult(
                    name=rule_name,
                    passed=False,
                    timed_out=True,
                    timeout_seconds=timeout_seconds,
                    group=group_name,
                    since_date=since_date,
                    policy=policy,
                )
            if caught_error is not None:
                raise caught_error
            if isinstance(outcome, RuleResult) and outcome.timeout_seconds is None:
                outcome.timeout_seconds = timeout_seconds
            return outcome

        try:
            outcome = run_func()
            if isinstance(outcome, RuleResult):
                if outcome.group is None:
                    outcome.group = group_name
                if outcome.since_date is None:
                    outcome.since_date = since_date
                return self._apply_policy(with_pattern_diagnostics(outcome), policy)
            return self._apply_policy(
                with_pattern_diagnostics(
                    RuleResult(
                        name=rule_name,
                        passed=True,
                        group=group_name,
                        since_date=since_date,
                        policy=policy,
                    )
                ),
                policy,
            )
        except AssertionError as exc:
            violations = getattr(exc, "violations", [])
            filtered_violations = getattr(exc, "filtered_violations", [])
            violation_context = [
                *collected_pattern_diagnostics(),
                *getattr(exc, "violation_context", []),
            ]
            return self._apply_policy(
                RuleResult(
                    name=rule_name,
                    passed=False,
                    violations=violations,
                    group=group_name,
                    since_date=getattr(exc, "since_date", since_date),
                    filtered_violations=filtered_violations,
                    violation_context=violation_context,
                    policy=policy,
                ),
                policy,
            )
        except Exception as exc:  # noqa: BLE001
            return self._apply_policy(
                RuleResult(
                    name=rule_name,
                    passed=False,
                    error=exc,
                    group=group_name,
                    since_date=since_date,
                    violation_context=collected_pattern_diagnostics(),
                    policy=policy,
                ),
                policy,
            )

    def run_all(
        self,
        group_filter: str | None = None,
        workers: int = 1,
        rule_policies: dict[str, str] | None = None,
    ) -> list[RuleResult]:
        """Execute all registered rules and collect results."""
        entries = [
            (func, group_name)
            for func, group_name in self._entries
            if group_filter is None or group_name == group_filter
        ]
        policies = [
            (rule_policies or {}).get(getattr(func, "_rule_name", func.__name__), "error")
            for func, _group_name in entries
        ]
        if workers <= 1:
            return [
                self._run_entry(func, group_name, policy)
                for (func, group_name), policy in zip(entries, policies, strict=True)
            ]
        funcs = [func for func, _group_name in entries]
        groups = [group_name for _func, group_name in entries]
        policy_values = policies
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(self._run_entry, funcs, groups, policy_values))


registry = RuleRegistry()


def rule(name: str, *, timeout: float | None = None) -> Callable[[RuleFn], RuleFn]:
    """Decorator for registering architecture rules with a display name."""

    def decorator(func: RuleFn) -> RuleFn:
        group_name = _get_current_group()
        setattr(func, "_rule_name", name)
        setattr(func, "_group", group_name)
        setattr(func, "_timeout", timeout)

        @wraps(func)
        def wrapped() -> None | RuleResult:
            return func()

        setattr(wrapped, "_rule_name", name)
        setattr(wrapped, "_group", group_name)
        setattr(wrapped, "_timeout", timeout)
        if getattr(func, "_skipped", False):
            setattr(wrapped, "_skipped", True)
            setattr(wrapped, "_skip_reason", getattr(func, "_skip_reason", None))
        if getattr(func, "_since_date", None) is not None:
            setattr(wrapped, "_since_date", getattr(func, "_since_date"))
        registry.register(wrapped)
        return wrapped

    return decorator


def _rule_candidates(source: object) -> list[object]:
    if isinstance(source, ModuleType):
        return list(vars(source).values())
    if callable(source):
        return [source]
    if isinstance(source, Iterable):
        return list(source)
    raise TypeError(
        "use() expects a module, a rule function, or an iterable of rule "
        f"functions, got {type(source).__name__}."
    )


def use(*sources: object) -> None:
    """Register rules exported by one or more shared rule modules or packages.

    This is how a project adopts a shared, installable rule pack (for
    example an internal ``acme_archetype_rules`` package published for use
    across many repositories) instead of copy-pasting the same rules into
    every ``architecture.py``:

        from acme_archetype_rules import base_rules
        from archetype.rule import use

        use(base_rules)

    Each argument may be a module (every ``@rule``-decorated function found
    in it is registered), a single rule function, or an iterable of rule
    functions.

    Unlike a bare ``import``, calling ``use()`` is safe to repeat: Python
    only executes a module's top-level code — including ``@rule``
    decorators — the first time it is imported in a process. A bare import
    of a shared rule module would silently register no rules on any later
    load that reuses Python's module cache (for example, a monorepo's
    pytest plugin collecting a second ``architecture.py`` file after
    clearing the registry). ``use()`` re-registers the already-decorated
    functions directly, independent of whether Python re-executed the
    module.

    A shared rule's severity can still be overridden per project through
    the normal ``archetype.toml`` per-rule ``policy`` setting, matched by
    the rule's registered name — the same mechanism used for local rules.
    """
    for source in sources:
        for candidate in _rule_candidates(source):
            if callable(candidate) and hasattr(candidate, "_rule_name"):
                registry.register(candidate)


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
            violation_context = getattr(exc, "violation_context", [])
            return RuleResult(
                name=rule_name,
                passed=False,
                violations=violations,
                violation_context=violation_context,
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
                    get_files_modified_after(
                        date_str,
                        project_root,
                        exclude_patterns=query_module._exclude_patterns,
                    )
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
                setattr(
                    filtered_exc,
                    "violation_context",
                    getattr(exc, "violation_context", []),
                )
                raise filtered_exc from None

            if isinstance(outcome, RuleResult):
                if outcome.since_date is None:
                    outcome.since_date = date_str
                return outcome

            return RuleResult(name=rule_name, passed=True, since_date=date_str)

        setattr(wrapped, "_since_date", date_str)
        return wrapped

    return decorator
