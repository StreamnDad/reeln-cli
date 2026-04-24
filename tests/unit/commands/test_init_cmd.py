"""Tests for the init command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reeln.cli import app

runner = CliRunner()


@pytest.fixture()
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect config_dir() to a temp directory."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    monkeypatch.setattr("reeln.commands.init_cmd.config_dir", lambda: cfg_dir)
    monkeypatch.delenv("REELN_CONFIG", raising=False)
    monkeypatch.delenv("REELN_PROFILE", raising=False)
    return cfg_dir


def test_init_noninteractive_creates_config(tmp_path: Path) -> None:
    """All flags provided produces a valid config file."""
    cfg_file = tmp_path / "config.json"
    source = tmp_path / "source"
    output = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "hockey",
            "--source-dir", str(source),
            "--output-dir", str(output),
            "--config", str(cfg_file),
        ],
    )

    assert result.exit_code == 0, result.output
    assert cfg_file.exists()

    data = json.loads(cfg_file.read_text())
    assert data["sport"] == "hockey"
    assert data["paths"]["source_dir"] == str(source)
    assert data["paths"]["output_dir"] == str(output)


def test_init_creates_directories(tmp_path: Path) -> None:
    """Source and output directories are created."""
    cfg_file = tmp_path / "config.json"
    source = tmp_path / "deep" / "source"
    output = tmp_path / "deep" / "output"

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "soccer",
            "--source-dir", str(source),
            "--output-dir", str(output),
            "--config", str(cfg_file),
        ],
    )

    assert result.exit_code == 0, result.output
    assert source.is_dir()
    assert output.is_dir()


def test_init_includes_event_types(tmp_path: Path) -> None:
    """Config includes sport-specific event types."""
    cfg_file = tmp_path / "config.json"

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "hockey",
            "--source-dir", str(tmp_path / "src"),
            "--output-dir", str(tmp_path / "out"),
            "--config", str(cfg_file),
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(cfg_file.read_text())
    event_types = data.get("event_types", [])
    # Hockey should have goal, save, penalty, assist
    event_names = [
        et if isinstance(et, str) else et["name"] for et in event_types
    ]
    assert "goal" in event_names
    assert "save" in event_names


def test_init_generic_sport_no_event_types(tmp_path: Path) -> None:
    """Generic sport has no default event types."""
    cfg_file = tmp_path / "config.json"

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "generic",
            "--source-dir", str(tmp_path / "src"),
            "--output-dir", str(tmp_path / "out"),
            "--config", str(cfg_file),
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(cfg_file.read_text())
    # Generic has no event types, so field should be absent or empty
    assert not data.get("event_types", [])


def test_init_refuses_overwrite_without_force(tmp_path: Path) -> None:
    """Existing config without --force exits with error."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}")

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "hockey",
            "--source-dir", str(tmp_path / "src"),
            "--output-dir", str(tmp_path / "out"),
            "--config", str(cfg_file),
        ],
        input="n\n",
    )

    # Should exit non-zero or with cancellation message
    # stdin is not a tty in test runner, so non-interactive path is taken
    assert result.exit_code == 1


def test_init_force_overwrites_existing(tmp_path: Path) -> None:
    """--force overwrites an existing config file."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"config_version": 1, "sport": "generic"}))

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "basketball",
            "--source-dir", str(tmp_path / "src"),
            "--output-dir", str(tmp_path / "out"),
            "--config", str(cfg_file),
            "--force",
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(cfg_file.read_text())
    assert data["sport"] == "basketball"


def test_init_default_config_path(config_home: Path) -> None:
    """Without --config, uses default config_dir() / config.json."""
    source = config_home.parent / "source"
    output = config_home.parent / "output"

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "hockey",
            "--source-dir", str(source),
            "--output-dir", str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    expected = config_home / "config.json"
    assert expected.exists()


def test_init_config_has_render_profiles(tmp_path: Path) -> None:
    """Default render profiles are preserved in the generated config."""
    cfg_file = tmp_path / "config.json"

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "hockey",
            "--source-dir", str(tmp_path / "src"),
            "--output-dir", str(tmp_path / "out"),
            "--config", str(cfg_file),
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(cfg_file.read_text())
    assert "player-overlay" in data.get("render_profiles", {})


def test_init_config_version(tmp_path: Path) -> None:
    """Config version is set to current."""
    cfg_file = tmp_path / "config.json"

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "lacrosse",
            "--source-dir", str(tmp_path / "src"),
            "--output-dir", str(tmp_path / "out"),
            "--config", str(cfg_file),
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(cfg_file.read_text())
    assert data["config_version"] == 1


def test_init_output_shows_summary(tmp_path: Path) -> None:
    """Init output contains the summary panel."""
    cfg_file = tmp_path / "config.json"

    result = runner.invoke(
        app,
        [
            "init",
            "--sport", "hockey",
            "--source-dir", str(tmp_path / "src"),
            "--output-dir", str(tmp_path / "out"),
            "--config", str(cfg_file),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "initialized" in result.output
    assert "hockey" in result.output
    assert "Next steps" in result.output


def test_init_help() -> None:
    """Init --help shows the command description."""
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "guided" in result.output.lower() or "Set up" in result.output
