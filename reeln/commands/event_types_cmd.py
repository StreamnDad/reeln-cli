"""Event types configuration subcommands: list, add, remove, set, defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from reeln.core.config import load_config, save_config
from reeln.core.errors import ConfigError
from reeln.core.event_types import default_event_types
from reeln.models.config import EventTypeEntry

app = typer.Typer(no_args_is_help=True, help="Manage configured event types.")


@app.command("list")
def list_cmd(
    profile: Optional[str] = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Show configured event types (or sport defaults if none configured)."""
    try:
        config = load_config(path=config_path, profile=profile)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if config.event_types:
        for et in config.event_types:
            label = f"{et.name} (team)" if et.team_specific else et.name
            typer.echo(label)
    else:
        defaults = default_event_types(config.sport)
        if defaults:
            typer.echo(f"No event types configured. Defaults for {config.sport}:")
            for t in defaults:
                typer.echo(f"  {t}")
        else:
            typer.echo("No event types configured.")


@app.command()
def add(
    event_type: str = typer.Argument(..., help="Event type to add."),
    team: bool = typer.Option(False, "--team", help="Mark as team-specific (Home/Away variants)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Add an event type to the configuration."""
    try:
        config = load_config(path=config_path, profile=profile)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    existing_names = [et.name for et in config.event_types]
    if event_type in existing_names:
        typer.echo(f"Event type '{event_type}' already configured.")
        return

    config.event_types.append(EventTypeEntry(name=event_type, team_specific=team))
    save_config(config, path=config_path)
    names = ", ".join(et.name for et in config.event_types)
    typer.echo(f"Added '{event_type}'{' (team)' if team else ''}. Event types: {names}")


@app.command()
def remove(
    event_type: str = typer.Argument(..., help="Event type to remove."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Remove an event type from the configuration."""
    try:
        config = load_config(path=config_path, profile=profile)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    match = next((et for et in config.event_types if et.name == event_type), None)
    if match is None:
        typer.echo(f"Error: Event type '{event_type}' not found in configuration.", err=True)
        raise typer.Exit(code=1)

    config.event_types.remove(match)
    save_config(config, path=config_path)
    remaining = ", ".join(et.name for et in config.event_types) if config.event_types else "(empty)"
    typer.echo(f"Removed '{event_type}'. Event types: {remaining}")


@app.command("set")
def set_cmd(
    event_types: list[str] = typer.Argument(..., help="Event types to set (replaces existing)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Replace all configured event types."""
    try:
        config = load_config(path=config_path, profile=profile)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    config.event_types = [EventTypeEntry(name=t) for t in event_types]
    save_config(config, path=config_path)
    typer.echo(f"Event types set: {', '.join(et.name for et in config.event_types)}")


@app.command()
def defaults(
    profile: Optional[str] = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Show default event types for the configured sport."""
    try:
        config = load_config(path=config_path, profile=profile)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    types = default_event_types(config.sport)
    if types:
        typer.echo(f"Default event types for {config.sport}:")
        for t in types:
            typer.echo(f"  {t}")
    else:
        typer.echo(f"No default event types for {config.sport}.")
