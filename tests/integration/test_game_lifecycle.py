"""Core-layer integration tests for the game lifecycle.

Tests seams between core/highlights.py, core/segment.py, core/ffmpeg.py,
and models/game.py. Subprocess is mocked — no real ffmpeg required.
"""

from __future__ import annotations

from pathlib import Path

from reeln.core.highlights import (
    create_game_directory,
    init_game,
    load_game_state,
    merge_game_highlights,
    process_segment,
)
from reeln.core.segment import segment_dir_name
from reeln.models.config import VideoConfig
from reeln.models.game import GameInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FFMPEG = Path("/usr/bin/ffmpeg")


def _populate_segment(game_dir: Path, sport: str, seg_num: int, count: int = 3, ext: str = ".mkv") -> list[Path]:
    """Create dummy video files in a segment directory."""
    alias = segment_dir_name(sport, seg_num)
    seg_dir = game_dir / alias
    files: list[Path] = []
    for i in range(1, count + 1):
        f = seg_dir / f"replay_{i:02d}{ext}"
        f.touch()
        files.append(f)
    return files


def _touch_segment_output(game_dir: Path, sport: str, seg_num: int, date: str) -> Path:
    """Touch the expected segment merge output file so downstream steps find it."""
    alias = segment_dir_name(sport, seg_num)
    output = game_dir.parent / f"{alias}_{date}.mkv"
    output.touch()
    return output


# ---------------------------------------------------------------------------
# Hockey lifecycle
# ---------------------------------------------------------------------------


class TestHockeyLifecycle:
    """Full hockey game lifecycle: init → 3 segments → highlights."""

    def test_full_lifecycle_state_transitions(
        self,
        tmp_path: Path,
        hockey_game_info: GameInfo,
        mock_ffmpeg_run: list[list[str]],
    ) -> None:
        """Game state evolves: segments_processed grows, highlighted flips."""
        game_dir = create_game_directory(tmp_path, hockey_game_info)

        # Process 3 periods
        for seg in range(1, 4):
            _populate_segment(game_dir, "hockey", seg)
            _, messages = process_segment(
                game_dir,
                seg,
                ffmpeg_path=_FFMPEG,
            )
            assert "Merge complete" in messages
            # Touch output so highlights can find it
            _touch_segment_output(game_dir, "hockey", seg, "2026-02-26")

            state = load_game_state(game_dir)
            assert seg in state.segments_processed

        state = load_game_state(game_dir)
        assert state.segments_processed == [1, 2, 3]
        assert state.highlighted is False

        # Merge highlights
        _, messages = merge_game_highlights(game_dir, ffmpeg_path=_FFMPEG)
        assert "Highlights merge complete" in messages

        state = load_game_state(game_dir)
        assert state.highlighted is True

    def test_lifecycle_golden_commands(
        self,
        tmp_path: Path,
        hockey_game_info: GameInfo,
        mock_ffmpeg_run: list[list[str]],
    ) -> None:
        """Verify 4 ffmpeg calls (3 segments + 1 highlights), all stream-copy."""
        game_dir = create_game_directory(tmp_path, hockey_game_info)

        for seg in range(1, 4):
            _populate_segment(game_dir, "hockey", seg)
            process_segment(game_dir, seg, ffmpeg_path=_FFMPEG)
            _touch_segment_output(game_dir, "hockey", seg, "2026-02-26")

        merge_game_highlights(game_dir, ffmpeg_path=_FFMPEG)

        assert len(mock_ffmpeg_run) == 4
        for cmd in mock_ffmpeg_run:
            assert "-c" in cmd
            copy_idx = cmd.index("-c")
            assert cmd[copy_idx + 1] == "copy"

    def test_lifecycle_directory_structure(
        self,
        tmp_path: Path,
        hockey_game_info: GameInfo,
        mock_ffmpeg_run: list[list[str]],
    ) -> None:
        """Game dir contains period-1/, period-2/, period-3/, game.json."""
        game_dir = create_game_directory(tmp_path, hockey_game_info)

        assert (game_dir / "period-1").is_dir()
        assert (game_dir / "period-2").is_dir()
        assert (game_dir / "period-3").is_dir()
        assert (game_dir / "game.json").is_file()

    def test_lifecycle_with_custom_video_config(
        self,
        tmp_path: Path,
        hockey_game_info: GameInfo,
        mock_ffmpeg_run: list[list[str]],
        custom_video_config: VideoConfig,
    ) -> None:
        """VideoConfig(libx265, crf=22, opus) flows into ffmpeg command args."""
        game_dir = create_game_directory(tmp_path, hockey_game_info)

        # Use mixed containers to force re-encode (copy=False)
        seg_dir = game_dir / "period-1"
        (seg_dir / "replay_01.mkv").touch()
        (seg_dir / "replay_02.mp4").touch()

        process_segment(
            game_dir,
            1,
            ffmpeg_path=_FFMPEG,
            video_config=custom_video_config,
        )

        assert len(mock_ffmpeg_run) == 1
        cmd = mock_ffmpeg_run[0]
        assert "-c:v" in cmd
        assert "libx265" in cmd
        assert "-crf" in cmd
        crf_idx = cmd.index("-crf")
        assert cmd[crf_idx + 1] == "22"
        assert "-c:a" in cmd
        assert "opus" in cmd

    def test_output_file_naming(
        self,
        tmp_path: Path,
        hockey_game_info: GameInfo,
        mock_ffmpeg_run: list[list[str]],
    ) -> None:
        """Segment output: period-1_2026-02-26.mkv, highlights: roseville_vs_mahtomedi_2026-02-26.mkv."""
        game_dir = create_game_directory(tmp_path, hockey_game_info)
        _populate_segment(game_dir, "hockey", 1)

        result, _ = process_segment(game_dir, 1, ffmpeg_path=_FFMPEG)
        assert result.output.name == "period-1_2026-02-26.mkv"

        # Touch all 3 segment outputs for highlights
        for seg in range(1, 4):
            _touch_segment_output(game_dir, "hockey", seg, "2026-02-26")

        hl_result, _ = merge_game_highlights(game_dir, ffmpeg_path=_FFMPEG)
        assert hl_result.output.name == "roseville_vs_mahtomedi_2026-02-26.mkv"


# ---------------------------------------------------------------------------
# Basketball lifecycle
# ---------------------------------------------------------------------------


class TestBasketballLifecycle:
    """Basketball game: 4 quarters."""

    def test_full_lifecycle_four_quarters(
        self,
        tmp_path: Path,
        basketball_game_info: GameInfo,
        mock_ffmpeg_run: list[list[str]],
    ) -> None:
        """4 quarters produce quarter-N/ dirs and 5 ffmpeg calls."""
        game_dir = create_game_directory(tmp_path, basketball_game_info)

        for seg in range(1, 5):
            alias = segment_dir_name("basketball", seg)
            assert alias == f"quarter-{seg}"
            assert (game_dir / alias).is_dir()

            _populate_segment(game_dir, "basketball", seg)
            process_segment(game_dir, seg, ffmpeg_path=_FFMPEG)
            _touch_segment_output(game_dir, "basketball", seg, "2026-02-26")

        merge_game_highlights(game_dir, ffmpeg_path=_FFMPEG)

        # 4 segment merges + 1 highlights merge = 5 calls
        assert len(mock_ffmpeg_run) == 5

        state = load_game_state(game_dir)
        assert state.segments_processed == [1, 2, 3, 4]
        assert state.highlighted is True


# ---------------------------------------------------------------------------
# Mixed container lifecycle
# ---------------------------------------------------------------------------


class TestMixedContainerLifecycle:
    """Mixed extensions trigger re-encode."""

    def test_mixed_containers_trigger_reencode(
        self,
        tmp_path: Path,
        hockey_game_info: GameInfo,
        mock_ffmpeg_run: list[list[str]],
    ) -> None:
        """.mkv + .mp4 in same segment → re-encode (no -c copy)."""
        game_dir = create_game_directory(tmp_path, hockey_game_info)
        seg_dir = game_dir / "period-1"
        (seg_dir / "replay_01.mkv").touch()
        (seg_dir / "replay_02.mp4").touch()

        result, messages = process_segment(game_dir, 1, ffmpeg_path=_FFMPEG)

        assert result.copy is False
        assert "re-encode (mixed containers)" in " ".join(messages)

        cmd = mock_ffmpeg_run[0]
        assert "-c:v" in cmd
        assert "-c" not in cmd or cmd[cmd.index("-c:v") - 1] != "-c"  # no bare -c copy


# ---------------------------------------------------------------------------
# Double header lifecycle
# ---------------------------------------------------------------------------


class TestDoubleHeaderLifecycle:
    """Double header auto-numbering."""

    def test_double_header_auto_numbering(
        self,
        tmp_path: Path,
        mock_ffmpeg_run: list[list[str]],
    ) -> None:
        """Second game gets _g2 suffix, independent state."""
        info1 = GameInfo(
            date="2026-02-26",
            home_team="roseville",
            away_team="mahtomedi",
            sport="hockey",
        )
        game_dir1, _ = init_game(tmp_path, info1)
        assert "_g" not in game_dir1.name

        # Finish first game before starting second
        from reeln.core.finish import finish_game

        finish_game(game_dir1)

        info2 = GameInfo(
            date="2026-02-26",
            home_team="roseville",
            away_team="mahtomedi",
            sport="hockey",
        )
        game_dir2, _ = init_game(tmp_path, info2)
        assert game_dir2.name.endswith("_g2")

        # States are independent — re-init game_dir1 state for segment processing
        from reeln.core.highlights import save_game_state

        state1 = load_game_state(game_dir1)
        state1.finished = False
        state1.finished_at = ""
        save_game_state(state1, game_dir1)

        _populate_segment(game_dir1, "hockey", 1)
        process_segment(game_dir1, 1, ffmpeg_path=_FFMPEG)

        state1 = load_game_state(game_dir1)
        state2 = load_game_state(game_dir2)
        assert state1.segments_processed == [1]
        assert state2.segments_processed == []


# ---------------------------------------------------------------------------
# Concat file cleanup
# ---------------------------------------------------------------------------


class TestConcatFileCleanup:
    """Temporary concat files should be cleaned up."""

    def test_no_leftover_concat_files(
        self,
        tmp_path: Path,
        hockey_game_info: GameInfo,
        mock_ffmpeg_run: list[list[str]],
    ) -> None:
        """No .txt files left after full lifecycle."""
        game_dir = create_game_directory(tmp_path, hockey_game_info)

        for seg in range(1, 4):
            _populate_segment(game_dir, "hockey", seg)
            process_segment(game_dir, seg, ffmpeg_path=_FFMPEG)
            _touch_segment_output(game_dir, "hockey", seg, "2026-02-26")

        merge_game_highlights(game_dir, ffmpeg_path=_FFMPEG)

        # Search entire game dir tree for leftover .txt files
        txt_files = list(game_dir.rglob("*.txt"))
        assert txt_files == [], f"Leftover concat files: {txt_files}"
