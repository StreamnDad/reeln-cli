"""Guided first-time configuration."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from reeln.core.config import (
    config_dir,
    default_config,
    save_config,
)
from reeln.core.errors import PromptAborted
from reeln.core.event_types import default_event_type_entries
from reeln.core.segment import list_sports
from reeln.models.config import AppConfig, PathConfig

console = Console()


def _interactive() -> bool:
    """Return True if stdin is an interactive terminal."""
    return sys.stdin.isatty()


def _require_questionary() -> types.ModuleType:
    """Lazy-import questionary with a helpful error if missing."""
    if not _interactive():
        msg = (
            "Interactive prompts require a terminal. "
            "Provide --sport, --source-dir, and --output-dir for non-interactive use."
        )
        raise typer.BadParameter(msg)
    try:
        import questionary
    except ImportError:
        raise typer.BadParameter(
            "Interactive prompts require the 'questionary' package. "
            "Install it with: pip install reeln[interactive]"
        ) from None
    return questionary


def _prompt_sport(preset: str | None) -> str:
    """Prompt for sport selection, or return preset."""
    if preset is not None:
        return preset
    questionary = _require_questionary()
    choices = [alias.sport for alias in list_sports()]
    answer: str | None = questionary.select(
        "Sport:",
        choices=choices,
        default="hockey",
    ).ask()
    if not answer:
        raise PromptAborted("Sport prompt cancelled")
    return answer


def _prompt_path(label: str, preset: Path | None, default_hint: str) -> Path:
    """Prompt for a directory path, or return preset."""
    if preset is not None:
        return preset
    questionary = _require_questionary()
    answer: str | None = questionary.text(
        f"{label}:",
        default=default_hint,
    ).ask()
    if not answer:
        raise PromptAborted(f"{label} prompt cancelled")
    return Path(answer)


def _prompt_overwrite(path: Path) -> bool:
    """Ask user whether to overwrite an existing config file."""
    questionary = _require_questionary()
    answer: bool | None = questionary.confirm(
        f"Config already exists at {path}. Overwrite?",
        default=False,
    ).ask()
    return bool(answer)


def init(
    sport: str | None = typer.Option(None, "--sport", help="Sport type"),
    source_dir: Path | None = typer.Option(
        None, "--source-dir", help="Replay source directory"
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Game output directory"
    ),
    config_path: Path | None = typer.Option(
        None, "--config", help="Config file path"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing config"
    ),
) -> None:
    """Set up reeln with guided configuration."""
    # 1. Resolve config path
    target = config_path if config_path is not None else config_dir() / "config.json"

    # 2. Check for existing config
    if target.exists() and not force:
        if _interactive():
            if not _prompt_overwrite(target):
                console.print("[yellow]Init cancelled.[/yellow]")
                raise typer.Exit(0)
        else:
            console.print(
                f"[yellow]Config already exists at {target}. "
                "Use --force to overwrite.[/yellow]"
            )
            raise typer.Exit(1)

    # 3. Gather inputs (prompt interactively when not provided)
    sport_val = _prompt_sport(sport)
    source = _prompt_path(
        "Replay source directory",
        source_dir,
        str(Path.home() / "Videos" / "OBS"),
    )
    output = _prompt_path(
        "Game output directory",
        output_dir,
        str(Path.home() / "Videos" / "reeln"),
    )

    # 4. Build config from defaults + user inputs
    cfg = default_config()
    cfg = AppConfig(
        config_version=cfg.config_version,
        sport=sport_val,
        event_types=default_event_type_entries(sport_val),
        video=cfg.video,
        paths=PathConfig(
            source_dir=source.expanduser(),
            source_glob=cfg.paths.source_glob,
            output_dir=output.expanduser(),
            temp_dir=cfg.paths.temp_dir,
        ),
        render_profiles=cfg.render_profiles,
        iterations=cfg.iterations,
        branding=cfg.branding,
        orchestration=cfg.orchestration,
        plugins=cfg.plugins,
    )

    # 5. Create directories
    source.expanduser().mkdir(parents=True, exist_ok=True)
    output.expanduser().mkdir(parents=True, exist_ok=True)

    # 6. Save config
    saved_path = save_config(cfg, target)

    # 7. Summary
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Sport", sport_val)
    table.add_row("Source", str(source.expanduser()))
    table.add_row("Output", str(output.expanduser()))
    table.add_row("Config", str(saved_path))

    event_names = [et.name for et in cfg.event_types]
    if event_names:
        table.add_row("Events", ", ".join(event_names))

    console.print()
    console.print(
        Panel(
            table,
            title="[green]reeln initialized[/green]",
            border_style="green",
        )
    )
    console.print()
    console.print("Next steps:")
    console.print("  reeln game init    Create your first game")
    console.print("  reeln config show  View full configuration")
    console.print("  reeln doctor       Run health checks")
