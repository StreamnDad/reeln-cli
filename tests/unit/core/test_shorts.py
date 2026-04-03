"""Tests for short-form filter builders, validation, and plan assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from reeln.core.errors import RenderError
from reeln.core.shorts import (
    _build_atempo_chain,
    _escape_filter_path,
    _resolve_smart,
    _round_even,
    build_audio_speed_filter,
    build_crop_filter,
    build_filter_chain,
    build_final_scale_filter,
    build_lut_filter,
    build_overflow_crop_filter,
    build_pad_filter,
    build_scale_filter,
    build_speed_filter,
    build_speed_segments_filters,
    build_subtitle_filter,
    compute_speed_segments_duration,
    plan_preview,
    plan_short,
    validate_short_config,
    validate_speed_segments,
)
from reeln.models.profile import SpeedSegment
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


def test_validate_scale_too_low(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Scale must be 0\.5-3\.0"):
        validate_short_config(_cfg(tmp_path, scale=0.4))


def test_validate_scale_too_high(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match=r"Scale must be 0\.5-3\.0"):
        validate_short_config(_cfg(tmp_path, scale=3.1))


def test_validate_scale_at_bounds(tmp_path: Path) -> None:
    validate_short_config(_cfg(tmp_path, scale=0.5))
    validate_short_config(_cfg(tmp_path, scale=3.0))


def test_validate_smart_zoom_frames_too_low(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="Smart zoom frames must be 1-20"):
        validate_short_config(_cfg(tmp_path, smart_zoom_frames=0))


def test_validate_smart_zoom_frames_too_high(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="Smart zoom frames must be 1-20"):
        validate_short_config(_cfg(tmp_path, smart_zoom_frames=21))


def test_validate_smart_zoom_frames_at_bounds(tmp_path: Path) -> None:
    validate_short_config(_cfg(tmp_path, smart_zoom_frames=1))
    validate_short_config(_cfg(tmp_path, smart_zoom_frames=20))


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
    assert result == "lut3d=/tmp/grade.cube"


def test_build_subtitle_filter() -> None:
    result = build_subtitle_filter(Path("/tmp/subs.ass"))
    assert result == "subtitles=f=/tmp/subs.ass"


def test_escape_filter_path_no_special_chars() -> None:
    assert _escape_filter_path(Path("/tmp/video.mp4")) == "/tmp/video.mp4"


def test_escape_filter_path_all_special_chars() -> None:
    """Backslash, colon, quote, brackets, semicolon, comma are all escaped."""
    result = _escape_filter_path(Path("/a:b'c[d]e;f,g"))
    assert result == "/a\\:b\\'c\\[d\\]e\\;f\\,g"


def test_escape_filter_path_backslash_first() -> None:
    """Backslash is escaped before other chars to avoid double-escaping."""
    result = _escape_filter_path(Path("/a\\:b"))
    assert result == "/a\\\\\\:b"


def test_build_lut_filter_special_path() -> None:
    result = build_lut_filter(Path("/path/to:grade.cube"))
    assert result == "lut3d=/path/to\\:grade.cube"


def test_build_subtitle_filter_special_path() -> None:
    result = build_subtitle_filter(Path("/path/to:subs.ass"))
    assert result == "subtitles=f=/path/to\\:subs.ass"


# ---------------------------------------------------------------------------
# _round_even
# ---------------------------------------------------------------------------


def test_round_even_already_even() -> None:
    assert _round_even(1080) == 1080


def test_round_even_odd() -> None:
    assert _round_even(1081) == 1082


def test_round_even_zero() -> None:
    assert _round_even(0) == 0


# ---------------------------------------------------------------------------
# build_scale_filter with scale
# ---------------------------------------------------------------------------


def test_build_scale_filter_pad_with_scale() -> None:
    result = build_scale_filter(crop_mode=CropMode.PAD, target_width=1080, target_height=1920, scale=1.3)
    # 1080 * 1.3 = 1404
    assert result == "scale=1404:-2:flags=lanczos"


def test_build_scale_filter_crop_with_scale() -> None:
    result = build_scale_filter(crop_mode=CropMode.CROP, target_width=1080, target_height=1920, scale=1.3)
    # 1920 * 1.3 = 2496
    assert result == "scale=-2:2496:flags=lanczos"


def test_build_scale_filter_pad_scale_rounds_even() -> None:
    # 1080 * 1.1 = 1188 (already even)
    result = build_scale_filter(crop_mode=CropMode.PAD, target_width=1080, target_height=1920, scale=1.1)
    assert result == "scale=1188:-2:flags=lanczos"


def test_build_scale_filter_crop_scale_rounds_odd_up() -> None:
    # 1920 * 1.05 = 2016 (even)
    result = build_scale_filter(crop_mode=CropMode.CROP, target_width=1080, target_height=1920, scale=1.05)
    assert result == "scale=-2:2016:flags=lanczos"


# ---------------------------------------------------------------------------
# build_overflow_crop_filter
# ---------------------------------------------------------------------------


def test_build_overflow_crop_filter_structure() -> None:
    result = build_overflow_crop_filter(target_width=1080, target_height=1920)
    assert "min(iw,1080)" in result
    assert "min(ih,1920)" in result
    assert "crop=" in result


# ---------------------------------------------------------------------------
# _resolve_smart
# ---------------------------------------------------------------------------


def test_resolve_smart_pad_no_smart() -> None:
    mode, smart = _resolve_smart(CropMode.PAD, False)
    assert mode == CropMode.PAD
    assert smart is False


def test_resolve_smart_crop_no_smart() -> None:
    mode, smart = _resolve_smart(CropMode.CROP, False)
    assert mode == CropMode.CROP
    assert smart is False


def test_resolve_smart_pad_with_smart_flag() -> None:
    mode, smart = _resolve_smart(CropMode.PAD, True)
    assert mode == CropMode.PAD
    assert smart is True


def test_resolve_smart_crop_with_smart_flag() -> None:
    mode, smart = _resolve_smart(CropMode.CROP, True)
    assert mode == CropMode.CROP
    assert smart is True


def test_resolve_smart_deprecated_smart() -> None:
    mode, smart = _resolve_smart(CropMode.SMART, False)
    assert mode == CropMode.CROP
    assert smart is True


def test_resolve_smart_deprecated_smart_pad() -> None:
    mode, smart = _resolve_smart(CropMode.SMART_PAD, False)
    assert mode == CropMode.PAD
    assert smart is True


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
    assert chain.startswith(f"lut3d={lut}")
    assert audio is None


def test_build_filter_chain_with_subtitle(tmp_path: Path) -> None:
    sub = tmp_path / "subs.ass"
    cfg = _cfg(tmp_path, subtitle=sub)
    chain, _audio = build_filter_chain(cfg)
    assert chain.endswith(f"subtitles=f={sub}")


def test_build_filter_chain_pad_full(tmp_path: Path) -> None:
    """Full pad mode chain: LUT -> speed -> scale -> pad -> subtitle."""
    lut = tmp_path / "grade.cube"
    sub = tmp_path / "subs.ass"
    cfg = _cfg(tmp_path, speed=0.5, lut=lut, subtitle=sub)
    chain, audio = build_filter_chain(cfg)
    expected = f"lut3d={lut},setpts=PTS/0.5,scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,subtitles=f={sub}"
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
        f"lut3d={lut},"
        "setpts=PTS/0.5,"
        "scale=-2:1920:flags=lanczos,"
        "crop=w=ih*1080/1920:h=ih:x=(iw-ih*1080/1920)*0.3:y=0,"
        "scale=1080:1920:flags=lanczos,"
        f"subtitles=f={sub}"
    )
    assert chain == expected
    assert audio == "atempo=0.5"


def test_build_filter_chain_square_format(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, width=1080, height=1080)
    chain, _ = build_filter_chain(cfg)
    assert "pad=1080:1080" in chain


# ---------------------------------------------------------------------------
# Filter chain: scale combinations
# ---------------------------------------------------------------------------


def test_build_filter_chain_pad_with_scale(tmp_path: Path) -> None:
    """Pad + scale>1.0: scale up, overflow crop, then pad."""
    cfg = _cfg(tmp_path, scale=1.3)
    chain, _ = build_filter_chain(cfg)
    # Scale to 1404 (1080*1.3)
    assert "scale=1404:-2:flags=lanczos" in chain
    # Overflow crop back to 1080x1920
    assert "min(iw,1080)" in chain
    assert "min(ih,1920)" in chain
    # Then pad
    assert "pad=1080:1920" in chain


def test_build_filter_chain_crop_with_scale(tmp_path: Path) -> None:
    """Crop + scale>1.0: scale to larger height, crop, final scale."""
    cfg = _cfg(tmp_path, crop_mode=CropMode.CROP, scale=1.3)
    chain, _ = build_filter_chain(cfg)
    # Scale to 2496 (1920*1.3)
    assert "scale=-2:2496:flags=lanczos" in chain
    # Static crop
    assert "crop=w=ih*1080/1920" in chain
    # Final scale
    assert "scale=1080:1920:flags=lanczos" in chain
    # No overflow crop
    assert "min(iw," not in chain


def test_build_filter_chain_pad_scale_1_no_overflow_crop(tmp_path: Path) -> None:
    """Pad at scale=1.0 should NOT have overflow crop."""
    cfg = _cfg(tmp_path)
    chain, _ = build_filter_chain(cfg)
    assert "min(iw," not in chain


def test_build_filter_chain_smart_flag_pad(tmp_path: Path) -> None:
    """smart=True + pad uses smart pad filter with height-based scale."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.4),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, smart=True)
    chain, _ = build_filter_chain(cfg, zoom_path=zp)
    # Smart pad scales by height for horizontal panning room
    assert "scale=-2:1920:flags=lanczos" in chain
    # Smart pad uses overlay on colour background
    assert "color=c=black:s=1080x1920" in chain
    assert "[_bg][_fg]overlay=" in chain


def test_build_filter_chain_smart_pad_with_subtitle(tmp_path: Path) -> None:
    """smart pad + subtitle routes subtitle through post_filters."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    sub = tmp_path / "overlay.ass"
    sub.write_text("[Script Info]\n")
    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, smart=True, subtitle=sub)
    chain, audio = build_filter_chain(cfg, zoom_path=zp)
    assert "subtitles=" in chain
    assert "format=yuv420p" in chain
    assert audio is None


def test_build_filter_chain_smart_pad_with_speed(tmp_path: Path) -> None:
    """smart pad + speed!=1.0 returns audio_filter."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, smart=True, speed=0.5)
    chain, audio = build_filter_chain(cfg, zoom_path=zp)
    assert "overlay=" in chain
    assert audio == "atempo=0.5"


def test_build_filter_chain_smart_flag_crop(tmp_path: Path) -> None:
    """smart=True + crop uses smart crop filter."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, crop_mode=CropMode.CROP, smart=True)
    chain, _ = build_filter_chain(cfg, zoom_path=zp)
    assert "scale=-2:1920:flags=lanczos" in chain
    # Smart crop uses dynamic expressions
    assert "crop=w=" in chain
    assert "scale=1080:1920:flags=lanczos" in chain


def test_build_filter_chain_smart_flag_no_zoom_path_raises(tmp_path: Path) -> None:
    """smart=True without zoom_path raises RenderError."""
    cfg = _cfg(tmp_path, smart=True)
    with pytest.raises(RenderError, match="Smart crop mode requires a zoom path"):
        build_filter_chain(cfg)


def test_build_filter_chain_smart_with_scale(tmp_path: Path) -> None:
    """smart + crop + scale>1.0: bigger scale, then smart crop."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, crop_mode=CropMode.CROP, smart=True, scale=1.3)
    chain, _ = build_filter_chain(cfg, zoom_path=zp)
    # Scale is 1920*1.3 = 2496
    assert "scale=-2:2496:flags=lanczos" in chain
    # Smart crop
    assert "crop=w=" in chain


def test_build_filter_chain_deprecated_smart_backward_compat(tmp_path: Path) -> None:
    """CropMode.SMART still produces crop + smart crop."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART)
    chain, _ = build_filter_chain(cfg, zoom_path=zp)
    assert "scale=-2:1920:flags=lanczos" in chain
    assert "crop=w=" in chain
    assert "scale=1080:1920:flags=lanczos" in chain


def test_build_filter_chain_deprecated_smart_pad_backward_compat(tmp_path: Path) -> None:
    """CropMode.SMART_PAD still produces pad + smart pad with height-based scale."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.4),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD)
    chain, _ = build_filter_chain(cfg, zoom_path=zp)
    # Smart pad scales by height
    assert "scale=-2:1920:flags=lanczos" in chain
    assert "color=c=black:s=1080x1920" in chain
    assert "[_bg][_fg]overlay=" in chain


def test_build_filter_chain_deprecated_smart_no_zoom_path_raises(tmp_path: Path) -> None:
    """CropMode.SMART without zoom_path raises."""
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART)
    with pytest.raises(RenderError, match="Smart crop mode requires a zoom path"):
        build_filter_chain(cfg)


def test_build_filter_chain_deprecated_smart_pad_no_zoom_path_raises(tmp_path: Path) -> None:
    """CropMode.SMART_PAD without zoom_path raises."""
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD)
    with pytest.raises(RenderError, match="Smart crop mode requires a zoom path"):
        build_filter_chain(cfg)


def test_build_filter_chain_pad_smart_with_scale(tmp_path: Path) -> None:
    """Pad + smart + scale>1.0: scales by height*scale, no overflow crop."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.4),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, smart=True, scale=1.3)
    chain, _ = build_filter_chain(cfg, zoom_path=zp)
    # Smart pad scales by height * scale = 1920 * 1.3 = 2496
    assert "scale=-2:2496:flags=lanczos" in chain
    # No overflow crop in smart pad — the overlay handles clipping
    assert "min(iw," not in chain
    assert "[_bg][_fg]overlay=" in chain  # smart pad via overlay


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


def test_plan_preview_propagates_scale(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, scale=1.3)
    plan = plan_preview(cfg)
    assert plan.filter_complex is not None
    # Preview is half-res (540), scaled by 1.3 = 702
    assert "scale=702:-2:flags=lanczos" in plan.filter_complex


def test_plan_preview_propagates_smart(tmp_path: Path) -> None:
    """Preview with smart=True but no zoom_path raises."""
    cfg = _cfg(tmp_path, smart=True)
    with pytest.raises(RenderError, match="Smart crop mode requires a zoom path"):
        plan_preview(cfg)


def test_plan_preview_propagates_speed_segments(tmp_path: Path) -> None:
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs)
    plan = plan_preview(cfg)
    assert plan.filter_complex is not None
    assert "split=2" in plan.filter_complex
    assert "asplit=2" in plan.filter_complex
    assert plan.audio_filter is None


# ---------------------------------------------------------------------------
# validate_speed_segments
# ---------------------------------------------------------------------------


def test_compute_speed_segments_duration_basic() -> None:
    """Output duration accounts for speed changes in each segment."""
    segs = (
        SpeedSegment(speed=1.0, until=5.0),
        SpeedSegment(speed=0.5, until=8.0),
        SpeedSegment(speed=1.0),
    )
    # 5s@1x + 3s@0.5x + 2s@1x = 5 + 6 + 2 = 13
    assert compute_speed_segments_duration(segs, 10.0) == pytest.approx(13.0)


def test_compute_speed_segments_duration_all_normal() -> None:
    """All-1x segments produce same duration as source."""
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=1.0))
    assert compute_speed_segments_duration(segs, 10.0) == pytest.approx(10.0)


def test_compute_speed_segments_duration_all_slow() -> None:
    """All-0.5x produces double the source duration."""
    segs = (SpeedSegment(speed=0.5, until=5.0), SpeedSegment(speed=0.5))
    assert compute_speed_segments_duration(segs, 10.0) == pytest.approx(20.0)


def test_validate_speed_segments_valid_two() -> None:
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    validate_speed_segments(segs)


def test_validate_speed_segments_valid_three() -> None:
    segs = (
        SpeedSegment(speed=1.0, until=5.0),
        SpeedSegment(speed=0.5, until=8.0),
        SpeedSegment(speed=1.0),
    )
    validate_speed_segments(segs)


def test_validate_speed_segments_single_segment() -> None:
    with pytest.raises(RenderError, match="at least 2 segments"):
        validate_speed_segments((SpeedSegment(speed=0.5),))


def test_validate_speed_segments_last_has_until() -> None:
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5, until=10.0))
    with pytest.raises(RenderError, match="last segment must have until=None"):
        validate_speed_segments(segs)


def test_validate_speed_segments_non_last_missing_until() -> None:
    segs = (SpeedSegment(speed=1.0), SpeedSegment(speed=0.5))
    with pytest.raises(RenderError, match="must have 'until' set"):
        validate_speed_segments(segs)


def test_validate_speed_segments_until_not_increasing() -> None:
    segs = (
        SpeedSegment(speed=1.0, until=8.0),
        SpeedSegment(speed=0.5, until=5.0),
        SpeedSegment(speed=1.0),
    )
    with pytest.raises(RenderError, match="strictly increasing"):
        validate_speed_segments(segs)


def test_validate_speed_segments_until_zero() -> None:
    segs = (SpeedSegment(speed=1.0, until=0.0), SpeedSegment(speed=0.5))
    with pytest.raises(RenderError, match="must be positive"):
        validate_speed_segments(segs)


def test_validate_speed_segments_until_negative() -> None:
    segs = (SpeedSegment(speed=1.0, until=-1.0), SpeedSegment(speed=0.5))
    with pytest.raises(RenderError, match="must be positive"):
        validate_speed_segments(segs)


def test_validate_speed_segments_speed_too_low() -> None:
    segs = (SpeedSegment(speed=0.1, until=5.0), SpeedSegment(speed=1.0))
    with pytest.raises(RenderError, match=r"speed must be 0\.25-4\.0"):
        validate_speed_segments(segs)


def test_validate_speed_segments_speed_too_high() -> None:
    segs = (SpeedSegment(speed=5.0, until=5.0), SpeedSegment(speed=1.0))
    with pytest.raises(RenderError, match=r"speed must be 0\.25-4\.0"):
        validate_speed_segments(segs)


def test_validate_speed_segments_speed_at_bounds() -> None:
    segs = (SpeedSegment(speed=0.25, until=5.0), SpeedSegment(speed=4.0))
    validate_speed_segments(segs)


def test_validate_short_config_speed_and_speed_segments_mutual_exclusion(tmp_path: Path) -> None:
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed=0.5, speed_segments=segs)
    with pytest.raises(RenderError, match="mutually exclusive"):
        validate_short_config(cfg)


def test_validate_short_config_speed_segments_validated(tmp_path: Path) -> None:
    """speed_segments on ShortConfig are validated during validate_short_config."""
    segs = (SpeedSegment(speed=0.5),)  # single segment → error
    cfg = _cfg(tmp_path, speed_segments=segs)
    with pytest.raises(RenderError, match="at least 2 segments"):
        validate_short_config(cfg)


# ---------------------------------------------------------------------------
# _build_atempo_chain
# ---------------------------------------------------------------------------


def test_build_atempo_chain_normal() -> None:
    assert _build_atempo_chain(1.0) == "atempo=1.0"


def test_build_atempo_chain_half() -> None:
    assert _build_atempo_chain(0.5) == "atempo=0.5"


def test_build_atempo_chain_quarter() -> None:
    result = _build_atempo_chain(0.25)
    assert result == "atempo=0.5,atempo=0.5"


def test_build_atempo_chain_fast() -> None:
    assert _build_atempo_chain(2.0) == "atempo=2.0"


# ---------------------------------------------------------------------------
# build_speed_segments_filters
# ---------------------------------------------------------------------------


def test_build_speed_segments_filters_two_segments() -> None:
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    video, audio = build_speed_segments_filters(segs)

    # Video: split, trim segments, concat
    assert "[_vsrc]split=2[v0][v1]" in video
    assert "[v0]trim=0.0:5.0,setpts=PTS-STARTPTS[sv0]" in video
    assert "[v1]trim=5.0,setpts=PTS-STARTPTS,setpts=PTS/0.5[sv1]" in video
    assert "[sv0][sv1]concat=n=2:v=1:a=0[_vout]" in video

    # Audio: asplit, atrim segments, concat
    assert "[_asrc]asplit=2[a0][a1]" in audio
    assert "[a0]atrim=0.0:5.0,asetpts=PTS-STARTPTS[sa0]" in audio
    assert "[a1]atrim=5.0,asetpts=PTS-STARTPTS,atempo=0.5[sa1]" in audio
    assert "[sa0][sa1]concat=n=2:v=0:a=1[_aout]" in audio


def test_build_speed_segments_filters_three_segments() -> None:
    segs = (
        SpeedSegment(speed=1.0, until=5.0),
        SpeedSegment(speed=0.5, until=8.0),
        SpeedSegment(speed=1.0),
    )
    video, audio = build_speed_segments_filters(segs)
    assert "split=3" in video
    assert "asplit=3" in audio
    assert "concat=n=3:v=1:a=0" in video
    assert "concat=n=3:v=0:a=1" in audio
    # Middle segment has both trim boundaries
    assert "trim=5.0:8.0" in video
    assert "atrim=5.0:8.0" in audio


def test_build_speed_segments_filters_speed_1_no_extra_setpts() -> None:
    """Segments with speed=1.0 omit the speed setpts/atempo."""
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    video, audio = build_speed_segments_filters(segs)
    # v0 (speed=1.0) should NOT have setpts=PTS/1.0
    v0_part = video.split(";")[1]  # [v0]trim=...
    assert "setpts=PTS/1.0" not in v0_part
    # a0 (speed=1.0) should NOT have atempo
    a0_part = audio.split(";")[1]
    assert "atempo" not in a0_part


def test_build_speed_segments_filters_very_slow_speed() -> None:
    """Speed < 0.5 uses chained atempo."""
    segs = (SpeedSegment(speed=0.25, until=5.0), SpeedSegment(speed=1.0))
    _, audio = build_speed_segments_filters(segs)
    assert "atempo=0.5,atempo=0.5" in audio


# ---------------------------------------------------------------------------
# Filter chain with speed_segments
# ---------------------------------------------------------------------------


def test_build_filter_chain_speed_segments_pad(tmp_path: Path) -> None:
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs)
    chain, audio = build_filter_chain(cfg)
    # Video graph uses filter_complex with split/concat
    assert "split=2" in chain
    assert "concat=n=2:v=1:a=0" in chain
    # Post-speed filters: height-based scale (like smart pad), overflow crop, pad
    assert "scale=-2:1920:flags=lanczos" in chain
    assert "min(iw,1080)" in chain  # overflow crop
    assert "pad=1080:1920" in chain
    # Audio also in filter_complex
    assert "asplit=2" in chain
    assert "concat=n=2:v=0:a=1" in chain
    # audio_filter is None (audio in filter_complex)
    assert audio is None


def test_build_filter_chain_speed_segments_crop(tmp_path: Path) -> None:
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, crop_mode=CropMode.CROP, speed_segments=segs)
    chain, audio = build_filter_chain(cfg)
    assert "crop=w=ih*1080/1920" in chain
    assert "scale=1080:1920:flags=lanczos" in chain
    assert audio is None


def test_build_filter_chain_speed_segments_with_lut(tmp_path: Path) -> None:
    lut = tmp_path / "grade.cube"
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, lut=lut)
    chain, _ = build_filter_chain(cfg)
    # LUT goes before split
    lut_pos = chain.index("lut3d=")
    split_pos = chain.index("split=2")
    assert lut_pos < split_pos


def test_build_filter_chain_speed_segments_with_subtitle(tmp_path: Path) -> None:
    sub = tmp_path / "subs.ass"
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, subtitle=sub)
    chain, _ = build_filter_chain(cfg)
    # Subtitle goes after concat
    concat_pos = chain.index("concat=n=2:v=1:a=0")
    sub_pos = chain.index("subtitles=")
    assert sub_pos > concat_pos


def test_build_filter_chain_speed_segments_with_smart_pad(tmp_path: Path) -> None:
    """speed_segments + smart pad uses overlay on colour background after concat."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
    )
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, smart=True)
    chain, audio = build_filter_chain(cfg, zoom_path=zp, source_fps=60.0)
    # Audio is embedded in filter_complex
    assert audio is None
    # Should contain colour source, overlay with t-based expression, and stream labels
    assert "color=c=black:s=1080x1920" in chain
    assert "overlay=" in chain
    assert "[vfinal]" in chain
    assert "[afinal]" in chain
    # Speed segments split/concat present
    assert "split=2" in chain
    assert "trim=" in chain
    assert "concat=n=2:v=1:a=0" in chain
    # Height-based scale for pad mode
    assert "scale=-2:" in chain


def test_build_filter_chain_speed_segments_smart_pad_with_subtitle(tmp_path: Path) -> None:
    """speed_segments + smart pad + subtitle routes subtitle through post-overlay."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    sub = tmp_path / "overlay.ass"
    sub.write_text("[Script Info]\n")
    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, smart=True, subtitle=sub)
    chain, audio = build_filter_chain(cfg, zoom_path=zp, source_fps=30.0)
    assert audio is None
    assert "overlay=" in chain
    assert "subtitles=" in chain
    assert "format=yuv420p" in chain
    assert "[_ov]" in chain


def test_build_filter_chain_speed_segments_smart_pad_with_lut(tmp_path: Path) -> None:
    """speed_segments + smart pad + LUT wires LUT as pre-filter before split."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    lut = tmp_path / "color.cube"
    lut.write_text("LUT\n")
    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, smart=True, lut=lut)
    chain, audio = build_filter_chain(cfg, zoom_path=zp, source_fps=30.0)
    assert audio is None
    assert "lut3d=" in chain
    assert "overlay=" in chain
    # LUT should appear before split
    lut_pos = chain.index("lut3d=")
    split_pos = chain.index("split=")
    assert lut_pos < split_pos


def test_build_filter_chain_speed_segments_smart_crop(tmp_path: Path) -> None:
    """speed_segments + smart crop uses smart crop filter after concat."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, crop_mode=CropMode.CROP, smart=True)
    chain, audio = build_filter_chain(cfg, zoom_path=zp, source_fps=30.0)
    assert audio is None
    assert "[vfinal]" in chain
    assert "[afinal]" in chain
    # Smart crop filter after concat
    assert "crop=w=" in chain
    assert "scale=1080:1920:flags=lanczos" in chain


def test_build_filter_chain_speed_segments_pad_with_scale(tmp_path: Path) -> None:
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, scale=1.3)
    chain, _ = build_filter_chain(cfg)
    # Pad + scale > 1.0: height-based scale + overflow crop
    assert "min(iw,1080)" in chain
    assert "scale=-2:2496:flags=lanczos" in chain


# ---------------------------------------------------------------------------
# Branding in filter chains
# ---------------------------------------------------------------------------


def test_validate_branding_bad_extension(tmp_path: Path) -> None:
    branding = tmp_path / "brand.txt"
    branding.write_text("hi")
    with pytest.raises(RenderError, match=r"Branding file must be \.ass"):
        validate_short_config(_cfg(tmp_path, branding=branding))


def test_validate_branding_good_extension(tmp_path: Path) -> None:
    branding = tmp_path / "brand.ass"
    branding.write_text("[Script Info]\n")
    validate_short_config(_cfg(tmp_path, branding=branding))


def test_build_filter_chain_with_branding_pad(tmp_path: Path) -> None:
    """Path 1 (simple pad): branding appended after subtitle."""
    brand = tmp_path / "brand.ass"
    brand.write_text("[Script Info]\n")
    cfg = _cfg(tmp_path, branding=brand)
    chain, _ = build_filter_chain(cfg)
    escaped = str(brand).replace(":", "\\:").replace(",", "\\,")
    assert f"subtitles=f={escaped}" in chain


def test_build_filter_chain_with_branding_crop(tmp_path: Path) -> None:
    """Path 1 (simple crop): branding appended after subtitle."""
    brand = tmp_path / "brand.ass"
    brand.write_text("[Script Info]\n")
    cfg = _cfg(tmp_path, crop_mode=CropMode.CROP, branding=brand)
    chain, _ = build_filter_chain(cfg)
    assert "subtitles=" in chain


def test_build_filter_chain_branding_after_subtitle(tmp_path: Path) -> None:
    """Path 1: branding filter appears after subtitle filter."""
    sub = tmp_path / "overlay.ass"
    sub.write_text("[Script Info]\n")
    brand = tmp_path / "brand.ass"
    brand.write_text("[Script Info]\n")
    cfg = _cfg(tmp_path, subtitle=sub, branding=brand)
    chain, _ = build_filter_chain(cfg)
    sub_escaped = str(sub).replace(":", "\\:").replace(",", "\\,")
    brand_escaped = str(brand).replace(":", "\\:").replace(",", "\\,")
    sub_pos = chain.index(f"subtitles=f={sub_escaped}")
    brand_pos = chain.index(f"subtitles=f={brand_escaped}")
    assert brand_pos > sub_pos


def test_build_filter_chain_smart_pad_with_branding(tmp_path: Path) -> None:
    """Path 2 (smart pad): branding in post_filters."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    brand = tmp_path / "brand.ass"
    brand.write_text("[Script Info]\n")
    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    cfg = _cfg(tmp_path, smart=True, branding=brand)
    chain, _ = build_filter_chain(cfg, zoom_path=zp)
    assert "overlay=" in chain
    assert "subtitles=" in chain


def test_build_filter_chain_speed_segments_static_with_branding(tmp_path: Path) -> None:
    """Path 3 (speed segments static): branding in post list."""
    brand = tmp_path / "brand.ass"
    brand.write_text("[Script Info]\n")
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, branding=brand)
    chain, audio = build_filter_chain(cfg)
    assert audio is None
    assert "subtitles=" in chain
    assert "[vfinal]" in chain


def test_build_filter_chain_speed_segments_smart_pad_with_branding(tmp_path: Path) -> None:
    """Path 4 (speed segments + smart pad): branding in post_overlay."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    brand = tmp_path / "brand.ass"
    brand.write_text("[Script Info]\n")
    zp = ZoomPath(
        duration=10.0,
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
    )
    segs = (SpeedSegment(speed=1.0, until=5.0), SpeedSegment(speed=0.5))
    cfg = _cfg(tmp_path, speed_segments=segs, smart=True, branding=brand)
    chain, audio = build_filter_chain(cfg, zoom_path=zp, source_fps=30.0)
    assert audio is None
    assert "overlay=" in chain
    assert "subtitles=" in chain
    assert "format=yuv420p" in chain
    assert "[_ov]" in chain


def test_plan_preview_passes_branding(tmp_path: Path) -> None:
    """plan_preview passes branding through to the preview config."""
    brand = tmp_path / "brand.ass"
    brand.write_text("[Script Info]\n")
    cfg = _cfg(tmp_path, branding=brand)
    plan = plan_preview(cfg)
    assert "subtitles=" in plan.filter_complex
