"""Hook registry — register handlers and emit hooks safely."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reeln.core.log import get_logger
from reeln.plugins.hooks import Hook, HookContext

log: logging.Logger = get_logger(__name__)

HandlerFunc = Callable[[HookContext], None]

_registry: HookRegistry | None = None


class HookRegistry:
    """Central registry for hook handlers.

    Handlers registered via :meth:`register` are called when :meth:`emit`
    fires the corresponding hook.  All exceptions from handlers are caught
    and logged — a misbehaving plugin never breaks core operations.
    """

    def __init__(self) -> None:
        self._handlers: dict[Hook, list[HandlerFunc]] = {}

    def register(self, hook: Hook, handler: HandlerFunc) -> None:
        """Register a handler for *hook*."""
        self._handlers.setdefault(hook, []).append(handler)

    def emit(self, hook: Hook, context: HookContext | None = None) -> None:
        """Emit *hook*, calling all registered handlers.

        If *context* is ``None``, a default ``HookContext`` is created.
        Exceptions from handlers are caught and logged.
        """
        ctx = context or HookContext(hook=hook)
        for handler in self._handlers.get(hook, []):
            try:
                handler(ctx)
            except Exception:
                log.exception("Hook handler failed for %s", hook.value)

    def has_handlers(self, hook: Hook) -> bool:
        """Return whether any handlers are registered for *hook*."""
        return bool(self._handlers.get(hook))

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()


def get_registry() -> HookRegistry:
    """Return the module-level singleton registry."""
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the singleton registry (for test isolation)."""
    global _registry
    if _registry is not None:
        _registry.clear()
    _registry = None
