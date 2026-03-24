"""Tests for game finish logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reeln.core.errors import MediaError
from reeln.core.finish import _build_summary, finish_game, relocate_outputs
from reeln.models.game import (
    GameEvent,
    GameInfo,
    GameState,
    RenderEntry,
    game_state_to_dict,
)
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.registry import get_registry


def _write_state(game_dir: Path, state: GameState) -> Path:
    """Write a game.json to *game_dir*."""
    state_file = game_dir / "game.json"
    data = game_state_to_dict(state)
    state_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return state_file


def _make_state(**kwargs: object) -> GameState:
    """Create a GameState with sensible defaults."""
    gi = GameInfo(date="2026-02-26", home_team="roseville", away_team="mahtomedi", sport="hockey")
    defaults: dict[str, object] = {"game_info": gi}
    defaults.update(kwargs)
    return GameState(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# finish_game
# ---------------------------------------------------------------------------


def test_finish_game(tmp_path: Path) -> None:
    state = _make_state(segments_processed=[1, 2, 3])
    _write_state(tmp_path, state)

    result, messages = finish_game(tmp_path)

    assert result.finished is True
    assert result.finished_at != ""
    assert any("Finished" in m for m in messages)

    # State file should be updated
    raw = json.loads((tmp_path / "game.json").read_text(encoding="utf-8"))
    assert raw["finished"] is True
    assert raw["finished_at"] != ""


def test_finish_game_dry_run(tmp_path: Path) -> None:
    state = _make_state()
    _write_state(tmp_path, state)

    result, messages = finish_game(tmp_path, dry_run=True)

    assert result.finished is True
    assert result.finished_at != ""
    assert any("Finished" in m for m in messages)

    # State file should NOT be updated
    raw = json.loads((tmp_path / "game.json").read_text(encoding="utf-8"))
    assert raw["finished"] is False
    assert raw["finished_at"] == ""


def test_finish_game_already_finished(tmp_path: Path) -> None:
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    with pytest.raises(MediaError, match="already finished"):
        finish_game(tmp_path)


def test_finish_game_no_state_file(tmp_path: Path) -> None:
    with pytest.raises(MediaError, match="not found"):
        finish_game(tmp_path)


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------


def test_build_summary_basic() -> None:
    state = _make_state(
        segments_processed=[1, 2, 3],
        highlighted=True,
        finished=True,
        finished_at="2026-02-26T14:00:00+00:00",
    )
    messages = _build_summary(state)

    assert "Game: roseville vs mahtomedi (2026-02-26)" in messages
    assert "Segments processed: 3" in messages
    assert "Events: 0" in messages
    assert "Renders: 0" in messages
    assert "Highlighted: yes" in messages
    assert "Status: Finished" in messages


def test_build_summary_not_highlighted() -> None:
    state = _make_state(finished=True)
    messages = _build_summary(state)
    assert "Highlighted: no" in messages


def test_build_summary_with_events() -> None:
    events = [
        GameEvent(id="a", clip="c1.mkv", segment_number=1, event_type="goal"),
        GameEvent(id="b", clip="c2.mkv", segment_number=1, event_type=""),
        GameEvent(id="c", clip="c3.mkv", segment_number=2, event_type="save"),
    ]
    state = _make_state(finished=True, events=events)
    messages = _build_summary(state)
    assert "Events: 3 total (2 tagged, 1 untagged)" in messages


def test_build_summary_with_renders() -> None:
    renders = [
        RenderEntry(
            input="clip.mkv",
            output="clip_short.mp4",
            segment_number=1,
            format="1080x1920",
            crop_mode="pad",
            rendered_at="2026-02-26T12:00:00+00:00",
        ),
    ]
    state = _make_state(finished=True, renders=renders)
    messages = _build_summary(state)
    assert "Renders: 1" in messages


# ---------------------------------------------------------------------------
# Hook emissions
# ---------------------------------------------------------------------------


def test_finish_game_emits_on_game_finish(tmp_path: Path) -> None:
    state = _make_state(segments_processed=[1, 2, 3])
    _write_state(tmp_path, state)

    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_GAME_FINISH, emitted.append)

    finish_game(tmp_path)

    assert len(emitted) == 1
    assert emitted[0].hook is Hook.ON_GAME_FINISH
    assert "game_dir" in emitted[0].data
    assert "state" in emitted[0].data
    assert emitted[0].data["state"].finished is True


def test_finish_game_emits_on_post_game_finish(tmp_path: Path) -> None:
    state = _make_state(segments_processed=[1])
    _write_state(tmp_path, state)

    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_POST_GAME_FINISH, emitted.append)

    finish_game(tmp_path)

    assert len(emitted) == 1
    assert emitted[0].hook is Hook.ON_POST_GAME_FINISH
    assert "game_dir" in emitted[0].data
    assert "state" in emitted[0].data


def test_finish_game_post_finish_shares_context(tmp_path: Path) -> None:
    """ON_POST_GAME_FINISH receives shared context from ON_GAME_FINISH handlers."""
    state = _make_state()
    _write_state(tmp_path, state)

    def finish_handler(ctx: HookContext) -> None:
        ctx.shared["game_events"] = ["goal", "save"]

    post_received: list[HookContext] = []
    get_registry().register(Hook.ON_GAME_FINISH, finish_handler)
    get_registry().register(Hook.ON_POST_GAME_FINISH, post_received.append)

    finish_game(tmp_path)

    assert len(post_received) == 1
    assert post_received[0].shared["game_events"] == ["goal", "save"]


def test_finish_game_dry_run_no_post_hook(tmp_path: Path) -> None:
    state = _make_state()
    _write_state(tmp_path, state)

    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_POST_GAME_FINISH, emitted.append)

    finish_game(tmp_path, dry_run=True)

    assert len(emitted) == 0


def test_finish_game_dry_run_no_hook(tmp_path: Path) -> None:
    state = _make_state()
    _write_state(tmp_path, state)

    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_GAME_FINISH, emitted.append)

    finish_game(tmp_path, dry_run=True)

    assert len(emitted) == 0


# ---------------------------------------------------------------------------
# relocate_outputs
# ---------------------------------------------------------------------------


def test_relocate_outputs_moves_files(tmp_path: Path) -> None:
    """Segment and highlights outputs are moved into game_dir/outputs/."""
    game_dir = tmp_path / "2026-03-15_a_vs_b"
    game_dir.mkdir()
    # Create output files in game_dir.parent (tmp_path)
    seg = tmp_path / "period-1_2026-03-15.mkv"
    seg.write_bytes(b"segment")
    hl = tmp_path / "a_vs_b_2026-03-15.mkv"
    hl.write_bytes(b"highlights")

    state = _make_state(
        segment_outputs=["period-1_2026-03-15.mkv"],
        highlights_output="a_vs_b_2026-03-15.mkv",
    )

    relocated, messages = relocate_outputs(game_dir, state)

    assert len(relocated) == 2
    assert (game_dir / "outputs" / "period-1_2026-03-15.mkv").is_file()
    assert (game_dir / "outputs" / "a_vs_b_2026-03-15.mkv").is_file()
    assert not seg.exists()
    assert not hl.exists()
    assert any("Relocated" in m for m in messages)


def test_relocate_outputs_dry_run(tmp_path: Path) -> None:
    """Dry run reports but does not move files."""
    game_dir = tmp_path / "2026-03-15_a_vs_b"
    game_dir.mkdir()
    seg = tmp_path / "period-1_2026-03-15.mkv"
    seg.write_bytes(b"segment")

    state = _make_state(segment_outputs=["period-1_2026-03-15.mkv"])

    relocated, messages = relocate_outputs(game_dir, state, dry_run=True)

    assert len(relocated) == 1
    assert seg.exists()  # not moved
    assert not (game_dir / "outputs").exists()
    assert any("Would relocate" in m for m in messages)


def test_relocate_outputs_missing_files(tmp_path: Path) -> None:
    """Missing output files are skipped gracefully."""
    game_dir = tmp_path / "2026-03-15_a_vs_b"
    game_dir.mkdir()

    state = _make_state(
        segment_outputs=["period-1_2026-03-15.mkv"],
        highlights_output="a_vs_b_2026-03-15.mkv",
    )

    relocated, messages = relocate_outputs(game_dir, state)

    assert relocated == []
    assert messages == []


def test_relocate_outputs_no_outputs(tmp_path: Path) -> None:
    """No outputs in state means nothing to relocate."""
    game_dir = tmp_path / "2026-03-15_a_vs_b"
    game_dir.mkdir()

    state = _make_state()

    relocated, messages = relocate_outputs(game_dir, state)

    assert relocated == []
    assert messages == []


def test_relocate_outputs_partial_missing(tmp_path: Path) -> None:
    """Some files exist, some don't — only existing ones are moved."""
    game_dir = tmp_path / "2026-03-15_a_vs_b"
    game_dir.mkdir()
    seg = tmp_path / "period-1_2026-03-15.mkv"
    seg.write_bytes(b"segment")
    # period-2 doesn't exist

    state = _make_state(
        segment_outputs=["period-1_2026-03-15.mkv", "period-2_2026-03-15.mkv"],
    )

    relocated, messages = relocate_outputs(game_dir, state)

    assert len(relocated) == 1
    assert (game_dir / "outputs" / "period-1_2026-03-15.mkv").is_file()
    assert len(messages) == 1


# ---------------------------------------------------------------------------
# finish_game — relocate integration
# ---------------------------------------------------------------------------


def test_finish_game_relocates_outputs(tmp_path: Path) -> None:
    """finish_game calls relocate_outputs and includes messages."""
    game_dir = tmp_path / "2026-03-15_a_vs_b"
    game_dir.mkdir()
    seg = tmp_path / "period-1_2026-03-15.mkv"
    seg.write_bytes(b"segment")

    state = _make_state(segment_outputs=["period-1_2026-03-15.mkv"])
    _write_state(game_dir, state)

    result, messages = finish_game(game_dir)

    assert result.finished is True
    assert (game_dir / "outputs" / "period-1_2026-03-15.mkv").is_file()
    assert not seg.exists()
    assert any("Relocated" in m for m in messages)


def test_finish_game_dry_run_no_relocate(tmp_path: Path) -> None:
    """Dry run does not relocate outputs."""
    game_dir = tmp_path / "2026-03-15_a_vs_b"
    game_dir.mkdir()
    seg = tmp_path / "period-1_2026-03-15.mkv"
    seg.write_bytes(b"segment")

    state = _make_state(segment_outputs=["period-1_2026-03-15.mkv"])
    _write_state(game_dir, state)

    result, messages = finish_game(game_dir, dry_run=True)

    assert result.finished is True
    assert seg.exists()  # not moved
    assert not any("Relocated" in m for m in messages)
