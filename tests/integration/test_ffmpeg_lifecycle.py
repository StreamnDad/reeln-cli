"""Integration tests requiring a real ffmpeg binary — actual video processing.

All tests are marked @pytest.mark.integration and excluded from `make test`.
Run with: make test-integration
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from reeln.core.ffmpeg import probe_duration, probe_fps, probe_resolution
from reeln.core.highlights import (
    create_game_directory,
    load_game_state,
    merge_game_highlights,
    process_segment,
)
from reeln.core.segment import segment_dir_name
from reeln.models.game import GameInfo

# ---------------------------------------------------------------------------
# Real ffmpeg lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRealFfmpegLifecycle:
    """End-to-end tests with real ffmpeg processing real video files."""

    def test_stream_copy_lifecycle(
        self,
        tmp_path: Path,
        real_ffmpeg_path: Path,
        make_real_test_video: Callable[..., Path],
    ) -> None:
        """3 periods, same-container, concat produces valid output."""
        info = GameInfo(
            date="2026-02-26",
            home_team="roseville",
            away_team="mahtomedi",
            sport="hockey",
        )
        game_dir = create_game_directory(tmp_path, info)

        # Generate real videos and process each period
        for seg in range(1, 4):
            alias = segment_dir_name("hockey", seg)
            seg_dir = game_dir / alias
            for i in range(1, 3):
                make_real_test_video(seg_dir / f"replay_{i:02d}.mkv", duration=1.0)

            result, messages = process_segment(
                game_dir,
                seg,
                ffmpeg_path=real_ffmpeg_path,
            )
            assert result.output.is_file()
            assert "Merge complete" in messages

            dur = probe_duration(real_ffmpeg_path, result.output)
            assert dur is not None
            assert dur > 0

        state = load_game_state(game_dir)
        assert state.segments_processed == [1, 2, 3]

        # Merge highlights
        hl_result, hl_messages = merge_game_highlights(
            game_dir,
            ffmpeg_path=real_ffmpeg_path,
        )
        assert hl_result.output.is_file()
        assert "Highlights merge complete" in hl_messages

        dur = probe_duration(real_ffmpeg_path, hl_result.output)
        assert dur is not None
        assert dur > 0

        state = load_game_state(game_dir)
        assert state.highlighted is True

    def test_reencode_lifecycle_mixed_containers(
        self,
        tmp_path: Path,
        real_ffmpeg_path: Path,
        make_real_test_video: Callable[..., Path],
    ) -> None:
        """Mixed .mkv + .mp4 triggers re-encode, output is valid."""
        info = GameInfo(
            date="2026-02-26",
            home_team="roseville",
            away_team="mahtomedi",
            sport="hockey",
        )
        game_dir = create_game_directory(tmp_path, info)
        seg_dir = game_dir / "period-1"

        make_real_test_video(seg_dir / "replay_01.mkv", duration=1.0)
        make_real_test_video(seg_dir / "replay_02.mp4", duration=1.0)

        result, messages = process_segment(
            game_dir,
            1,
            ffmpeg_path=real_ffmpeg_path,
        )
        assert result.copy is False
        assert result.output.is_file()
        assert "re-encode (mixed containers)" in " ".join(messages)

        dur = probe_duration(real_ffmpeg_path, result.output)
        assert dur is not None
        assert dur > 0

    def test_single_file_segment(
        self,
        tmp_path: Path,
        real_ffmpeg_path: Path,
        make_real_test_video: Callable[..., Path],
    ) -> None:
        """Single video in a segment still produces valid output."""
        info = GameInfo(
            date="2026-02-26",
            home_team="roseville",
            away_team="mahtomedi",
            sport="hockey",
        )
        game_dir = create_game_directory(tmp_path, info)
        seg_dir = game_dir / "period-1"

        make_real_test_video(seg_dir / "replay_01.mkv", duration=2.0)

        result, messages = process_segment(
            game_dir,
            1,
            ffmpeg_path=real_ffmpeg_path,
        )
        assert result.output.is_file()
        assert "Merge complete" in messages


# ---------------------------------------------------------------------------
# Real ffmpeg probe
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRealFfmpegProbe:
    """Probe functions against real generated video files."""

    def test_probe_duration_returns_positive(
        self,
        tmp_path: Path,
        real_ffmpeg_path: Path,
        make_real_test_video: Callable[..., Path],
    ) -> None:
        """2s video → duration approximately 2.0."""
        video = make_real_test_video(tmp_path / "test.mkv", duration=2.0)
        dur = probe_duration(real_ffmpeg_path, video)
        assert dur is not None
        assert 1.5 < dur < 3.0

    def test_probe_fps_returns_expected(
        self,
        tmp_path: Path,
        real_ffmpeg_path: Path,
        make_real_test_video: Callable[..., Path],
    ) -> None:
        """testsrc rate=30 → fps approximately 30."""
        video = make_real_test_video(tmp_path / "test.mkv", duration=1.0)
        fps = probe_fps(real_ffmpeg_path, video)
        assert fps is not None
        assert 25 < fps < 35

    def test_probe_resolution_returns_expected(
        self,
        tmp_path: Path,
        real_ffmpeg_path: Path,
        make_real_test_video: Callable[..., Path],
    ) -> None:
        """320x240 testsrc → (320, 240)."""
        video = make_real_test_video(tmp_path / "test.mkv", duration=1.0)
        res = probe_resolution(real_ffmpeg_path, video)
        assert res is not None
        assert res == (320, 240)
