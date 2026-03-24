"""Template engine, provider protocol, and ASS subtitle helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from reeln.core.errors import RenderError
from reeln.models.game import GameEvent, GameInfo
from reeln.models.template import TemplateContext

# ---------------------------------------------------------------------------
# TemplateProvider protocol
# ---------------------------------------------------------------------------


class TemplateProvider(Protocol):
    """Extension point for plugins to contribute template variables.

    Plugins implement this protocol and register via entry points.
    The registry calls ``provide()`` and merges the returned context
    into the base context.
    """

    name: str

    def provide(
        self,
        game_info: GameInfo,
        event: GameEvent | None = None,
    ) -> TemplateContext: ...


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def render_template(template: str, context: TemplateContext) -> str:
    """Replace ``{{key}}`` placeholders with values from *context*.

    Unresolved placeholders are left as-is.
    """
    rendered = template
    for key, value in context.variables.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def render_template_file(
    template_path: Path,
    context: TemplateContext,
) -> str:
    """Read a template file and render it.

    Raises ``RenderError`` if the file cannot be read or has wrong extension.
    """
    if not template_path.is_file():
        raise RenderError(f"Template file not found: {template_path}")
    if template_path.suffix.lower() != ".ass":
        raise RenderError(f"Template must be an .ass file, got {template_path.suffix!r}")
    try:
        content = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderError(f"Failed to read template {template_path}: {exc}") from exc
    return render_template(content, context)


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


def build_base_context(
    game_info: GameInfo,
    event: GameEvent | None = None,
) -> TemplateContext:
    """Build a ``TemplateContext`` from game info and an optional event.

    Includes: home_team, away_team, date, sport, venue, game_number,
    and (if event is present) event_type, player, segment_number,
    event_id, plus all keys from event.metadata.
    """
    variables: dict[str, str] = {
        "home_team": game_info.home_team,
        "away_team": game_info.away_team,
        "date": game_info.date,
        "sport": game_info.sport,
        "venue": game_info.venue,
        "game_number": str(game_info.game_number),
        "game_time": game_info.game_time,
        "period_length": str(game_info.period_length),
        "level": game_info.level,
        "tournament": game_info.tournament,
    }
    if event is not None:
        variables["event_type"] = event.event_type
        variables["player"] = event.player
        variables["segment_number"] = str(event.segment_number)
        variables["event_id"] = event.id
        for k, v in event.metadata.items():
            variables[k] = str(v)
    return TemplateContext(variables=variables)


def collect_provider_context(
    providers: list[TemplateProvider],
    game_info: GameInfo,
    event: GameEvent | None = None,
) -> TemplateContext:
    """Aggregate context from all registered ``TemplateProvider`` instances."""
    result = TemplateContext()
    for provider in providers:
        ctx = provider.provide(game_info, event)
        result = result.merge(ctx)
    return result


# ---------------------------------------------------------------------------
# ASS subtitle helpers
# ---------------------------------------------------------------------------


def rgb_to_ass(rgb: tuple[int, int, int], alpha: int = 0) -> str:
    """Convert an RGB tuple to ASS color format (BGR with alpha).

    ASS format: ``&HAABBGGRR`` where AA is alpha (00=opaque, FF=transparent).
    """
    r, g, b = rgb
    alpha_clamped = max(0, min(255, alpha))
    return f"&H{alpha_clamped:02X}{b:02X}{g:02X}{r:02X}"


def format_ass_time(seconds: float) -> str:
    """Format seconds as an ASS timestamp ``H:MM:SS.CC``."""
    total = max(0.0, float(seconds))
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = int(total % 60)
    centiseconds = round((total - int(total)) * 100)
    if centiseconds >= 100:
        centiseconds = 99  # pragma: no cover
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"
