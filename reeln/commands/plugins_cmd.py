"""Plugin management commands: list, enable, disable, search, info, install, update, inputs."""

from __future__ import annotations

import typer

from reeln.core.config import load_config, save_config
from reeln.core.errors import RegistryError
from reeln.core.plugin_registry import (
    build_plugin_status,
    fetch_registry,
    get_installed_version,
    install_plugin,
    uninstall_plugin,
    update_all_plugins,
    update_plugin,
)
from reeln.models.plugin import PluginStatus
from reeln.plugins.loader import (
    discover_plugins,
)

from reeln.commands.style import bold, error, label, success, warn

app = typer.Typer(no_args_is_help=True, help="Plugin management commands.")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _status_badge(enabled: bool, installed: bool) -> str:
    """Colored status badge."""
    if not installed:
        return label("not installed")
    if enabled:
        return success("enabled")
    return error("disabled")


def _version_str(status: PluginStatus) -> str:
    """Format version with optional upgrade indicator."""
    if not status.installed or not status.installed_version:
        return ""
    if status.update_available and status.available_version:
        return f"{status.installed_version} {warn(f'-> {status.available_version}')}"
    return status.installed_version


# ---------------------------------------------------------------------------
# plugins list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_plugins(
    refresh: bool = typer.Option(False, "--refresh", help="Force registry refresh."),
) -> None:
    """List installed and enabled plugins with version info."""
    config = load_config()
    plugins = discover_plugins()

    try:
        entries = fetch_registry(config.plugins.registry_url, force_refresh=refresh)
    except RegistryError:
        entries = []

    statuses = build_plugin_status(entries, plugins, config.plugins.enabled, config.plugins.disabled)
    installed = [st for st in statuses if st.installed]

    if not installed:
        typer.echo("No plugins installed.")
        return

    for st in installed:
        badge = _status_badge(st.enabled, st.installed)
        ver = _version_str(st)
        ver_part = f"  {ver}" if ver else ""

        typer.echo(f"  {bold(st.name)}  {badge}{ver_part}")
        if st.description:
            typer.echo(f"    {label(st.description)}")


# ---------------------------------------------------------------------------
# plugins search
# ---------------------------------------------------------------------------


@app.command()
def search(
    query: str = typer.Argument("", help="Search term (empty = show all)."),
    refresh: bool = typer.Option(False, "--refresh", help="Force registry refresh."),
) -> None:
    """Search the plugin registry."""
    config = load_config()
    try:
        entries = fetch_registry(config.plugins.registry_url, force_refresh=refresh)
    except RegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if not entries:
        typer.echo("No plugins in the registry.")
        return

    installed_plugins = discover_plugins()
    installed_names = {p.name for p in installed_plugins}

    matches = entries
    if query:
        q = query.lower()
        matches = [e for e in entries if q in e.name.lower() or q in e.description.lower()]

    if not matches:
        typer.echo(f"No plugins matching '{query}'.")
        return

    for entry in matches:
        installed = entry.name in installed_names
        badge = success("installed") if installed else label("available")
        typer.echo(f"  {bold(entry.name)}  {badge}")
        if entry.description:
            typer.echo(f"    {label(entry.description)}")


# ---------------------------------------------------------------------------
# plugins info
# ---------------------------------------------------------------------------


@app.command()
def info(
    name: str = typer.Argument(..., help="Plugin name."),
    refresh: bool = typer.Option(False, "--refresh", help="Force registry refresh."),
) -> None:
    """Show detailed information about a plugin."""
    config = load_config()
    try:
        entries = fetch_registry(config.plugins.registry_url, force_refresh=refresh)
    except RegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    entry = None
    for e in entries:
        if e.name == name:
            entry = e
            break

    if entry is None:
        typer.echo(f"Plugin '{name}' not found in the registry.")
        raise typer.Exit(1)

    installed_version = get_installed_version(entry.package) if entry.package else ""
    is_installed = bool(installed_version)

    typer.echo(f"\n  {bold(entry.name)}  {_status_badge(True, is_installed)}")
    typer.echo(f"  {entry.description}\n")

    typer.echo(f"  {label('Package:')}      {entry.package}")
    if is_installed:
        typer.echo(f"  {label('Version:')}      {installed_version}")
    typer.echo(f"  {label('Author:')}       {entry.author or 'N/A'}")
    typer.echo(f"  {label('License:')}      {entry.license or 'N/A'}")
    if entry.homepage:
        typer.echo(f"  {label('Homepage:')}     {entry.homepage}")

    from reeln.core.plugin_config import extract_schema_by_name

    schema = extract_schema_by_name(name)
    if schema is not None and schema.fields:
        typer.echo(f"\n  {label('Settings:')}")
        for f in schema.fields:
            req = warn(" (required)") if f.required else ""
            default = f" [{f.default}]" if f.default is not None else ""
            typer.echo(f"    {f.name}: {f.field_type}{req}{default}")
            if f.description:
                typer.echo(f"      {label(f.description)}")
    typer.echo()


# ---------------------------------------------------------------------------
# plugins install
# ---------------------------------------------------------------------------


@app.command()
def install(
    name: str = typer.Argument(..., help="Plugin name to install."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without installing."),
    installer: str = typer.Option("", "--installer", help="Force installer (pip, uv)."),
    version: str = typer.Option("", "--version", "-V", help="Version to install (e.g. 0.1.0, v0.1.0)."),
) -> None:
    """Install a plugin from the registry."""
    config = load_config()
    try:
        entries = fetch_registry(config.plugins.registry_url)
    except RegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    try:
        result = install_plugin(name, entries, dry_run=dry_run, installer=installer, version=version)
    except RegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if result.success:
        typer.echo(result.output if dry_run else f"Plugin '{name}' installed successfully.")
        # Auto-enable on install (not during dry-run)
        if not dry_run:
            if name not in config.plugins.enabled:
                config.plugins.enabled.append(name)
            if name in config.plugins.disabled:
                config.plugins.disabled.remove(name)
            from reeln.core.plugin_config import extract_schema_by_name, seed_defaults

            schema = extract_schema_by_name(name)
            if schema is not None:
                config.plugins.settings = seed_defaults(name, schema, config.plugins.settings)
            save_config(config)
            typer.echo(f"Plugin '{name}' enabled.")
    else:
        typer.echo(f"Failed to install '{name}': {result.error}", err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# plugins update
# ---------------------------------------------------------------------------


@app.command()
def update(
    name: str = typer.Argument("", help="Plugin to update (empty = all)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without updating."),
    installer: str = typer.Option("", "--installer", help="Force installer (pip, uv)."),
    version: str = typer.Option("", "--version", "-V", help="Version to update to (e.g. 0.1.0, v0.1.0)."),
) -> None:
    """Update a plugin or all installed plugins."""
    config = load_config()
    try:
        entries = fetch_registry(config.plugins.registry_url)
    except RegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if name:
        # Update single plugin
        try:
            result = update_plugin(name, entries, dry_run=dry_run, installer=installer, version=version)
        except RegistryError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

        if result.success:
            typer.echo(result.output if dry_run else f"Plugin '{name}' updated successfully.")
        else:
            typer.echo(f"Failed to update '{name}': {result.error}", err=True)
            raise typer.Exit(1)
    else:
        # Update all
        installed = discover_plugins()
        if not installed:
            typer.echo("No plugins installed.")
            return

        results = update_all_plugins(entries, installed, dry_run=dry_run, installer=installer)
        if not results:
            typer.echo("No installed plugins found in the registry.")
            return

        for r in results:
            if r.success:
                typer.echo(r.output if dry_run else f"Updated '{r.package}'.")
            else:
                typer.echo(f"Failed to update '{r.package}': {r.error}", err=True)


# ---------------------------------------------------------------------------
# plugins enable / disable
# ---------------------------------------------------------------------------


@app.command()
def enable(name: str = typer.Argument(..., help="Plugin name to enable.")) -> None:
    """Enable a plugin."""
    config = load_config()

    if name not in config.plugins.enabled:
        config.plugins.enabled.append(name)
    if name in config.plugins.disabled:
        config.plugins.disabled.remove(name)

    from reeln.core.plugin_config import extract_schema_by_name, seed_defaults

    schema = extract_schema_by_name(name)
    if schema is not None:
        config.plugins.settings = seed_defaults(name, schema, config.plugins.settings)

    save_config(config)
    typer.echo(f"Plugin '{name}' enabled.")


@app.command()
def disable(name: str = typer.Argument(..., help="Plugin name to disable.")) -> None:
    """Disable a plugin."""
    config = load_config()

    if name not in config.plugins.disabled:
        config.plugins.disabled.append(name)
    if name in config.plugins.enabled:
        config.plugins.enabled.remove(name)

    save_config(config)
    typer.echo(f"Plugin '{name}' disabled.")


@app.command()
def uninstall(
    name: str = typer.Argument(..., help="Plugin name to uninstall."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without uninstalling."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
    installer: str = typer.Option("", "--installer", help="Force installer (pip, uv)."),
) -> None:
    """Uninstall a plugin and remove it from config."""
    config = load_config()

    installed_version = ""
    try:
        entries = fetch_registry(config.plugins.registry_url)
    except RegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    # Find package name from registry
    entry = None
    for e in entries:
        if e.name == name:
            entry = e
            break

    if entry is not None and entry.package:
        installed_version = get_installed_version(entry.package)

    if not installed_version:
        typer.echo(f"Plugin '{name}' is not installed.")
        raise typer.Exit(1)

    if not force and not dry_run:
        confirm = typer.confirm(f"Uninstall plugin '{name}' ({installed_version})?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit()

    try:
        result = uninstall_plugin(name, entries, dry_run=dry_run, installer=installer)
    except RegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if result.success:
        typer.echo(result.output if dry_run else f"Plugin '{name}' uninstalled.")
        if not dry_run:
            if name in config.plugins.enabled:
                config.plugins.enabled.remove(name)
            if name not in config.plugins.disabled:
                config.plugins.disabled.append(name)
            save_config(config)
    else:
        typer.echo(f"Failed to uninstall '{name}': {result.error}", err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# plugins inputs
# ---------------------------------------------------------------------------


@app.command()
def inputs(
    command: str = typer.Option("", "--command", "-c", help="Filter by command scope (e.g. game_init)."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show plugin-contributed input fields for CLI commands."""
    import json

    from reeln.models.plugin_input import input_field_to_dict
    from reeln.plugins.inputs import get_input_collector
    from reeln.plugins.loader import activate_plugins

    config = load_config()
    activate_plugins(config.plugins)

    collector = get_input_collector()

    if command:
        commands = [command]
    else:
        from reeln.models.plugin_input import InputCommand

        commands = sorted(InputCommand._ALL)

    all_fields: list[dict[str, object]] = []
    for cmd in commands:
        fields = collector.fields_for_command(cmd)
        for f in fields:
            all_fields.append(input_field_to_dict(f))

    if json_output:
        typer.echo(json.dumps({"fields": all_fields}, indent=2))
        return

    if not all_fields:
        typer.echo("No plugin input contributions registered.")
        return

    # Group by command for readability
    by_command: dict[str, list[dict[str, object]]] = {}
    for f_dict in all_fields:
        cmd_name = str(f_dict.get("command", ""))
        by_command.setdefault(cmd_name, []).append(f_dict)

    for cmd_name, cmd_fields in sorted(by_command.items()):
        typer.echo(f"\n  {typer.style(cmd_name, bold=True)}")
        for f_dict in cmd_fields:
            req = warn(" (required)") if f_dict.get("required") else ""
            plugin = f_dict.get("plugin_name", "")
            plugin_str = f"  {label(f'[{plugin}]')}" if plugin else ""
            typer.echo(f"    {f_dict['id']}  {label(str(f_dict.get('type', '')))}{req}{plugin_str}")
            if f_dict.get("description"):
                typer.echo(f"      {label(str(f_dict['description']))}")
    typer.echo()
