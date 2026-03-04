"""Tests for short-form filter builders, validation, and plan assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from reeln.core.errors import RenderError
from reeln.core.shorts import (
    build_audio_speed_filter,
    build_crop_filter,
    build_filter_chain,
    build_final_scale_filter,
    build_lut_filter,
    build_pad_filter,
    build_scale_filter,
    build_speed_filter,
    build_subtitle_filter,
    plan_preview,
    plan_short,
    validate_short_config,
)
from reeln.models.short import CropMode, ShortConfig


def _cfg(tmp_path: Path, **kwargs: object) -> ShortConfig:
    """Helper to create a ShortConfig with test defaults."""
    defaults: dict[str, object] = {
        "input": tmp_path / "clip.mkv",
        "output": tmp_path / "out.mp4",
    }
    defaults.update(kwargs)
    return ShortConfig(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_short_config
# ---------------------------------------------------------------------------


def test_validate_valid_config(tmp_path: Path) -> None:
    validate_short_config(_cfg(tmp_path))


def test_validate_width_negative(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="Width must be positive"):
        validate_short_config(_cfg(tmp_path, width=-1))


def test_validate_width_zero(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="Width must be positive"):
        validate_short_config(_cfg(tmp_path, width=0))


def test_validate_width_odd(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="Width must be even"):
        validate_short_config(_cfg(tmp_path, width=1081))


def test_validate_height_negative(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="Height must be positive"):
        validate_short_config(_cfg(tmp_path, height=-2))


def test_validate_height_zero(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="Height must be positive"):
        validate_short_config(_cfg(tmp_path, height=0))


def test_validate_height_odd(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="Height must be even"):
        validate_short_config(_cfg(tmp_path, height=1921))


def test_validate_speed_too_low(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Speed must be 0\.5-2\.0"):
        validate_short_config(_cfg(tmp_path, speed=0.4))


def test_validate_speed_too_high(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Speed must be 0\.5-2\.0"):
        validate_short_config(_cfg(tmp_path, speed=2.1))


def test_validate_speed_at_bounds(tmp_path: Path) -> None:
    validate_short_config(_cfg(tmp_path, speed=0.5))
    validate_short_config(_cfg(tmp_path, speed=2.0))


def test_validate_anchor_x_below(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Anchor X must be 0\.0-1\.0"):
        validate_short_config(_cfg(tmp_path, anchor_x=-0.1))


def test_validate_anchor_x_above(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Anchor X must be 0\.0-1\.0"):
        validate_short_config(_cfg(tmp_path, anchor_x=1.1))


def test_validate_anchor_y_below(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Anchor Y must be 0\.0-1\.0"):
        validate_short_config(_cfg(tmp_path, anchor_y=-0.1))


def test_validate_anchor_y_above(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Anchor Y must be 0\.0-1\.0"):
        validate_short_config(_cfg(tmp_path, anchor_y=1.1))


def test_validate_lut_bad_suffix(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"LUT file must be \.cube or \.3dl"):
        validate_short_config(_cfg(tmp_path, lut=tmp_path / "grade.png"))


def test_validate_lut_cube_ok(tmp_path: Path) -> None:
    validate_short_config(_cfg(tmp_path, lut=tmp_path / "grade.cube"))


def test_validate_lut_3dl_ok(tmp_path: Path) -> None:
    validate_short_config(_cfg(tmp_path, lut=tmp_path / "grade.3dl"))


def test_validate_subtitle_bad_suffix(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Subtitle file must be \.ass"):
        validate_short_config(_cfg(tmp_path, subtitle=tmp_path / "subs.srt"))


def test_validate_subtitle_ass_ok(tmp_path: Path) -> None:
    validate_short_config(_cfg(tmp_path, subtitle=tmp_path / "subs.ass"))


# ---------------------------------------------------------------------------
# Individual filter builders
# ---------------------------------------------------------------------------


def test_build_scale_filter_pad() -> None:
    result = build_scale_filter(crop_mode=CropMode.PAD, target_width=1080, target_height=1920)
    assert result == "scale=1080:-2:flags=lanczos"


def test_build_scale_filter_crop() -> None:
    result = build_scale_filter(crop_mode=CropMode.CROP, target_width=1080, target_height=1920)
    assert result == "scale=-2:1920:flags=lanczos"


def test_build_scale_filter_square_pad() -> None:
    result = build_scale_filter(crop_mode=CropMode.PAD, target_width=1080, target_height=1080)
    assert result == "scale=1080:-2:flags=lanczos"


def test_build_pad_filter_vertical() -> None:
    result = build_pad_filter(target_width=1080, target_height=1920, pad_color="black")
    assert result == "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"


def test_build_pad_filter_custom_color() -> None:
    result = build_pad_filter(target_width=1080, target_height=1920, pad_color="0x1a1a1a")
    assert result == "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:0x1a1a1a"


def test_build_crop_filter_center() -> None:
    result = build_crop_filter(target_width=1080, target_height=1920, anchor_x=0.5, anchor_y=0.5)
    assert result == ("crop=w=ih*1080/1920:h=ih:x=(iw-ih*1080/1920)*0.5:y=0")


def test_build_crop_filter_left() -> None:
    result = build_crop_filter(target_width=1080, target_height=1920, anchor_x=0.0, anchor_y=0.5)
    assert "x=(iw-ih*1080/1920)*0.0" in result


def test_build_crop_filter_right() -> None:
    result = build_crop_filter(target_width=1080, target_height=1920, anchor_x=1.0, anchor_y=0.5)
    assert "x=(iw-ih*1080/1920)*1.0" in result


def test_build_crop_filter_custom_anchor() -> None:
    result = build_crop_filter(target_width=1080, target_height=1920, anchor_x=0.3, anchor_y=0.7)
    assert "x=(iw-ih*1080/1920)*0.3" in result


def test_build_final_scale_filter() -> None:
    result = build_final_scale_filter(target_width=1080, target_height=1920)
    assert result == "scale=1080:1920:flags=lanczos"


def test_build_speed_filter_slow() -> None:
    assert build_speed_filter(0.5) == "setpts=PTS/0.5"


def test_build_speed_filter_fast() -> None:
    assert build_speed_filter(2.0) == "setpts=PTS/2.0"


def test_build_audio_speed_filter_slow() -> None:
    assert build_audio_speed_filter(0.5) == "atempo=0.5"


def test_build_audio_speed_filter_fast() -> None:
    assert build_audio_speed_filter(2.0) == "atempo=2.0"


def test_build_lut_filter() -> None:
    result = build_lut_filter(Path("/tmp/grade.cube"))
    assert result == "lut3d='/tmp/grade.cube'"


def test_build_subtitle_filter() -> None:
    result = build_subtitle_filter(Path("/tmp/subs.ass"))
    assert result == "ass='/tmp/subs.ass'"


# ---------------------------------------------------------------------------
# Filter chain assembly
# ---------------------------------------------------------------------------


def test_build_filter_chain_pad_minimal(tmp_path: Path) -> None:
    """Pad mode with no extras: just scale + pad."""
    cfg = _cfg(tmp_path)
    chain, audio = build_filter_chain(cfg)
    assert chain == ("scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black")
    assert audio is None


def test_build_filter_chain_crop_minimal(tmp_path: Path) -> None:
    """Crop mode with no extras: scale + crop + final_scale."""
    cfg = _cfg(tmp_path, crop_mode=CropMode.CROP)
    chain, audio = build_filter_chain(cfg)
    assert chain == (
        "scale=-2:1920:flags=lanczos,crop=w=ih*1080/1920:h=ih:x=(iw-ih*1080/1920)*0.5:y=0,scale=1080:1920:flags=lanczos"
    )
    assert audio is None


def test_build_filter_chain_with_speed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, speed=0.5)
    chain, audio = build_filter_chain(cfg)
    assert "setpts=PTS/0.5" in chain
    assert audio == "atempo=0.5"


def test_build_filter_chain_with_lut(tmp_path: Path) -> None:
    lut = tmp_path / "grade.cube"
    cfg = _cfg(tmp_path, lut=lut)
    chain, audio = build_filter_chain(cfg)
    assert chain.startswith(f"lut3d='{lut}'")
    assert audio is None


def test_build_filter_chain_with_subtitle(tmp_path: Path) -> None:
    sub = tmp_path / "subs.ass"
    cfg = _cfg(tmp_path, subtitle=sub)
    chain, _audio = build_filter_chain(cfg)
    assert chain.endswith(f"ass='{sub}'")


def test_build_filter_chain_pad_full(tmp_path: Path) -> None:
    """Full pad mode chain: LUT -> speed -> scale -> pad -> subtitle."""
    lut = tmp_path / "grade.cube"
    sub = tmp_path / "subs.ass"
    cfg = _cfg(tmp_path, speed=0.5, lut=lut, subtitle=sub)
    chain, audio = build_filter_chain(cfg)
    expected = (
        f"lut3d='{lut}',setpts=PTS/0.5,scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,ass='{sub}'"
    )
    assert chain == expected
    assert audio == "atempo=0.5"


def test_build_filter_chain_crop_full(tmp_path: Path) -> None:
    """Full crop mode chain: LUT -> speed -> scale -> crop -> final_scale -> subtitle."""
    lut = tmp_path / "grade.cube"
    sub = tmp_path / "subs.ass"
    cfg = _cfg(
        tmp_path,
        crop_mode=CropMode.CROP,
        anchor_x=0.3,
        speed=0.5,
        lut=lut,
        subtitle=sub,
    )
    chain, audio = build_filter_chain(cfg)
    expected = (
        f"lut3d='{lut}',"
        "setpts=PTS/0.5,"
        "scale=-2:1920:flags=lanczos,"
        "crop=w=ih*1080/1920:h=ih:x=(iw-ih*1080/1920)*0.3:y=0,"
        "scale=1080:1920:flags=lanczos,"
        f"ass='{sub}'"
    )
    assert chain == expected
    assert audio == "atempo=0.5"


def test_build_filter_chain_square_format(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, width=1080, height=1080)
    chain, _ = build_filter_chain(cfg)
    assert "pad=1080:1080" in chain


# ---------------------------------------------------------------------------
# plan_short
# ---------------------------------------------------------------------------


def test_plan_short_defaults(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    plan = plan_short(cfg)
    assert plan.inputs == [tmp_path / "clip.mkv"]
    assert plan.output == tmp_path / "out.mp4"
    assert plan.codec == "libx264"
    assert plan.preset == "medium"
    assert plan.crf == 18
    assert plan.width == 1080
    assert plan.height == 1920
    assert plan.filter_complex is not None
    assert "scale=1080:-2:flags=lanczos" in plan.filter_complex
    assert plan.audio_filter is None


def test_plan_short_with_speed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, speed=0.5)
    plan = plan_short(cfg)
    assert plan.audio_filter == "atempo=0.5"
    assert plan.filter_complex is not None
    assert "setpts=PTS/0.5" in plan.filter_complex


def test_plan_short_custom_encoding(tmp_path: Path) -> None:
    cfg = _cfg(
        tmp_path,
        codec="libx265",
        preset="fast",
        crf=22,
        audio_codec="opus",
        audio_bitrate="192k",
    )
    plan = plan_short(cfg)
    assert plan.codec == "libx265"
    assert plan.preset == "fast"
    assert plan.crf == 22
    assert plan.audio_codec == "opus"
    assert plan.audio_bitrate == "192k"


def test_plan_short_validation_error(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, width=1081)
    with pytest.raises(RenderError, match="Width must be even"):
        plan_short(cfg)


# ---------------------------------------------------------------------------
# plan_preview
# ---------------------------------------------------------------------------


def test_plan_preview_half_resolution(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    plan = plan_preview(cfg)
    assert plan.width == 540
    assert plan.height == 960
    assert plan.preset == "ultrafast"
    assert plan.crf == 28


def test_plan_preview_square(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, width=1080, height=1080)
    plan = plan_preview(cfg)
    assert plan.width == 540
    assert plan.height == 540


def test_plan_preview_filter_uses_half_res(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    plan = plan_preview(cfg)
    assert plan.filter_complex is not None
    assert "scale=540:-2:flags=lanczos" in plan.filter_complex


def test_plan_preview_validation_error(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, speed=3.0)
    with pytest.raises(RenderError, match=r"Speed must be 0\.5-2\.0"):
        plan_preview(cfg)


def test_plan_preview_preserves_speed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, speed=0.5)
    plan = plan_preview(cfg)
    assert plan.audio_filter == "atempo=0.5"
    assert plan.filter_complex is not None
    assert "setpts=PTS/0.5" in plan.filter_complex


def test_plan_preview_even_rounding(tmp_path: Path) -> None:
    """Odd half-dimensions get rounded up to even."""
    cfg = _cfg(tmp_path, width=1080, height=1082)
    plan = plan_preview(cfg)
    assert plan.width == 540
    assert plan.height == 542  # 1082 // 2 = 541, + 1 = 542
