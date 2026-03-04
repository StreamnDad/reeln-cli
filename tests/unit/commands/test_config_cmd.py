"""Tests for the config command group."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from reeln.cli import app

runner = CliRunner()


def test_config_help_lists_commands() -> None:
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output
    assert "doctor" in result.output


def test_config_show_defaults(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "show", "--path", str(tmp_path / "nonexistent.json")])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["config_version"] == 1
    assert data["sport"] == "generic"


def test_config_show_from_file(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"config_version": 1, "sport": "hockey"}))
    result = runner.invoke(app, ["config", "show", "--path", str(cfg_file)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sport"] == "hockey"


def test_config_doctor_valid(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"config_version": 1, "sport": "hockey"}))
    result = runner.invoke(app, ["config", "doctor", "--path", str(cfg_file)])
    assert result.exit_code == 0
    assert "OK" in result.output
    assert str(cfg_file) in result.output


def test_config_doctor_defaults_no_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "doctor", "--path", str(tmp_path / "missing.json")])
    assert result.exit_code == 0
    assert "not found" in result.output
    assert "OK" in result.output


def test_config_doctor_invalid_version(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"config_version": 999, "sport": "hockey"}))
    result = runner.invoke(app, ["config", "doctor", "--path", str(cfg_file)])
    assert result.exit_code == 1
    assert "WARN" in result.output


# ---------------------------------------------------------------------------
# config doctor — plugin config validation
# ---------------------------------------------------------------------------


def test_config_doctor_valid_plugin_config(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "config_version": 1,
                "plugins": {"enabled": ["youtube"], "settings": {"youtube": {"api_key": "abc"}}},
            }
        )
    )
    with patch("reeln.core.config.validate_plugin_configs", return_value=[]):
        result = runner.invoke(app, ["config", "doctor", "--path", str(cfg_file)])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_config_doctor_invalid_plugin_config(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "config_version": 1,
                "plugins": {"enabled": ["youtube"], "settings": {"youtube": {}}},
            }
        )
    )
    with patch(
        "reeln.core.config.validate_plugin_configs",
        return_value=["Plugin 'youtube': missing required field 'api_key'"],
    ):
        result = runner.invoke(app, ["config", "doctor", "--path", str(cfg_file)])
    assert result.exit_code == 1
    assert "WARN" in result.output
    assert "api_key" in result.output


def test_config_doctor_no_schema(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "config_version": 1,
                "plugins": {"enabled": ["custom"], "settings": {"custom": {"k": "v"}}},
            }
        )
    )
    with patch("reeln.core.config.validate_plugin_configs", return_value=[]):
        result = runner.invoke(app, ["config", "doctor", "--path", str(cfg_file)])
    assert result.exit_code == 0
    assert "OK" in result.output
