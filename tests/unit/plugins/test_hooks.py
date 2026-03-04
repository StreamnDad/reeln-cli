"""Tests for the Hook enum, HookContext, and HookHandler protocol."""

from __future__ import annotations

from reeln.plugins.hooks import Hook, HookContext, HookHandler

# ---------------------------------------------------------------------------
# Hook enum
# ---------------------------------------------------------------------------


def test_hook_values() -> None:
    assert Hook.PRE_RENDER.value == "pre_render"
    assert Hook.POST_RENDER.value == "post_render"
    assert Hook.ON_CLIP_AVAILABLE.value == "on_clip_available"
    assert Hook.ON_EVENT_CREATED.value == "on_event_created"
    assert Hook.ON_EVENT_TAGGED.value == "on_event_tagged"
    assert Hook.ON_GAME_INIT.value == "on_game_init"
    assert Hook.ON_GAME_FINISH.value == "on_game_finish"
    assert Hook.ON_HIGHLIGHTS_MERGED.value == "on_highlights_merged"
    assert Hook.ON_SEGMENT_START.value == "on_segment_start"
    assert Hook.ON_SEGMENT_COMPLETE.value == "on_segment_complete"
    assert Hook.ON_ERROR.value == "on_error"


def test_hook_enum_count() -> None:
    assert len(Hook) == 11


def test_hook_members_unique() -> None:
    values = [h.value for h in Hook]
    assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# HookContext
# ---------------------------------------------------------------------------


def test_hook_context_defaults() -> None:
    ctx = HookContext(hook=Hook.PRE_RENDER)
    assert ctx.hook is Hook.PRE_RENDER
    assert ctx.data == {}


def test_hook_context_with_data() -> None:
    ctx = HookContext(hook=Hook.POST_RENDER, data={"plan": "test", "result": 42})
    assert ctx.hook is Hook.POST_RENDER
    assert ctx.data == {"plan": "test", "result": 42}


def test_hook_context_is_frozen() -> None:
    ctx = HookContext(hook=Hook.ON_ERROR)
    try:
        ctx.hook = Hook.PRE_RENDER  # type: ignore[misc]
        raise AssertionError("Should not allow mutation")
    except AttributeError:
        pass


# ---------------------------------------------------------------------------
# HookHandler protocol
# ---------------------------------------------------------------------------


def test_hook_handler_protocol_satisfied() -> None:
    """A plain callable satisfies the HookHandler protocol."""

    def my_handler(context: HookContext) -> None:
        pass

    handler: HookHandler = my_handler
    assert callable(handler)


def test_hook_handler_class_satisfies_protocol() -> None:
    """A class with __call__ satisfies the HookHandler protocol."""

    class MyHandler:
        def __call__(self, context: HookContext) -> None:
            pass

    handler: HookHandler = MyHandler()
    assert callable(handler)
