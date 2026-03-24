"""Tests for the plugins CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from reeln.cli import app
from reeln.core.errors import RegistryError
from reeln.core.plugin_registry import PipResult
from reeln.models.config import AppConfig, PluginsConfig
from reeln.models.plugin import PluginInfo, PluginStatus, RegistryEntry
from reeln.models.plugin_schema import ConfigField, PluginConfigSchema

runner = CliRunner()


# ---------------------------------------------------------------------------
# plugins list
# ---------------------------------------------------------------------------


def test_plugins_list_no_plugins_no_registry() -> None:
    with (
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch("reeln.commands.plugins_cmd.build_plugin_status", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "No plugins installed or available" in result.output


def test_plugins_list_shows_installed() -> None:
    statuses = [
        PluginStatus(
            name="youtube",
            installed=True,
            installed_version="1.0.0",
            available_version="1.1.0",
            enabled=True,
            capabilities=["uploader"],
            update_available=True,
        ),
        PluginStatus(
            name="llm",
            installed=True,
            installed_version="0.5.0",
            enabled=True,
            capabilities=["enricher", "generator"],
        ),
    ]
    with (
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch("reeln.commands.plugins_cmd.build_plugin_status", return_value=statuses),
    ):
        result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "youtube" in result.output
    assert "1.0.0" in result.output
    assert "1.1.0" in result.output
    assert "uploader" in result.output
    assert "llm" in result.output


def test_plugins_list_shows_not_installed() -> None:
    statuses = [
        PluginStatus(name="meta", installed=False, capabilities=["uploader"]),
    ]
    with (
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch("reeln.commands.plugins_cmd.build_plugin_status", return_value=statuses),
    ):
        result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "not installed" in result.output


def test_plugins_list_registry_error_graceful() -> None:
    with (
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch(
            "reeln.commands.plugins_cmd.fetch_registry",
            side_effect=RegistryError("offline"),
        ),
        patch("reeln.commands.plugins_cmd.build_plugin_status", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0


def test_plugins_list_with_refresh() -> None:
    with (
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]) as mock_fetch,
        patch("reeln.commands.plugins_cmd.build_plugin_status", return_value=[]),
    ):
        runner.invoke(app, ["plugins", "list", "--refresh"])
    mock_fetch.assert_called_once_with("", force_refresh=True)


def test_plugins_list_shows_disabled_status() -> None:
    statuses = [
        PluginStatus(name="youtube", installed=True, installed_version="1.0.0", enabled=False),
    ]
    with (
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch("reeln.commands.plugins_cmd.build_plugin_status", return_value=statuses),
    ):
        result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "disabled" in result.output


# ---------------------------------------------------------------------------
# plugins search
# ---------------------------------------------------------------------------


def test_plugins_search_all() -> None:
    entries = [
        RegistryEntry(name="youtube", package="reeln-youtube", description="YouTube uploader"),
        RegistryEntry(name="llm", package="reeln-llm", description="LLM enricher"),
    ]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "search"])
    assert result.exit_code == 0
    assert "youtube" in result.output
    assert "llm" in result.output


def test_plugins_search_with_query() -> None:
    entries = [
        RegistryEntry(name="youtube", package="reeln-youtube", description="YouTube uploader"),
        RegistryEntry(name="llm", package="reeln-llm", description="LLM enricher"),
    ]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "search", "youtube"])
    assert result.exit_code == 0
    assert "youtube" in result.output
    assert "llm" not in result.output


def test_plugins_search_no_matches() -> None:
    entries = [
        RegistryEntry(name="youtube", description="YouTube uploader"),
    ]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "search", "nonexistent"])
    assert result.exit_code == 0
    assert "No plugins matching" in result.output


def test_plugins_search_empty_registry() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "search"])
    assert result.exit_code == 0
    assert "No plugins in the registry" in result.output


def test_plugins_search_registry_error() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch(
            "reeln.commands.plugins_cmd.fetch_registry",
            side_effect=RegistryError("offline"),
        ),
    ):
        result = runner.invoke(app, ["plugins", "search"])
    assert result.exit_code == 1


def test_plugins_search_shows_installed_status() -> None:
    entries = [
        RegistryEntry(name="youtube", description="YouTube uploader"),
    ]
    installed = [PluginInfo(name="youtube", entry_point="yt:P")]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=installed),
    ):
        result = runner.invoke(app, ["plugins", "search"])
    assert "installed" in result.output


# ---------------------------------------------------------------------------
# plugins info
# ---------------------------------------------------------------------------


def test_plugins_info_found() -> None:
    entries = [
        RegistryEntry(
            name="youtube",
            package="reeln-youtube",
            description="YouTube uploader",
            capabilities=["uploader"],
            homepage="https://example.com",
            author="StreamnDad",
            license="AGPL-3.0",
        ),
    ]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value="1.0.0"),
    ):
        result = runner.invoke(app, ["plugins", "info", "youtube"])
    assert result.exit_code == 0
    assert "youtube" in result.output
    assert "reeln-youtube" in result.output
    assert "YouTube uploader" in result.output
    assert "uploader" in result.output
    assert "https://example.com" in result.output
    assert "1.0.0" in result.output
    assert "StreamnDad" in result.output
    assert "AGPL-3.0" in result.output


def test_plugins_info_not_found() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "info", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_plugins_info_not_installed() -> None:
    entries = [
        RegistryEntry(name="meta", package="reeln-meta", description="Meta uploader"),
    ]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value=""),
    ):
        result = runner.invoke(app, ["plugins", "info", "meta"])
    assert result.exit_code == 0
    assert "no" in result.output


def test_plugins_info_registry_error() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch(
            "reeln.commands.plugins_cmd.fetch_registry",
            side_effect=RegistryError("offline"),
        ),
    ):
        result = runner.invoke(app, ["plugins", "info", "youtube"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# plugins install
# ---------------------------------------------------------------------------


def test_plugins_install_success() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="install", output="ok")
    config = AppConfig()
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.install_plugin", return_value=pip_result),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
    ):
        result = runner.invoke(app, ["plugins", "install", "youtube"])
    assert result.exit_code == 0
    assert "installed successfully" in result.output
    assert "enabled" in result.output
    saved = mock_save.call_args[0][0]
    assert "youtube" in saved.plugins.enabled


def test_plugins_install_dry_run() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="dry-run", output="Would run: pip install")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.install_plugin", return_value=pip_result),
    ):
        result = runner.invoke(app, ["plugins", "install", "youtube", "--dry-run"])
    assert result.exit_code == 0
    assert "Would run:" in result.output


def test_plugins_install_failure() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=False, error="No matching distribution")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.install_plugin", return_value=pip_result),
    ):
        result = runner.invoke(app, ["plugins", "install", "youtube"])
    assert result.exit_code == 1
    assert "Failed" in result.output


def test_plugins_install_not_in_registry() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch(
            "reeln.commands.plugins_cmd.install_plugin",
            side_effect=RegistryError("not found"),
        ),
    ):
        result = runner.invoke(app, ["plugins", "install", "nonexistent"])
    assert result.exit_code == 1


def test_plugins_install_registry_error() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch(
            "reeln.commands.plugins_cmd.fetch_registry",
            side_effect=RegistryError("offline"),
        ),
    ):
        result = runner.invoke(app, ["plugins", "install", "youtube"])
    assert result.exit_code == 1


def test_plugins_install_with_version() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="install", output="ok")
    config = AppConfig()
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.install_plugin", return_value=pip_result) as mock_install,
        patch("reeln.commands.plugins_cmd.save_config"),
    ):
        result = runner.invoke(app, ["plugins", "install", "youtube", "--version", "1.2.0"])
    assert result.exit_code == 0
    assert "installed successfully" in result.output
    mock_install.assert_called_once_with(
        "youtube",
        entries,
        dry_run=False,
        installer="",
        version="1.2.0",
    )


def test_plugins_install_auto_enables_removes_from_disabled() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="install", output="ok")
    config = AppConfig(plugins=PluginsConfig(disabled=["youtube"]))
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.install_plugin", return_value=pip_result),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
    ):
        result = runner.invoke(app, ["plugins", "install", "youtube"])
    assert result.exit_code == 0
    saved = mock_save.call_args[0][0]
    assert "youtube" not in saved.plugins.disabled
    assert "youtube" in saved.plugins.enabled


# ---------------------------------------------------------------------------
# plugins update
# ---------------------------------------------------------------------------


def test_plugins_update_single_success() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="update", output="ok")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.update_plugin", return_value=pip_result),
    ):
        result = runner.invoke(app, ["plugins", "update", "youtube"])
    assert result.exit_code == 0
    assert "updated successfully" in result.output


def test_plugins_update_with_version() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="update", output="ok")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.update_plugin", return_value=pip_result) as mock_update,
    ):
        result = runner.invoke(app, ["plugins", "update", "youtube", "--version", "2.0.0"])
    assert result.exit_code == 0
    assert "updated successfully" in result.output
    mock_update.assert_called_once_with(
        "youtube",
        entries,
        dry_run=False,
        installer="",
        version="2.0.0",
    )


def test_plugins_update_single_failure() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=False, error="failed")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.update_plugin", return_value=pip_result),
    ):
        result = runner.invoke(app, ["plugins", "update", "youtube"])
    assert result.exit_code == 1


def test_plugins_update_all() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    installed = [PluginInfo(name="youtube", entry_point="yt:P")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="update")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=installed),
        patch("reeln.commands.plugins_cmd.update_all_plugins", return_value=[pip_result]),
    ):
        result = runner.invoke(app, ["plugins", "update"])
    assert result.exit_code == 0
    assert "Updated" in result.output


def test_plugins_update_all_no_plugins() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "update"])
    assert result.exit_code == 0
    assert "No plugins installed" in result.output


def test_plugins_update_all_none_in_registry() -> None:
    installed = [PluginInfo(name="custom", entry_point="c:P")]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=installed),
        patch("reeln.commands.plugins_cmd.update_all_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "update"])
    assert result.exit_code == 0
    assert "No installed plugins found" in result.output


def test_plugins_update_all_with_failure() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    installed = [PluginInfo(name="youtube", entry_point="yt:P")]
    pip_result = PipResult(success=False, package="reeln-youtube", action="update", error="Network error")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=installed),
        patch("reeln.commands.plugins_cmd.update_all_plugins", return_value=[pip_result]),
    ):
        result = runner.invoke(app, ["plugins", "update"])
    assert "Failed" in result.output


def test_plugins_list_installed_no_version() -> None:
    """Installed plugin with empty version string."""
    statuses = [
        PluginStatus(name="youtube", installed=True, installed_version="", enabled=True),
    ]
    with (
        patch("reeln.commands.plugins_cmd.discover_plugins", return_value=[]),
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch("reeln.commands.plugins_cmd.build_plugin_status", return_value=statuses),
    ):
        result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "youtube" in result.output
    assert "enabled" in result.output


def test_plugins_update_registry_error() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch(
            "reeln.commands.plugins_cmd.fetch_registry",
            side_effect=RegistryError("offline"),
        ),
    ):
        result = runner.invoke(app, ["plugins", "update", "youtube"])
    assert result.exit_code == 1


def test_plugins_update_not_in_registry() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=[]),
        patch(
            "reeln.commands.plugins_cmd.update_plugin",
            side_effect=RegistryError("not found"),
        ),
    ):
        result = runner.invoke(app, ["plugins", "update", "nonexistent"])
    assert result.exit_code == 1


def test_plugins_update_single_dry_run() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, output="Would run: pip install --upgrade reeln-youtube")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.update_plugin", return_value=pip_result),
    ):
        result = runner.invoke(app, ["plugins", "update", "youtube", "--dry-run"])
    assert result.exit_code == 0
    assert "Would run:" in result.output


# ---------------------------------------------------------------------------
# plugins enable
# ---------------------------------------------------------------------------


def test_plugins_enable(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"config_version": 1}))

    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
    ):
        result = runner.invoke(app, ["plugins", "enable", "my-plugin"])

    assert result.exit_code == 0
    assert "enabled" in result.output
    saved_config = mock_save.call_args[0][0]
    assert "my-plugin" in saved_config.plugins.enabled


def test_plugins_enable_removes_from_disabled(tmp_path: Path) -> None:
    config = AppConfig(plugins=PluginsConfig(disabled=["my-plugin"]))
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
    ):
        result = runner.invoke(app, ["plugins", "enable", "my-plugin"])

    assert result.exit_code == 0
    saved_config = mock_save.call_args[0][0]
    assert "my-plugin" not in saved_config.plugins.disabled
    assert "my-plugin" in saved_config.plugins.enabled


def test_plugins_enable_requires_name() -> None:
    result = runner.invoke(app, ["plugins", "enable"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# plugins disable
# ---------------------------------------------------------------------------


def test_plugins_disable(tmp_path: Path) -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
    ):
        result = runner.invoke(app, ["plugins", "disable", "my-plugin"])

    assert result.exit_code == 0
    assert "disabled" in result.output
    saved_config = mock_save.call_args[0][0]
    assert "my-plugin" in saved_config.plugins.disabled


def test_plugins_disable_removes_from_enabled(tmp_path: Path) -> None:
    config = AppConfig(plugins=PluginsConfig(enabled=["my-plugin"]))
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
    ):
        result = runner.invoke(app, ["plugins", "disable", "my-plugin"])

    assert result.exit_code == 0
    saved_config = mock_save.call_args[0][0]
    assert "my-plugin" not in saved_config.plugins.enabled
    assert "my-plugin" in saved_config.plugins.disabled


def test_plugins_disable_requires_name() -> None:
    result = runner.invoke(app, ["plugins", "disable"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# plugins help
# ---------------------------------------------------------------------------


def test_plugins_help() -> None:
    result = runner.invoke(app, ["plugins", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "enable" in result.output
    assert "disable" in result.output
    assert "search" in result.output
    assert "info" in result.output
    assert "install" in result.output
    assert "update" in result.output


# ---------------------------------------------------------------------------
# Plugin config schema integration
# ---------------------------------------------------------------------------


def _make_schema() -> PluginConfigSchema:
    return PluginConfigSchema(
        fields=(
            ConfigField(name="api_key", field_type="str", required=True, description="API key"),
            ConfigField(name="region", field_type="str", default="us-east-1"),
        )
    )


def test_plugins_enable_seeds_defaults() -> None:
    schema = PluginConfigSchema(fields=(ConfigField(name="host", default="localhost"),))
    config = AppConfig()
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
        patch("reeln.core.plugin_config.extract_schema_by_name", return_value=schema),
    ):
        result = runner.invoke(app, ["plugins", "enable", "my-plugin"])
    assert result.exit_code == 0
    saved = mock_save.call_args[0][0]
    assert saved.plugins.settings["my-plugin"]["host"] == "localhost"


def test_plugins_enable_no_schema() -> None:
    config = AppConfig()
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
        patch("reeln.core.plugin_config.extract_schema_by_name", return_value=None),
    ):
        result = runner.invoke(app, ["plugins", "enable", "my-plugin"])
    assert result.exit_code == 0
    saved = mock_save.call_args[0][0]
    assert "my-plugin" not in saved.plugins.settings


def test_plugins_enable_preserves_existing_settings() -> None:
    schema = PluginConfigSchema(fields=(ConfigField(name="host", default="localhost"),))
    config = AppConfig(plugins=PluginsConfig(settings={"my-plugin": {"host": "custom.example.com"}}))
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
        patch("reeln.core.plugin_config.extract_schema_by_name", return_value=schema),
    ):
        result = runner.invoke(app, ["plugins", "enable", "my-plugin"])
    assert result.exit_code == 0
    saved = mock_save.call_args[0][0]
    assert saved.plugins.settings["my-plugin"]["host"] == "custom.example.com"


def test_plugins_install_seeds_defaults() -> None:
    schema = PluginConfigSchema(fields=(ConfigField(name="region", default="us-east-1"),))
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="install", output="ok")
    config = AppConfig()
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.install_plugin", return_value=pip_result),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
        patch("reeln.core.plugin_config.extract_schema_by_name", return_value=schema),
    ):
        result = runner.invoke(app, ["plugins", "install", "youtube"])
    assert result.exit_code == 0
    saved = mock_save.call_args[0][0]
    assert saved.plugins.settings["youtube"]["region"] == "us-east-1"


def test_plugins_install_dry_run_no_seeding() -> None:
    entries = [RegistryEntry(name="youtube", package="reeln-youtube")]
    pip_result = PipResult(success=True, package="reeln-youtube", action="dry-run", output="Would run: pip install")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.install_plugin", return_value=pip_result),
    ):
        result = runner.invoke(app, ["plugins", "install", "youtube", "--dry-run"])
    assert result.exit_code == 0
    assert "Would run:" in result.output


def test_plugins_info_shows_schema() -> None:
    schema = _make_schema()
    entries = [
        RegistryEntry(
            name="youtube",
            package="reeln-youtube",
            description="YouTube uploader",
        ),
    ]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value=""),
        patch("reeln.core.plugin_config.extract_schema_by_name", return_value=schema),
    ):
        result = runner.invoke(app, ["plugins", "info", "youtube"])
    assert result.exit_code == 0
    assert "Config schema:" in result.output
    assert "api_key" in result.output
    assert "(required)" in result.output
    assert "region" in result.output
    assert "[default: us-east-1]" in result.output
    assert "API key" in result.output


def test_plugins_info_no_schema() -> None:
    entries = [
        RegistryEntry(name="youtube", package="reeln-youtube", description="YouTube uploader"),
    ]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value=""),
        patch("reeln.core.plugin_config.extract_schema_by_name", return_value=None),
    ):
        result = runner.invoke(app, ["plugins", "info", "youtube"])
    assert result.exit_code == 0
    assert "Config schema: none declared" in result.output


def test_plugins_info_shows_required_field() -> None:
    schema = PluginConfigSchema(fields=(ConfigField(name="token", required=True, description="Auth token"),))
    entries = [
        RegistryEntry(name="meta", package="reeln-meta", description="Meta"),
    ]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value="1.0.0"),
        patch("reeln.core.plugin_config.extract_schema_by_name", return_value=schema),
    ):
        result = runner.invoke(app, ["plugins", "info", "meta"])
    assert "token: str (required)" in result.output
    assert "Auth token" in result.output
