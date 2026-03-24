"""Tests for smart target zoom data models."""

from __future__ import annotations

from pathlib import Path

import pytest

from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint

# ---------------------------------------------------------------------------
# ZoomPoint
# ---------------------------------------------------------------------------


def test_zoom_point_defaults() -> None:
    p = ZoomPoint(timestamp=1.0, center_x=0.5, center_y=0.5)
    assert p.timestamp == 1.0
    assert p.center_x == 0.5
    assert p.center_y == 0.5
    assert p.confidence == 1.0


def test_zoom_point_custom_confidence() -> None:
    p = ZoomPoint(timestamp=2.5, center_x=0.3, center_y=0.7, confidence=0.85)
    assert p.confidence == 0.85


def test_zoom_point_is_frozen() -> None:
    p = ZoomPoint(timestamp=1.0, center_x=0.5, center_y=0.5)
    with pytest.raises(AttributeError):
        p.center_x = 0.6  # type: ignore[misc]


def test_zoom_point_boundary_values() -> None:
    p = ZoomPoint(timestamp=0.0, center_x=0.0, center_y=0.0, confidence=0.0)
    assert p.timestamp == 0.0
    assert p.center_x == 0.0
    assert p.center_y == 0.0
    assert p.confidence == 0.0


def test_zoom_point_max_boundary() -> None:
    p = ZoomPoint(timestamp=300.0, center_x=1.0, center_y=1.0, confidence=1.0)
    assert p.center_x == 1.0
    assert p.center_y == 1.0


# ---------------------------------------------------------------------------
# ZoomPath
# ---------------------------------------------------------------------------


def test_zoom_path_single_point() -> None:
    pt = ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5)
    path = ZoomPath(points=(pt,), source_width=1920, source_height=1080, duration=10.0)
    assert len(path.points) == 1
    assert path.source_width == 1920
    assert path.source_height == 1080
    assert path.duration == 10.0


def test_zoom_path_multiple_points() -> None:
    pts = (
        ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
        ZoomPoint(timestamp=5.0, center_x=0.7, center_y=0.5),
        ZoomPoint(timestamp=10.0, center_x=0.5, center_y=0.5),
    )
    path = ZoomPath(points=pts, source_width=1920, source_height=1080, duration=10.0)
    assert len(path.points) == 3
    assert path.points[0].center_x == 0.3
    assert path.points[2].center_x == 0.5


def test_zoom_path_is_frozen() -> None:
    pt = ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5)
    path = ZoomPath(points=(pt,), source_width=1920, source_height=1080, duration=10.0)
    with pytest.raises(AttributeError):
        path.duration = 20.0  # type: ignore[misc]


def test_zoom_path_empty_points() -> None:
    path = ZoomPath(points=(), source_width=1920, source_height=1080, duration=10.0)
    assert len(path.points) == 0


# ---------------------------------------------------------------------------
# ExtractedFrames
# ---------------------------------------------------------------------------


def test_extracted_frames_basic(tmp_path: Path) -> None:
    frames = (tmp_path / "frame_0.png", tmp_path / "frame_1.png")
    timestamps = (0.0, 5.0)
    ef = ExtractedFrames(
        frame_paths=frames,
        timestamps=timestamps,
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=59.94,
    )
    assert len(ef.frame_paths) == 2
    assert len(ef.timestamps) == 2
    assert ef.source_width == 1920
    assert ef.source_height == 1080
    assert ef.duration == 10.0
    assert ef.fps == 59.94


def test_extracted_frames_is_frozen(tmp_path: Path) -> None:
    ef = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(0.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=30.0,
    )
    with pytest.raises(AttributeError):
        ef.fps = 60.0  # type: ignore[misc]


def test_extracted_frames_single_frame(tmp_path: Path) -> None:
    ef = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=3840,
        source_height=2160,
        duration=30.0,
        fps=60.0,
    )
    assert len(ef.frame_paths) == 1
    assert ef.timestamps[0] == 5.0
