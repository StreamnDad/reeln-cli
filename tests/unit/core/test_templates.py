"""Tests for template engine, provider protocol, and ASS helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from reeln.core.errors import RenderError
from reeln.core.templates import (
    TemplateProvider,
    build_base_context,
    collect_provider_context,
    format_ass_time,
    render_template,
    render_template_file,
    rgb_to_ass,
)
from reeln.models.game import GameEvent, GameInfo
from reeln.models.template import TemplateContext

# ---------------------------------------------------------------------------
# render_template
# ---------------------------------------------------------------------------


def test_render_template_basic() -> None:
    ctx = TemplateContext(variables={"name": "Alice"})
    assert render_template("Hello {{name}}!", ctx) == "Hello Alice!"


def test_render_template_multiple_keys() -> None:
    ctx = TemplateContext(variables={"home": "Roseville", "away": "Mahtomedi"})
    result = render_template("{{home}} vs {{away}}", ctx)
    assert result == "Roseville vs Mahtomedi"


def test_render_template_unresolved_keys_left() -> None:
    ctx = TemplateContext(variables={"home": "Roseville"})
    result = render_template("{{home}} vs {{away}}", ctx)
    assert result == "Roseville vs {{away}}"


def test_render_template_empty_context() -> None:
    ctx = TemplateContext()
    assert render_template("no {{vars}} here", ctx) == "no {{vars}} here"


def test_render_template_empty_template() -> None:
    ctx = TemplateContext(variables={"key": "value"})
    assert render_template("", ctx) == ""


def test_render_template_repeated_key() -> None:
    ctx = TemplateContext(variables={"team": "Roseville"})
    result = render_template("{{team}} {{team}} {{team}}", ctx)
    assert result == "Roseville Roseville Roseville"


# ---------------------------------------------------------------------------
# render_template_file
# ---------------------------------------------------------------------------


def test_render_template_file_success(tmp_path: Path) -> None:
    template = tmp_path / "overlay.ass"
    template.write_text("Team: {{home_team}}\nPlayer: {{player}}", encoding="utf-8")
    ctx = TemplateContext(variables={"home_team": "Roseville", "player": "Smith"})
    result = render_template_file(template, ctx)
    assert result == "Team: Roseville\nPlayer: Smith"


def test_render_template_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ass"
    ctx = TemplateContext()
    with pytest.raises(RenderError, match="not found"):
        render_template_file(missing, ctx)


def test_render_template_file_wrong_extension(tmp_path: Path) -> None:
    wrong = tmp_path / "template.txt"
    wrong.write_text("content")
    ctx = TemplateContext()
    with pytest.raises(RenderError, match=r"must be an \.ass file"):
        render_template_file(wrong, ctx)


def test_render_template_file_read_error(tmp_path: Path) -> None:
    template = tmp_path / "overlay.ass"
    template.write_text("content")
    from unittest.mock import patch

    with (
        patch.object(Path, "read_text", side_effect=OSError("permission denied")),
        pytest.raises(RenderError, match="Failed to read"),
    ):
        render_template_file(template, TemplateContext())


# ---------------------------------------------------------------------------
# build_base_context
# ---------------------------------------------------------------------------


def test_build_base_context_game_info_only() -> None:
    info = GameInfo(
        date="2026-02-28",
        home_team="Roseville",
        away_team="Mahtomedi",
        sport="hockey",
        venue="OVAL",
        game_number=1,
    )
    ctx = build_base_context(info)
    assert ctx.get("home_team") == "Roseville"
    assert ctx.get("away_team") == "Mahtomedi"
    assert ctx.get("date") == "2026-02-28"
    assert ctx.get("sport") == "hockey"
    assert ctx.get("venue") == "OVAL"
    assert ctx.get("game_number") == "1"
    assert ctx.get("game_time") == ""
    assert ctx.get("period_length") == "0"
    assert ctx.get("level") == ""
    assert ctx.get("tournament") == ""
    assert ctx.get("event_type") == ""  # not present


def test_build_base_context_with_game_time() -> None:
    info = GameInfo(
        date="2026-02-28",
        home_team="A",
        away_team="B",
        sport="hockey",
        game_time="7:00 PM",
    )
    ctx = build_base_context(info)
    assert ctx.get("game_time") == "7:00 PM"


def test_build_base_context_with_level_and_tournament() -> None:
    info = GameInfo(
        date="2026-03-21",
        home_team="North",
        away_team="South",
        sport="hockey",
        level="2016",
        tournament="2026 Stars of Tomorrow",
    )
    ctx = build_base_context(info)
    assert ctx.get("level") == "2016"
    assert ctx.get("tournament") == "2026 Stars of Tomorrow"


def test_build_base_context_with_event() -> None:
    info = GameInfo(
        date="2026-02-28",
        home_team="Roseville",
        away_team="Mahtomedi",
        sport="hockey",
    )
    event = GameEvent(
        id="abc123",
        clip="period-1/replay.mkv",
        segment_number=1,
        event_type="goal",
        player="Smith",
        metadata={"assist_1": "Jones", "assist_2": "Brown"},
    )
    ctx = build_base_context(info, event)
    assert ctx.get("event_type") == "goal"
    assert ctx.get("player") == "Smith"
    assert ctx.get("segment_number") == "1"
    assert ctx.get("event_id") == "abc123"
    assert ctx.get("assist_1") == "Jones"
    assert ctx.get("assist_2") == "Brown"


def test_build_base_context_event_metadata_stringified() -> None:
    info = GameInfo(date="2026-02-28", home_team="A", away_team="B", sport="hockey")
    event = GameEvent(
        id="x",
        clip="c.mkv",
        segment_number=1,
        metadata={"score": 3, "shots": 15},
    )
    ctx = build_base_context(info, event)
    assert ctx.get("score") == "3"
    assert ctx.get("shots") == "15"


# ---------------------------------------------------------------------------
# collect_provider_context
# ---------------------------------------------------------------------------


def test_collect_provider_context_empty() -> None:
    info = GameInfo(date="d", home_team="h", away_team="a", sport="s")
    ctx = collect_provider_context([], info)
    assert ctx.variables == {}


def test_collect_provider_context_single() -> None:
    class ScoreProvider:
        name = "scoreboard"

        def provide(self, game_info: GameInfo, event: GameEvent | None = None) -> TemplateContext:
            return TemplateContext(variables={"score": "3-1"})

    info = GameInfo(date="d", home_team="h", away_team="a", sport="s")
    ctx = collect_provider_context([ScoreProvider()], info)
    assert ctx.get("score") == "3-1"


def test_collect_provider_context_multiple_merge_order() -> None:
    class ProviderA:
        name = "a"

        def provide(self, game_info: GameInfo, event: GameEvent | None = None) -> TemplateContext:
            return TemplateContext(variables={"key": "a", "only_a": "yes"})

    class ProviderB:
        name = "b"

        def provide(self, game_info: GameInfo, event: GameEvent | None = None) -> TemplateContext:
            return TemplateContext(variables={"key": "b", "only_b": "yes"})

    info = GameInfo(date="d", home_team="h", away_team="a", sport="s")
    ctx = collect_provider_context([ProviderA(), ProviderB()], info)
    assert ctx.get("key") == "b"  # later provider wins
    assert ctx.get("only_a") == "yes"
    assert ctx.get("only_b") == "yes"


def test_collect_provider_context_protocol_conformance() -> None:
    """Verify a class satisfies the TemplateProvider protocol."""

    class MyProvider:
        name = "test"

        def provide(self, game_info: GameInfo, event: GameEvent | None = None) -> TemplateContext:
            return TemplateContext(variables={"custom": "value"})

    provider: TemplateProvider = MyProvider()
    info = GameInfo(date="d", home_team="h", away_team="a", sport="s")
    ctx = provider.provide(info)
    assert ctx.get("custom") == "value"


# ---------------------------------------------------------------------------
# rgb_to_ass
# ---------------------------------------------------------------------------


def test_rgb_to_ass_white() -> None:
    assert rgb_to_ass((255, 255, 255)) == "&H00FFFFFF"


def test_rgb_to_ass_black() -> None:
    assert rgb_to_ass((0, 0, 0)) == "&H00000000"


def test_rgb_to_ass_red() -> None:
    # RGB(255, 0, 0) → ASS BGR → &H000000FF
    assert rgb_to_ass((255, 0, 0)) == "&H000000FF"


def test_rgb_to_ass_blue() -> None:
    # RGB(0, 0, 255) → ASS BGR → &H00FF0000
    assert rgb_to_ass((0, 0, 255)) == "&H00FF0000"


def test_rgb_to_ass_with_alpha() -> None:
    assert rgb_to_ass((255, 255, 255), alpha=0x66) == "&H66FFFFFF"


def test_rgb_to_ass_alpha_clamped() -> None:
    assert rgb_to_ass((0, 0, 0), alpha=300) == "&HFF000000"
    assert rgb_to_ass((0, 0, 0), alpha=-10) == "&H00000000"


# ---------------------------------------------------------------------------
# format_ass_time
# ---------------------------------------------------------------------------


def test_format_ass_time_zero() -> None:
    assert format_ass_time(0.0) == "0:00:00.00"


def test_format_ass_time_seconds() -> None:
    assert format_ass_time(5.5) == "0:00:05.50"


def test_format_ass_time_minutes() -> None:
    assert format_ass_time(125.25) == "0:02:05.25"


def test_format_ass_time_hours() -> None:
    assert format_ass_time(3661.0) == "1:01:01.00"


def test_format_ass_time_negative() -> None:
    assert format_ass_time(-5.0) == "0:00:00.00"


def test_format_ass_time_fractional() -> None:
    assert format_ass_time(0.01) == "0:00:00.01"
    assert format_ass_time(0.99) == "0:00:00.99"
