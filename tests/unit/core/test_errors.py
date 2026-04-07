"""Tests for the reeln error hierarchy and emit_on_error helper."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from reeln.core.errors import (
    ConfigError,
    FFmpegError,
    MediaError,
    PluginError,
    PromptAborted,
    QueueError,
    ReelnError,
    RegistryError,
    RenderError,
    SegmentError,
    emit_on_error,
)
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.registry import get_registry


@pytest.mark.parametrize(
    "exc_class",
    [
        ConfigError, FFmpegError, SegmentError, RenderError, PluginError,
        RegistryError, MediaError, QueueError, PromptAborted,
    ],
)
def test_subclass_inherits_from_reeln_error(exc_class: type[ReelnError]) -> None:
    assert issubclass(exc_class, ReelnError)


@pytest.mark.parametrize(
    "exc_class",
    [
        ReelnError,
        ConfigError,
        FFmpegError,
        SegmentError,
        RenderError,
        PluginError,
        RegistryError,
        MediaError,
        QueueError,
        PromptAborted,
    ],
)
def test_inherits_from_exception(exc_class: type[Exception]) -> None:
    assert issubclass(exc_class, Exception)


@pytest.mark.parametrize(
    "exc_class",
    [
        ReelnError,
        ConfigError,
        FFmpegError,
        SegmentError,
        RenderError,
        PluginError,
        RegistryError,
        MediaError,
        QueueError,
        PromptAborted,
    ],
)
def test_message_preserved(exc_class: type[ReelnError]) -> None:
    err = exc_class("test message")
    assert str(err) == "test message"


@pytest.mark.parametrize(
    "exc_class",
    [
        ReelnError,
        ConfigError,
        FFmpegError,
        SegmentError,
        RenderError,
        PluginError,
        RegistryError,
        MediaError,
        QueueError,
        PromptAborted,
    ],
)
def test_raise_and_catch(exc_class: type[ReelnError]) -> None:
    with pytest.raises(ReelnError, match="boom"):
        raise exc_class("boom")


# ---------------------------------------------------------------------------
# emit_on_error
# ---------------------------------------------------------------------------


def test_emit_on_error_fires_hook() -> None:
    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_ERROR, emitted.append)

    err = FFmpegError("ffmpeg failed")
    emit_on_error(err)

    assert len(emitted) == 1
    assert emitted[0].hook is Hook.ON_ERROR
    assert emitted[0].data["error"] is err
    assert emitted[0].data["error_type"] == "FFmpegError"
    assert emitted[0].data["message"] == "ffmpeg failed"


def test_emit_on_error_merges_context() -> None:
    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_ERROR, emitted.append)

    err = RenderError("bad plan")
    emit_on_error(err, context={"operation": "render", "plan": "test"})

    assert len(emitted) == 1
    assert emitted[0].data["operation"] == "render"
    assert emitted[0].data["plan"] == "test"
    assert emitted[0].data["error"] is err


def test_emit_on_error_suppresses_exceptions() -> None:
    """emit_on_error never raises, even if the hook itself fails."""

    def broken_handler(ctx: HookContext) -> None:
        raise RuntimeError("handler exploded")

    get_registry().register(Hook.ON_ERROR, broken_handler)

    # Should not raise
    emit_on_error(FFmpegError("test"))


def test_emit_on_error_suppresses_registry_failure() -> None:
    """emit_on_error never raises, even if the registry itself explodes."""
    with patch(
        "reeln.plugins.registry.get_registry",
        side_effect=RuntimeError("registry broken"),
    ):
        # Should not raise
        emit_on_error(FFmpegError("test"))


# ---------------------------------------------------------------------------
# RegistryError
# ---------------------------------------------------------------------------


def test_registry_error_is_plugin_error() -> None:
    assert issubclass(RegistryError, PluginError)


def test_registry_error_is_reeln_error() -> None:
    assert issubclass(RegistryError, ReelnError)


def test_registry_error_message() -> None:
    err = RegistryError("fetch failed")
    assert str(err) == "fetch failed"
