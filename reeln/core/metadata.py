"""Centralized metadata generation for publish workflows."""

from __future__ import annotations

from typing import Any

from reeln.models.game import GameEvent, GameInfo


def generate_title(
    game_info: GameInfo | None = None,
    game_event: GameEvent | None = None,
    player: str = "",
    assists: str = "",
) -> str:
    """Generate a publish title from game and event context.

    Format: ``{player} {event_type} - {home_team} vs {away_team}``
    Falls back gracefully when fields are missing.
    """
    parts: list[str] = []

    # Player + event type
    event_type = game_event.event_type if game_event else ""
    effective_player = player or (game_event.player if game_event else "")
    if effective_player:
        label = event_type.title() if event_type else "Highlight"
        parts.append(f"{effective_player} {label}")
    elif event_type:
        parts.append(event_type.title())

    # Teams
    if game_info:
        parts.append(f"{game_info.home_team} vs {game_info.away_team}")

    return " - ".join(parts) if parts else "Highlight"


def generate_description(
    game_info: GameInfo | None = None,
    game_event: GameEvent | None = None,
    player: str = "",
    assists: str = "",
) -> str:
    """Generate a publish description from game and event context."""
    lines: list[str] = []

    if game_info:
        matchup = f"{game_info.home_team} vs {game_info.away_team}"
        if game_info.date:
            matchup += f" ({game_info.date})"
        lines.append(matchup)

        context_parts: list[str] = []
        if game_info.sport:
            context_parts.append(game_info.sport.title())
        if game_info.level:
            context_parts.append(game_info.level)
        if game_info.tournament:
            context_parts.append(game_info.tournament)
        if context_parts:
            lines.append(" | ".join(context_parts))

    effective_assists = assists
    if not effective_assists and game_event:
        effective_assists = game_event.metadata.get("assists", "")
    if effective_assists:
        lines.append(f"Assists: {effective_assists}")

    return "\n".join(lines)


def build_publish_metadata(
    *,
    title: str = "",
    description: str = "",
    game_info: GameInfo | None = None,
    game_event: GameEvent | None = None,
    player: str = "",
    assists: str = "",
    plugin_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the metadata dict that uploader plugins receive."""
    meta: dict[str, Any] = {
        "title": title,
        "description": description,
    }

    if game_info:
        meta["home_team"] = game_info.home_team
        meta["away_team"] = game_info.away_team
        meta["date"] = game_info.date
        meta["sport"] = game_info.sport
        if game_info.level:
            meta["level"] = game_info.level
        if game_info.tournament:
            meta["tournament"] = game_info.tournament

    if game_event:
        meta["event_type"] = game_event.event_type
        meta["event_id"] = game_event.id
        if game_event.metadata:
            meta["event_metadata"] = dict(game_event.metadata)

    if player:
        meta["player"] = player
    if assists:
        meta["assists"] = assists
    if plugin_inputs:
        meta["plugin_inputs"] = dict(plugin_inputs)

    return meta
