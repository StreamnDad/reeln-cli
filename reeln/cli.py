"""Central Typer app for the reeln CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from reeln import __version__
from reeln.commands import config_cmd, game, media, plugins_cmd, render
from reeln.core.log import setup_logging

app = typer.Typer(
    name="reeln",
    no_args_is_help=True,
    invoke_without_command=True,
    rich_markup_mode="rich",
    help="Platform-agnostic CLI toolkit for livestreamers.",
)

app.add_typer(game.app, name="game")
app.add_typer(render.app, name="render")
app.add_typer(media.app, name="media")
app.add_typer(config_cmd.app, name="config")
app.add_typer(plugins_cmd.app, name="plugins")


def _build_version_lines() -> list[str]:
    """Build version output lines: reeln version, ffmpeg info, plugins."""
    lines: list[str] = [f"reeln {__version__}"]

    # FFmpeg info
    try:
        from reeln.core.ffmpeg import check_version, discover_ffmpeg

        ffmpeg_path = discover_ffmpeg()
        version = check_version(ffmpeg_path)
        lines.append(f"ffmpeg {version} ({ffmpeg_path})")
    except Exception:
        lines.append("ffmpeg: not found")

    # Plugin versions
    try:
        from reeln.core.plugin_registry import get_installed_version
        from reeln.plugins.loader import discover_plugins

        plugins = discover_plugins()
        plugin_lines: list[str] = []
        for p in plugins:
            if p.package:
                ver = get_installed_version(p.package)
                if ver:
                    plugin_lines.append(f"  {p.name} {ver}")
        if plugin_lines:
            lines.append("plugins:")
            lines.extend(plugin_lines)
    except Exception:
        pass

    return lines


def _version_callback(value: bool) -> None:
    if value:
        for line in _build_version_lines():
            typer.echo(line)
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    log_format: str = typer.Option(
        "human",
        "--log-format",
        envvar="REELN_LOG_FORMAT",
        help="Log output format: human or json.",
    ),
) -> None:
    """Platform-agnostic CLI toolkit for livestreamers."""
    setup_logging(log_format=log_format)


@app.command()
def doctor(
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Run health checks: ffmpeg, config, permissions."""
    from reeln.core.doctor import doctor_exit_code, format_results, run_doctor

    results = run_doctor(config_path=config, profile=profile)
    lines = format_results(results)
    for line in lines:
        typer.echo(line)
    code = doctor_exit_code(results)
    raise typer.Exit(code=code)
