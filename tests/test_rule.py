"""Tests for rule registration and execution behavior."""

import time
import importlib
import types
from pathlib import Path

import pytest

from archetype.analysis.models import Violation
from archetype.rule import group, registry, rule, skip, use, warn

rule_module = importlib.import_module("archetype.rule")


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    registry.clear()
    yield
    registry.clear()


def test_decorated_function_is_registered() -> None:
    @rule("registered_rule")
    def sample_rule() -> None:
        return None

    assert registry._rules == [sample_rule]


def test_run_all_returns_passing_result_when_rule_succeeds() -> None:
    @rule("passing_rule")
    def passing_rule() -> None:
        return None

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "passing_rule"
    assert results[0].passed is True
    assert results[0].violations == []
    assert results[0].error is None


def test_run_all_captures_assertion_error_violations() -> None:
    violations = [
        Violation(
            module="simple_project.api",
            file=Path("simple_project/api.py"),
            line=1,
            message="API must not import DB directly.",
        )
    ]

    @rule("failing_rule")
    def failing_rule() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", violations)
        raise exc

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "failing_rule"
    assert results[0].passed is False
    assert results[0].violations == violations
    assert results[0].error is None


def test_run_all_captures_non_assertion_error() -> None:
    @rule("broken_rule")
    def broken_rule() -> None:
        raise RuntimeError("unexpected error")

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "broken_rule"
    assert results[0].passed is False
    assert isinstance(results[0].error, RuntimeError)


def test_clear_removes_all_registered_rules() -> None:
    @rule("rule_one")
    def rule_one() -> None:
        return None

    @rule("rule_two")
    def rule_two() -> None:
        return None

    assert len(registry._rules) == 2
    registry.clear()
    assert registry._rules == []


def test_warned_rule_returns_warned_result_on_assertion() -> None:
    violations = [
        Violation(
            module="simple_project.api",
            file=Path("simple_project/api.py"),
            line=1,
            message="API must not import DB directly.",
        )
    ]

    @rule("warned-failing-rule")
    @warn
    def warned_failing_rule() -> None:
        exc = AssertionError("rule failed")
        setattr(exc, "violations", violations)
        raise exc

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "warned-failing-rule"
    assert results[0].passed is False
    assert results[0].warned is True
    assert results[0].is_warning is True
    assert results[0].violations == violations
    assert results[0].error is None


def test_warned_rule_that_passes_is_marked_as_warning_rule() -> None:
    @rule("warned-passing-rule")
    @warn
    def warned_passing_rule() -> None:
        return None

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "warned-passing-rule"
    assert results[0].passed is True
    assert results[0].warned is False
    assert results[0].is_warning is True


def test_registry_run_all_includes_warned_and_normal_results() -> None:
    @rule("normal-pass")
    def normal_pass() -> None:
        return None

    @rule("warned-fail")
    @warn
    def warned_fail() -> None:
        exc = AssertionError("warn-only failure")
        setattr(exc, "violations", [])
        raise exc

    results = registry.run_all()

    assert len(results) == 2
    by_name = {result.name: result for result in results}
    assert by_name["normal-pass"].passed is True
    assert by_name["normal-pass"].warned is False
    assert by_name["warned-fail"].passed is False
    assert by_name["warned-fail"].warned is True
    assert by_name["warned-fail"].is_warning is True


def test_warned_rules_do_not_count_as_hard_failures_for_ci() -> None:
    @rule("warned-fail")
    @warn
    def warned_fail() -> None:
        exc = AssertionError("warn-only failure")
        setattr(exc, "violations", [])
        raise exc

    results = registry.run_all()
    hard_failures = sum(1 for result in results if not result.passed and not result.warned)

    assert hard_failures == 0


def test_skipped_rule_is_not_executed_in_run_all() -> None:
    calls = {"count": 0}

    @rule("skipped-rule")
    @skip
    def skipped_rule() -> None:
        calls["count"] += 1

    results = registry.run_all()

    assert len(results) == 1
    assert calls["count"] == 0


def test_skipped_rule_result_marks_skipped_and_passed() -> None:
    @rule("skipped-rule")
    @skip
    def skipped_rule() -> None:
        raise AssertionError("must never execute")

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "skipped-rule"
    assert results[0].skipped is True
    assert results[0].passed is True
    assert results[0].violations == []


def test_skip_reason_is_stored_in_rule_result() -> None:
    reason = "Fixing in refactor-auth branch"

    @rule("skipped-with-reason")
    @skip(reason=reason)
    def skipped_with_reason() -> None:
        raise AssertionError("must never execute")

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].skipped is True
    assert results[0].skip_reason == reason


def test_skip_without_reason_sets_none_in_rule_result() -> None:
    @rule("skipped-no-reason")
    @skip
    def skipped_no_reason() -> None:
        raise AssertionError("must never execute")

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].skipped is True
    assert results[0].skip_reason is None


def test_skip_without_parentheses_matches_skip_call_without_args() -> None:
    @rule("skip-no-parens")
    @skip
    def skip_no_parens() -> None:
        raise AssertionError("must never execute")

    @rule("skip-empty-parens")
    @skip()
    def skip_empty_parens() -> None:
        raise AssertionError("must never execute")

    results = registry.run_all()
    by_name = {result.name: result for result in results}

    assert by_name["skip-no-parens"].skipped is True
    assert by_name["skip-no-parens"].skip_reason is None
    assert by_name["skip-empty-parens"].skipped is True
    assert by_name["skip-empty-parens"].skip_reason is None


def test_skipped_rules_do_not_count_as_hard_failures_for_ci() -> None:
    @rule("skipped-rule")
    @skip
    def skipped_rule() -> None:
        raise AssertionError("must never execute")

    results = registry.run_all()
    hard_failures = sum(
        1 for result in results if not result.passed and not result.warned
    )

    assert hard_failures == 0


def test_rule_result_includes_group_when_rule_registered_in_group() -> None:
    with group("Layer boundaries"):

        @rule("grouped-rule")
        def grouped_rule() -> None:
            return None

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].name == "grouped-rule"
    assert results[0].group == "Layer boundaries"


def test_rule_with_timeout_completing_in_time_passes_normally() -> None:
    @rule("fast-rule", timeout=0.2)
    def fast_rule() -> None:
        time.sleep(0.01)

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].timed_out is False


def test_rule_exceeding_timeout_is_marked_timed_out_and_failed() -> None:
    @rule("slow-rule", timeout=0.05)
    def slow_rule() -> None:
        time.sleep(0.5)

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].timed_out is True


def test_timed_out_rule_result_includes_timeout_seconds() -> None:
    @rule("slow-rule", timeout=0.05)
    def slow_rule() -> None:
        time.sleep(0.5)

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].timeout_seconds == 0.05


def test_rule_without_timeout_avoids_thread_execution_path(monkeypatch) -> None:
    class GuardThread:
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401
            raise AssertionError("thread should not be used without timeout")

    monkeypatch.setattr(rule_module.threading, "Thread", GuardThread)

    @rule("no-timeout-rule")
    def no_timeout_rule() -> None:
        return None

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].timed_out is False


def test_registering_two_different_functions_with_same_name_raises() -> None:
    @rule("shared-name")
    def first_rule() -> None:
        return None

    with pytest.raises(ValueError, match="already registered"):

        @rule("shared-name")
        def second_rule() -> None:
            return None


def test_reregistering_the_same_function_object_is_a_noop() -> None:
    @rule("idempotent-rule")
    def idempotent_rule() -> None:
        return None

    registry.register(idempotent_rule)
    registry.register(idempotent_rule)

    assert registry._rules.count(idempotent_rule) == 1


def test_use_registers_all_rules_found_in_a_module() -> None:
    shared = types.ModuleType("shared_rules_fixture")

    @rule("shared-rule-one")
    def shared_rule_one() -> None:
        return None

    @rule("shared-rule-two")
    def shared_rule_two() -> None:
        return None

    registry.clear()
    shared.shared_rule_one = shared_rule_one
    shared.shared_rule_two = shared_rule_two
    shared.not_a_rule = lambda: None

    use(shared)

    names = {result.name for result in registry.run_all()}
    assert names == {"shared-rule-one", "shared-rule-two"}


def test_use_accepts_a_single_rule_function() -> None:
    @rule("standalone-shared-rule")
    def standalone_shared_rule() -> None:
        return None

    registry.clear()
    use(standalone_shared_rule)

    results = registry.run_all()
    assert len(results) == 1
    assert results[0].name == "standalone-shared-rule"


def test_use_accepts_an_iterable_of_rule_functions() -> None:
    @rule("iterable-rule-one")
    def iterable_rule_one() -> None:
        return None

    @rule("iterable-rule-two")
    def iterable_rule_two() -> None:
        return None

    registry.clear()
    use([iterable_rule_one, iterable_rule_two])

    names = {result.name for result in registry.run_all()}
    assert names == {"iterable-rule-one", "iterable-rule-two"}


def test_use_can_be_called_immediately_after_the_defining_import() -> None:
    """`use()` right after import must not double-register (see docstring:
    the decorator already registered once during that same import)."""

    @rule("just-decorated-rule")
    def just_decorated_rule() -> None:
        return None

    use(just_decorated_rule)

    assert registry._rules.count(just_decorated_rule) == 1


def test_use_reregisters_after_registry_clear_without_reimport() -> None:
    """Simulates a monorepo pytest collection: the shared module is only
    ever imported once by Python, but `use()` must repopulate the registry
    on every subsequent architecture.py load after it is cleared."""
    shared = types.ModuleType("shared_rules_fixture_reregister")

    @rule("monorepo-shared-rule")
    def monorepo_shared_rule() -> None:
        return None

    shared.monorepo_shared_rule = monorepo_shared_rule

    # First "architecture.py" load.
    registry.clear()
    use(shared)
    assert [r.name for r in registry.run_all()] == ["monorepo-shared-rule"]

    # Second "architecture.py" load in the same process: the module object
    # is the same (no re-import happens), but use() must still repopulate
    # the freshly cleared registry.
    registry.clear()
    use(shared)
    assert [r.name for r in registry.run_all()] == ["monorepo-shared-rule"]


def test_use_rejects_unsupported_argument_types() -> None:
    with pytest.raises(TypeError):
        use(42)


def test_registry_continues_executing_rules_after_timeout() -> None:
    @rule("slow-rule", timeout=0.05)
    def slow_rule() -> None:
        time.sleep(0.5)

    @rule("fast-rule")
    def fast_rule() -> None:
        return None

    results = registry.run_all()
    by_name = {result.name: result for result in results}

    assert len(results) == 2
    assert by_name["slow-rule"].timed_out is True
    assert by_name["slow-rule"].passed is False
    assert by_name["fast-rule"].passed is True
