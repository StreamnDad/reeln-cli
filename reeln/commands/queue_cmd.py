"""Queue management commands: list, show, edit, publish, remove, targets."""

from __future__ import annotations

from pathlib import Path

import typer

from reeln.commands.style import bold, error, label, success, warn
from reeln.core.errors import QueueError
from reeln.models.queue import PublishStatus, QueueStatus

app = typer.Typer(no_args_is_help=True, help="Render queue management commands.")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _status_badge(status: QueueStatus) -> str:
    """Colored badge for queue item status."""
    if status is QueueStatus.PUBLISHED:
        return success("published")
    if status is QueueStatus.PARTIAL:
        return warn("partial")
    if status is QueueStatus.FAILED:
        return error("failed")
    if status is QueueStatus.PUBLISHING:
        return warn("publishing")
    if status is QueueStatus.REMOVED:
        return label("removed")
    return label("rendered")


def _publish_badge(status: PublishStatus) -> str:
    """Colored badge for publish target status."""
    if status is PublishStatus.PUBLISHED:
        return success("published")
    if status is PublishStatus.FAILED:
        return error("failed")
    if status is PublishStatus.SKIPPED:
        return label("skipped")
    return label("pending")


def _short_id(item_id: str) -> str:
    """Display a short version of the ID."""
    return bold(item_id[:8])


# ---------------------------------------------------------------------------
# queue list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_queue(
    game_dir: Path | None = typer.Option(None, "--game-dir", "-g", help="Game directory."),
    all_games: bool = typer.Option(False, "--all", "-a", help="List across all games."),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status."),
) -> None:
    """List queued render items."""
    from reeln.core.queue import load_queue, load_queue_index

    dirs: list[Path] = []
    if all_games:
        index = load_queue_index()
        dirs = [Path(d) for d in index]
    elif game_dir:
        dirs = [game_dir]
    else:
        dirs = [Path.cwd()]

    status_filter: QueueStatus | None = None
    if status:
        try:
            status_filter = QueueStatus(status)
        except ValueError as exc:
            typer.echo(error(f"Unknown status: {status}"), err=True)
            raise typer.Exit(code=1) from exc

    total = 0
    for d in dirs:
        queue = load_queue(d)
        items = list(queue.items)
        if status_filter:
            items = [i for i in items if i.status is status_filter]
        items = [i for i in items if i.status is not QueueStatus.REMOVED]

        if not items:
            continue

        if all_games:
            typer.echo(f"\n{bold(str(d))}")

        for item in items:
            badge = _status_badge(item.status)
            title = item.title or "(untitled)"
            typer.echo(f"  {_short_id(item.id)}  {badge}  {title}")
            total += 1

    if total == 0:
        typer.echo("No queue items found.")


# ---------------------------------------------------------------------------
# queue show
# ---------------------------------------------------------------------------


@app.command()
def show(
    item_id: str = typer.Argument(..., help="Queue item ID (or prefix)."),
    game_dir: Path | None = typer.Option(None, "--game-dir", "-g", help="Game directory."),
) -> None:
    """Show detailed info for a queue item."""
    from reeln.core.queue import get_queue_item

    d = game_dir or Path.cwd()
    item = get_queue_item(d, item_id)
    if item is None:
        typer.echo(error(f"Queue item '{item_id}' not found."), err=True)
        raise typer.Exit(code=1)

    typer.echo(f"  {bold('ID:')}           {item.id}")
    typer.echo(f"  {bold('Status:')}       {_status_badge(item.status)}")
    typer.echo(f"  {bold('Title:')}        {item.title or '(untitled)'}")
    typer.echo(f"  {bold('Description:')}  {item.description or '(none)'}")
    typer.echo(f"  {bold('Output:')}       {item.output}")

    if item.duration_seconds is not None:
        typer.echo(f"  {bold('Duration:')}     {item.duration_seconds:.1f}s")
    if item.file_size_bytes is not None:
        size_mb = item.file_size_bytes / (1024 * 1024)
        typer.echo(f"  {bold('File size:')}    {size_mb:.1f} MB")

    if item.home_team or item.away_team:
        typer.echo(f"  {bold('Game:')}         {item.home_team} vs {item.away_team}")
    if item.player:
        typer.echo(f"  {bold('Player:')}       {item.player}")
    if item.assists:
        typer.echo(f"  {bold('Assists:')}      {item.assists}")
    if item.render_profile:
        typer.echo(f"  {bold('Profile:')}      {item.render_profile}")
    if item.crop_mode:
        typer.echo(f"  {bold('Crop mode:')}    {item.crop_mode}")
    typer.echo(f"  {bold('Queued at:')}    {item.queued_at}")

    if item.publish_targets:
        typer.echo(f"\n  {bold('Publish targets:')}")
        for t in item.publish_targets:
            badge = _publish_badge(t.status)
            url_part = f"  {t.url}" if t.url else ""
            err_part = f"  {error(t.error)}" if t.error else ""
            typer.echo(f"    {t.target}:  {badge}{url_part}{err_part}")


# ---------------------------------------------------------------------------
# queue edit
# ---------------------------------------------------------------------------


@app.command()
def edit(
    item_id: str = typer.Argument(..., help="Queue item ID (or prefix)."),
    title: str | None = typer.Option(None, "--title", "-t", help="New title."),
    description: str | None = typer.Option(None, "--description", "-d", help="New description."),
    game_dir: Path | None = typer.Option(None, "--game-dir", "-g", help="Game directory."),
) -> None:
    """Edit title or description of a queue item."""
    from reeln.core.queue import update_queue_item

    if title is None and description is None:
        typer.echo(error("Provide --title and/or --description to edit."), err=True)
        raise typer.Exit(code=1)

    d = game_dir or Path.cwd()
    try:
        updated = update_queue_item(d, item_id, title=title, description=description)
    except QueueError as exc:
        typer.echo(error(str(exc)), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Updated {_short_id(updated.id)}: {updated.title}")


# ---------------------------------------------------------------------------
# queue publish
# ---------------------------------------------------------------------------


@app.command()
def publish(
    item_id: str = typer.Argument(..., help="Queue item ID (or prefix)."),
    target: str | None = typer.Option(None, "--target", "-t", help="Publish to specific target only."),
    game_dir: Path | None = typer.Option(None, "--game-dir", "-g", help="Game directory."),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Publish a queue item to one or all targets."""
    from reeln.core.config import load_config
    from reeln.core.queue import get_queue_item, publish_queue_item
    from reeln.plugins.loader import activate_plugins

    d = game_dir or Path.cwd()

    # Use stored config_profile from queue item unless CLI --profile overrides
    effective_profile = profile
    if effective_profile is None:
        item = get_queue_item(d, item_id)
        if item is not None and item.config_profile:
            effective_profile = item.config_profile

    cfg = load_config(path=config, profile=effective_profile)
    plugins = activate_plugins(cfg.plugins)

    try:
        published = publish_queue_item(d, item_id, plugins, target=target)
    except QueueError as exc:
        typer.echo(error(str(exc)), err=True)
        raise typer.Exit(code=1) from exc

    for t in published.publish_targets:
        if t.status is PublishStatus.PUBLISHED:
            typer.echo(f"  {success('✓')} Published to {bold(t.target)}: {t.url}")
        elif t.status is PublishStatus.FAILED:
            typer.echo(f"  {error('✗')} Failed {bold(t.target)}: {t.error}")


# ---------------------------------------------------------------------------
# queue publish-all
# ---------------------------------------------------------------------------


@app.command(name="publish-all")
def publish_all_cmd(
    game_dir: Path | None = typer.Option(None, "--game-dir", "-g", help="Game directory."),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Publish all rendered items in the queue."""
    from reeln.core.config import load_config
    from reeln.core.queue import publish_all
    from reeln.plugins.loader import activate_plugins

    d = game_dir or Path.cwd()
    cfg = load_config(path=config, profile=profile)
    plugins = activate_plugins(cfg.plugins)

    results = publish_all(d, plugins)
    if not results:
        typer.echo("No items to publish.")
        return

    for item in results:
        typer.echo(f"  {_short_id(item.id)}  {_status_badge(item.status)}  {item.title}")


# ---------------------------------------------------------------------------
# queue remove
# ---------------------------------------------------------------------------


@app.command()
def remove(
    item_id: str = typer.Argument(..., help="Queue item ID (or prefix)."),
    game_dir: Path | None = typer.Option(None, "--game-dir", "-g", help="Game directory."),
) -> None:
    """Remove a queue item (soft-delete)."""
    from reeln.core.queue import remove_from_queue

    d = game_dir or Path.cwd()
    try:
        removed = remove_from_queue(d, item_id)
    except QueueError as exc:
        typer.echo(error(str(exc)), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Removed {_short_id(removed.id)}: {removed.title}")


# ---------------------------------------------------------------------------
# queue targets
# ---------------------------------------------------------------------------


@app.command()
def targets(
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """List available publish targets from loaded plugins."""
    from reeln.core.config import load_config
    from reeln.core.queue import discover_targets
    from reeln.plugins.loader import activate_plugins

    cfg = load_config(path=config, profile=profile)
    plugins = activate_plugins(cfg.plugins)
    target_list = discover_targets(plugins)

    if not target_list:
        typer.echo("No publish targets available. Install an uploader plugin.")
        return

    for t in target_list:
        typer.echo(f"  {bold(t)}")
