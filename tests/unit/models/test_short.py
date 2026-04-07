"""Tests for short-form render configuration models."""

from __future__ import annotations

from pathlib import Path

import pytest

from reeln.models.short import (
    ANCHOR_POSITIONS,
    FORMAT_SIZES,
    CropAnchor,
    CropMode,
    OutputFormat,
    ShortConfig,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_crop_mode_pad() -> None:
    assert CropMode.PAD.value == "pad"


def test_crop_mode_crop() -> None:
    assert CropMode.CROP.value == "crop"


def test_crop_mode_smart() -> None:
    assert CropMode.SMART.value == "smart"


def test_crop_mode_smart_pad() -> None:
    assert CropMode.SMART_PAD.value == "smart_pad"


def test_crop_mode_from_string() -> None:
    assert CropMode("pad") == CropMode.PAD
    assert CropMode("crop") == CropMode.CROP
    assert CropMode("smart") == CropMode.SMART
    assert CropMode("smart_pad") == CropMode.SMART_PAD


def test_output_format_vertical() -> None:
    assert OutputFormat.VERTICAL.value == "vertical"


def test_output_format_square() -> None:
    assert OutputFormat.SQUARE.value == "square"


def test_crop_anchor_values() -> None:
    assert CropAnchor.CENTER.value == "center"
    assert CropAnchor.TOP.value == "top"
    assert CropAnchor.BOTTOM.value == "bottom"
    assert CropAnchor.LEFT.value == "left"
    assert CropAnchor.RIGHT.value == "right"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_anchor_positions_all_anchors_present() -> None:
    for anchor in CropAnchor:
        assert anchor in ANCHOR_POSITIONS


def test_anchor_positions_center() -> None:
    assert ANCHOR_POSITIONS[CropAnchor.CENTER] == (0.5, 0.5)


def test_anchor_positions_top() -> None:
    assert ANCHOR_POSITIONS[CropAnchor.TOP] == (0.5, 0.0)


def test_anchor_positions_bottom() -> None:
    assert ANCHOR_POSITIONS[CropAnchor.BOTTOM] == (0.5, 1.0)


def test_anchor_positions_left() -> None:
    assert ANCHOR_POSITIONS[CropAnchor.LEFT] == (0.0, 0.5)


def test_anchor_positions_right() -> None:
    assert ANCHOR_POSITIONS[CropAnchor.RIGHT] == (1.0, 0.5)


def test_format_sizes_vertical() -> None:
    assert FORMAT_SIZES[OutputFormat.VERTICAL] == (1080, 1920)


def test_format_sizes_square() -> None:
    assert FORMAT_SIZES[OutputFormat.SQUARE] == (1080, 1080)


def test_format_sizes_all_formats_present() -> None:
    for fmt in OutputFormat:
        assert fmt in FORMAT_SIZES


# ---------------------------------------------------------------------------
# ShortConfig
# ---------------------------------------------------------------------------


def test_short_config_defaults(tmp_path: Path) -> None:
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4")
    assert cfg.width == 1080
    assert cfg.height == 1920
    assert cfg.crop_mode == CropMode.PAD
    assert cfg.anchor_x == 0.5
    assert cfg.anchor_y == 0.5
    assert cfg.scale == 1.0
    assert cfg.smart is False
    assert cfg.pad_color == "black"
    assert cfg.speed == 1.0
    assert cfg.lut is None
    assert cfg.subtitle is None
    assert cfg.codec == "libx264"
    assert cfg.preset == "medium"
    assert cfg.crf == 18
    assert cfg.audio_codec == "aac"
    assert cfg.audio_bitrate == "128k"
    assert cfg.smart_zoom_frames == 5


def test_short_config_custom_values(tmp_path: Path) -> None:
    lut = tmp_path / "grade.cube"
    sub = tmp_path / "subs.ass"
    cfg = ShortConfig(
        input=tmp_path / "clip.mkv",
        output=tmp_path / "out.mp4",
        width=1080,
        height=1080,
        crop_mode=CropMode.CROP,
        anchor_x=0.3,
        anchor_y=0.7,
        pad_color="white",
        speed=0.5,
        lut=lut,
        subtitle=sub,
        codec="libx265",
        preset="fast",
        crf=22,
        audio_codec="opus",
        audio_bitrate="192k",
    )
    assert cfg.width == 1080
    assert cfg.height == 1080
    assert cfg.crop_mode == CropMode.CROP
    assert cfg.anchor_x == 0.3
    assert cfg.speed == 0.5
    assert cfg.lut == lut
    assert cfg.subtitle == sub
    assert cfg.codec == "libx265"


def test_short_config_scale_custom(tmp_path: Path) -> None:
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4", scale=1.5)
    assert cfg.scale == 1.5


def test_short_config_smart_custom(tmp_path: Path) -> None:
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4", smart=True)
    assert cfg.smart is True


def test_short_config_smart_zoom_frames_custom(tmp_path: Path) -> None:
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4", smart_zoom_frames=10)
    assert cfg.smart_zoom_frames == 10


def test_short_config_branding_default_none(tmp_path: Path) -> None:
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4")
    assert cfg.branding is None


def test_short_config_branding_custom(tmp_path: Path) -> None:
    brand = tmp_path / "brand.ass"
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4", branding=brand)
    assert cfg.branding == brand


def test_short_config_logo_default_none(tmp_path: Path) -> None:
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4")
    assert cfg.logo is None


def test_short_config_logo_custom(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4", logo=logo)
    assert cfg.logo == logo


def test_short_config_is_frozen(tmp_path: Path) -> None:
    cfg = ShortConfig(input=tmp_path / "clip.mkv", output=tmp_path / "out.mp4")
    with pytest.raises(AttributeError):
        cfg.width = 720  # type: ignore[misc]
