"""Tests for zoom debug output writer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from reeln.core.zoom_debug import (
    _annotate_frames,
    _build_annotate_command,
    write_zoom_debug,
)
from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint


def _make_frames(tmp_path: Path, count: int = 2) -> ExtractedFrames:
    """Create ExtractedFrames with actual files on disk."""
    frames_dir = tmp_path / "extracted"
    frames_dir.mkdir()
    paths: list[Path] = []
    timestamps: list[float] = []
    for i in range(count):
        p = frames_dir / f"frame_{i:04d}.png"
        p.write_bytes(b"fake png data")
        paths.append(p)
        timestamps.append(float(i) * 5.0)
    return ExtractedFrames(
        frame_paths=tuple(paths),
        timestamps=tuple(timestamps),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )


def _make_zoom_path() -> ZoomPath:
    return ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=5.0, center_x=0.7, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.5, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )


# ---------------------------------------------------------------------------
# write_zoom_debug
# ---------------------------------------------------------------------------


def test_write_zoom_debug_creates_directory(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path)

    result = write_zoom_debug(game_dir, frames, None, 1080, 1920)

    assert result == game_dir / "debug" / "zoom"
    assert result.is_dir()


def test_write_zoom_debug_copies_frames(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path, count=3)

    debug_dir = write_zoom_debug(game_dir, frames, None, 1080, 1920)

    for i in range(3):
        dest = debug_dir / f"frame_{i:04d}.png"
        assert dest.is_file()
        assert not dest.is_symlink()
        assert dest.read_bytes() == frames.frame_paths[i].read_bytes()


def test_write_zoom_debug_writes_json_without_zoom_path(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path)

    debug_dir = write_zoom_debug(game_dir, frames, None, 1080, 1920)

    json_path = debug_dir / "zoom_path.json"
    assert json_path.is_file()
    data = json.loads(json_path.read_text())
    assert data["source_width"] == 1920
    assert data["source_height"] == 1080
    assert data["duration"] == 10.0
    assert data["fps"] == 60.0
    assert data["frame_count"] == 2
    assert data["target_width"] == 1080
    assert data["target_height"] == 1920
    assert data["zoom_path"] is None
    assert data["ffmpeg_expressions"] is None


def test_write_zoom_debug_writes_json_with_zoom_path(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path)
    zoom_path = _make_zoom_path()

    debug_dir = write_zoom_debug(game_dir, frames, zoom_path, 1080, 1920)

    json_path = debug_dir / "zoom_path.json"
    data = json.loads(json_path.read_text())
    assert data["zoom_path"] is not None
    assert data["zoom_path"]["point_count"] == 3
    assert len(data["zoom_path"]["points"]) == 3
    assert data["zoom_path"]["points"][0]["center_x"] == 0.3
    assert data["zoom_path"]["points"][1]["center_x"] == 0.7
    assert data["ffmpeg_expressions"] is not None
    assert "x_lerp" in data["ffmpeg_expressions"]
    assert "y_lerp" in data["ffmpeg_expressions"]
    assert "crop_filter" in data["ffmpeg_expressions"]
    assert "crop=w=" in data["ffmpeg_expressions"]["crop_filter"]


def test_write_zoom_debug_idempotent(tmp_path: Path) -> None:
    """Calling twice overwrites without error."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path)
    zoom_path = _make_zoom_path()

    write_zoom_debug(game_dir, frames, zoom_path, 1080, 1920)
    debug_dir = write_zoom_debug(game_dir, frames, zoom_path, 1080, 1920)

    assert (debug_dir / "zoom_path.json").is_file()


def test_write_zoom_debug_missing_frame_file(tmp_path: Path) -> None:
    """Missing frame files are skipped (no copy created)."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = ExtractedFrames(
        frame_paths=(tmp_path / "nonexistent.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=30.0,
    )

    debug_dir = write_zoom_debug(game_dir, frames, None, 1080, 1920)

    link = debug_dir / "frame_0000.png"
    assert not link.exists()


def test_write_zoom_debug_zoom_path_confidence(tmp_path: Path) -> None:
    """Confidence values are included in the JSON output."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path, count=1)
    zoom_path = ZoomPath(
        points=(ZoomPoint(timestamp=5.0, center_x=0.5, center_y=0.5, confidence=0.85),),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    debug_dir = write_zoom_debug(game_dir, frames, zoom_path, 1080, 1920)

    data = json.loads((debug_dir / "zoom_path.json").read_text())
    assert data["zoom_path"]["points"][0]["confidence"] == 0.85


# ---------------------------------------------------------------------------
# _build_annotate_command
# ---------------------------------------------------------------------------


def test_build_annotate_command_structure(tmp_path: Path) -> None:
    """Command contains drawbox filters for crosshair and crop box."""
    frame = tmp_path / "frame.png"
    out = tmp_path / "annotated.png"
    point = ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5)
    cmd = _build_annotate_command(Path("/usr/bin/ffmpeg"), frame, out, point, 1920, 1080, 1080, 1920)
    assert cmd[0] == "/usr/bin/ffmpeg"
    assert "-vf" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "drawbox" in vf
    assert "green" in vf
    assert "red" in vf


def test_build_annotate_command_clamps_crop_box(tmp_path: Path) -> None:
    """Crop box position is clamped to source bounds."""
    point = ZoomPoint(timestamp=0.0, center_x=1.0, center_y=1.0)
    cmd = _build_annotate_command(
        Path("/usr/bin/ffmpeg"),
        tmp_path / "f.png",
        tmp_path / "o.png",
        point,
        1920,
        1080,
        1080,
        1920,
    )
    vf = cmd[cmd.index("-vf") + 1]
    # Box x should be clamped, not go negative or beyond bounds
    assert "drawbox" in vf


def test_build_annotate_command_zero_center(tmp_path: Path) -> None:
    """Center at 0,0 still produces valid crosshair coordinates."""
    point = ZoomPoint(timestamp=0.0, center_x=0.0, center_y=0.0)
    cmd = _build_annotate_command(
        Path("/usr/bin/ffmpeg"),
        tmp_path / "f.png",
        tmp_path / "o.png",
        point,
        1920,
        1080,
        1080,
        1920,
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "drawbox" in vf


# ---------------------------------------------------------------------------
# _annotate_frames
# ---------------------------------------------------------------------------


def test_annotate_frames_success(tmp_path: Path) -> None:
    """Annotated frames are created when ffmpeg succeeds."""
    frames = _make_frames(tmp_path, count=2)
    zoom_path = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=5.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch("reeln.core.zoom_debug.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        result = _annotate_frames(Path("/usr/bin/ffmpeg"), frames, zoom_path, 1080, 1920, out_dir)

    assert mock_run.call_count == 2
    assert len(result) == 2
    assert all("annotated_" in p.name for p in result)


def test_annotate_frames_skips_missing_point(tmp_path: Path) -> None:
    """Frames without a matching zoom point are skipped."""
    frames = _make_frames(tmp_path, count=2)
    # Only one point at timestamp 0.0, no point at 5.0
    zoom_path = ZoomPath(
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch("reeln.core.zoom_debug.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        result = _annotate_frames(Path("/usr/bin/ffmpeg"), frames, zoom_path, 1080, 1920, out_dir)

    assert mock_run.call_count == 1
    assert len(result) == 1


def test_annotate_frames_skips_missing_file(tmp_path: Path) -> None:
    """Frames where the file doesn't exist are skipped."""
    frames = ExtractedFrames(
        frame_paths=(tmp_path / "nonexistent.png",),
        timestamps=(0.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=30.0,
    )
    zoom_path = ZoomPath(
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch("reeln.core.zoom_debug.subprocess.run") as mock_run:
        result = _annotate_frames(Path("/usr/bin/ffmpeg"), frames, zoom_path, 1080, 1920, out_dir)

    mock_run.assert_not_called()
    assert result == []


def test_annotate_frames_handles_ffmpeg_error(tmp_path: Path) -> None:
    """ffmpeg failure is logged and skipped, not raised."""
    import subprocess as sp

    frames = _make_frames(tmp_path, count=1)
    zoom_path = ZoomPath(
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "reeln.core.zoom_debug.subprocess.run",
        side_effect=sp.CalledProcessError(1, "ffmpeg"),
    ):
        result = _annotate_frames(Path("/usr/bin/ffmpeg"), frames, zoom_path, 1080, 1920, out_dir)

    assert result == []


def test_annotate_frames_handles_timeout(tmp_path: Path) -> None:
    """Timeout is caught and skipped."""
    import subprocess as sp

    frames = _make_frames(tmp_path, count=1)
    zoom_path = ZoomPath(
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "reeln.core.zoom_debug.subprocess.run",
        side_effect=sp.TimeoutExpired("ffmpeg", 30),
    ):
        result = _annotate_frames(Path("/usr/bin/ffmpeg"), frames, zoom_path, 1080, 1920, out_dir)

    assert result == []


def test_annotate_frames_handles_os_error(tmp_path: Path) -> None:
    """OSError (e.g. ffmpeg not found) is caught and skipped."""
    frames = _make_frames(tmp_path, count=1)
    zoom_path = ZoomPath(
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch("reeln.core.zoom_debug.subprocess.run", side_effect=OSError("nope")):
        result = _annotate_frames(Path("/usr/bin/ffmpeg"), frames, zoom_path, 1080, 1920, out_dir)

    assert result == []


# ---------------------------------------------------------------------------
# write_zoom_debug with annotations
# ---------------------------------------------------------------------------


def test_write_zoom_debug_with_ffmpeg_path_generates_annotated(tmp_path: Path) -> None:
    """When ffmpeg_path is provided with a zoom path, annotated frames are generated."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path, count=2)
    zoom_path = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=5.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    with patch("reeln.core.zoom_debug.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        write_zoom_debug(game_dir, frames, zoom_path, 1080, 1920, ffmpeg_path=Path("/usr/bin/ffmpeg"))

    assert mock_run.call_count == 2


def test_write_zoom_debug_annotate_all_fail(tmp_path: Path) -> None:
    """When all annotate commands fail, no 'Wrote N annotated frames' log but no crash."""
    import subprocess as sp

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path, count=2)
    zoom_path = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=5.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    with patch(
        "reeln.core.zoom_debug.subprocess.run",
        side_effect=sp.CalledProcessError(1, "ffmpeg"),
    ):
        debug_dir = write_zoom_debug(game_dir, frames, zoom_path, 1080, 1920, ffmpeg_path=Path("/usr/bin/ffmpeg"))

    # Should still create the directory and zoom_path.json
    assert debug_dir.is_dir()
    assert (debug_dir / "zoom_path.json").is_file()


def test_write_zoom_debug_without_ffmpeg_skips_annotations(tmp_path: Path) -> None:
    """Without ffmpeg_path, no annotated frames are generated."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path, count=2)
    zoom_path = _make_zoom_path()

    with patch("reeln.core.zoom_debug.subprocess.run") as mock_run:
        write_zoom_debug(game_dir, frames, zoom_path, 1080, 1920)

    mock_run.assert_not_called()


def test_write_zoom_debug_without_zoom_path_skips_annotations(tmp_path: Path) -> None:
    """Without zoom_path, no annotated frames are generated even with ffmpeg_path."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path)

    with patch("reeln.core.zoom_debug.subprocess.run") as mock_run:
        write_zoom_debug(game_dir, frames, None, 1080, 1920, ffmpeg_path=Path("/usr/bin/ffmpeg"))

    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# write_zoom_debug with plugin_debug
# ---------------------------------------------------------------------------


def test_write_zoom_debug_plugin_debug(tmp_path: Path) -> None:
    """Plugin debug data is written as plugin_debug.json."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path, count=1)

    debug_data = {"prompt": "analyze this frame", "model": "gpt-4o", "tokens": 150}
    debug_dir = write_zoom_debug(game_dir, frames, None, 1080, 1920, plugin_debug=debug_data)

    plugin_json = debug_dir / "plugin_debug.json"
    assert plugin_json.is_file()
    data = json.loads(plugin_json.read_text())
    assert data["prompt"] == "analyze this frame"
    assert data["model"] == "gpt-4o"
    assert data["tokens"] == 150


def test_write_zoom_debug_no_plugin_debug(tmp_path: Path) -> None:
    """Without plugin_debug, no plugin_debug.json is written."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path, count=1)

    debug_dir = write_zoom_debug(game_dir, frames, None, 1080, 1920)

    assert not (debug_dir / "plugin_debug.json").exists()


def test_write_zoom_debug_plugin_debug_empty_dict(tmp_path: Path) -> None:
    """Empty plugin_debug dict is not written."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    frames = _make_frames(tmp_path, count=1)

    debug_dir = write_zoom_debug(game_dir, frames, None, 1080, 1920, plugin_debug={})

    assert not (debug_dir / "plugin_debug.json").exists()
