"""Tests for the plugins CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from reeln.cli import app
from reeln.core.errors import RegistryError
from reeln.core.plugin_registry import PipResult
from reeln.models.auth import AuthCheckResult, AuthStatus, PluginAuthReport
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
    assert "No plugins installed" in result.output


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
            description="YouTube video uploader",
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
    assert "llm" in result.output


def test_plugins_list_hides_not_installed() -> None:
    """Uninstalled plugins are not shown in list — use search instead."""
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
    assert "meta" not in result.output
    assert "No plugins installed" in result.output


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
        RegistryEntry(name="bare", package="reeln-bare"),
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
            homepage="https://github.com/example/reeln-youtube",
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
    assert "Settings:" in result.output
    assert "api_key" in result.output
    assert "(required)" in result.output
    assert "region" in result.output
    assert "us-east-1" in result.output
    assert "API key" in result.output
    assert "Homepage:" in result.output


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
    # No settings section when schema is None
    assert "Settings:" not in result.output


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


# ---------------------------------------------------------------------------
# plugins uninstall
# ---------------------------------------------------------------------------


def test_plugins_uninstall_success() -> None:
    entries = [RegistryEntry(name="google", package="reeln-plugin-google")]
    pip_result = PipResult(success=True, package="reeln-plugin-google", action="uninstall")
    config = AppConfig(plugins=PluginsConfig(enabled=["google"]))
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=config),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value="1.0.0"),
        patch("reeln.commands.plugins_cmd.uninstall_plugin", return_value=pip_result),
        patch("reeln.commands.plugins_cmd.save_config") as mock_save,
    ):
        result = runner.invoke(app, ["plugins", "uninstall", "google", "--force"])
    assert result.exit_code == 0
    assert "uninstalled" in result.output
    mock_save.assert_called_once()
    saved_config = mock_save.call_args[0][0]
    assert "google" not in saved_config.plugins.enabled
    assert "google" in saved_config.plugins.disabled


def test_plugins_uninstall_not_installed() -> None:
    entries = [RegistryEntry(name="google", package="reeln-plugin-google")]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value=""),
    ):
        result = runner.invoke(app, ["plugins", "uninstall", "google", "--force"])
    assert result.exit_code == 1
    assert "not installed" in result.output


def test_plugins_uninstall_cancelled() -> None:
    entries = [RegistryEntry(name="google", package="reeln-plugin-google")]
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value="1.0.0"),
    ):
        result = runner.invoke(app, ["plugins", "uninstall", "google"], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output


def test_plugins_uninstall_confirmed() -> None:
    entries = [RegistryEntry(name="google", package="reeln-plugin-google")]
    pip_result = PipResult(success=True, package="reeln-plugin-google", action="uninstall")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value="1.0.0"),
        patch("reeln.commands.plugins_cmd.uninstall_plugin", return_value=pip_result),
        patch("reeln.commands.plugins_cmd.save_config"),
    ):
        result = runner.invoke(app, ["plugins", "uninstall", "google"], input="y\n")
    assert result.exit_code == 0
    assert "uninstalled" in result.output


def test_plugins_uninstall_dry_run() -> None:
    entries = [RegistryEntry(name="google", package="reeln-plugin-google")]
    pip_result = PipResult(
        success=True,
        package="reeln-plugin-google",
        action="dry-run",
        output="Would run: uv pip uninstall reeln-plugin-google",
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value="1.0.0"),
        patch("reeln.commands.plugins_cmd.uninstall_plugin", return_value=pip_result),
    ):
        result = runner.invoke(app, ["plugins", "uninstall", "google", "--dry-run"])
    assert result.exit_code == 0
    assert "Would run" in result.output


def test_plugins_uninstall_failure() -> None:
    entries = [RegistryEntry(name="google", package="reeln-plugin-google")]
    pip_result = PipResult(success=False, package="reeln-plugin-google", action="uninstall", error="permission denied")
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", return_value=entries),
        patch("reeln.commands.plugins_cmd.get_installed_version", return_value="1.0.0"),
        patch("reeln.commands.plugins_cmd.uninstall_plugin", return_value=pip_result),
    ):
        result = runner.invoke(app, ["plugins", "uninstall", "google", "--force"])
    assert result.exit_code == 1
    assert "permission denied" in result.output


def test_plugins_uninstall_registry_error() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.plugins_cmd.fetch_registry", side_effect=RegistryError("offline")),
    ):
        result = runner.invoke(app, ["plugins", "uninstall", "google", "--force"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# plugins inputs
# ---------------------------------------------------------------------------


def test_plugins_inputs_no_plugins() -> None:
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "inputs"])
    assert result.exit_code == 0
    assert "No plugin input contributions" in result.output


def test_plugins_inputs_with_fields() -> None:
    from reeln.models.plugin_input import InputField, PluginInputSchema
    from reeln.plugins.inputs import reset_input_collector

    class FakePlugin:
        input_schema = PluginInputSchema(
            fields=(
                InputField(
                    id="thumb",
                    label="Thumbnail",
                    field_type="file",
                    command="game_init",
                    plugin_name="google",
                    description="Thumbnail for livestream",
                ),
            )
        )

    def _fake_activate(cfg: object) -> dict[str, object]:
        collector = reset_input_collector()
        p = FakePlugin()
        collector.register_plugin_inputs(p, "google")
        return {"google": p}

    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", side_effect=_fake_activate),
    ):
        result = runner.invoke(app, ["plugins", "inputs", "--command", "game_init"])
    assert result.exit_code == 0
    assert "game_init" in result.output
    assert "thumb" in result.output
    assert "google" in result.output
    assert "Thumbnail for livestream" in result.output


def test_plugins_inputs_json_output() -> None:
    from reeln.models.plugin_input import InputField, PluginInputSchema
    from reeln.plugins.inputs import reset_input_collector

    class FakePlugin:
        input_schema = PluginInputSchema(
            fields=(
                InputField(
                    id="thumb",
                    label="Thumbnail",
                    field_type="file",
                    command="game_init",
                    plugin_name="google",
                ),
            )
        )

    def _fake_activate(cfg: object) -> dict[str, object]:
        collector = reset_input_collector()
        p = FakePlugin()
        collector.register_plugin_inputs(p, "google")
        return {"google": p}

    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", side_effect=_fake_activate),
    ):
        result = runner.invoke(app, ["plugins", "inputs", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["fields"]) == 1
    assert data["fields"][0]["id"] == "thumb"


def test_plugins_inputs_all_commands() -> None:
    """Without --command, all command scopes are queried."""
    from reeln.plugins.inputs import reset_input_collector

    def _fake_activate(cfg: object) -> dict[str, object]:
        reset_input_collector()
        return {}

    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", side_effect=_fake_activate),
    ):
        result = runner.invoke(app, ["plugins", "inputs"])
    assert result.exit_code == 0
    assert "No plugin input contributions" in result.output


def test_plugins_inputs_required_field() -> None:
    from reeln.models.plugin_input import InputField, PluginInputSchema
    from reeln.plugins.inputs import reset_input_collector

    class FakePlugin:
        input_schema = PluginInputSchema(
            fields=(
                InputField(
                    id="api_key",
                    label="API Key",
                    field_type="str",
                    command="game_init",
                    plugin_name="test",
                    required=True,
                ),
            )
        )

    def _fake_activate(cfg: object) -> dict[str, object]:
        collector = reset_input_collector()
        p = FakePlugin()
        collector.register_plugin_inputs(p, "test")
        return {"test": p}

    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", side_effect=_fake_activate),
    ):
        result = runner.invoke(app, ["plugins", "inputs", "--command", "game_init"])
    assert result.exit_code == 0
    assert "(required)" in result.output


# ---------------------------------------------------------------------------
# plugins auth
# ---------------------------------------------------------------------------


def test_auth_no_plugins() -> None:
    """Exit 1 when no plugins support auth."""
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 1
    assert "No plugins with authentication support found" in result.output


def test_auth_single_plugin_ok() -> None:
    """Successful auth check for a single plugin."""
    report = PluginAuthReport(
        plugin_name="google",
        results=[
            AuthCheckResult(
                service="YouTube",
                status=AuthStatus.OK,
                message="Connected",
                identity="StreamnDad Hockey",
                scopes=["youtube", "youtube.upload"],
            )
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"google": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 0
    assert "google" in result.output
    assert "YouTube" in result.output
    assert "StreamnDad Hockey" in result.output
    assert "authenticated" in result.output


def test_auth_name_filter() -> None:
    """Filter auth by plugin name."""
    report = PluginAuthReport(
        plugin_name="meta",
        results=[
            AuthCheckResult(service="Facebook Page", status=AuthStatus.OK, message="ok"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"meta": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]) as mock_collect,
    ):
        result = runner.invoke(app, ["plugins", "auth", "meta"])
    assert result.exit_code == 0
    assert "meta" in result.output
    mock_collect.assert_called_once_with({"meta": mock_collect.call_args[0][0]["meta"]}, name_filter="meta")


def test_auth_name_filter_no_match() -> None:
    """Exit 1 when filtered plugin not found."""
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[]),
    ):
        result = runner.invoke(app, ["plugins", "auth", "nonexistent"])
    assert result.exit_code == 1
    assert "nonexistent" in result.output


def test_auth_fail_exit_code() -> None:
    """Exit 1 when any check has FAIL status."""
    report = PluginAuthReport(
        plugin_name="tiktok",
        results=[
            AuthCheckResult(service="TikTok", status=AuthStatus.FAIL, message="Token invalid"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"tiktok": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 1
    assert "failed" in result.output
    assert "Token invalid" in result.output


def test_auth_expired_exit_code() -> None:
    """Exit 1 when any check has EXPIRED status."""
    report = PluginAuthReport(
        plugin_name="tiktok",
        results=[
            AuthCheckResult(service="TikTok", status=AuthStatus.EXPIRED, message="Token expired"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"tiktok": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 1
    assert "expired" in result.output


def test_auth_warn_status_exit_zero() -> None:
    """Exit 0 when worst status is WARN (not FAIL/EXPIRED)."""
    report = PluginAuthReport(
        plugin_name="meta",
        results=[
            AuthCheckResult(service="Threads", status=AuthStatus.WARN, message="Limited scope"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"meta": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 0
    assert "warning" in result.output


def test_auth_not_configured_exit_zero() -> None:
    """Exit 0 for NOT_CONFIGURED status."""
    report = PluginAuthReport(
        plugin_name="cloudflare",
        results=[
            AuthCheckResult(service="R2", status=AuthStatus.NOT_CONFIGURED, message="No env var"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"cloudflare": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 0
    assert "not configured" in result.output


def test_auth_json_output() -> None:
    """JSON output contains expected structure."""
    report = PluginAuthReport(
        plugin_name="google",
        results=[
            AuthCheckResult(
                service="YouTube",
                status=AuthStatus.OK,
                message="ok",
                identity="StreamnDad",
                scopes=["youtube"],
                required_scopes=["youtube", "youtube.upload"],
            )
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"google": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "plugins" in data
    assert data["plugins"][0]["name"] == "google"
    assert data["plugins"][0]["results"][0]["service"] == "YouTube"
    assert data["plugins"][0]["results"][0]["status"] == "ok"
    assert data["plugins"][0]["results"][0]["identity"] == "StreamnDad"


def test_auth_json_fail_exit_code() -> None:
    """JSON output still exits 1 on FAIL."""
    report = PluginAuthReport(
        plugin_name="openai",
        results=[
            AuthCheckResult(service="OpenAI", status=AuthStatus.FAIL, message="Bad key"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"openai": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["plugins"][0]["results"][0]["status"] == "fail"


def test_auth_refresh_success() -> None:
    """--refresh for a single plugin succeeds."""
    report = PluginAuthReport(
        plugin_name="tiktok",
        results=[
            AuthCheckResult(service="TikTok", status=AuthStatus.OK, message="Refreshed"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"tiktok": object()}),
        patch("reeln.plugins.loader.refresh_auth", return_value=report),
    ):
        result = runner.invoke(app, ["plugins", "auth", "--refresh", "tiktok"])
    assert result.exit_code == 0
    assert "authenticated" in result.output


def test_auth_refresh_without_name() -> None:
    """--refresh without a name exits with error."""
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
    ):
        result = runner.invoke(app, ["plugins", "auth", "--refresh"])
    assert result.exit_code == 1
    assert "--refresh requires a plugin name" in result.output


def test_auth_refresh_plugin_not_found() -> None:
    """--refresh for a missing plugin exits with error."""
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.plugins.loader.refresh_auth", return_value=None),
    ):
        result = runner.invoke(app, ["plugins", "auth", "--refresh", "missing"])
    assert result.exit_code == 1
    assert "missing" in result.output
    assert "not found or does not support auth" in result.output


def test_auth_renders_missing_scopes() -> None:
    """Missing scopes are displayed in human output."""
    report = PluginAuthReport(
        plugin_name="meta",
        results=[
            AuthCheckResult(
                service="Threads",
                status=AuthStatus.WARN,
                message="Missing scope",
                scopes=["pages_read"],
                required_scopes=["pages_read", "threads_basic"],
            ),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"meta": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 0
    assert "threads_basic" in result.output


def test_auth_renders_hint() -> None:
    """Hints are displayed in human output."""
    report = PluginAuthReport(
        plugin_name="meta",
        results=[
            AuthCheckResult(
                service="Facebook Page",
                status=AuthStatus.FAIL,
                message="Token invalid",
                hint="Re-generate token in developer dashboard",
            ),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"meta": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 1
    assert "Re-generate token" in result.output


def test_auth_renders_expiry() -> None:
    """Expiry is displayed in human output."""
    report = PluginAuthReport(
        plugin_name="tiktok",
        results=[
            AuthCheckResult(
                service="TikTok",
                status=AuthStatus.OK,
                message="ok",
                expires_at="2026-12-31T23:59:59",
            ),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"tiktok": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 0
    assert "2026-12-31T23:59:59" in result.output


def test_auth_multi_service_meta() -> None:
    """Meta returns multiple service results (Facebook, Instagram, Threads)."""
    report = PluginAuthReport(
        plugin_name="meta",
        results=[
            AuthCheckResult(service="Facebook Page", status=AuthStatus.OK, message="ok", identity="My Page"),
            AuthCheckResult(service="Instagram", status=AuthStatus.OK, message="ok", identity="@streamndad"),
            AuthCheckResult(service="Threads", status=AuthStatus.WARN, message="Limited", hint="Add threads scope"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"meta": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 0
    assert "Facebook Page" in result.output
    assert "Instagram" in result.output
    assert "Threads" in result.output
    assert "My Page" in result.output
    assert "@streamndad" in result.output


def test_auth_required_scopes_all_present() -> None:
    """When all required scopes are granted, no 'Missing' line appears."""
    report = PluginAuthReport(
        plugin_name="google",
        results=[
            AuthCheckResult(
                service="YouTube",
                status=AuthStatus.OK,
                message="ok",
                scopes=["youtube", "youtube.upload"],
                required_scopes=["youtube", "youtube.upload"],
            ),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"google": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 0
    assert "Missing" not in result.output
    assert "Scopes:" in result.output


def test_auth_ok_message_not_shown() -> None:
    """Message is not displayed for OK status (only identity/scopes shown)."""
    report = PluginAuthReport(
        plugin_name="google",
        results=[
            AuthCheckResult(service="YouTube", status=AuthStatus.OK, message="All good"),
        ],
    )
    with (
        patch("reeln.commands.plugins_cmd.load_config", return_value=AppConfig()),
        patch("reeln.plugins.loader.activate_plugins", return_value={"google": object()}),
        patch("reeln.plugins.loader.collect_auth_checks", return_value=[report]),
    ):
        result = runner.invoke(app, ["plugins", "auth"])
    assert result.exit_code == 0
    # Message "All good" should NOT appear for OK status (only shown for non-OK)
    assert "All good" not in result.output
