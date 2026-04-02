"""Tests for the config event-types subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from reeln.cli import app

runner = CliRunner()


def _write_config(path: Path, *, sport: str = "hockey", event_types: list[str] | None = None) -> Path:
    cfg = {"config_version": 1, "sport": sport}
    if event_types is not None:
        cfg["event_types"] = event_types
    path.write_text(json.dumps(cfg))
    return path


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_event_types_list_shows_configured(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", event_types=["goal", "save"])
    result = runner.invoke(app, ["config", "event-types", "list", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "goal" in result.output
    assert "save" in result.output


def test_event_types_list_empty_shows_defaults(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", sport="hockey")
    result = runner.invoke(app, ["config", "event-types", "list", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "Defaults for hockey" in result.output
    assert "goal" in result.output


def test_event_types_list_empty_generic_no_defaults(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", sport="generic")
    result = runner.invoke(app, ["config", "event-types", "list", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "No event types configured." in result.output


def test_event_types_list_missing_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "event-types", "list", "--config", str(tmp_path / "nope.json")])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_event_types_add(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", event_types=["goal"])
    result = runner.invoke(app, ["config", "event-types", "add", "penalty", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "Added 'penalty'" in result.output

    # Verify persisted
    data = json.loads(cfg.read_text())
    assert "penalty" in data["event_types"]
    assert "goal" in data["event_types"]


def test_event_types_add_to_empty(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json")
    result = runner.invoke(app, ["config", "event-types", "add", "goal", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "Added 'goal'" in result.output

    data = json.loads(cfg.read_text())
    assert data["event_types"] == ["goal"]


def test_event_types_add_duplicate(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", event_types=["goal"])
    result = runner.invoke(app, ["config", "event-types", "add", "goal", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "already configured" in result.output


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


def test_event_types_remove(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", event_types=["goal", "save", "penalty"])
    result = runner.invoke(app, ["config", "event-types", "remove", "save", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "Removed 'save'" in result.output

    data = json.loads(cfg.read_text())
    assert data["event_types"] == ["goal", "penalty"]


def test_event_types_remove_nonexistent(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", event_types=["goal"])
    result = runner.invoke(app, ["config", "event-types", "remove", "penalty", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_event_types_remove_last(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", event_types=["goal"])
    result = runner.invoke(app, ["config", "event-types", "remove", "goal", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "(empty)" in result.output


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_event_types_set(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", event_types=["goal"])
    result = runner.invoke(app, ["config", "event-types", "set", "penalty", "assist", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "penalty" in result.output
    assert "assist" in result.output

    data = json.loads(cfg.read_text())
    assert data["event_types"] == ["penalty", "assist"]


def test_event_types_set_replaces_existing(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", event_types=["goal", "save"])
    result = runner.invoke(app, ["config", "event-types", "set", "foul", "--config", str(cfg)])
    assert result.exit_code == 0

    data = json.loads(cfg.read_text())
    assert data["event_types"] == ["foul"]


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------


def test_event_types_defaults_hockey(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", sport="hockey")
    result = runner.invoke(app, ["config", "event-types", "defaults", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "hockey" in result.output
    assert "goal" in result.output
    assert "save" in result.output


def test_event_types_defaults_generic(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", sport="generic")
    result = runner.invoke(app, ["config", "event-types", "defaults", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "No default event types" in result.output


def test_event_types_defaults_soccer(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "config.json", sport="soccer")
    result = runner.invoke(app, ["config", "event-types", "defaults", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "soccer" in result.output
    assert "corner" in result.output


def test_event_types_defaults_missing_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "event-types", "defaults", "--config", str(tmp_path / "nope.json")])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_default_event_type_entries() -> None:
    from reeln.core.event_types import default_event_type_entries

    entries = default_event_type_entries("hockey")
    assert len(entries) > 0
    assert entries[0].name == "goal"
    assert entries[0].team_specific is True


def test_default_event_type_entries_unknown_sport() -> None:
    from reeln.core.event_types import default_event_type_entries

    assert default_event_type_entries("curling") == []
