"""Event listing, tagging, resolution, and compilation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reeln.core.errors import MediaError
from reeln.core.highlights import load_game_state, save_game_state
from reeln.models.config import VideoConfig
from reeln.models.game import GameEvent
from reeln.models.render_plan import CompilationResult

# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------


def list_events(
    game_dir: Path,
    *,
    segment_number: int | None = None,
    event_type: str | None = None,
    untagged_only: bool = False,
) -> list[GameEvent]:
    """Filter and return events from game state."""
    state = load_game_state(game_dir)
    events = state.events

    if segment_number is not None:
        events = [e for e in events if e.segment_number == segment_number]
    if event_type is not None:
        events = [e for e in events if e.event_type == event_type]
    if untagged_only:
        events = [e for e in events if not e.event_type]

    return events


# ---------------------------------------------------------------------------
# ID resolution
# ---------------------------------------------------------------------------


def resolve_event_id(events: list[GameEvent], prefix: str) -> GameEvent:
    """Find an event by ID or unique prefix.

    Raises ``MediaError`` if the prefix is ambiguous or not found.
    """
    matches = [e for e in events if e.id.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        raise MediaError(f"No event found matching ID prefix: {prefix!r}")
    raise MediaError(f"Ambiguous event ID prefix: {prefix!r} matches {len(matches)} events")


# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------


def tag_event(
    game_dir: Path,
    event_id: str,
    *,
    event_type: str | None = None,
    player: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
) -> GameEvent:
    """Update fields on a single event. Returns the updated event."""
    state = load_game_state(game_dir)
    event = resolve_event_id(state.events, event_id)

    if event_type is not None:
        event.event_type = event_type
    if player is not None:
        event.player = player
    if metadata_updates:
        event.metadata.update(metadata_updates)

    save_game_state(state, game_dir)

    from reeln.plugins.hooks import Hook, HookContext
    from reeln.plugins.registry import get_registry

    get_registry().emit(
        Hook.ON_EVENT_TAGGED,
        HookContext(hook=Hook.ON_EVENT_TAGGED, data={"event": event}),
    )

    return event


def tag_events_in_segment(
    game_dir: Path,
    segment_number: int,
    *,
    event_type: str | None = None,
    player: str | None = None,
) -> list[GameEvent]:
    """Bulk-update all events in a segment. Returns updated events."""
    state = load_game_state(game_dir)
    matched = [e for e in state.events if e.segment_number == segment_number]

    if not matched:
        raise MediaError(f"No events found for segment {segment_number}")

    for event in matched:
        if event_type is not None:
            event.event_type = event_type
        if player is not None:
            event.player = player

    save_game_state(state, game_dir)
    return matched


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def compile_events(
    game_dir: Path,
    *,
    ffmpeg_path: Path,
    video_config: VideoConfig | None = None,
    event_type: str | None = None,
    segment_number: int | None = None,
    player: str | None = None,
    output: Path | None = None,
    dry_run: bool = False,
) -> tuple[CompilationResult, list[str]]:
    """Compile raw clips matching filter criteria into a single video."""
    from reeln.core.ffmpeg import (
        build_concat_command,
        run_ffmpeg,
        write_concat_file,
    )

    vc = video_config or VideoConfig()

    state = load_game_state(game_dir)
    info = state.game_info
    events = state.events

    if segment_number is not None:
        events = [e for e in events if e.segment_number == segment_number]
    if event_type is not None:
        events = [e for e in events if e.event_type == event_type]
    if player is not None:
        events = [e for e in events if e.player == player]

    if not events:
        raise MediaError("No events match the given criteria")

    # Sort by segment number, then clip path (filename within segment)
    events.sort(key=lambda e: (e.segment_number, e.clip))

    # Resolve clip paths
    files: list[Path] = []
    for ev in events:
        p = game_dir / ev.clip if not Path(ev.clip).is_absolute() else Path(ev.clip)
        if not p.is_file():
            raise MediaError(f"Event clip not found: {p}")
        files.append(p)

    # Build output name
    if output is not None:
        out = output
    else:
        filter_label = event_type or (f"segment-{segment_number}" if segment_number else "all")
        out = game_dir / f"{info.home_team}_vs_{info.away_team}_{info.date}_{filter_label}_compilation.mkv"

    extensions = {f.suffix.lower() for f in files}
    copy = len(extensions) <= 1

    messages: list[str] = []
    messages.append(f"Events: {len(events)}")
    for ev in events:
        label = ev.event_type or "untagged"
        messages.append(f"  [{label}] {ev.clip}")
    messages.append(f"Mode: {'stream copy' if copy else 're-encode (mixed formats)'}")
    messages.append(f"Output: {out}")

    if dry_run:
        result = CompilationResult(
            output=out,
            event_ids=[e.id for e in events],
            input_files=list(files),
            copy=copy,
        )
        messages.insert(0, "Dry run — no files written")
        return result, messages

    concat_file = write_concat_file(files, game_dir)
    cmd: list[str] = []
    try:
        cmd = build_concat_command(
            ffmpeg_path,
            concat_file,
            out,
            copy=copy,
            video_codec=vc.codec,
            crf=vc.crf,
            audio_codec=vc.audio_codec,
        )
        try:
            run_ffmpeg(cmd)
        except Exception as exc:
            from reeln.core.errors import emit_on_error

            emit_on_error(exc, context={"operation": "compile_events"})
            raise
    finally:
        concat_file.unlink(missing_ok=True)

    result = CompilationResult(
        output=out,
        event_ids=[e.id for e in events],
        input_files=list(files),
        copy=copy,
        ffmpeg_command=list(cmd),
    )

    messages.append("Compilation complete")
    return result, messages
