"""Event subcommands: list, tag, tag-all."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from reeln.core.config import load_config
from reeln.core.errors import ReelnError
from reeln.plugins.loader import activate_plugins

app = typer.Typer(no_args_is_help=True, help="Event tracking commands.")


def _resolve_game_dir(output_dir: Path | None, config_output_dir: Path | None) -> Path:
    """Resolve game directory (same logic as game commands)."""
    from reeln.commands.game import _resolve_game_dir as _resolve

    return _resolve(output_dir, config_output_dir)


@app.command("list")
def list_cmd(
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Game directory."),
    segment: Optional[int] = typer.Option(None, "--segment", "-s", help="Filter by segment number."),
    event_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by event type."),
    untagged: bool = typer.Option(False, "--untagged", help="Show only untagged events."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """List registered events in the current game."""
    from reeln.core.events import list_events

    try:
        config = load_config(path=config_path, profile=profile)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    game_dir = _resolve_game_dir(output_dir, config.paths.output_dir)

    try:
        events = list_events(
            game_dir,
            segment_number=segment,
            event_type=event_type,
            untagged_only=untagged,
        )
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not events:
        typer.echo("No events found.")
        return

    # Header
    typer.echo(f"{'ID':<10} {'Seg':>3} {'Type':<12} {'Player':<12} Clip")
    for ev in events:
        eid = ev.id[:8]
        seg = str(ev.segment_number)
        etype = ev.event_type or "(untagged)"
        player = ev.player or ""
        typer.echo(f"{eid:<10} {seg:>3} {etype:<12} {player:<12} {ev.clip}")


@app.command()
def tag(
    event_id: str = typer.Argument(..., help="Event ID (or prefix)."),
    event_type: Optional[str] = typer.Option(None, "--type", "-t", help="Event type (e.g. goal, save)."),
    player: Optional[str] = typer.Option(None, "--player", "-p", help="Player name/number."),
    meta: Optional[list[str]] = typer.Option(None, "--meta", "-m", help="Metadata key=value pair."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Game directory."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Tag an event with type, player, and metadata."""
    from reeln.core.events import tag_event

    try:
        config = load_config(path=config_path, profile=profile)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    activate_plugins(config.plugins)

    game_dir = _resolve_game_dir(output_dir, config.paths.output_dir)

    metadata_updates: dict[str, str] | None = None
    if meta:
        metadata_updates = {}
        for item in meta:
            if "=" not in item:
                typer.echo(
                    f"Error: Invalid metadata format: {item!r}. Use key=value.",
                    err=True,
                )
                raise typer.Exit(code=1)
            key, value = item.split("=", 1)
            metadata_updates[key] = value

    try:
        updated = tag_event(
            game_dir,
            event_id,
            event_type=event_type,
            player=player,
            metadata_updates=metadata_updates,
        )
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Updated event {updated.id[:8]}")
    if event_type is not None:
        typer.echo(f"  Type: {event_type}")
    if player is not None:
        typer.echo(f"  Player: {player}")
    if metadata_updates:
        for k, v in metadata_updates.items():
            typer.echo(f"  {k}: {v}")


@app.command("tag-all")
def tag_all(
    segment_number: int = typer.Argument(..., help="Segment number."),
    event_type: Optional[str] = typer.Option(None, "--type", "-t", help="Event type."),
    player: Optional[str] = typer.Option(None, "--player", "-p", help="Player name/number."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Game directory."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Bulk-tag all events in a segment."""
    from reeln.core.events import tag_events_in_segment

    try:
        config = load_config(path=config_path, profile=profile)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    game_dir = _resolve_game_dir(output_dir, config.paths.output_dir)

    try:
        updated = tag_events_in_segment(
            game_dir,
            segment_number,
            event_type=event_type,
            player=player,
        )
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Updated {len(updated)} event(s) in segment {segment_number}")
    if event_type is not None:
        typer.echo(f"  Type: {event_type}")
    if player is not None:
        typer.echo(f"  Player: {player}")
