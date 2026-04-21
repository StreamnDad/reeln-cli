"""Overlay context building for bundled ASS subtitle templates."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from reeln.core.errors import RenderError
from reeln.core.templates import format_ass_time, rgb_to_ass
from reeln.models.template import TemplateContext


def resolve_builtin_template(name: str) -> Path:
    """Resolve a builtin template name to its package data path.

    Accepts names like ``"goal_overlay"`` (no extension).
    Raises ``RenderError`` if the builtin template does not exist.
    """
    resource = files("reeln.data.templates").joinpath(f"{name}.ass")
    path = Path(str(resource))
    if not path.is_file():
        raise RenderError(f"Builtin template not found: {name!r}")
    return path


def overlay_font_size(text: str, base: int, min_size: int, max_chars: int) -> int:
    """Proportionally scale down font size for long text.

    Returns *base* when text fits, scales linearly down to *min_size*
    for text exceeding *max_chars*.
    """
    cleaned = text.strip()
    if not cleaned or len(cleaned) <= max_chars:
        return base
    scale = max_chars / len(cleaned)
    return max(min_size, round(base * scale))


def _parse_assists(event_metadata: dict[str, Any] | None) -> tuple[str, str]:
    """Extract up to two assist strings from event metadata.

    Handles both list and comma-separated string formats:
    - ``{"assists": ["#7 Jones", "#5 Brown"]}``
    - ``{"assists": "#7 Jones, #5 Brown"}``
    """
    if event_metadata is None:
        return ("", "")
    raw = event_metadata.get("assists", "")
    if isinstance(raw, list):
        parts = [str(a).strip() for a in raw if str(a).strip()]
    elif isinstance(raw, str) and raw.strip():
        parts = [a.strip() for a in raw.split(",") if a.strip()]
    else:
        parts = []
    assist_1 = parts[0] if parts else ""
    assist_2 = parts[1] if len(parts) > 1 else ""
    return (assist_1, assist_2)


def _parse_color(hex_str: str) -> tuple[int, int, int] | None:
    """Parse a hex color string like ``'#C8102E'`` or ``'C8102E'`` to (R, G, B)."""
    s = hex_str.strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


# Default colors when team profiles aren't available
_DEFAULT_PRIMARY = (30, 30, 30)
_DEFAULT_SECONDARY = (200, 200, 200)
_DEFAULT_NAME = (255, 255, 255)


def build_overlay_context(
    base: TemplateContext,
    *,
    duration: float = 10.0,
    event_metadata: dict[str, Any] | None = None,
    home_colors: list[str] | None = None,
    away_colors: list[str] | None = None,
    y_offset: int = 0,
    scoring_team: str | None = None,
    has_logo: bool = False,
) -> TemplateContext:
    """Enrich a template context with overlay-specific variables.

    Adds all computed variables needed by the builtin ``goal_overlay.ass``
    template: layout coordinates, ASS colors, font sizes, timing, and
    assist text.

    Uses ``base["player"]`` as scorer text and *event_metadata* ``assists``
    key for assist lines.  Falls back to default colors when team colors
    aren't provided.
    """
    scorer_text = base.get("player", "").strip()
    assist_1, assist_2 = _parse_assists(event_metadata)
    has_assists = bool(assist_1 or assist_2)

    # Timing — add 1s buffer past video duration so the overlay never
    # disappears before the last frame (ffmpeg truncates to the shorter
    # stream via shortest=1 or the video's own duration).
    end_time = duration + 1.0
    scorer_start = format_ass_time(0.0)
    scorer_end = format_ass_time(end_time)
    assist_start = format_ass_time(0.0)
    assist_end = format_ass_time(end_time if has_assists else 0.0)
    box_end = format_ass_time(end_time)

    # Font sizing — reduce max_chars when a logo is present so text
    # stays within the clipped region and doesn't run under the logo.
    scorer_max_chars = 18 if has_logo else 24
    assist_max_chars = 22 if has_logo else 30
    scorer_base = 46 if has_assists else 54
    scorer_min = 32 if has_assists else 38
    goal_scorer_fs = str(overlay_font_size(
        scorer_text, base=scorer_base, min_size=scorer_min, max_chars=scorer_max_chars,
    ))
    goal_assist_fs = str(overlay_font_size(
        f"{assist_1} {assist_2}".strip(), base=32, min_size=24, max_chars=assist_max_chars,
    ))

    # Colors
    primary_rgb = _DEFAULT_PRIMARY
    secondary_rgb = _DEFAULT_SECONDARY
    name_rgb = _DEFAULT_NAME

    if home_colors and len(home_colors) >= 1:
        parsed = _parse_color(home_colors[0])
        if parsed is not None:
            primary_rgb = parsed
    if home_colors and len(home_colors) >= 2:
        parsed = _parse_color(home_colors[1])
        if parsed is not None:
            secondary_rgb = parsed

    outline_rgb = (0, 0, 0) if name_rgb == (255, 255, 255) else (255, 255, 255)

    ass_primary_color = rgb_to_ass(primary_rgb, 0)
    ass_secondary_color = rgb_to_ass(secondary_rgb, 0)
    ass_primary_back = rgb_to_ass(primary_rgb, 0x66)
    ass_name_color = rgb_to_ass(name_rgb, 0)
    ass_team_text_color = rgb_to_ass(name_rgb, 0x40)
    ass_name_outline_color = rgb_to_ass(outline_rgb, 0)

    # Team and level from base context — uppercase for visual emphasis.
    # When a tournament is configured, promote it to the title position
    # and combine team/level into the secondary slot.
    tournament = base.get("tournament", "").strip()
    team_name = (scoring_team if scoring_team is not None else base.get("home_team", "")).upper()
    level = base.get("level", "").upper()
    if tournament:
        goal_scorer_team = tournament.upper()
        team_level = f"{team_name}/{level}" if level else team_name
    else:
        goal_scorer_team = team_name
        team_level = level

    # Logo reserve — when a logo is present, clip text rendering to the
    # left portion of the box so it doesn't overlap the logo image.
    # 200 ASS-units reserved for logo + padding on the right side.
    _LOGO_RESERVE = 200
    text_right = str(3 + 1914 - _LOGO_RESERVE) if has_logo else "1920"

    # Layout coordinates (ported from old CLI)
    variables: dict[str, str] = {
        "box_end": box_end,
        "goal_scorer_text": scorer_text,
        "goal_assist_1": assist_1,
        "goal_assist_2": assist_2,
        "goal_scorer_team": goal_scorer_team,
        "team_level": team_level,
        "scorer_start": scorer_start,
        "scorer_end": scorer_end,
        "assist_start": assist_start,
        "assist_end": assist_end,
        "goal_scorer_fs": goal_scorer_fs,
        "goal_assist_fs": goal_assist_fs,
        "ass_primary_color": ass_primary_color,
        "ass_secondary_color": ass_secondary_color,
        "ass_primary_back": ass_primary_back,
        "ass_name_color": ass_name_color,
        "ass_team_text_color": ass_team_text_color,
        "ass_name_outline_color": ass_name_outline_color,
        "goal_overlay_text_right": text_right,
        "goal_overlay_border_x": "0",
        "goal_overlay_border_y": str(817 + y_offset),
        "goal_overlay_border_w": "1920",
        "goal_overlay_border_h": str(148 if has_assists else 141),
        "goal_overlay_box_x": "3",
        "goal_overlay_box_y": str(820 + y_offset),
        "goal_overlay_box_w": "1914",
        "goal_overlay_box_h": str(142 if has_assists else 135),
        "goal_overlay_team_x": "83",
        "goal_overlay_team_y": str(828 + y_offset),
        "goal_overlay_scorer_x": "113",
        "goal_overlay_scorer_y": str(852 + y_offset),
        "goal_overlay_assist_1_x": "140",
        "goal_overlay_assist_1_y": str(895 + y_offset),
        "goal_overlay_assist_2_x": "140",
        "goal_overlay_assist_2_y": str(921 + y_offset),
    }

    return base.merge(TemplateContext(variables=variables))
