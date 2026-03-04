"""Tests for RenderPlan, RenderResult, SegmentResult, HighlightsResult, IterationResult, and PruneResult data models."""

from __future__ import annotations

from pathlib import Path

from reeln.models.render_plan import (
    CompilationResult,
    HighlightsResult,
    IterationResult,
    PruneResult,
    RenderPlan,
    RenderResult,
    SegmentResult,
)


def test_render_plan_defaults(tmp_path: Path) -> None:
    plan = RenderPlan(inputs=[tmp_path / "a.mkv"], output=tmp_path / "out.mp4")
    assert plan.codec == "libx264"
    assert plan.preset == "medium"
    assert plan.crf == 18
    assert plan.width is None
    assert plan.height is None
    assert plan.fps is None
    assert plan.audio_codec == "aac"
    assert plan.audio_bitrate == "128k"
    assert plan.filter_complex is None
    assert plan.audio_filter is None
    assert plan.extra_args == []


def test_render_plan_custom_values(tmp_path: Path) -> None:
    plan = RenderPlan(
        inputs=[tmp_path / "a.mkv", tmp_path / "b.mkv"],
        output=tmp_path / "out.mp4",
        codec="libx265",
        preset="fast",
        crf=22,
        width=1080,
        height=1920,
        fps="30",
        audio_codec="opus",
        audio_bitrate="192k",
        extra_args=["-movflags", "+faststart"],
    )
    assert plan.codec == "libx265"
    assert plan.width == 1080
    assert plan.height == 1920
    assert plan.fps == "30"
    assert len(plan.inputs) == 2
    assert plan.extra_args == ["-movflags", "+faststart"]


def test_render_plan_with_filter_complex(tmp_path: Path) -> None:
    plan = RenderPlan(
        inputs=[tmp_path / "a.mkv"],
        output=tmp_path / "out.mp4",
        filter_complex="scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        audio_filter="atempo=0.5",
    )
    assert plan.filter_complex is not None
    assert "scale=1080:-2" in plan.filter_complex
    assert plan.audio_filter == "atempo=0.5"


def test_render_plan_is_frozen(tmp_path: Path) -> None:
    plan = RenderPlan(inputs=[tmp_path / "a.mkv"], output=tmp_path / "out.mp4")
    import dataclasses

    assert dataclasses.fields(plan)  # is a dataclass
    # Frozen means assignment raises
    with __import__("pytest").raises(AttributeError):
        plan.crf = 99  # type: ignore[misc]


def test_render_plan_filter_fields_frozen(tmp_path: Path) -> None:
    plan = RenderPlan(
        inputs=[tmp_path / "a.mkv"],
        output=tmp_path / "out.mp4",
        filter_complex="some_filter",
    )
    with __import__("pytest").raises(AttributeError):
        plan.filter_complex = "other"  # type: ignore[misc]


def test_render_result_defaults(tmp_path: Path) -> None:
    result = RenderResult(output=tmp_path / "out.mp4")
    assert result.duration_seconds is None
    assert result.file_size_bytes is None
    assert result.ffmpeg_command == []


def test_render_result_with_metadata(tmp_path: Path) -> None:
    result = RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=123.45,
        file_size_bytes=1024000,
    )
    assert result.duration_seconds == 123.45
    assert result.file_size_bytes == 1024000


def test_render_result_ffmpeg_command(tmp_path: Path) -> None:
    cmd = ["ffmpeg", "-i", "in.mkv", "out.mp4"]
    result = RenderResult(output=tmp_path / "out.mp4", ffmpeg_command=cmd)
    assert result.ffmpeg_command == cmd


def test_render_result_is_frozen(tmp_path: Path) -> None:
    result = RenderResult(output=tmp_path / "out.mp4")
    import pytest as pt

    with pt.raises(AttributeError):
        result.output = Path("/other")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SegmentResult
# ---------------------------------------------------------------------------


def test_segment_result_fields(tmp_path: Path) -> None:
    result = SegmentResult(
        segment_number=1,
        segment_dir=tmp_path / "period-1",
        input_files=[tmp_path / "a.mkv", tmp_path / "b.mkv"],
        output=tmp_path / "period-1_2026-02-26.mkv",
        copy=True,
    )
    assert result.segment_number == 1
    assert result.segment_dir == tmp_path / "period-1"
    assert len(result.input_files) == 2
    assert result.copy is True
    assert result.events_created == 0
    assert result.ffmpeg_command == []


def test_segment_result_with_events_created(tmp_path: Path) -> None:
    result = SegmentResult(
        segment_number=1,
        segment_dir=tmp_path / "period-1",
        input_files=[tmp_path / "a.mkv"],
        output=tmp_path / "out.mkv",
        copy=True,
        events_created=3,
    )
    assert result.events_created == 3


def test_segment_result_ffmpeg_command(tmp_path: Path) -> None:
    cmd = ["ffmpeg", "-f", "concat", "-i", "list.txt", "out.mkv"]
    result = SegmentResult(
        segment_number=1,
        segment_dir=tmp_path / "period-1",
        input_files=[],
        output=tmp_path / "out.mkv",
        copy=True,
        ffmpeg_command=cmd,
    )
    assert result.ffmpeg_command == cmd


def test_segment_result_is_frozen(tmp_path: Path) -> None:
    result = SegmentResult(
        segment_number=1,
        segment_dir=tmp_path / "period-1",
        input_files=[],
        output=tmp_path / "out.mkv",
        copy=True,
    )
    import pytest as pt

    with pt.raises(AttributeError):
        result.copy = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HighlightsResult
# ---------------------------------------------------------------------------


def test_highlights_result_fields(tmp_path: Path) -> None:
    result = HighlightsResult(
        output=tmp_path / "game.mkv",
        segment_files=[tmp_path / "s1.mkv", tmp_path / "s2.mkv"],
        copy=False,
    )
    assert result.output == tmp_path / "game.mkv"
    assert len(result.segment_files) == 2
    assert result.copy is False
    assert result.ffmpeg_command == []


def test_highlights_result_ffmpeg_command(tmp_path: Path) -> None:
    cmd = ["ffmpeg", "-f", "concat", "-i", "list.txt", "game.mkv"]
    result = HighlightsResult(
        output=tmp_path / "game.mkv",
        segment_files=[],
        copy=True,
        ffmpeg_command=cmd,
    )
    assert result.ffmpeg_command == cmd


def test_highlights_result_is_frozen(tmp_path: Path) -> None:
    result = HighlightsResult(
        output=tmp_path / "game.mkv",
        segment_files=[],
        copy=True,
    )
    import pytest as pt

    with pt.raises(AttributeError):
        result.copy = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CompilationResult
# ---------------------------------------------------------------------------


def test_compilation_result_fields(tmp_path: Path) -> None:
    result = CompilationResult(
        output=tmp_path / "goals.mkv",
        event_ids=["abc123", "def456"],
        input_files=[tmp_path / "a.mkv", tmp_path / "b.mkv"],
        copy=True,
    )
    assert result.output == tmp_path / "goals.mkv"
    assert result.event_ids == ["abc123", "def456"]
    assert len(result.input_files) == 2
    assert result.copy is True
    assert result.ffmpeg_command == []


def test_compilation_result_ffmpeg_command(tmp_path: Path) -> None:
    cmd = ["ffmpeg", "-f", "concat", "-i", "list.txt", "goals.mkv"]
    result = CompilationResult(
        output=tmp_path / "goals.mkv",
        event_ids=["abc123"],
        input_files=[tmp_path / "a.mkv"],
        copy=True,
        ffmpeg_command=cmd,
    )
    assert result.ffmpeg_command == cmd


def test_compilation_result_is_frozen(tmp_path: Path) -> None:
    result = CompilationResult(
        output=tmp_path / "out.mkv",
        event_ids=[],
        input_files=[],
        copy=True,
    )
    import pytest as pt

    with pt.raises(AttributeError):
        result.copy = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IterationResult
# ---------------------------------------------------------------------------


def test_iteration_result_fields(tmp_path: Path) -> None:
    result = IterationResult(
        output=tmp_path / "final.mp4",
        iteration_outputs=[tmp_path / "iter1.mp4", tmp_path / "iter2.mp4"],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    assert result.output == tmp_path / "final.mp4"
    assert len(result.iteration_outputs) == 2
    assert result.profile_names == ["fullspeed", "slowmo"]
    assert result.concat_copy is True


def test_iteration_result_is_frozen(tmp_path: Path) -> None:
    result = IterationResult(
        output=tmp_path / "final.mp4",
        iteration_outputs=[],
        profile_names=[],
        concat_copy=True,
    )
    import pytest as pt

    with pt.raises(AttributeError):
        result.concat_copy = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PruneResult
# ---------------------------------------------------------------------------


def test_prune_result_defaults() -> None:
    result = PruneResult()
    assert result.removed_paths == []
    assert result.bytes_freed == 0
    assert result.errors == []


def test_prune_result_accumulation(tmp_path: Path) -> None:
    result = PruneResult()
    result.removed_paths.append(tmp_path / "a.mkv")
    result.removed_paths.append(tmp_path / "b.mkv")
    result.bytes_freed += 1024
    result.errors.append("permission denied: c.mkv")
    assert len(result.removed_paths) == 2
    assert result.bytes_freed == 1024
    assert len(result.errors) == 1


def test_prune_result_is_mutable(tmp_path: Path) -> None:
    result = PruneResult()
    result.bytes_freed = 999
    assert result.bytes_freed == 999
