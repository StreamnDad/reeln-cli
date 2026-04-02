"""Tests for the native bridge module."""

from __future__ import annotations


def test_import_succeeds() -> None:
    """reeln_native should be importable as a required dependency."""
    from reeln.native import get_native

    mod = get_native()
    assert hasattr(mod, "__version__")


def test_get_native_returns_module() -> None:
    """get_native() returns the reeln_native module."""
    from reeln.native import get_native

    mod = get_native()
    # Verify it exposes expected functions
    assert callable(getattr(mod, "probe", None))
