"""Tests for top-level public API exports."""

from __future__ import annotations

from archetype import module


def test_module_is_exported() -> None:
    """from archetype import module should work and return a callable."""
    # The fix ensures module is the real function, not None
    assert callable(module)
    assert module.__name__ == "module"
