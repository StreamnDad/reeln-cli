"""Debug output for smart zoom: write extracted frames and zoom path data."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from reeln.core.log import get_logger
from reeln.core.zoom import build_piecewise_lerp, build_smart_crop_filter
from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint

log: logging.Logger = get_logger(__name__)


def _build_annotate_command(
    ffmpeg_path: Path,
    frame_path: Path,
    output_path: Path,
    point: ZoomPoint,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
) -> list[str]:
    """Build an ffmpeg command to draw crosshairs and crop box on a frame.

    Draws:
    - A red crosshair at the detected center point
    - A green rectangle showing the crop region
    """
    cx = int(point.center_x * source_width)
    cy = int(point.center_y * source_height)

    # Crop box dimensions (same ratio as the smart crop filter)
    crop_w = int(source_height * target_width / target_height)
    crop_h = source_height

    # Crop box position (clamped to source bounds)
    box_x = max(0, min(source_width - crop_w, int(point.center_x * (source_width - crop_w))))
    box_y = max(0, min(source_height - crop_h, int(point.center_y * (source_height - crop_h))))

    # Crosshair lines (horizontal + vertical through center, 2px thick)
    cross_len = 40
    filters = [
        # Crop box (green)
        f"drawbox=x={box_x}:y={box_y}:w={crop_w}:h={crop_h}:color=green@0.6:t=3",
        # Horizontal crosshair
        f"drawbox=x={max(0, cx - cross_len)}:y={max(0, cy - 1)}:w={cross_len * 2}:h=2:color=red:t=fill",
        # Vertical crosshair
        f"drawbox=x={max(0, cx - 1)}:y={max(0, cy - cross_len)}:w=2:h={cross_len * 2}:color=red:t=fill",
    ]

    return [
        str(ffmpeg_path),
        "-y",
        "-v",
        "error",
        "-i",
        str(frame_path),
        "-vf",
        ",".join(filters),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(output_path),
    ]


def _annotate_frames(
    ffmpeg_path: Path,
    extracted: ExtractedFrames,
    zoom_path: ZoomPath,
    target_width: int,
    target_height: int,
    output_dir: Path,
) -> list[Path]:
    """Render annotated copies of extracted frames with crosshairs and crop boxes.

    Returns paths to the annotated frame files. Frames without a matching
    zoom point are skipped. Failures are logged and skipped.
    """
    annotated: list[Path] = []
    point_by_ts = {p.timestamp: p for p in zoom_path.points}

    for i, (frame_path, ts) in enumerate(zip(extracted.frame_paths, extracted.timestamps, strict=True)):
        point = point_by_ts.get(ts)
        if point is None or not frame_path.is_file():
            continue

        out_path = output_dir / f"annotated_{i:04d}.png"
        cmd = _build_annotate_command(
            ffmpeg_path,
            frame_path,
            out_path,
            point,
            extracted.source_width,
            extracted.source_height,
            target_width,
            target_height,
        )
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
            annotated.append(out_path)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            log.debug("Failed to annotate frame %d, skipping", i, exc_info=True)

    return annotated


def write_zoom_debug(
    game_dir: Path,
    extracted: ExtractedFrames,
    zoom_path: ZoomPath | None,
    target_width: int,
    target_height: int,
    *,
    ffmpeg_path: Path | None = None,
    plugin_debug: dict[str, object] | None = None,
) -> Path:
    """Write zoom debug artifacts to ``game_dir/debug/zoom/``.

    Creates:
    - ``frame_NNNN.png`` — copies of extracted frame files
    - ``annotated_NNNN.png`` — frames with crosshair and crop box overlay
    - ``zoom_path.json`` — full zoom path data + generated ffmpeg expressions
    - ``plugin_debug.json`` — plugin-provided debug data (prompts, model, etc.)

    When *ffmpeg_path* is provided and a zoom path exists, annotated frames
    with crosshairs and crop boxes are generated.

    Returns the debug directory path.
    """
    debug_dir = game_dir / "debug" / "zoom"
    debug_dir.mkdir(parents=True, exist_ok=True)

    # Copy extracted frames into debug dir (not symlink — the temp
    # extraction directory is cleaned up after rendering).
    for i, frame_path in enumerate(extracted.frame_paths):
        dest = debug_dir / f"frame_{i:04d}.png"
        dest.unlink(missing_ok=True)
        if frame_path.is_file():
            shutil.copy2(frame_path, dest)

    # Generate annotated frames with crosshairs + crop box
    if zoom_path is not None and ffmpeg_path is not None:
        annotated = _annotate_frames(ffmpeg_path, extracted, zoom_path, target_width, target_height, debug_dir)
        if annotated:
            log.debug("Wrote %d annotated frames to %s", len(annotated), debug_dir)

    # Write zoom path JSON
    data: dict[str, object] = {
        "source_width": extracted.source_width,
        "source_height": extracted.source_height,
        "duration": extracted.duration,
        "fps": extracted.fps,
        "frame_count": len(extracted.frame_paths),
        "timestamps": list(extracted.timestamps),
        "target_width": target_width,
        "target_height": target_height,
    }

    if zoom_path is not None:
        points_data = [
            {
                "timestamp": p.timestamp,
                "center_x": p.center_x,
                "center_y": p.center_y,
                "confidence": p.confidence,
            }
            for p in zoom_path.points
        ]
        data["zoom_path"] = {
            "points": points_data,
            "point_count": len(zoom_path.points),
        }

        # Include generated ffmpeg expressions for inspection
        x_values = [(p.timestamp, p.center_x) for p in zoom_path.points]
        y_values = [(p.timestamp, p.center_y) for p in zoom_path.points]
        data["ffmpeg_expressions"] = {
            "x_lerp": build_piecewise_lerp(x_values, zoom_path.duration),
            "y_lerp": build_piecewise_lerp(y_values, zoom_path.duration),
            "crop_filter": build_smart_crop_filter(zoom_path, target_width, target_height),
        }
    else:
        data["zoom_path"] = None
        data["ffmpeg_expressions"] = None

    zoom_json = debug_dir / "zoom_path.json"
    zoom_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Write plugin debug data (prompts, model info, etc.)
    if plugin_debug:
        plugin_json = debug_dir / "plugin_debug.json"
        plugin_json.write_text(json.dumps(plugin_debug, indent=2, default=str), encoding="utf-8")

    return debug_dir
