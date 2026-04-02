"""Non-interactive hook execution for external callers (e.g. reeln-dock)."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import typer

from reeln.core.config import load_config
from reeln.core.errors import ReelnError
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.loader import activate_plugins
from reeln.plugins.registry import get_registry

app = typer.Typer(no_args_is_help=True, help="Hook execution commands (JSON-in/JSON-out).")


# ---------------------------------------------------------------------------
# In-memory log capture
# ---------------------------------------------------------------------------


class _LogCapture(logging.Handler):
    """Collects log records emitted during hook execution."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []
        self.errors: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        if record.levelno >= logging.ERROR:
            self.errors.append(msg)
        else:
            self.records.append(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HOOK_LOOKUP: dict[str, Hook] = {h.value: h for h in Hook}


def _resolve_hook(name: str) -> Hook:
    """Resolve a hook name string to a Hook enum, case-insensitive."""
    normalised = name.lower().removeprefix("hook.").strip()
    hook = _HOOK_LOOKUP.get(normalised)
    if hook is None:
        valid = ", ".join(sorted(_HOOK_LOOKUP))
        raise typer.BadParameter(f"Unknown hook: {name!r}. Valid hooks: {valid}")
    return hook


def _dicts_to_namespaces(data: dict[str, Any]) -> dict[str, Any]:
    """Convert nested dicts to SimpleNamespace objects.

    Plugins use ``getattr(context.data["game_info"], "home_team", "")``
    which requires attribute-style access.  JSON input produces plain dicts
    where ``getattr`` doesn't find keys.  Converting to SimpleNamespace
    bridges the gap.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = SimpleNamespace(**_dicts_to_namespaces(value))
        else:
            result[key] = value
    return result


def _parse_json_arg(value: str | None, label: str) -> dict[str, Any]:
    """Parse a JSON string or @file reference into a dict."""
    if not value:
        return {}
    text = value
    if value.startswith("@"):
        file_path = Path(value[1:])
        if not file_path.is_file():
            raise typer.BadParameter(f"{label} file not found: {file_path}")
        text = file_path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON for {label}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise typer.BadParameter(f"{label} must be a JSON object, got {type(parsed).__name__}")
    return parsed


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@app.command()
def run(
    hook_name: str = typer.Argument(..., help="Hook to emit (e.g. on_game_init, on_game_ready)."),
    context_json: str | None = typer.Option(
        None,
        "--context-json",
        help="Hook context data as JSON string or @file path.",
    ),
    shared_json: str | None = typer.Option(
        None,
        "--shared-json",
        help="Shared dict from a previous hook (for chaining). JSON string or @file path.",
    ),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    """Execute a single hook and return results as JSON.

    Loads enabled plugins from config, emits the specified hook with the
    provided context, and prints the resulting shared dict as JSON to stdout.
    Designed for machine consumption — no interactive prompts, no ANSI output.

    \b
    Examples:
        reeln hooks run on_game_init --context-json '{"game_dir": "/path", "game_info": {...}}'
        reeln hooks run on_game_ready --context-json '{"game_dir": "/path"}' --shared-json '@/tmp/shared.json'
    """
    # Resolve hook enum
    hook = _resolve_hook(hook_name)

    # Parse JSON inputs
    context_data = _parse_json_arg(context_json, "context-json")
    shared_data = _parse_json_arg(shared_json, "shared-json")

    # Install log capture before plugin activation
    capture = _LogCapture()
    capture.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(capture)
    # Ensure plugin-level logs are captured
    root_logger.setLevel(min(root_logger.level, logging.INFO))

    success = True
    result_shared: dict[str, Any] = {}

    try:
        # Load config and activate plugins
        try:
            config = load_config(path=config_path, profile=profile)
        except ReelnError as exc:
            raise typer.Exit(code=1) from _emit_error(f"Config load failed: {exc}")

        activate_plugins(config.plugins)

        # Convert nested dicts to SimpleNamespace for getattr-based plugin access
        enriched_data = _dicts_to_namespaces(context_data)

        # Build context and emit
        ctx = HookContext(hook=hook, data=enriched_data, shared=dict(shared_data))
        get_registry().emit(hook, ctx)

        result_shared = dict(ctx.shared)

    except typer.Exit:
        raise
    except Exception as exc:
        success = False
        capture.errors.append(f"Hook execution failed: {exc}")
    finally:
        root_logger.removeHandler(capture)

    # Emit JSON result to stdout
    output = {
        "success": success,
        "hook": hook.value,
        "shared": result_shared,
        "logs": capture.records,
        "errors": capture.errors,
    }
    sys.stdout.write(json.dumps(output, default=str) + "\n")


def _emit_error(message: str) -> Exception:
    """Write an error JSON response and return an exception for chaining."""
    output = {
        "success": False,
        "hook": "",
        "shared": {},
        "logs": [],
        "errors": [message],
    }
    sys.stdout.write(json.dumps(output) + "\n")
    return ReelnError(message)


@app.command(name="list")
def list_hooks() -> None:
    """List all available hook names."""
    for hook in Hook:
        typer.echo(hook.value)
