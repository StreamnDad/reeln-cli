"""Tests for the HookRegistry, get_registry, and reset_registry."""

from __future__ import annotations

from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.registry import FilteredRegistry, HookRegistry, get_registry, reset_registry

# ---------------------------------------------------------------------------
# HookRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_emit() -> None:
    registry = HookRegistry()
    calls: list[HookContext] = []
    registry.register(Hook.PRE_RENDER, calls.append)

    ctx = HookContext(hook=Hook.PRE_RENDER, data={"plan": "test"})
    registry.emit(Hook.PRE_RENDER, ctx)

    assert len(calls) == 1
    assert calls[0] is ctx


def test_registry_multiple_handlers() -> None:
    registry = HookRegistry()
    calls: list[str] = []
    registry.register(Hook.POST_RENDER, lambda ctx: calls.append("a"))
    registry.register(Hook.POST_RENDER, lambda ctx: calls.append("b"))

    registry.emit(Hook.POST_RENDER, HookContext(hook=Hook.POST_RENDER))
    assert calls == ["a", "b"]


def test_registry_emit_no_handlers() -> None:
    """Emitting a hook with no handlers is a no-op."""
    registry = HookRegistry()
    registry.emit(Hook.ON_ERROR, HookContext(hook=Hook.ON_ERROR))


def test_registry_emit_default_context() -> None:
    """When context is None, a default HookContext is created."""
    registry = HookRegistry()
    received: list[HookContext] = []
    registry.register(Hook.ON_GAME_INIT, received.append)

    registry.emit(Hook.ON_GAME_INIT)

    assert len(received) == 1
    assert received[0].hook is Hook.ON_GAME_INIT
    assert received[0].data == {}


def test_registry_handler_exception_caught() -> None:
    """A misbehaving handler doesn't break other handlers."""
    registry = HookRegistry()
    calls: list[str] = []

    registry.register(Hook.ON_ERROR, lambda ctx: calls.append("first"))

    def bad_handler(ctx: HookContext) -> None:
        raise RuntimeError("plugin crash")

    registry.register(Hook.ON_ERROR, bad_handler)
    registry.register(Hook.ON_ERROR, lambda ctx: calls.append("third"))

    registry.emit(Hook.ON_ERROR, HookContext(hook=Hook.ON_ERROR))

    assert calls == ["first", "third"]


def test_registry_has_handlers_true() -> None:
    registry = HookRegistry()
    registry.register(Hook.PRE_RENDER, lambda ctx: None)
    assert registry.has_handlers(Hook.PRE_RENDER) is True


def test_registry_has_handlers_false() -> None:
    registry = HookRegistry()
    assert registry.has_handlers(Hook.PRE_RENDER) is False


def test_registry_has_handlers_empty_after_clear() -> None:
    registry = HookRegistry()
    registry.register(Hook.PRE_RENDER, lambda ctx: None)
    registry.clear()
    assert registry.has_handlers(Hook.PRE_RENDER) is False


def test_registry_clear() -> None:
    registry = HookRegistry()
    registry.register(Hook.PRE_RENDER, lambda ctx: None)
    registry.register(Hook.POST_RENDER, lambda ctx: None)
    registry.clear()

    calls: list[HookContext] = []
    registry.emit(Hook.PRE_RENDER, HookContext(hook=Hook.PRE_RENDER))
    registry.emit(Hook.POST_RENDER, HookContext(hook=Hook.POST_RENDER))
    assert calls == []


def test_registry_different_hooks_independent() -> None:
    registry = HookRegistry()
    pre_calls: list[str] = []
    post_calls: list[str] = []
    registry.register(Hook.PRE_RENDER, lambda ctx: pre_calls.append("pre"))
    registry.register(Hook.POST_RENDER, lambda ctx: post_calls.append("post"))

    registry.emit(Hook.PRE_RENDER, HookContext(hook=Hook.PRE_RENDER))
    assert pre_calls == ["pre"]
    assert post_calls == []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_registry_returns_singleton() -> None:
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_reset_registry_clears_singleton() -> None:
    r1 = get_registry()
    reset_registry()
    r2 = get_registry()
    assert r1 is not r2


def test_reset_registry_when_none() -> None:
    """reset_registry is safe to call even when no registry exists."""
    reset_registry()
    reset_registry()  # double-reset should not raise


# ---------------------------------------------------------------------------
# FilteredRegistry
# ---------------------------------------------------------------------------


def test_filtered_registry_allows_declared_hook() -> None:
    backing = HookRegistry()
    filtered = FilteredRegistry(backing, {Hook.ON_GAME_INIT}, "myplugin")
    calls: list[HookContext] = []
    filtered.register(Hook.ON_GAME_INIT, calls.append)

    backing.emit(Hook.ON_GAME_INIT, HookContext(hook=Hook.ON_GAME_INIT))
    assert len(calls) == 1


def test_filtered_registry_blocks_undeclared_hook() -> None:
    backing = HookRegistry()
    filtered = FilteredRegistry(backing, {Hook.ON_GAME_INIT}, "myplugin")
    calls: list[HookContext] = []
    filtered.register(Hook.ON_ERROR, calls.append)

    backing.emit(Hook.ON_ERROR, HookContext(hook=Hook.ON_ERROR))
    assert len(calls) == 0


def test_filtered_registry_delegates_emit() -> None:
    backing = HookRegistry()
    calls: list[HookContext] = []
    backing.register(Hook.PRE_RENDER, calls.append)

    filtered = FilteredRegistry(backing, {Hook.PRE_RENDER}, "myplugin")
    filtered.emit(Hook.PRE_RENDER, HookContext(hook=Hook.PRE_RENDER))
    assert len(calls) == 1


def test_filtered_registry_delegates_has_handlers() -> None:
    backing = HookRegistry()
    backing.register(Hook.PRE_RENDER, lambda ctx: None)

    filtered = FilteredRegistry(backing, {Hook.PRE_RENDER}, "myplugin")
    assert filtered.has_handlers(Hook.PRE_RENDER) is True
    assert filtered.has_handlers(Hook.ON_ERROR) is False


def test_filtered_registry_delegates_clear() -> None:
    backing = HookRegistry()
    backing.register(Hook.PRE_RENDER, lambda ctx: None)

    filtered = FilteredRegistry(backing, {Hook.PRE_RENDER}, "myplugin")
    filtered.clear()
    assert backing.has_handlers(Hook.PRE_RENDER) is False
