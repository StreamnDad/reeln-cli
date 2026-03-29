"""Config command group: show, doctor."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from reeln.commands import event_types_cmd
from reeln.core.config import (
    config_to_dict,
    default_config_path,
    load_config,
    validate_config,
)
from reeln.core.errors import ConfigError

app = typer.Typer(no_args_is_help=True, help="Configuration commands.")
app.add_typer(event_types_cmd.app, name="event-types")


@app.command()
def show(
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    path: Path | None = typer.Option(None, "--path", help="Explicit config file path."),
) -> None:
    """Display current configuration."""
    try:
        config = load_config(path=path, profile=profile)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    data = config_to_dict(config, full=True)
    typer.echo(json.dumps(data, indent=2))


@app.command()
def doctor(
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    path: Path | None = typer.Option(None, "--path", help="Explicit config file path."),
) -> None:
    """Validate configuration, warn on issues."""
    try:
        config = load_config(path=path, profile=profile)
    except ConfigError as exc:
        typer.echo(f"Config file: {path or default_config_path(profile)}")
        typer.echo(f"  WARN: {exc}")
        raise typer.Exit(code=1) from exc

    data = config_to_dict(config)
    issues = validate_config(data)

    from reeln.core.config import validate_plugin_configs

    plugin_issues = validate_plugin_configs(config.plugins.settings)
    issues.extend(plugin_issues)

    config_path = path or default_config_path(profile)
    if config_path.is_file():
        typer.echo(f"Config file: {config_path}")
    else:
        typer.echo(f"Config file: {config_path} (not found, using defaults)")

    if issues:
        for issue in issues:
            typer.echo(f"  WARN: {issue}")
        raise typer.Exit(code=1)

    typer.echo("  OK: Configuration is valid")
