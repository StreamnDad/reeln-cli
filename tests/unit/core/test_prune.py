"""Tests for artifact cleanup — prune_game, prune_all, helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reeln.core.errors import MediaError
from reeln.core.prune import (
    _build_prune_summary,
    _file_size,
    _remove_dir_if_empty,
    _remove_file,
    find_game_dirs,
    format_bytes,
    prune_all,
    prune_game,
)
from reeln.models.game import (
    GameEvent,
    GameInfo,
    GameState,
    game_state_to_dict,
)
from reeln.models.render_plan import PruneResult


def _write_state(game_dir: Path, state: GameState) -> Path:
    """Write a game.json to *game_dir*."""
    game_dir.mkdir(parents=True, exist_ok=True)
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
# format_bytes
# ---------------------------------------------------------------------------


def test_format_bytes_zero() -> None:
    assert format_bytes(0) == "0 B"


def test_format_bytes_small() -> None:
    assert format_bytes(512) == "512 B"


def test_format_bytes_kb() -> None:
    assert format_bytes(1024) == "1.0 KB"


def test_format_bytes_mb() -> None:
    assert format_bytes(1_500_000) == "1.4 MB"


def test_format_bytes_gb() -> None:
    assert format_bytes(2_500_000_000) == "2.3 GB"


def test_format_bytes_tb() -> None:
    assert format_bytes(1_500_000_000_000) == "1.4 TB"


# ---------------------------------------------------------------------------
# _file_size
# ---------------------------------------------------------------------------


def test_file_size_existing(tmp_path: Path) -> None:
    f = tmp_path / "test.txt"
    f.write_text("hello")
    assert _file_size(f) == 5


def test_file_size_missing(tmp_path: Path) -> None:
    assert _file_size(tmp_path / "nope.txt") == 0


# ---------------------------------------------------------------------------
# _remove_file
# ---------------------------------------------------------------------------


def test_remove_file_actual(tmp_path: Path) -> None:
    f = tmp_path / "test.mkv"
    f.write_bytes(b"x" * 100)
    result = PruneResult()

    _remove_file(f, dry_run=False, result=result)

    assert not f.exists()
    assert len(result.removed_paths) == 1
    assert result.bytes_freed == 100
    assert result.errors == []


def test_remove_file_dry_run(tmp_path: Path) -> None:
    f = tmp_path / "test.mkv"
    f.write_bytes(b"x" * 100)
    result = PruneResult()

    _remove_file(f, dry_run=True, result=result)

    assert f.exists()  # not actually removed
    assert len(result.removed_paths) == 1
    assert result.bytes_freed == 100


def test_remove_file_error(tmp_path: Path) -> None:
    f = tmp_path / "gone.mkv"
    # File doesn't exist — unlink will fail
    result = PruneResult()

    _remove_file(f, dry_run=False, result=result)

    assert len(result.removed_paths) == 0
    assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# _remove_dir_if_empty
# ---------------------------------------------------------------------------


def test_remove_dir_if_empty(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()

    _remove_dir_if_empty(d, dry_run=False)

    assert not d.exists()


def test_remove_dir_if_empty_not_empty(tmp_path: Path) -> None:
    d = tmp_path / "notempty"
    d.mkdir()
    (d / "file.txt").write_text("x")

    _remove_dir_if_empty(d, dry_run=False)

    assert d.exists()


def test_remove_dir_if_empty_dry_run(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()

    _remove_dir_if_empty(d, dry_run=True)

    assert d.exists()  # not removed in dry run


def test_remove_dir_if_empty_not_dir(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x")

    # Should not raise, just skip
    _remove_dir_if_empty(f, dry_run=False)

    assert f.exists()


def test_remove_dir_if_empty_missing(tmp_path: Path) -> None:
    # Should not raise on missing path
    _remove_dir_if_empty(tmp_path / "nope", dry_run=False)


def test_remove_dir_if_empty_oserror(tmp_path: Path) -> None:
    """OSError during rmdir is silently swallowed."""
    from unittest.mock import patch

    d = tmp_path / "empty"
    d.mkdir()

    with patch.object(Path, "rmdir", side_effect=OSError("permission denied")):
        # Should not raise
        _remove_dir_if_empty(d, dry_run=False)


# ---------------------------------------------------------------------------
# prune_game
# ---------------------------------------------------------------------------


def test_prune_game_removes_generated(tmp_path: Path) -> None:
    """Removes segment merges and highlight reels but keeps tagged event clips."""
    events = [
        GameEvent(id="a", clip="period-1/Replay_001.mkv", segment_number=1, event_type="goal"),
    ]
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events)
    _write_state(tmp_path, state)

    # Create files
    p1 = tmp_path / "period-1"
    p1.mkdir()
    event_clip = p1 / "Replay_001.mkv"
    event_clip.write_bytes(b"x" * 50)
    merge = p1 / "period-1_2026-02-26.mkv"
    merge.write_bytes(b"x" * 200)
    highlights = tmp_path / "roseville_vs_mahtomedi_2026-02-26.mkv"
    highlights.write_bytes(b"x" * 300)

    result, messages = prune_game(tmp_path)

    assert event_clip.exists()  # preserved (tagged)
    assert not merge.exists()  # removed
    assert not highlights.exists()  # removed
    assert len(result.removed_paths) == 2
    assert result.bytes_freed == 500
    assert any("2 file(s)" in m for m in messages)


def test_prune_game_all_files(tmp_path: Path) -> None:
    """With all_files=True, also removes tagged event clips."""
    events = [
        GameEvent(id="a", clip="period-1/Replay_001.mkv", segment_number=1, event_type="goal"),
    ]
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events)
    _write_state(tmp_path, state)

    p1 = tmp_path / "period-1"
    p1.mkdir()
    event_clip = p1 / "Replay_001.mkv"
    event_clip.write_bytes(b"x" * 50)
    merge = p1 / "period-1_2026-02-26.mkv"
    merge.write_bytes(b"x" * 200)

    result, _messages = prune_game(tmp_path, all_files=True)

    assert not event_clip.exists()  # removed with --all
    assert not merge.exists()
    assert len(result.removed_paths) == 2
    # period-1 dir should be removed (now empty)
    assert not p1.exists()


def test_prune_game_warns_untagged_clips(tmp_path: Path) -> None:
    """Without --force, untagged event clips are warned about but not removed."""
    events = [
        GameEvent(id="a", clip="period-1/Replay_001.mkv", segment_number=1, event_type="goal"),
        GameEvent(id="b", clip="period-1/Replay_002.mkv", segment_number=1),  # untagged
    ]
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events)
    _write_state(tmp_path, state)

    p1 = tmp_path / "period-1"
    p1.mkdir()
    tagged = p1 / "Replay_001.mkv"
    tagged.write_bytes(b"x" * 50)
    untagged = p1 / "Replay_002.mkv"
    untagged.write_bytes(b"x" * 50)

    result, messages = prune_game(tmp_path)

    assert tagged.exists()  # tagged — preserved
    assert untagged.exists()  # untagged — not removed without --force
    assert len(result.removed_paths) == 0
    assert any("untagged clip(s)" in m for m in messages)
    assert any("--force" in m for m in messages)
    assert any("Replay_002.mkv" in m for m in messages)


def test_prune_game_force_removes_untagged(tmp_path: Path) -> None:
    """With --force, untagged event clips are removed."""
    events = [
        GameEvent(id="a", clip="period-1/Replay_001.mkv", segment_number=1, event_type="goal"),
        GameEvent(id="b", clip="period-1/Replay_002.mkv", segment_number=1),  # untagged
    ]
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events)
    _write_state(tmp_path, state)

    p1 = tmp_path / "period-1"
    p1.mkdir()
    tagged = p1 / "Replay_001.mkv"
    tagged.write_bytes(b"x" * 50)
    untagged = p1 / "Replay_002.mkv"
    untagged.write_bytes(b"x" * 50)

    result, messages = prune_game(tmp_path, force=True)

    assert tagged.exists()  # tagged — preserved
    assert not untagged.exists()  # untagged — removed with --force
    assert len(result.removed_paths) == 1
    assert not any("untagged clip(s)" in m for m in messages)


def test_prune_game_force_with_generated(tmp_path: Path) -> None:
    """With --force, both untagged clips and generated files are removed."""
    events = [
        GameEvent(id="a", clip="period-1/Replay_001.mkv", segment_number=1, event_type="goal"),
        GameEvent(id="b", clip="period-1/Replay_002.mkv", segment_number=1),  # untagged
    ]
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events)
    _write_state(tmp_path, state)

    p1 = tmp_path / "period-1"
    p1.mkdir()
    (p1 / "Replay_001.mkv").write_bytes(b"x" * 50)
    (p1 / "Replay_002.mkv").write_bytes(b"x" * 50)
    merge = p1 / "period-1_2026-02-26.mkv"
    merge.write_bytes(b"x" * 200)

    result, _messages = prune_game(tmp_path, force=True)

    assert (p1 / "Replay_001.mkv").exists()  # tagged — preserved
    assert not (p1 / "Replay_002.mkv").exists()  # untagged — removed
    assert not merge.exists()  # generated — removed
    assert len(result.removed_paths) == 2


def test_prune_game_all_overrides_force(tmp_path: Path) -> None:
    """--all removes everything including tagged clips, regardless of --force."""
    events = [
        GameEvent(id="a", clip="period-1/Replay_001.mkv", segment_number=1, event_type="goal"),
        GameEvent(id="b", clip="period-1/Replay_002.mkv", segment_number=1),  # untagged
    ]
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events)
    _write_state(tmp_path, state)

    p1 = tmp_path / "period-1"
    p1.mkdir()
    (p1 / "Replay_001.mkv").write_bytes(b"x" * 50)
    (p1 / "Replay_002.mkv").write_bytes(b"x" * 50)

    result, _messages = prune_game(tmp_path, all_files=True)

    assert not (p1 / "Replay_001.mkv").exists()  # removed with --all
    assert not (p1 / "Replay_002.mkv").exists()  # removed with --all
    assert len(result.removed_paths) == 2


def test_prune_game_untagged_dry_run(tmp_path: Path) -> None:
    """Dry run with --force reports untagged clips but doesn't remove them."""
    events = [
        GameEvent(id="a", clip="period-1/Replay_001.mkv", segment_number=1),  # untagged
    ]
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events)
    _write_state(tmp_path, state)

    p1 = tmp_path / "period-1"
    p1.mkdir()
    clip = p1 / "Replay_001.mkv"
    clip.write_bytes(b"x" * 50)

    result, messages = prune_game(tmp_path, force=True, dry_run=True)

    assert clip.exists()  # dry run — not actually removed
    assert len(result.removed_paths) == 1
    assert any("Would remove" in m for m in messages)


def test_prune_game_removes_temp_files(tmp_path: Path) -> None:
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    (tmp_path / "concat.txt").write_text("file 'a.mkv'\n")
    (tmp_path / "temp.tmp").write_text("temp")

    result, _messages = prune_game(tmp_path)

    assert not (tmp_path / "concat.txt").exists()
    assert not (tmp_path / "temp.tmp").exists()
    assert len(result.removed_paths) == 2


def test_prune_game_preserves_game_json(tmp_path: Path) -> None:
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    result, _messages = prune_game(tmp_path)

    assert (tmp_path / "game.json").exists()
    assert len(result.removed_paths) == 0


def test_prune_game_nothing_to_prune(tmp_path: Path) -> None:
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    result, messages = prune_game(tmp_path)

    assert len(result.removed_paths) == 0
    assert any("Nothing to prune" in m for m in messages)


def test_prune_game_dry_run(tmp_path: Path) -> None:
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    merge = tmp_path / "highlight.mkv"
    merge.write_bytes(b"x" * 100)

    result, messages = prune_game(tmp_path, dry_run=True)

    assert merge.exists()  # not actually removed
    assert len(result.removed_paths) == 1
    assert any("Would remove" in m for m in messages)


def test_prune_game_not_finished(tmp_path: Path) -> None:
    state = _make_state(finished=False)
    _write_state(tmp_path, state)

    with pytest.raises(MediaError, match="must be finished"):
        prune_game(tmp_path)


def test_prune_game_removes_debug_contents(tmp_path: Path) -> None:
    """Prune always removes debug directory contents."""
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    debug = tmp_path / "debug"
    debug.mkdir()
    (debug / "segment_merge_2026-03-02.json").write_text('{"operation": "test"}')
    (debug / "index.html").write_text("<html></html>")

    result, _messages = prune_game(tmp_path)

    assert not (debug / "segment_merge_2026-03-02.json").exists()
    assert not (debug / "index.html").exists()
    assert len(result.removed_paths) == 2


def test_prune_game_removes_empty_debug_dir(tmp_path: Path) -> None:
    """Prune removes the empty debug directory after clearing its contents."""
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    debug = tmp_path / "debug"
    debug.mkdir()
    (debug / "test.json").write_text("{}")

    prune_game(tmp_path)

    assert not debug.exists()


def test_prune_game_debug_dry_run(tmp_path: Path) -> None:
    """Dry run reports debug files but does not remove them."""
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    debug = tmp_path / "debug"
    debug.mkdir()
    artifact = debug / "test.json"
    artifact.write_text('{"operation": "test"}')

    result, messages = prune_game(tmp_path, dry_run=True)

    assert artifact.exists()
    assert len(result.removed_paths) == 1
    assert any("Would remove" in m for m in messages)


def test_prune_game_debug_with_subdirectory(tmp_path: Path) -> None:
    """Prune handles subdirectories inside debug/ (skips non-files)."""
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    debug = tmp_path / "debug"
    debug.mkdir()
    sub = debug / "subdir"
    sub.mkdir()
    (sub / "nested.json").write_text("{}")
    (debug / "top.json").write_text("{}")

    result, _messages = prune_game(tmp_path)

    # Both files removed, subdir should be empty and cleaned up
    assert len(result.removed_paths) == 2
    assert not debug.exists()


def test_prune_game_no_debug_dir(tmp_path: Path) -> None:
    """No debug directory is a no-op (no error)."""
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    result, _messages = prune_game(tmp_path)
    assert len(result.removed_paths) == 0


def test_prune_game_removes_outputs_contents(tmp_path: Path) -> None:
    """Prune removes files inside the outputs/ directory."""
    state = _make_state(
        finished=True,
        finished_at="2026-02-26T14:00:00+00:00",
        segment_outputs=["period-1_2026-02-26.mkv"],
        highlights_output="roseville_vs_mahtomedi_2026-02-26.mkv",
    )
    _write_state(tmp_path, state)

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "period-1_2026-02-26.mkv").write_bytes(b"x" * 200)
    (outputs / "roseville_vs_mahtomedi_2026-02-26.mkv").write_bytes(b"x" * 300)

    result, _messages = prune_game(tmp_path)

    assert not (outputs / "period-1_2026-02-26.mkv").exists()
    assert not (outputs / "roseville_vs_mahtomedi_2026-02-26.mkv").exists()
    assert len(result.removed_paths) == 2
    assert result.bytes_freed == 500
    # Empty outputs dir should be cleaned up
    assert not outputs.exists()


def test_prune_game_outputs_dry_run(tmp_path: Path) -> None:
    """Dry run reports outputs/ files but does not remove them."""
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "period-1_2026-02-26.mkv").write_bytes(b"x" * 200)

    result, messages = prune_game(tmp_path, dry_run=True)

    assert (outputs / "period-1_2026-02-26.mkv").exists()
    assert len(result.removed_paths) == 1
    assert any("Would remove" in m for m in messages)


def test_prune_game_ignores_non_video_non_temp(tmp_path: Path) -> None:
    """Non-video, non-temp files should be left alone."""
    state = _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00")
    _write_state(tmp_path, state)

    other = tmp_path / "notes.md"
    other.write_text("some notes")

    result, _messages = prune_game(tmp_path)

    assert other.exists()
    assert len(result.removed_paths) == 0


# ---------------------------------------------------------------------------
# find_game_dirs
# ---------------------------------------------------------------------------


def test_find_game_dirs_single(tmp_path: Path) -> None:
    """Base is itself a game dir."""
    state = _make_state()
    _write_state(tmp_path, state)

    dirs = find_game_dirs(tmp_path)
    assert dirs == [tmp_path]


def test_find_game_dirs_children(tmp_path: Path) -> None:
    g1 = tmp_path / "2026-02-26_a_vs_b"
    g2 = tmp_path / "2026-02-27_c_vs_d"
    _write_state(g1, _make_state())
    _write_state(g2, _make_state())

    # Also a non-game dir
    (tmp_path / "random").mkdir()

    dirs = find_game_dirs(tmp_path)
    assert len(dirs) == 2
    assert g1 in dirs
    assert g2 in dirs


def test_find_game_dirs_none(tmp_path: Path) -> None:
    dirs = find_game_dirs(tmp_path)
    assert dirs == []


def test_find_game_dirs_missing_base(tmp_path: Path) -> None:
    dirs = find_game_dirs(tmp_path / "nonexistent")
    assert dirs == []


# ---------------------------------------------------------------------------
# prune_all
# ---------------------------------------------------------------------------


def test_prune_all_multiple_games(tmp_path: Path) -> None:
    g1 = tmp_path / "game1"
    g2 = tmp_path / "game2"
    _write_state(g1, _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00"))
    _write_state(g2, _make_state(finished=True, finished_at="2026-02-27T14:00:00+00:00"))

    (g1 / "highlight.mkv").write_bytes(b"x" * 100)
    (g2 / "highlight.mkv").write_bytes(b"x" * 200)

    result, messages = prune_all(tmp_path)

    assert len(result.removed_paths) == 2
    assert result.bytes_freed == 300
    assert any("game1:" in m for m in messages)
    assert any("game2:" in m for m in messages)


def test_prune_all_skips_unfinished(tmp_path: Path) -> None:
    g1 = tmp_path / "finished_game"
    g2 = tmp_path / "ongoing_game"
    _write_state(g1, _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00"))
    _write_state(g2, _make_state(finished=False))

    (g1 / "highlight.mkv").write_bytes(b"x" * 100)
    (g2 / "highlight.mkv").write_bytes(b"x" * 200)

    result, messages = prune_all(tmp_path)

    assert len(result.removed_paths) == 1  # only finished game
    assert (g2 / "highlight.mkv").exists()  # unfinished untouched
    assert any("Skipping ongoing_game: not finished" in m for m in messages)


def test_prune_all_no_games(tmp_path: Path) -> None:
    result, messages = prune_all(tmp_path)

    assert len(result.removed_paths) == 0
    assert any("No game directories found" in m for m in messages)


def test_prune_all_dry_run(tmp_path: Path) -> None:
    g1 = tmp_path / "game1"
    _write_state(g1, _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00"))
    (g1 / "highlight.mkv").write_bytes(b"x" * 100)

    result, _messages = prune_all(tmp_path, dry_run=True)

    assert (g1 / "highlight.mkv").exists()
    assert len(result.removed_paths) == 1


def test_prune_all_with_all_files(tmp_path: Path) -> None:
    g1 = tmp_path / "game1"
    events = [GameEvent(id="a", clip="clip.mkv", segment_number=1, event_type="goal")]
    _write_state(g1, _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events))
    (g1 / "clip.mkv").write_bytes(b"x" * 50)

    result, _messages = prune_all(tmp_path, all_files=True)

    assert not (g1 / "clip.mkv").exists()
    assert len(result.removed_paths) == 1


def test_prune_all_with_force(tmp_path: Path) -> None:
    g1 = tmp_path / "game1"
    events = [GameEvent(id="a", clip="clip.mkv", segment_number=1)]  # untagged
    _write_state(g1, _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events))
    (g1 / "clip.mkv").write_bytes(b"x" * 50)

    result, _messages = prune_all(tmp_path, force=True)

    assert not (g1 / "clip.mkv").exists()
    assert len(result.removed_paths) == 1


def test_prune_all_warns_untagged_without_force(tmp_path: Path) -> None:
    g1 = tmp_path / "game1"
    events = [GameEvent(id="a", clip="clip.mkv", segment_number=1)]  # untagged
    _write_state(g1, _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00", events=events))
    (g1 / "clip.mkv").write_bytes(b"x" * 50)

    result, messages = prune_all(tmp_path)

    assert (g1 / "clip.mkv").exists()  # not removed without --force
    assert len(result.removed_paths) == 0
    assert any("untagged clip(s)" in m for m in messages)


def test_prune_all_nothing_to_prune(tmp_path: Path) -> None:
    """All games finished but no files to remove."""
    g1 = tmp_path / "game1"
    _write_state(g1, _make_state(finished=True, finished_at="2026-02-26T14:00:00+00:00"))

    result, messages = prune_all(tmp_path)

    assert len(result.removed_paths) == 0
    assert any("Nothing to prune" in m for m in messages)


# ---------------------------------------------------------------------------
# _build_prune_summary
# ---------------------------------------------------------------------------


def test_build_prune_summary_with_files() -> None:
    result = PruneResult(
        removed_paths=[Path("a.mkv"), Path("b.mkv")],
        bytes_freed=2048,
    )
    messages = _build_prune_summary(result, dry_run=False)
    assert any("Removed 2 file(s)" in m for m in messages)
    assert any("2.0 KB" in m for m in messages)


def test_build_prune_summary_dry_run() -> None:
    result = PruneResult(
        removed_paths=[Path("a.mkv")],
        bytes_freed=1024,
    )
    messages = _build_prune_summary(result, dry_run=True)
    assert any("Would remove 1 file(s)" in m for m in messages)


def test_build_prune_summary_nothing() -> None:
    result = PruneResult()
    messages = _build_prune_summary(result, dry_run=False)
    assert messages == ["Nothing to prune"]


def test_build_prune_summary_with_errors() -> None:
    result = PruneResult(
        removed_paths=[Path("a.mkv")],
        bytes_freed=100,
        errors=["permission denied: b.mkv"],
    )
    messages = _build_prune_summary(result, dry_run=False)
    assert any("Errors: 1" in m for m in messages)
    assert any("permission denied" in m for m in messages)
