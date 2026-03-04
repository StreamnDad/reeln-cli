"""Tests for event listing, tagging, resolution, and compilation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from reeln.core.errors import MediaError
from reeln.core.events import (
    compile_events,
    list_events,
    resolve_event_id,
    tag_event,
    tag_events_in_segment,
)
from reeln.core.highlights import load_game_state
from reeln.models.game import GameEvent, GameInfo, GameState, game_state_to_dict
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.registry import get_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_state(game_dir: Path, state: GameState) -> None:
    data = game_state_to_dict(state)
    (game_dir / "game.json").write_text(json.dumps(data), encoding="utf-8")


def _make_state(events: list[GameEvent] | None = None) -> GameState:
    gi = GameInfo(date="2026-02-28", home_team="roseville", away_team="mahtomedi", sport="hockey")
    return GameState(game_info=gi, created_at="t1", events=events or [])


def _make_event(
    event_id: str = "abc123",
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


def _mock_ffmpeg_success() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------


def test_list_events_all(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    ev2 = _make_event("bbb", "period-2/r1.mkv", 2, "save")
    _write_state(tmp_path, _make_state([ev1, ev2]))

    result = list_events(tmp_path)
    assert len(result) == 2


def test_list_events_filter_segment(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    ev2 = _make_event("bbb", "period-2/r1.mkv", 2, "save")
    _write_state(tmp_path, _make_state([ev1, ev2]))

    result = list_events(tmp_path, segment_number=1)
    assert len(result) == 1
    assert result[0].id == "aaa"


def test_list_events_filter_type(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", event_type="goal")
    ev2 = _make_event("bbb", event_type="save")
    _write_state(tmp_path, _make_state([ev1, ev2]))

    result = list_events(tmp_path, event_type="goal")
    assert len(result) == 1
    assert result[0].event_type == "goal"


def test_list_events_untagged_only(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", event_type="goal")
    ev2 = _make_event("bbb", event_type="")
    _write_state(tmp_path, _make_state([ev1, ev2]))

    result = list_events(tmp_path, untagged_only=True)
    assert len(result) == 1
    assert result[0].id == "bbb"


def test_list_events_empty(tmp_path: Path) -> None:
    _write_state(tmp_path, _make_state())
    assert list_events(tmp_path) == []


def test_list_events_combined_filters(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    ev2 = _make_event("bbb", "period-1/r2.mkv", 1, "save")
    ev3 = _make_event("ccc", "period-2/r1.mkv", 2, "goal")
    _write_state(tmp_path, _make_state([ev1, ev2, ev3]))

    result = list_events(tmp_path, segment_number=1, event_type="goal")
    assert len(result) == 1
    assert result[0].id == "aaa"


# ---------------------------------------------------------------------------
# resolve_event_id
# ---------------------------------------------------------------------------


def test_resolve_event_id_exact(tmp_path: Path) -> None:
    ev = _make_event("abcdef123456")
    result = resolve_event_id([ev], "abcdef123456")
    assert result.id == "abcdef123456"


def test_resolve_event_id_prefix(tmp_path: Path) -> None:
    ev = _make_event("abcdef123456")
    result = resolve_event_id([ev], "abcdef")
    assert result.id == "abcdef123456"


def test_resolve_event_id_not_found(tmp_path: Path) -> None:
    ev = _make_event("abcdef123456")
    with pytest.raises(MediaError, match="No event found"):
        resolve_event_id([ev], "zzz")


def test_resolve_event_id_ambiguous(tmp_path: Path) -> None:
    ev1 = _make_event("abc111")
    ev2 = _make_event("abc222")
    with pytest.raises(MediaError, match="Ambiguous"):
        resolve_event_id([ev1, ev2], "abc")


# ---------------------------------------------------------------------------
# tag_event
# ---------------------------------------------------------------------------


def test_tag_event_type(tmp_path: Path) -> None:
    ev = _make_event("abc123")
    _write_state(tmp_path, _make_state([ev]))

    updated = tag_event(tmp_path, "abc123", event_type="goal")
    assert updated.event_type == "goal"

    # Verify persisted
    state = load_game_state(tmp_path)
    assert state.events[0].event_type == "goal"


def test_tag_event_player(tmp_path: Path) -> None:
    ev = _make_event("abc123")
    _write_state(tmp_path, _make_state([ev]))

    updated = tag_event(tmp_path, "abc123", player="#17")
    assert updated.player == "#17"


def test_tag_event_metadata(tmp_path: Path) -> None:
    ev = _make_event("abc123")
    _write_state(tmp_path, _make_state([ev]))

    updated = tag_event(tmp_path, "abc123", metadata_updates={"assists": ["#9"]})
    assert updated.metadata == {"assists": ["#9"]}


def test_tag_event_metadata_merges(tmp_path: Path) -> None:
    ev = _make_event("abc123")
    ev.metadata = {"title": "Great goal"}
    _write_state(tmp_path, _make_state([ev]))

    updated = tag_event(tmp_path, "abc123", metadata_updates={"assists": ["#9"]})
    assert updated.metadata == {"title": "Great goal", "assists": ["#9"]}


def test_tag_event_multiple_fields(tmp_path: Path) -> None:
    ev = _make_event("abc123")
    _write_state(tmp_path, _make_state([ev]))

    updated = tag_event(tmp_path, "abc123", event_type="goal", player="#17")
    assert updated.event_type == "goal"
    assert updated.player == "#17"


def test_tag_event_prefix_match(tmp_path: Path) -> None:
    ev = _make_event("abcdef123456")
    _write_state(tmp_path, _make_state([ev]))

    updated = tag_event(tmp_path, "abcdef", event_type="save")
    assert updated.event_type == "save"


def test_tag_event_no_changes(tmp_path: Path) -> None:
    ev = _make_event("abc123", event_type="goal")
    _write_state(tmp_path, _make_state([ev]))

    updated = tag_event(tmp_path, "abc123")
    assert updated.event_type == "goal"


# ---------------------------------------------------------------------------
# tag_events_in_segment
# ---------------------------------------------------------------------------


def test_tag_events_in_segment_type(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-1/r1.mkv", 1)
    ev2 = _make_event("bbb", "period-1/r2.mkv", 1)
    ev3 = _make_event("ccc", "period-2/r1.mkv", 2)
    _write_state(tmp_path, _make_state([ev1, ev2, ev3]))

    updated = tag_events_in_segment(tmp_path, 1, event_type="goal")
    assert len(updated) == 2
    assert all(e.event_type == "goal" for e in updated)

    # Segment 2 unaffected
    state = load_game_state(tmp_path)
    assert state.events[2].event_type == ""


def test_tag_events_in_segment_player(tmp_path: Path) -> None:
    ev = _make_event("aaa", segment_number=1)
    _write_state(tmp_path, _make_state([ev]))

    updated = tag_events_in_segment(tmp_path, 1, player="#17")
    assert updated[0].player == "#17"


def test_tag_events_in_segment_no_events(tmp_path: Path) -> None:
    _write_state(tmp_path, _make_state())

    with pytest.raises(MediaError, match="No events found for segment"):
        tag_events_in_segment(tmp_path, 1, event_type="goal")


def test_tag_events_in_segment_wrong_segment(tmp_path: Path) -> None:
    ev = _make_event("aaa", segment_number=1)
    _write_state(tmp_path, _make_state([ev]))

    with pytest.raises(MediaError, match="No events found for segment 2"):
        tag_events_in_segment(tmp_path, 2, event_type="goal")


# ---------------------------------------------------------------------------
# compile_events
# ---------------------------------------------------------------------------


def test_compile_events_all(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    ev2 = _make_event("bbb", "period-2/r1.mkv", 2, "goal")
    _write_state(tmp_path, _make_state([ev1, ev2]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()
    (tmp_path / "period-2").mkdir()
    (tmp_path / "period-2" / "r1.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_ffmpeg_success()):
        result, messages = compile_events(
            tmp_path,
            ffmpeg_path=ffmpeg,
            event_type="goal",
        )

    assert len(result.event_ids) == 2
    assert len(result.input_files) == 2
    assert result.copy is True
    assert "goal" in str(result.output)
    assert any("Compilation complete" in m for m in messages)


def test_compile_events_filter_segment(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    ev2 = _make_event("bbb", "period-2/r1.mkv", 2, "goal")
    _write_state(tmp_path, _make_state([ev1, ev2]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()
    (tmp_path / "period-2").mkdir()
    (tmp_path / "period-2" / "r1.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_ffmpeg_success()):
        result, _ = compile_events(
            tmp_path,
            ffmpeg_path=ffmpeg,
            segment_number=1,
        )

    assert len(result.event_ids) == 1
    assert result.event_ids[0] == "aaa"
    assert "segment-1" in str(result.output)


def test_compile_events_filter_player(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-1/r1.mkv", 1, "goal", "#17")
    ev2 = _make_event("bbb", "period-1/r2.mkv", 1, "goal", "#22")
    _write_state(tmp_path, _make_state([ev1, ev2]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()
    (tmp_path / "period-1" / "r2.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_ffmpeg_success()):
        result, _ = compile_events(
            tmp_path,
            ffmpeg_path=ffmpeg,
            player="#17",
        )

    assert len(result.event_ids) == 1
    assert result.event_ids[0] == "aaa"


def test_compile_events_no_matches(tmp_path: Path) -> None:
    _write_state(tmp_path, _make_state())

    ffmpeg = Path("/usr/bin/ffmpeg")
    with pytest.raises(MediaError, match="No events match"):
        compile_events(tmp_path, ffmpeg_path=ffmpeg, event_type="goal")


def test_compile_events_missing_clip(tmp_path: Path) -> None:
    ev = _make_event("aaa", "period-1/missing.mkv", 1, "goal")
    _write_state(tmp_path, _make_state([ev]))

    ffmpeg = Path("/usr/bin/ffmpeg")
    with pytest.raises(MediaError, match="Event clip not found"):
        compile_events(tmp_path, ffmpeg_path=ffmpeg, event_type="goal")


def test_compile_events_dry_run(tmp_path: Path) -> None:
    ev = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    _write_state(tmp_path, _make_state([ev]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    result, messages = compile_events(
        tmp_path,
        ffmpeg_path=ffmpeg,
        event_type="goal",
        dry_run=True,
    )

    assert any("Dry run" in m for m in messages)
    assert not any("Compilation complete" in m for m in messages)
    assert len(result.event_ids) == 1


def test_compile_events_custom_output(tmp_path: Path) -> None:
    ev = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    _write_state(tmp_path, _make_state([ev]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    custom_out = tmp_path / "my_reel.mp4"
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_ffmpeg_success()):
        result, _ = compile_events(
            tmp_path,
            ffmpeg_path=ffmpeg,
            event_type="goal",
            output=custom_out,
        )

    assert result.output == custom_out


def test_compile_events_default_output_no_filter(tmp_path: Path) -> None:
    ev = _make_event("aaa", "period-1/r1.mkv", 1)
    _write_state(tmp_path, _make_state([ev]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_ffmpeg_success()):
        result, _ = compile_events(tmp_path, ffmpeg_path=ffmpeg)

    assert "all_compilation" in str(result.output)


def test_compile_events_mixed_formats(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    ev2 = _make_event("bbb", "period-1/r2.mp4", 1, "goal")
    _write_state(tmp_path, _make_state([ev1, ev2]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()
    (tmp_path / "period-1" / "r2.mp4").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_ffmpeg_success()):
        result, messages = compile_events(
            tmp_path,
            ffmpeg_path=ffmpeg,
            event_type="goal",
        )

    assert result.copy is False
    assert any("re-encode" in m for m in messages)


def test_compile_events_sorted_by_segment_then_clip(tmp_path: Path) -> None:
    ev1 = _make_event("aaa", "period-2/r1.mkv", 2, "goal")
    ev2 = _make_event("bbb", "period-1/r2.mkv", 1, "goal")
    ev3 = _make_event("ccc", "period-1/r1.mkv", 1, "goal")
    _write_state(tmp_path, _make_state([ev1, ev2, ev3]))
    for d in ("period-1", "period-2"):
        (tmp_path / d).mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()
    (tmp_path / "period-1" / "r2.mkv").touch()
    (tmp_path / "period-2" / "r1.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_ffmpeg_success()):
        result, _ = compile_events(
            tmp_path,
            ffmpeg_path=ffmpeg,
            event_type="goal",
        )

    # Sorted: segment 1 first (r1, r2), then segment 2
    assert result.event_ids == ["ccc", "bbb", "aaa"]


def test_compile_events_uses_video_config(tmp_path: Path) -> None:
    from reeln.models.config import VideoConfig

    ev1 = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    ev2 = _make_event("bbb", "period-1/r2.mp4", 1, "goal")  # mixed → re-encode
    _write_state(tmp_path, _make_state([ev1, ev2]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()
    (tmp_path / "period-1" / "r2.mp4").touch()

    vc = VideoConfig(codec="libx265", crf=22, audio_codec="opus")
    ffmpeg = Path("/usr/bin/ffmpeg")
    captured_cmd: list[str] = []

    def capture_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_cmd.extend(cmd)
        return _mock_ffmpeg_success()

    with patch("reeln.core.ffmpeg.subprocess.run", side_effect=capture_run):
        compile_events(
            tmp_path,
            ffmpeg_path=ffmpeg,
            event_type="goal",
            video_config=vc,
        )

    assert "-c:v" in captured_cmd
    idx = captured_cmd.index("-c:v")
    assert captured_cmd[idx + 1] == "libx265"


def test_compile_events_cleans_up_concat_file(tmp_path: Path) -> None:
    ev = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    _write_state(tmp_path, _make_state([ev]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_ffmpeg_success()):
        compile_events(tmp_path, ffmpeg_path=ffmpeg, event_type="goal")

    txt_files = list(tmp_path.glob("*.txt"))
    assert txt_files == []


def test_compile_events_cleans_up_on_error(tmp_path: Path) -> None:
    from reeln.core.errors import FFmpegError

    ev = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    _write_state(tmp_path, _make_state([ev]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()

    ffmpeg = Path("/usr/bin/ffmpeg")
    fail_proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail")

    with (
        patch("reeln.core.ffmpeg.subprocess.run", return_value=fail_proc),
        pytest.raises(FFmpegError),
    ):
        compile_events(tmp_path, ffmpeg_path=ffmpeg, event_type="goal")

    txt_files = list(tmp_path.glob("*.txt"))
    assert txt_files == []


# ---------------------------------------------------------------------------
# Hook emissions
# ---------------------------------------------------------------------------


def test_compile_events_emits_on_error_on_ffmpeg_failure(tmp_path: Path) -> None:
    from reeln.core.errors import FFmpegError

    ev = _make_event("aaa", "period-1/r1.mkv", 1, "goal")
    _write_state(tmp_path, _make_state([ev]))
    (tmp_path / "period-1").mkdir()
    (tmp_path / "period-1" / "r1.mkv").touch()

    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_ERROR, emitted.append)

    ffmpeg = Path("/usr/bin/ffmpeg")
    fail_proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail")

    with (
        patch("reeln.core.ffmpeg.subprocess.run", return_value=fail_proc),
        pytest.raises(FFmpegError),
    ):
        compile_events(tmp_path, ffmpeg_path=ffmpeg, event_type="goal")

    assert len(emitted) == 1
    assert emitted[0].hook is Hook.ON_ERROR
    assert emitted[0].data["operation"] == "compile_events"


def test_tag_event_emits_on_event_tagged(tmp_path: Path) -> None:
    ev = _make_event("abc123")
    _write_state(tmp_path, _make_state([ev]))

    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_EVENT_TAGGED, emitted.append)

    tag_event(tmp_path, "abc123", event_type="goal")

    assert len(emitted) == 1
    assert emitted[0].hook is Hook.ON_EVENT_TAGGED
    assert emitted[0].data["event"].event_type == "goal"


def test_tag_event_no_changes_still_emits(tmp_path: Path) -> None:
    """Hook fires even when no fields change (tag was still called)."""
    ev = _make_event("abc123", event_type="goal")
    _write_state(tmp_path, _make_state([ev]))

    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_EVENT_TAGGED, emitted.append)

    tag_event(tmp_path, "abc123")

    assert len(emitted) == 1
