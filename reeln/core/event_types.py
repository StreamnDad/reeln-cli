"""Default event type definitions per sport."""

from __future__ import annotations

from reeln.models.config import EventTypeEntry

_DEFAULT_EVENT_TYPES: dict[str, list[tuple[str, bool]]] = {
    "hockey": [("goal", True), ("save", True), ("penalty", True), ("assist", False)],
    "basketball": [("basket", True), ("foul", True), ("turnover", True), ("block", True)],
    "soccer": [("goal", True), ("foul", True), ("corner", False), ("offside", False), ("save", True)],
    "football": [("touchdown", True), ("field-goal", True), ("interception", True), ("sack", True)],
    "nfl": [("touchdown", True), ("field-goal", True), ("interception", True), ("sack", True)],
    "american-football": [("touchdown", True), ("field-goal", True), ("interception", True), ("sack", True)],
    "baseball": [("hit", True), ("strikeout", True), ("home-run", True), ("catch", True)],
    "lacrosse": [("goal", True), ("save", True), ("penalty", True), ("ground-ball", False)],
}


def default_event_types(sport: str) -> list[str]:
    """Return default event type names for a sport."""
    entries = _DEFAULT_EVENT_TYPES.get(sport.lower(), [])
    return [name for name, _ in entries]


def default_event_type_entries(sport: str) -> list[EventTypeEntry]:
    """Return default event types with team-specific flags for a sport."""
    entries = _DEFAULT_EVENT_TYPES.get(sport.lower(), [])
    return [EventTypeEntry(name=name, team_specific=team) for name, team in entries]
