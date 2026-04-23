"""Central Typer app for the reeln CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from reeln import __version__
from reeln.commands import config_cmd, game, hooks_cmd, init_cmd, media, plugins_cmd, queue_cmd, render
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
app.add_typer(hooks_cmd.app, name="hooks")
app.add_typer(queue_cmd.app, name="queue")
app.command()(init_cmd.init)


def _version_callback(value: bool) -> None:
    if value:
        from reeln.commands.style import bold, error, label, success

        typer.echo(f"  {bold('reeln')}  {success(__version__)}")

        # FFmpeg info
        try:
            from reeln.core.ffmpeg import check_version, discover_ffmpeg

            ffmpeg_path = discover_ffmpeg()
            version = check_version(ffmpeg_path)
            typer.echo(f"  {bold('ffmpeg')}  {version}  {label(str(ffmpeg_path))}")
        except Exception:
            typer.echo(f"  {bold('ffmpeg')}  {error('not found')}")

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
                        plugin_lines.append(f"    {p.name}  {label(ver)}")
            if plugin_lines:
                typer.echo(f"  {bold('plugins:')}")
                for pl in plugin_lines:
                    typer.echo(pl)
        except Exception:
            pass

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
    log_level: str = typer.Option(
        "WARNING",
        "--log-level",
        envvar="REELN_LOG_LEVEL",
        help="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    ),
    no_enforce_hooks: bool = typer.Option(
        False,
        "--no-enforce-hooks",
        help="Disable registry-based hook enforcement for plugins.",
    ),
) -> None:
    """Platform-agnostic CLI toolkit for livestreamers."""
    import logging

    if no_enforce_hooks:
        from reeln.plugins.loader import set_enforce_hooks_override

        set_enforce_hooks_override(disable=True)

    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        typer.echo(f"Invalid log level: {log_level}", err=True)
        raise typer.Exit(code=2)
    setup_logging(level=numeric_level, log_format=log_format)


@app.command()
def doctor(
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Run health checks: ffmpeg, config, permissions, plugins."""
    from reeln.core.config import load_config
    from reeln.core.doctor import doctor_exit_code, format_results, run_doctor
    from reeln.models.doctor import DoctorCheck
    from reeln.plugins.loader import activate_plugins, collect_doctor_checks

    extra: list[DoctorCheck] = []
    try:
        cfg = load_config(path=config, profile=profile)
        loaded = activate_plugins(cfg.plugins)
        extra = collect_doctor_checks(loaded)
    except Exception:
        pass  # config/plugin errors are reported by run_doctor's own checks

    results = run_doctor(config_path=config, profile=profile, extra_checks=extra)
    lines = format_results(results)
    for line in lines:
        typer.echo(line)
    code = doctor_exit_code(results)
    raise typer.Exit(code=code)
