"""Media command group: prune."""

from __future__ import annotations

from pathlib import Path

import typer

from reeln.core.config import load_config
from reeln.core.errors import ReelnError

app = typer.Typer(no_args_is_help=True, help="Media management commands.")


@app.command()
def prune(
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base directory to scan for games."),
    all_files: bool = typer.Option(False, "--all", help="Also remove raw event clips."),
    force: bool = typer.Option(False, "--force", "-f", help="Remove untagged event clips."),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed."),
) -> None:
    """Remove generated artifacts from all finished games."""
    from reeln.core.prune import prune_all

    try:
        config = load_config(path=config_path, profile=profile)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    base = output_dir or config.paths.output_dir or Path.cwd()

    try:
        _, messages = prune_all(base, all_files=all_files, force=force, dry_run=dry_run)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for msg in messages:
        typer.echo(msg)
