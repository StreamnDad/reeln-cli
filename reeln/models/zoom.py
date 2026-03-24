"""Data models for smart target zoom."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ZoomPoint:
    """A single detected target position at a given timestamp.

    Coordinates are normalized to 0.0-1.0 relative to source dimensions.
    """

    timestamp: float
    center_x: float
    center_y: float
    confidence: float = 1.0


@dataclass(frozen=True)
class ZoomPath:
    """An ordered sequence of zoom points describing a camera pan path."""

    points: tuple[ZoomPoint, ...]
    source_width: int
    source_height: int
    duration: float


@dataclass(frozen=True)
class ExtractedFrames:
    """Result of extracting frames from a video for analysis."""

    frame_paths: tuple[Path, ...]
    timestamps: tuple[float, ...]
    source_width: int
    source_height: int
    duration: float
    fps: float
