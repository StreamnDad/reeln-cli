"""Sport alias registry, segment resolution, validation, and directory naming."""

from __future__ import annotations

import logging
from typing import Any

from reeln.core.errors import SegmentError
from reeln.core.log import get_logger
from reeln.models.segment import Segment, SportAlias

log: logging.Logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Built-in sport registry
# ---------------------------------------------------------------------------

_BUILTIN_SPORTS: dict[str, SportAlias] = {
    "hockey": SportAlias(sport="hockey", segment_name="period", segment_count=3, duration_minutes=20),
    "basketball": SportAlias(sport="basketball", segment_name="quarter", segment_count=4, duration_minutes=12),
    "soccer": SportAlias(sport="soccer", segment_name="half", segment_count=2, duration_minutes=45),
    "football": SportAlias(sport="football", segment_name="half", segment_count=2, duration_minutes=30),
    "baseball": SportAlias(sport="baseball", segment_name="inning", segment_count=9, duration_minutes=None),
    "lacrosse": SportAlias(sport="lacrosse", segment_name="quarter", segment_count=4, duration_minutes=12),
    "generic": SportAlias(sport="generic", segment_name="segment", segment_count=1, duration_minutes=None),
}

_custom_sports: dict[str, SportAlias] = {}


# ---------------------------------------------------------------------------
# Registry management
# ---------------------------------------------------------------------------


def register_sport(alias: SportAlias) -> None:
    """Register a custom sport alias. Overrides builtins if the name matches."""
    _custom_sports[alias.sport] = alias
    log.debug("Registered custom sport: %s", alias.sport)


def unregister_sport(sport: str) -> None:
    """Remove a custom sport registration."""
    _custom_sports.pop(sport, None)


def clear_custom_sports() -> None:
    """Remove all custom sport registrations."""
    _custom_sports.clear()


def get_sport(sport: str) -> SportAlias:
    """Look up a sport alias by name.

    Custom registrations take precedence over builtins.
    Raises ``SegmentError`` if the sport is not found.
    """
    if sport in _custom_sports:
        return _custom_sports[sport]
    if sport in _BUILTIN_SPORTS:
        return _BUILTIN_SPORTS[sport]
    available = sorted({*_BUILTIN_SPORTS, *_custom_sports})
    raise SegmentError(f"Unknown sport {sport!r}. Available: {', '.join(available)}")


def list_sports() -> list[SportAlias]:
    """Return all registered sports (builtins + custom), sorted by name."""
    merged = {**_BUILTIN_SPORTS, **_custom_sports}
    return [merged[k] for k in sorted(merged)]


# ---------------------------------------------------------------------------
# Directory naming
# ---------------------------------------------------------------------------


def segment_dir_name(sport: str, segment_number: int) -> str:
    """Return the directory name for a segment, e.g. ``'period-1'``, ``'quarter-3'``."""
    alias = get_sport(sport)
    validate_segment_number(segment_number)
    return f"{alias.segment_name}-{segment_number}"


def segment_display_name(sport: str, segment_number: int) -> str:
    """Return a human-readable segment label, e.g. ``'Period 1'``, ``'Quarter 3'``."""
    alias = get_sport(sport)
    validate_segment_number(segment_number)
    return f"{alias.segment_name.capitalize()} {segment_number}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_segment_number(segment_number: int) -> None:
    """Validate that a segment number is positive (1-indexed).

    Raises ``SegmentError`` if invalid.
    """
    if segment_number < 1:
        raise SegmentError(f"Segment number must be >= 1, got {segment_number}")


def validate_segment_for_sport(sport: str, segment_number: int) -> list[str]:
    """Validate a segment number against a sport's expected count.

    Returns a list of warnings (empty if OK). Does not raise — segment
    count is a hint, not a hard limit.
    """
    validate_segment_number(segment_number)
    alias = get_sport(sport)
    warnings: list[str] = []
    if segment_number > alias.segment_count:
        warnings.append(
            f"Segment {segment_number} exceeds expected count of {alias.segment_count} "
            f"for {alias.sport} ({alias.segment_name}s)"
        )
    return warnings


# ---------------------------------------------------------------------------
# Segment creation
# ---------------------------------------------------------------------------


def make_segment(sport: str, segment_number: int) -> Segment:
    """Create a ``Segment`` for the given sport and number."""
    dir_name = segment_dir_name(sport, segment_number)
    return Segment(number=segment_number, alias=dir_name)


def make_segments(sport: str, count: int | None = None) -> list[Segment]:
    """Create all segments for a sport.

    If *count* is ``None``, uses the sport's default segment count.
    """
    alias = get_sport(sport)
    n = count if count is not None else alias.segment_count
    return [make_segment(sport, i) for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# Custom sport from config dict
# ---------------------------------------------------------------------------


def sport_from_dict(data: dict[str, Any]) -> SportAlias:
    """Create a ``SportAlias`` from a config dict entry."""
    sport = str(data.get("sport", ""))
    if not sport:
        raise SegmentError("Custom sport entry missing 'sport' name")
    segment_name = str(data.get("segment_name", "segment"))
    segment_count = int(data.get("segment_count", 1))
    raw_duration = data.get("duration_minutes")
    duration_minutes = int(raw_duration) if raw_duration is not None else None
    return SportAlias(
        sport=sport,
        segment_name=segment_name,
        segment_count=segment_count,
        duration_minutes=duration_minutes,
    )
