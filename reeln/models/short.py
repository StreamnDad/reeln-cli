"""Short-form render configuration: crop modes, output formats, anchors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CropMode(Enum):
    """How to handle aspect ratio mismatch."""

    PAD = "pad"
    CROP = "crop"


class OutputFormat(Enum):
    """Named output format presets."""

    VERTICAL = "vertical"
    SQUARE = "square"


class CropAnchor(Enum):
    """Named crop anchor positions."""

    CENTER = "center"
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


ANCHOR_POSITIONS: dict[CropAnchor, tuple[float, float]] = {
    CropAnchor.CENTER: (0.5, 0.5),
    CropAnchor.TOP: (0.5, 0.0),
    CropAnchor.BOTTOM: (0.5, 1.0),
    CropAnchor.LEFT: (0.0, 0.5),
    CropAnchor.RIGHT: (1.0, 0.5),
}

FORMAT_SIZES: dict[OutputFormat, tuple[int, int]] = {
    OutputFormat.VERTICAL: (1080, 1920),
    OutputFormat.SQUARE: (1080, 1080),
}


@dataclass(frozen=True)
class ShortConfig:
    """Configuration for rendering a short-form video."""

    input: Path
    output: Path
    width: int = 1080
    height: int = 1920
    crop_mode: CropMode = CropMode.PAD
    anchor_x: float = 0.5
    anchor_y: float = 0.5
    pad_color: str = "black"
    speed: float = 1.0
    lut: Path | None = None
    subtitle: Path | None = None
    # Encoding (flows from VideoConfig)
    codec: str = "libx264"
    preset: str = "medium"
    crf: int = 18
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"
