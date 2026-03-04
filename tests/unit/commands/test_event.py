"""Tests for event CLI commands: list, tag, tag-all."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from reeln.cli import app
from reeln.models.game import (
    GameEvent,
    GameInfo,
    GameState,
    game_state_to_dict,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(path: Path) -> Path:
    cfg = path / "config.json"
    cfg.write_text('{"config_version": 1}', encoding="utf-8")
    return cfg


def _write_state(game_dir: Path, state: GameState) -> None:
    data = game_state_to_dict(state)
    (game_dir / "game.json").write_text(json.dumps(data), encoding="utf-8")


def _make_state(events: list[GameEvent] | None = None) -> GameState:
    gi = GameInfo(date="2026-02-28", home_team="roseville", away_team="mahtomedi", sport="hockey")
    return GameState(game_info=gi, created_at="t1", events=events or [])


def _make_event(
    event_id: str = "abc12345",
    clip: str = "period-1/Replay_001.mkv",
    segment_number: int = 1,
    event_type: str = "",
    player: str = "",
) -> GameEvent:
    return GameEvent(
        id=event_id,
        clip=clip,
        segment_number=segment_number,
        event_type=event_type,
        player=player,
        created_at="2026-02-28T18:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# game event list
# ---------------------------------------------------------------------------


def test_event_list_shows_events(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev = _make_event(event_type="goal", player="#17")
    _write_state(tmp_path, _make_state([ev]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 0
    assert "abc12345" in result.output
    assert "goal" in result.output
    assert "#17" in result.output
    assert "Replay_001" in result.output


def test_event_list_no_events(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    _write_state(tmp_path, _make_state())

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 0
    assert "No events found" in result.output


def test_event_list_filter_segment(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev1 = _make_event("aaa11111", "period-1/r1.mkv", 1, "goal")
    ev2 = _make_event("bbb22222", "period-2/r1.mkv", 2, "save")
    _write_state(tmp_path, _make_state([ev1, ev2]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--segment",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert "aaa11111" in result.output
    assert "bbb22222" not in result.output


def test_event_list_filter_type(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev1 = _make_event("aaa11111", event_type="goal")
    ev2 = _make_event("bbb22222", event_type="save")
    _write_state(tmp_path, _make_state([ev1, ev2]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--type",
            "goal",
        ],
    )
    assert result.exit_code == 0
    assert "aaa11111" in result.output
    assert "bbb22222" not in result.output


def test_event_list_untagged(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev1 = _make_event("aaa11111", event_type="goal")
    ev2 = _make_event("bbb22222", event_type="")
    _write_state(tmp_path, _make_state([ev1, ev2]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--untagged",
        ],
    )
    assert result.exit_code == 0
    assert "bbb22222" in result.output
    assert "aaa11111" not in result.output


def test_event_list_shows_untagged_label(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev = _make_event(event_type="")
    _write_state(tmp_path, _make_state([ev]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
        ],
    )
    assert "(untagged)" in result.output


# ---------------------------------------------------------------------------
# game event tag
# ---------------------------------------------------------------------------


def test_event_tag_type(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev = _make_event("abc12345")
    _write_state(tmp_path, _make_state([ev]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag",
            "abc12345",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--type",
            "goal",
        ],
    )
    assert result.exit_code == 0
    assert "Updated event abc12345" in result.output
    assert "Type: goal" in result.output

    # Verify persistence
    state_data = json.loads((tmp_path / "game.json").read_text(encoding="utf-8"))
    assert state_data["events"][0]["event_type"] == "goal"


def test_event_tag_player(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev = _make_event("abc12345")
    _write_state(tmp_path, _make_state([ev]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag",
            "abc12345",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--player",
            "#17",
        ],
    )
    assert result.exit_code == 0
    assert "Player: #17" in result.output


def test_event_tag_metadata(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev = _make_event("abc12345")
    _write_state(tmp_path, _make_state([ev]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag",
            "abc12345",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--meta",
            "title=Great goal",
        ],
    )
    assert result.exit_code == 0
    assert "title: Great goal" in result.output


def test_event_tag_invalid_metadata(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev = _make_event("abc12345")
    _write_state(tmp_path, _make_state([ev]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag",
            "abc12345",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--meta",
            "badformat",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid metadata format" in result.output


def test_event_tag_not_found(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    _write_state(tmp_path, _make_state())

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag",
            "nonexistent",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--type",
            "goal",
        ],
    )
    assert result.exit_code == 1
    assert "No event found" in result.output


def test_event_tag_prefix_match(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev = _make_event("abcdef123456")
    _write_state(tmp_path, _make_state([ev]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag",
            "abcdef",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--type",
            "save",
        ],
    )
    assert result.exit_code == 0
    assert "Updated event abcdef12" in result.output


# ---------------------------------------------------------------------------
# game event tag-all
# ---------------------------------------------------------------------------


def test_event_tag_all_type(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev1 = _make_event("aaa11111", "period-1/r1.mkv", 1)
    ev2 = _make_event("bbb22222", "period-1/r2.mkv", 1)
    _write_state(tmp_path, _make_state([ev1, ev2]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag-all",
            "1",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--type",
            "goal",
        ],
    )
    assert result.exit_code == 0
    assert "Updated 2 event(s)" in result.output
    assert "Type: goal" in result.output


def test_event_tag_all_player(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    ev = _make_event("aaa11111", segment_number=1)
    _write_state(tmp_path, _make_state([ev]))

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag-all",
            "1",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--player",
            "#17",
        ],
    )
    assert result.exit_code == 0
    assert "Player: #17" in result.output


def test_event_tag_all_no_events(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    _write_state(tmp_path, _make_state())

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "tag-all",
            "1",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
            "--type",
            "goal",
        ],
    )
    assert result.exit_code == 1
    assert "No events found" in result.output


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_event_list_bad_config(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.json"
    cfg.write_text("not json{{{", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_event_list_no_game_dir(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(empty),
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 1
    assert "No game directory" in result.output


def test_event_list_bad_game_state(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    (tmp_path / "game.json").write_text("not json{{{", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "game",
            "event",
            "list",
            "-o",
            str(tmp_path),
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
