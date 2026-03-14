"""Game finish logic — state transition and summary."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from reeln.core.errors import MediaError
from reeln.core.highlights import load_game_state, save_game_state
from reeln.core.log import get_logger
from reeln.models.game import GameState

log: logging.Logger = get_logger(__name__)


def finish_game(
    game_dir: Path,
    *,
    dry_run: bool = False,
) -> tuple[GameState, list[str]]:
    """Mark a game as finished and return a summary.

    Sets ``state.finished = True`` and ``state.finished_at`` to the current
    UTC timestamp.  If *dry_run* is ``True`` the state file is not written.

    Returns the updated ``GameState`` and a list of human-readable summary
    messages.

    Raises ``MediaError`` if the game is already finished.
    """
    state = load_game_state(game_dir)

    if state.finished:
        raise MediaError("Game is already finished")

    state.finished = True
    state.finished_at = datetime.now(UTC).isoformat()

    if not dry_run:
        save_game_state(state, game_dir)

        from reeln.plugins.hooks import Hook, HookContext
        from reeln.plugins.registry import get_registry

        hook_data = {"game_dir": game_dir, "state": state}
        ctx = HookContext(hook=Hook.ON_GAME_FINISH, data=hook_data)
        get_registry().emit(Hook.ON_GAME_FINISH, ctx)

        # Second pass — plugins read what others wrote during FINISH
        post_ctx = HookContext(
            hook=Hook.ON_POST_GAME_FINISH, data=hook_data, shared=ctx.shared
        )
        get_registry().emit(Hook.ON_POST_GAME_FINISH, post_ctx)

        log.info("Game finished: %s", game_dir)

    messages = _build_summary(state)
    return state, messages


def _build_summary(state: GameState) -> list[str]:
    """Build human-readable summary lines for a finished game."""
    info = state.game_info
    messages: list[str] = []

    messages.append(f"Game: {info.home_team} vs {info.away_team} ({info.date})")
    messages.append(f"Segments processed: {len(state.segments_processed)}")

    total_events = len(state.events)
    tagged = sum(1 for e in state.events if e.event_type)
    untagged = total_events - tagged
    if total_events > 0:
        messages.append(f"Events: {total_events} total ({tagged} tagged, {untagged} untagged)")
    else:
        messages.append("Events: 0")

    messages.append(f"Renders: {len(state.renders)}")
    messages.append(f"Highlighted: {'yes' if state.highlighted else 'no'}")
    messages.append("Status: Finished")

    return messages
