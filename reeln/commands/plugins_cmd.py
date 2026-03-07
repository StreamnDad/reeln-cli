"""Plugin management commands: list, enable, disable, search, info, install, update."""

from __future__ import annotations

import typer

from reeln.core.config import load_config, save_config
from reeln.core.errors import RegistryError
from reeln.core.plugin_registry import (
    build_plugin_status,
    fetch_registry,
    get_installed_version,
    install_plugin,
    update_all_plugins,
    update_plugin,
)
from reeln.plugins.loader import (
    discover_plugins,
)

app = typer.Typer(no_args_is_help=True, help="Plugin management commands.")


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

    if not statuses:
        typer.echo("No plugins installed or available.")
        return

    for st in statuses:
        # Name
        parts: list[str] = [f"  {st.name}"]

        # Version info
        if st.installed and st.installed_version:
            if st.update_available and st.available_version:
                parts.append(f"{st.installed_version} -> {st.available_version}")
            else:
                parts.append(st.installed_version)
        elif not st.installed:
            parts.append("not installed")

        # Status
        if st.installed:
            parts.append("enabled" if st.enabled else "disabled")

        # Capabilities
        if st.capabilities:
            parts.append(f"[{', '.join(st.capabilities)}]")

        typer.echo("  ".join(parts))


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
        status = "installed" if entry.name in installed_names else "available"
        typer.echo(f"  {entry.name}  {status}  {entry.description}")


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

    typer.echo(f"Name:         {entry.name}")
    typer.echo(f"Package:      {entry.package}")
    typer.echo(f"Description:  {entry.description}")
    typer.echo(f"Capabilities: {', '.join(entry.capabilities) if entry.capabilities else 'none'}")
    typer.echo(f"Homepage:     {entry.homepage or 'N/A'}")
    typer.echo(f"Author:       {entry.author or 'N/A'}")
    typer.echo(f"License:      {entry.license or 'N/A'}")
    typer.echo(f"Installed:    {'yes' if is_installed else 'no'}")
    if is_installed:
        typer.echo(f"Version:      {installed_version}")

    from reeln.core.plugin_config import extract_schema_by_name

    schema = extract_schema_by_name(name)
    if schema is not None:
        typer.echo("Config schema:")
        for f in schema.fields:
            req = " (required)" if f.required else ""
            default = f" [default: {f.default}]" if f.default is not None else ""
            desc = f"  — {f.description}" if f.description else ""
            typer.echo(f"  {f.name}: {f.field_type}{req}{default}{desc}")
    else:
        typer.echo("Config schema: none declared")


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
