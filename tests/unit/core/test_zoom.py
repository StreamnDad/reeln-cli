"""Tests for piecewise lerp and smart crop filter builders."""

from __future__ import annotations

from pathlib import Path

import pytest

from reeln.core.errors import RenderError
from reeln.core.shorts import build_filter_chain
from reeln.core.zoom import _downsample, build_piecewise_lerp, build_smart_crop_filter
from reeln.models.short import CropMode, ShortConfig
from reeln.models.zoom import ZoomPath, ZoomPoint

# ---------------------------------------------------------------------------
# build_piecewise_lerp
# ---------------------------------------------------------------------------


def test_lerp_empty_values() -> None:
    assert build_piecewise_lerp([], 10.0) == "0"


def test_lerp_single_point() -> None:
    result = build_piecewise_lerp([(5.0, 0.5)], 10.0)
    assert result == "0.5"


def test_lerp_two_points() -> None:
    result = build_piecewise_lerp([(0.0, 0.3), (10.0, 0.7)], 10.0)
    # Flat: lt(t,10)*lerp + gte(t,10)*0.7
    assert "lt(t,10)" in result
    assert "0.3" in result
    assert "0.7" in result
    # No nested if() calls — uses sum-of-products
    assert "if(" not in result


def test_lerp_three_points() -> None:
    result = build_piecewise_lerp([(0.0, 0.2), (5.0, 0.8), (10.0, 0.5)], 10.0)
    # Three terms: lt(t,5)*lerp01 + gte(t,5)*lt(t,10)*lerp12 + gte(t,10)*0.5
    assert "lt(t,5)" in result
    assert "gte(t,5)*lt(t,10)" in result
    assert "gte(t,10)*0.5" in result


def test_lerp_custom_time_expr() -> None:
    result = build_piecewise_lerp([(0.0, 0.0), (10.0, 1.0)], 10.0, time_expr="T")
    # Time expression should use T
    assert "lt(T," in result
    assert "gte(T," in result


def test_lerp_zero_duration_segment() -> None:
    """Two points at the same timestamp should not divide by zero."""
    result = build_piecewise_lerp([(5.0, 0.3), (5.0, 0.7)], 10.0)
    # With dt=0, should use the first point's value
    assert "0.3" in result


def test_lerp_values_clamp_to_last() -> None:
    """After the last point, expression should return the last value."""
    result = build_piecewise_lerp([(0.0, 0.1), (5.0, 0.9)], 10.0)
    # Last term clamps to 0.9
    assert "gte(t,5)*0.9" in result


def test_lerp_many_points_downsampled() -> None:
    """Many points are downsampled to stay within ffmpeg parser limits."""
    values = [(float(i), float(i) / 20.0) for i in range(20)]
    result = build_piecewise_lerp(values, 20.0)
    # Should not use any nested if() — all flat sum-of-products
    assert "if(" not in result
    # Downsampled to 9 points = 8 segments: 1 lt() + 7 gte()*lt() + 1 gte() clamp
    assert result.count("lt(t,") == 8  # first term + 7 middle terms
    assert result.count("gte(t,") == 8  # 7 middle terms + 1 clamp term


def test_lerp_nine_points_not_downsampled() -> None:
    """Nine points (8 segments) should not be downsampled."""
    values = [(float(i), float(i) / 9.0) for i in range(9)]
    result = build_piecewise_lerp(values, 9.0)
    assert result.count("lt(t,") == 8
    assert result.count("gte(t,") == 8


# ---------------------------------------------------------------------------
# _downsample
# ---------------------------------------------------------------------------


def test_downsample_under_limit() -> None:
    values = [(0.0, 0.1), (1.0, 0.5), (2.0, 0.9)]
    assert _downsample(values, 5) is values  # same object, not a copy


def test_downsample_at_limit() -> None:
    values = [(float(i), float(i)) for i in range(5)]
    assert _downsample(values, 5) is values


def test_downsample_preserves_endpoints() -> None:
    values = [(float(i), float(i)) for i in range(20)]
    result = _downsample(values, 5)
    assert len(result) == 5
    assert result[0] == values[0]
    assert result[-1] == values[-1]


def test_downsample_evenly_spaced() -> None:
    values = [(float(i), float(i)) for i in range(10)]
    result = _downsample(values, 4)
    assert len(result) == 4
    assert result[0] == (0.0, 0.0)
    assert result[-1] == (9.0, 9.0)
    # Inner points should be roughly evenly distributed
    for pt in result[1:-1]:
        assert pt in values


# ---------------------------------------------------------------------------
# build_smart_crop_filter
# ---------------------------------------------------------------------------


def _make_zoom_path(
    points: list[tuple[float, float, float]] | None = None,
) -> ZoomPath:
    """Create a ZoomPath from (timestamp, center_x, center_y) tuples."""
    if points is None:
        points = [(0.0, 0.5, 0.5), (10.0, 0.5, 0.5)]
    return ZoomPath(
        points=tuple(ZoomPoint(timestamp=t, center_x=cx, center_y=cy) for t, cx, cy in points),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )


def test_smart_crop_filter_structure() -> None:
    path = _make_zoom_path()
    result = build_smart_crop_filter(path, 1080, 1920)
    assert result.startswith("crop=w='")
    assert "ih*1080/1920" in result
    assert ":h='ih':" in result
    assert ":x='" in result
    assert ":y='" in result


def test_smart_crop_filter_static_center() -> None:
    """Static center should produce constant 0.5 values in lerp."""
    path = _make_zoom_path([(0.0, 0.5, 0.5)])
    result = build_smart_crop_filter(path, 1080, 1920)
    assert "0.5" in result


def test_smart_crop_filter_panning() -> None:
    """A pan from left to right should produce lerp with 0.2 and 0.8."""
    path = _make_zoom_path([(0.0, 0.2, 0.5), (10.0, 0.8, 0.5)])
    result = build_smart_crop_filter(path, 1080, 1920)
    assert "0.2" in result
    assert "0.8" in result


def test_smart_crop_filter_clamps_x() -> None:
    """X expression should be clamped with max(0,min(...))."""
    path = _make_zoom_path()
    result = build_smart_crop_filter(path, 1080, 1920)
    assert "max(0,min(" in result


def test_smart_crop_filter_clamps_y() -> None:
    """Y expression should be clamped with max(0,min(...))."""
    path = _make_zoom_path([(0.0, 0.5, 0.0), (10.0, 0.5, 1.0)])
    result = build_smart_crop_filter(path, 1080, 1920)
    # Should have max(0,min()) for both x and y
    assert result.count("max(0,min(") == 2


def test_smart_crop_filter_values_single_quoted() -> None:
    """Crop parameter values are single-quoted to protect commas from ffmpeg's filter parser."""
    path = _make_zoom_path()
    result = build_smart_crop_filter(path, 1080, 1920)
    assert "w='" in result
    assert "h='" in result
    assert "x='" in result
    assert "y='" in result


def test_smart_crop_filter_multi_point() -> None:
    """Three-point path should produce flat sum-of-products expressions."""
    path = _make_zoom_path(
        [
            (0.0, 0.2, 0.5),
            (5.0, 0.7, 0.5),
            (10.0, 0.4, 0.5),
        ]
    )
    result = build_smart_crop_filter(path, 1080, 1920)
    # Flat expression: lt()*lerp + gte()*lt()*lerp + gte()*clamp
    assert "lt(t," in result
    assert "gte(t," in result


# ---------------------------------------------------------------------------
# build_filter_chain with SMART mode
# ---------------------------------------------------------------------------


def _cfg(tmp_path: Path, **kwargs: object) -> ShortConfig:
    defaults: dict[str, object] = {
        "input": tmp_path / "clip.mkv",
        "output": tmp_path / "out.mp4",
    }
    defaults.update(kwargs)
    return ShortConfig(**defaults)  # type: ignore[arg-type]


def test_filter_chain_smart_without_zoom_path_raises(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART)
    with pytest.raises(RenderError, match="Smart crop mode requires a zoom path"):
        build_filter_chain(cfg)


def test_filter_chain_smart_with_zoom_path(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART)
    path = _make_zoom_path()
    chain, audio = build_filter_chain(cfg, zoom_path=path)
    # Should have scale, smart crop, final scale
    assert "scale=-2:1920:flags=lanczos" in chain
    assert "crop=w=" in chain
    assert "scale=1080:1920:flags=lanczos" in chain
    assert audio is None


def test_filter_chain_smart_with_speed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART, speed=0.5)
    path = _make_zoom_path()
    chain, audio = build_filter_chain(cfg, zoom_path=path)
    assert "setpts=PTS/0.5" in chain
    assert audio == "atempo=0.5"


def test_filter_chain_smart_with_lut_and_subtitle(tmp_path: Path) -> None:
    lut = tmp_path / "grade.cube"
    sub = tmp_path / "subs.ass"
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART, lut=lut, subtitle=sub)
    path = _make_zoom_path()
    chain, _ = build_filter_chain(cfg, zoom_path=path)
    assert chain.startswith(f"lut3d={lut}")
    assert chain.endswith(f"subtitles=f={sub}")
    assert "crop=w=" in chain


def test_filter_chain_pad_unaffected_by_zoom_path(tmp_path: Path) -> None:
    """zoom_path should be ignored in non-smart modes."""
    cfg = _cfg(tmp_path, crop_mode=CropMode.PAD)
    path = _make_zoom_path()
    chain, _ = build_filter_chain(cfg, zoom_path=path)
    assert "crop=w=" not in chain
    assert "pad=1080:1920" in chain


def test_filter_chain_crop_unaffected_by_zoom_path(tmp_path: Path) -> None:
    """Static crop mode should ignore zoom_path."""
    cfg = _cfg(tmp_path, crop_mode=CropMode.CROP)
    path = _make_zoom_path()
    chain, _ = build_filter_chain(cfg, zoom_path=path)
    assert "x=(iw-ih*1080/1920)*0.5" in chain


# ---------------------------------------------------------------------------
# build_smart_pad_filter
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# build_smart_pad_filter (overlay expression)
# ---------------------------------------------------------------------------


def test_smart_pad_filter_structure() -> None:
    from reeln.core.zoom import build_smart_pad_filter

    path = _make_zoom_path()
    result = build_smart_pad_filter(path, 1080, 1920)
    assert result.startswith("overlay=x='")
    assert ":y='(H-h)/2'" in result
    assert ":eval=frame" in result
    assert ":shortest=1" in result


def test_smart_pad_filter_x_tracks_center_x() -> None:
    """X expression should follow center_x values via lerp."""
    from reeln.core.zoom import build_smart_pad_filter

    path = _make_zoom_path([(0.0, 0.2, 0.5), (10.0, 0.8, 0.5)])
    result = build_smart_pad_filter(path, 1080, 1920)
    assert "min(0,max(W-w," in result
    assert "0.2" in result
    assert "0.8" in result


def test_smart_pad_filter_y_static_center() -> None:
    """Y is always vertically centered — no dynamic tracking in pad mode."""
    from reeln.core.zoom import build_smart_pad_filter

    path = _make_zoom_path([(0.0, 0.5, 0.0), (10.0, 0.5, 1.0)])
    result = build_smart_pad_filter(path, 1080, 1920)
    assert ":y='(H-h)/2'" in result


def test_smart_pad_filter_xy_single_quoted() -> None:
    """X and Y expressions are single-quoted to protect commas."""
    from reeln.core.zoom import build_smart_pad_filter

    path = _make_zoom_path()
    result = build_smart_pad_filter(path, 1080, 1920)
    assert result.startswith("overlay=x='")
    assert ":y='" in result


# ---------------------------------------------------------------------------
# build_smart_pad_graph (multi-stream overlay graph)
# ---------------------------------------------------------------------------


def test_smart_pad_graph_structure() -> None:
    from reeln.core.zoom import build_smart_pad_graph

    path = _make_zoom_path()
    result = build_smart_pad_graph(
        pre_filters=["scale=1080:-2:flags=lanczos"],
        zoom_path=path,
        target_width=1080,
        target_height=1920,
    )
    # colour background source (default 30fps)
    assert "color=c=black:s=1080x1920:r=30/1[_bg]" in result
    # pre-filters on input
    assert "[0:v]scale=1080:-2:flags=lanczos[_fg]" in result
    # overlay
    assert "[_bg][_fg]overlay=" in result
    assert ":eval=frame" in result


def test_smart_pad_graph_custom_color() -> None:
    from reeln.core.zoom import build_smart_pad_graph

    path = _make_zoom_path()
    result = build_smart_pad_graph(
        pre_filters=["scale=1080:-2:flags=lanczos"],
        zoom_path=path,
        target_width=1080,
        target_height=1920,
        pad_color="white",
    )
    assert "color=c=white:s=1080x1920" in result


def test_smart_pad_graph_with_post_filters() -> None:
    from reeln.core.zoom import build_smart_pad_graph

    path = _make_zoom_path()
    result = build_smart_pad_graph(
        pre_filters=["scale=1080:-2:flags=lanczos"],
        zoom_path=path,
        target_width=1080,
        target_height=1920,
        post_filters=["subtitles=f=subs.ass"],
    )
    # subtitle in a separate filter stage via stream label with format buffer
    assert "[_ov]" in result
    assert result.endswith("[_ov]format=yuv420p,subtitles=f=subs.ass")


def test_smart_pad_graph_no_pre_filters() -> None:
    from reeln.core.zoom import build_smart_pad_graph

    path = _make_zoom_path()
    result = build_smart_pad_graph(
        pre_filters=[],
        zoom_path=path,
        target_width=1080,
        target_height=1920,
    )
    assert "[0:v]null[_fg]" in result


def test_smart_pad_graph_custom_fps() -> None:
    from reeln.core.zoom import build_smart_pad_graph

    path = _make_zoom_path()
    result = build_smart_pad_graph(
        pre_filters=["scale=1080:-2:flags=lanczos"],
        zoom_path=path,
        target_width=1080,
        target_height=1920,
        source_fps=60.0,
    )
    assert "color=c=black:s=1080x1920:r=60/1[_bg]" in result


def test_smart_pad_graph_fractional_fps() -> None:
    from reeln.core.zoom import build_smart_pad_graph

    path = _make_zoom_path()
    result = build_smart_pad_graph(
        pre_filters=["scale=1080:-2:flags=lanczos"],
        zoom_path=path,
        target_width=1080,
        target_height=1920,
        source_fps=59.94,
    )
    assert "r=2997/50[_bg]" in result


def test_smart_pad_graph_ntsc_fps() -> None:
    """NTSC 59.94005994… fps converts to exact 60000/1001 fraction."""
    from reeln.core.zoom import build_smart_pad_graph

    path = _make_zoom_path()
    result = build_smart_pad_graph(
        pre_filters=["scale=1080:-2:flags=lanczos"],
        zoom_path=path,
        target_width=1080,
        target_height=1920,
        source_fps=60000 / 1001,
    )
    assert "r=60000/1001[_bg]" in result


def test_fps_to_fraction_common_rates() -> None:
    """_fps_to_fraction recovers exact fractions for common video rates."""
    from reeln.core.zoom import _fps_to_fraction

    assert _fps_to_fraction(30.0) == "30/1"
    assert _fps_to_fraction(60.0) == "60/1"
    assert _fps_to_fraction(24.0) == "24/1"
    assert _fps_to_fraction(60000 / 1001) == "60000/1001"
    assert _fps_to_fraction(30000 / 1001) == "30000/1001"
    assert _fps_to_fraction(24000 / 1001) == "24000/1001"


def test_smart_pad_graph_square() -> None:
    from reeln.core.zoom import build_smart_pad_graph

    path = _make_zoom_path()
    result = build_smart_pad_graph(
        pre_filters=["scale=1080:-2:flags=lanczos"],
        zoom_path=path,
        target_width=1080,
        target_height=1080,
    )
    assert "s=1080x1080" in result


# ---------------------------------------------------------------------------
# build_filter_chain with SMART_PAD mode
# ---------------------------------------------------------------------------


def test_filter_chain_smart_pad_source_fps(tmp_path: Path) -> None:
    """Smart pad graph uses the provided source_fps for the color source."""
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD)
    path = _make_zoom_path()
    chain, _ = build_filter_chain(cfg, zoom_path=path, source_fps=60.0)
    assert "r=60/1[_bg]" in chain


def test_filter_chain_smart_pad_without_zoom_path_raises(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD)
    with pytest.raises(RenderError, match="Smart crop mode requires a zoom path"):
        build_filter_chain(cfg)


def test_filter_chain_smart_pad_with_zoom_path(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD)
    path = _make_zoom_path()
    chain, audio = build_filter_chain(cfg, zoom_path=path)
    # Smart pad scales by height (like crop) for horizontal panning room
    assert "scale=-2:1920:flags=lanczos" in chain
    assert "color=c=black:s=1080x1920" in chain
    assert "[_bg][_fg]overlay=" in chain
    assert audio is None


def test_filter_chain_smart_pad_with_speed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD, speed=0.5)
    path = _make_zoom_path()
    chain, audio = build_filter_chain(cfg, zoom_path=path)
    assert "setpts=PTS/0.5" in chain
    assert audio == "atempo=0.5"


def test_filter_chain_smart_pad_uses_pad_color(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD, pad_color="white")
    path = _make_zoom_path()
    chain, _ = build_filter_chain(cfg, zoom_path=path)
    assert "color=c=white" in chain


def test_filter_chain_smart_pad_no_final_scale(tmp_path: Path) -> None:
    """SMART_PAD should NOT have a final scale filter (overlay handles sizing)."""
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD)
    path = _make_zoom_path()
    chain, _ = build_filter_chain(cfg, zoom_path=path)
    # Should only have one scale filter (the initial pre-filter), not a final scale
    assert chain.count("scale=") == 1


def test_filter_chain_smart_pad_with_subtitle(tmp_path: Path) -> None:
    """Subtitle should be appended after overlay in the graph."""
    sub = tmp_path / "subs.ass"
    cfg = _cfg(tmp_path, crop_mode=CropMode.SMART_PAD, subtitle=sub)
    path = _make_zoom_path()
    chain, _ = build_filter_chain(cfg, zoom_path=path)
    assert f"subtitles=f={sub}" in chain
    assert chain.endswith(f"[_ov]format=yuv420p,subtitles=f={sub}")
