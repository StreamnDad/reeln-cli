"""Tests for overlay context building and builtin template resolution."""

from __future__ import annotations

import pytest

from reeln.core.errors import RenderError
from reeln.core.overlay import (
    _parse_assists,
    _parse_color,
    build_overlay_context,
    overlay_font_size,
    resolve_builtin_template,
)
from reeln.core.templates import format_ass_time, rgb_to_ass
from reeln.models.template import TemplateContext

# ---------------------------------------------------------------------------
# resolve_builtin_template
# ---------------------------------------------------------------------------


class TestResolveBuiltinTemplate:
    def test_valid_template(self) -> None:
        path = resolve_builtin_template("goal_overlay")
        assert path.is_file()
        assert path.name == "goal_overlay.ass"

    def test_missing_template(self) -> None:
        with pytest.raises(RenderError, match="Builtin template not found"):
            resolve_builtin_template("nonexistent_template")

    def test_branding_template(self) -> None:
        path = resolve_builtin_template("branding")
        assert path.is_file()
        assert path.name == "branding.ass"


# ---------------------------------------------------------------------------
# overlay_font_size
# ---------------------------------------------------------------------------


class TestOverlayFontSize:
    def test_fits_in_max_chars(self) -> None:
        assert overlay_font_size("Short", base=46, min_size=32, max_chars=24) == 46

    def test_empty_string(self) -> None:
        assert overlay_font_size("", base=46, min_size=32, max_chars=24) == 46

    def test_whitespace_only(self) -> None:
        assert overlay_font_size("   ", base=46, min_size=32, max_chars=24) == 46

    def test_exact_max_chars(self) -> None:
        text = "A" * 24
        assert overlay_font_size(text, base=46, min_size=32, max_chars=24) == 46

    def test_scales_down(self) -> None:
        # 30 chars with max 24 -> scale = 24/30 = 0.8 -> 46 * 0.8 = 36.8 -> round = 37
        text = "A" * 30
        result = overlay_font_size(text, base=46, min_size=32, max_chars=24)
        assert result == 37

    def test_clamps_to_min(self) -> None:
        # Very long text should clamp to min_size
        text = "A" * 100
        result = overlay_font_size(text, base=46, min_size=32, max_chars=24)
        assert result == 32

    def test_with_leading_trailing_whitespace(self) -> None:
        # "  Short  " strips to "Short" (5 chars) which fits
        assert overlay_font_size("  Short  ", base=46, min_size=32, max_chars=24) == 46


# ---------------------------------------------------------------------------
# _parse_assists
# ---------------------------------------------------------------------------


class TestParseAssists:
    def test_list_format(self) -> None:
        meta = {"assists": ["#7 Jones", "#5 Brown"]}
        assert _parse_assists(meta) == ("#7 Jones", "#5 Brown")

    def test_comma_string_format(self) -> None:
        meta = {"assists": "#7 Jones, #5 Brown"}
        assert _parse_assists(meta) == ("#7 Jones", "#5 Brown")

    def test_single_assist_list(self) -> None:
        meta = {"assists": ["#7 Jones"]}
        assert _parse_assists(meta) == ("#7 Jones", "")

    def test_single_assist_string(self) -> None:
        meta = {"assists": "#7 Jones"}
        assert _parse_assists(meta) == ("#7 Jones", "")

    def test_empty_list(self) -> None:
        meta = {"assists": []}
        assert _parse_assists(meta) == ("", "")

    def test_empty_string(self) -> None:
        meta = {"assists": ""}
        assert _parse_assists(meta) == ("", "")

    def test_no_assists_key(self) -> None:
        meta = {"player": "#17 Smith"}
        assert _parse_assists(meta) == ("", "")

    def test_none_metadata(self) -> None:
        assert _parse_assists(None) == ("", "")

    def test_list_with_whitespace_entries(self) -> None:
        meta = {"assists": ["#7 Jones", "  ", "#5 Brown"]}
        assert _parse_assists(meta) == ("#7 Jones", "#5 Brown")

    def test_non_list_non_string(self) -> None:
        meta = {"assists": 42}
        assert _parse_assists(meta) == ("", "")


# ---------------------------------------------------------------------------
# _parse_color
# ---------------------------------------------------------------------------


class TestParseColor:
    def test_with_hash(self) -> None:
        assert _parse_color("#C8102E") == (200, 16, 46)

    def test_without_hash(self) -> None:
        assert _parse_color("FF0000") == (255, 0, 0)

    def test_lowercase(self) -> None:
        assert _parse_color("#ff8800") == (255, 136, 0)

    def test_white(self) -> None:
        assert _parse_color("#FFFFFF") == (255, 255, 255)

    def test_black(self) -> None:
        assert _parse_color("#000000") == (0, 0, 0)

    def test_too_short(self) -> None:
        assert _parse_color("#FFF") is None

    def test_too_long(self) -> None:
        assert _parse_color("#FFFFFFFF") is None

    def test_invalid_hex(self) -> None:
        assert _parse_color("#GGGGGG") is None

    def test_whitespace(self) -> None:
        assert _parse_color("  #C8102E  ") == (200, 16, 46)

    def test_empty(self) -> None:
        assert _parse_color("") is None


# ---------------------------------------------------------------------------
# build_overlay_context
# ---------------------------------------------------------------------------


class TestBuildOverlayContext:
    def _base_ctx(self, **kwargs: str) -> TemplateContext:
        defaults = {
            "home_team": "Roseville",
            "away_team": "Burnsville",
            "sport": "hockey",
            "level": "bantam",
            "player": "#17 Smith",
        }
        defaults.update(kwargs)
        return TemplateContext(variables=defaults)

    def test_full_scorer_and_assists(self) -> None:
        ctx = self._base_ctx()
        meta = {"assists": ["#22 Jones", "#5 Brown"]}
        result = build_overlay_context(ctx, duration=8.0, event_metadata=meta)

        assert result.get("goal_scorer_text") == "#17 Smith"
        assert result.get("goal_assist_1") == "#22 Jones"
        assert result.get("goal_assist_2") == "#5 Brown"
        assert result.get("goal_scorer_team") == "ROSEVILLE"
        assert result.get("team_level") == "BANTAM"

        # Timing: assists visible
        assert result.get("scorer_start") == format_ass_time(0.0)
        assert result.get("scorer_end") == format_ass_time(9.0)
        assert result.get("assist_start") == format_ass_time(0.0)
        assert result.get("assist_end") == format_ass_time(9.0)
        assert result.get("box_end") == format_ass_time(9.0)

    def test_no_assists_hides_assist_timing(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, duration=10.0, event_metadata={})

        assert result.get("goal_assist_1") == ""
        assert result.get("goal_assist_2") == ""
        # Assist end time should be 0 (hidden)
        assert result.get("assist_end") == format_ass_time(0.0)
        # Scorer still visible
        assert result.get("scorer_end") == format_ass_time(11.0)

    def test_no_player(self) -> None:
        ctx = self._base_ctx(player="")
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("goal_scorer_text") == ""

    def test_font_size_with_assists(self) -> None:
        ctx = self._base_ctx()
        meta = {"assists": ["#22 Jones"]}
        result = build_overlay_context(ctx, event_metadata=meta)
        # With assists: base=46, min=32
        fs = int(result.get("goal_scorer_fs"))
        assert fs == 46  # "#17 Smith" is short enough

    def test_font_size_without_assists(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={})
        # Without assists: base=54, min=38
        fs = int(result.get("goal_scorer_fs"))
        assert fs == 54

    def test_default_colors(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={})
        # Default primary (30, 30, 30)
        assert result.get("ass_primary_color") == rgb_to_ass((30, 30, 30), 0)
        # Default secondary (200, 200, 200)
        assert result.get("ass_secondary_color") == rgb_to_ass((200, 200, 200), 0)
        # Default name (255, 255, 255) -> outline is black
        assert result.get("ass_name_color") == rgb_to_ass((255, 255, 255), 0)
        assert result.get("ass_name_outline_color") == rgb_to_ass((0, 0, 0), 0)

    def test_custom_home_colors(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(
            ctx,
            event_metadata={},
            home_colors=["#C8102E", "#FFFFFF"],
        )
        assert result.get("ass_primary_color") == rgb_to_ass((200, 16, 46), 0)
        assert result.get("ass_secondary_color") == rgb_to_ass((255, 255, 255), 0)

    def test_single_home_color(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(
            ctx,
            event_metadata={},
            home_colors=["#C8102E"],
        )
        # Primary from home_colors[0], secondary stays default
        assert result.get("ass_primary_color") == rgb_to_ass((200, 16, 46), 0)
        assert result.get("ass_secondary_color") == rgb_to_ass((200, 200, 200), 0)

    def test_invalid_home_color_uses_default(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(
            ctx,
            event_metadata={},
            home_colors=["invalid", "also-bad"],
        )
        assert result.get("ass_primary_color") == rgb_to_ass((30, 30, 30), 0)
        assert result.get("ass_secondary_color") == rgb_to_ass((200, 200, 200), 0)

    def test_y_offset(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={}, y_offset=50)
        assert result.get("goal_overlay_border_y") == str(817 + 50)
        assert result.get("goal_overlay_box_y") == str(820 + 50)
        assert result.get("goal_overlay_team_y") == str(828 + 50)
        assert result.get("goal_overlay_scorer_y") == str(852 + 50)
        assert result.get("goal_overlay_assist_1_y") == str(892 + 50)
        assert result.get("goal_overlay_assist_2_y") == str(914 + 50)

    def test_zero_y_offset(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("goal_overlay_border_y") == "817"
        assert result.get("goal_overlay_box_y") == "820"

    def test_layout_coordinates_fixed(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("goal_overlay_border_x") == "0"
        assert result.get("goal_overlay_border_w") == "1920"
        assert result.get("goal_overlay_border_h") == "141"
        assert result.get("goal_overlay_box_x") == "3"
        assert result.get("goal_overlay_box_w") == "1914"
        assert result.get("goal_overlay_box_h") == "135"
        assert result.get("goal_overlay_team_x") == "83"
        assert result.get("goal_overlay_scorer_x") == "113"
        assert result.get("goal_overlay_assist_1_x") == "140"
        assert result.get("goal_overlay_assist_2_x") == "140"

    def test_preserves_base_context(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={})
        # Original base context keys should still be accessible
        assert result.get("home_team") == "Roseville"
        assert result.get("away_team") == "Burnsville"
        assert result.get("sport") == "hockey"

    def test_duration_default(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("scorer_end") == format_ass_time(11.0)
        assert result.get("box_end") == format_ass_time(11.0)

    def test_none_event_metadata(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata=None)
        assert result.get("goal_assist_1") == ""
        assert result.get("goal_assist_2") == ""

    def test_primary_back_has_alpha(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={})
        # Default primary (30, 30, 30) with alpha 0x66
        assert result.get("ass_primary_back") == rgb_to_ass((30, 30, 30), 0x66)

    def test_team_text_color_has_alpha(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("ass_team_text_color") == rgb_to_ass((255, 255, 255), 0x40)

    def test_scoring_team_overrides_home_team(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={}, scoring_team="Bears")
        assert result.get("goal_scorer_team") == "BEARS"

    def test_team_level_uses_level_not_sport(self) -> None:
        ctx = self._base_ctx(level="2016")
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("team_level") == "2016"

    def test_team_level_empty_when_no_level(self) -> None:
        ctx = self._base_ctx(level="")
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("team_level") == ""

    def test_scoring_team_none_uses_home_team(self) -> None:
        ctx = self._base_ctx()
        result = build_overlay_context(ctx, event_metadata={}, scoring_team=None)
        assert result.get("goal_scorer_team") == "ROSEVILLE"

    def test_tournament_promotes_to_title(self) -> None:
        ctx = self._base_ctx(tournament="Presidents Cup")
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("goal_scorer_team") == "PRESIDENTS CUP"
        assert result.get("team_level") == "ROSEVILLE/BANTAM"

    def test_tournament_with_scoring_team(self) -> None:
        ctx = self._base_ctx(tournament="Presidents Cup")
        result = build_overlay_context(ctx, event_metadata={}, scoring_team="Bears")
        assert result.get("goal_scorer_team") == "PRESIDENTS CUP"
        assert result.get("team_level") == "BEARS/BANTAM"

    def test_tournament_without_level(self) -> None:
        ctx = self._base_ctx(tournament="Presidents Cup", level="")
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("goal_scorer_team") == "PRESIDENTS CUP"
        assert result.get("team_level") == "ROSEVILLE"

    def test_no_tournament_keeps_original_format(self) -> None:
        ctx = self._base_ctx(tournament="")
        result = build_overlay_context(ctx, event_metadata={})
        assert result.get("goal_scorer_team") == "ROSEVILLE"
        assert result.get("team_level") == "BANTAM"
