"""Custom exception hierarchy for reeln."""

from __future__ import annotations

import logging
from typing import Any

from reeln.core.log import get_logger

_log: logging.Logger = get_logger(__name__)


class ReelnError(Exception):
    """Base exception for all reeln errors."""


class ConfigError(ReelnError):
    """Configuration loading or validation error."""


class FFmpegError(ReelnError):
    """FFmpeg discovery, version, or execution error."""


class SegmentError(ReelnError):
    """Segment resolution or validation error."""


class RenderError(ReelnError):
    """Render planning or execution error."""


class PluginError(ReelnError):
    """Plugin loading or hook dispatch error."""


class RegistryError(PluginError):
    """Remote plugin registry fetch or parse error."""


class MediaError(ReelnError):
    """Media file operation error."""


class PromptAborted(ReelnError):
    """User cancelled an interactive prompt."""


def emit_on_error(error: Exception, *, context: dict[str, Any] | None = None) -> None:
    """Emit ``Hook.ON_ERROR`` with error details.

    Doubly exception-safe — exceptions from the hook emission itself are
    caught and logged so this helper never raises.
    """
    try:
        from reeln.plugins.hooks import Hook, HookContext
        from reeln.plugins.registry import get_registry

        data: dict[str, Any] = {
            "error": error,
            "error_type": type(error).__name__,
            "message": str(error),
        }
        if context:
            data.update(context)
        get_registry().emit(
            Hook.ON_ERROR,
            HookContext(hook=Hook.ON_ERROR, data=data),
        )
    except Exception:
        _log.debug("Failed to emit ON_ERROR hook", exc_info=True)
