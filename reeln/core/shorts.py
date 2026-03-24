"""Filter graph builders and render planning for short-form video."""

from __future__ import annotations

from pathlib import Path

from reeln.core.errors import RenderError
from reeln.models.profile import SpeedSegment
from reeln.models.render_plan import RenderPlan
from reeln.models.short import CropMode, ShortConfig
from reeln.models.zoom import ZoomPath

_VALID_LUT_SUFFIXES: set[str] = {".cube", ".3dl"}
_VALID_SUBTITLE_SUFFIXES: set[str] = {".ass"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_short_config(config: ShortConfig) -> None:
    """Validate a ShortConfig, raising ``RenderError`` on invalid values."""
    if config.width <= 0:
        raise RenderError(f"Width must be positive, got {config.width}")
    if config.width % 2 != 0:
        raise RenderError(f"Width must be even, got {config.width}")
    if config.height <= 0:
        raise RenderError(f"Height must be positive, got {config.height}")
    if config.height % 2 != 0:
        raise RenderError(f"Height must be even, got {config.height}")
    if not 0.5 <= config.speed <= 2.0:
        raise RenderError(f"Speed must be 0.5-2.0, got {config.speed}")
    if not 0.0 <= config.anchor_x <= 1.0:
        raise RenderError(f"Anchor X must be 0.0-1.0, got {config.anchor_x}")
    if not 0.0 <= config.anchor_y <= 1.0:
        raise RenderError(f"Anchor Y must be 0.0-1.0, got {config.anchor_y}")
    if not 0.5 <= config.scale <= 3.0:
        raise RenderError(f"Scale must be 0.5-3.0, got {config.scale}")
    if not 1 <= config.smart_zoom_frames <= 20:
        raise RenderError(f"Smart zoom frames must be 1-20, got {config.smart_zoom_frames}")
    if config.lut is not None and config.lut.suffix.lower() not in _VALID_LUT_SUFFIXES:
        raise RenderError(f"LUT file must be .cube or .3dl, got {config.lut.suffix!r}")
    if config.subtitle is not None and config.subtitle.suffix.lower() not in _VALID_SUBTITLE_SUFFIXES:
        raise RenderError(f"Subtitle file must be .ass, got {config.subtitle.suffix!r}")
    if config.branding is not None and config.branding.suffix.lower() not in _VALID_SUBTITLE_SUFFIXES:
        raise RenderError(f"Branding file must be .ass, got {config.branding.suffix!r}")
    if config.speed_segments is not None and config.speed != 1.0:
        raise RenderError("Cannot use both speed and speed_segments — they are mutually exclusive")
    if config.speed_segments is not None:
        validate_speed_segments(config.speed_segments)


def validate_speed_segments(segments: tuple[SpeedSegment, ...]) -> None:
    """Validate speed segment list.

    Rules:
    - At least 2 segments (otherwise use scalar ``speed``)
    - All segments except the last must have ``until`` set
    - Last segment must have ``until=None``
    - ``until`` values must be strictly increasing and positive
    - All speeds must be in [0.25, 4.0] range
    """
    if len(segments) < 2:
        raise RenderError("speed_segments requires at least 2 segments (use scalar speed for uniform speed)")
    for i, seg in enumerate(segments):
        if not 0.25 <= seg.speed <= 4.0:
            raise RenderError(f"speed_segments[{i}]: speed must be 0.25-4.0, got {seg.speed}")
    for i, seg in enumerate(segments[:-1]):
        if seg.until is None:
            raise RenderError(f"speed_segments[{i}]: all segments except the last must have 'until' set")
        if seg.until <= 0:
            raise RenderError(f"speed_segments[{i}]: 'until' must be positive, got {seg.until}")
    if segments[-1].until is not None:
        raise RenderError("speed_segments: last segment must have until=None (runs to end of clip)")
    prev_until = 0.0
    for i, seg in enumerate(segments[:-1]):
        assert seg.until is not None
        if seg.until <= prev_until:
            raise RenderError(
                f"speed_segments[{i}]: 'until' values must be strictly increasing, "
                f"got {seg.until} after {prev_until}"
            )
        prev_until = seg.until


# ---------------------------------------------------------------------------
# Individual filter builders
# ---------------------------------------------------------------------------


def _round_even(value: int) -> int:
    """Round *value* up to the nearest even integer."""
    return value + (value % 2)


def build_scale_filter(*, crop_mode: CropMode, target_width: int, target_height: int, scale: float = 1.0) -> str:
    """Build the initial scale filter for pad or crop mode.

    Pad mode scales to target width (content fits within frame).
    Crop mode scales to target height (content fills the frame).

    When *scale* > 1.0 the intermediate dimensions are larger, producing
    a zoom-in effect after subsequent crop/pad.
    """
    if crop_mode == CropMode.PAD:
        w = _round_even(int(target_width * scale))
        return f"scale={w}:-2:flags=lanczos"
    h = _round_even(int(target_height * scale))
    return f"scale=-2:{h}:flags=lanczos"


def build_overflow_crop_filter(*, target_width: int, target_height: int) -> str:
    """Crop to target dimensions when the intermediate frame overflows.

    Used with pad + scale > 1.0: after scaling up and before padding,
    crop any overflow back to target size (centered).
    """
    return (
        f"crop=w='min(iw,{target_width})':h='min(ih,{target_height})':"
        f"x='(iw-min(iw,{target_width}))/2':y='(ih-min(ih,{target_height}))/2'"
    )


def build_pad_filter(*, target_width: int, target_height: int, pad_color: str) -> str:
    """Build a pad filter to center content within the target frame."""
    return f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:{pad_color}"


def build_crop_filter(*, target_width: int, target_height: int, anchor_x: float, anchor_y: float) -> str:
    """Build a crop filter to extract a region from the scaled frame.

    Uses the anchor_x position for horizontal crop offset.
    The anchor_y is reserved for future vertical crop scenarios.
    """
    return f"crop=w=ih*{target_width}/{target_height}:h=ih:x=(iw-ih*{target_width}/{target_height})*{anchor_x}:y=0"


def build_final_scale_filter(*, target_width: int, target_height: int) -> str:
    """Build a final scale filter to ensure exact output dimensions after crop."""
    return f"scale={target_width}:{target_height}:flags=lanczos"


def build_speed_filter(speed: float) -> str:
    """Build a video speed (setpts) filter."""
    return f"setpts=PTS/{speed}"


def build_audio_speed_filter(speed: float) -> str:
    """Build an audio speed (atempo) filter."""
    return f"atempo={speed}"


def build_lut_filter(lut_path: Path) -> str:
    """Build a LUT color grading filter."""
    return f"lut3d={_escape_filter_path(lut_path)}"


def _escape_filter_path(path: Path) -> str:
    """Escape a file path for use in ffmpeg filter option values.

    ffmpeg's filter parser treats several characters as special inside
    filter option values.  Each must be backslash-escaped so the path
    is treated literally — no wrapping single quotes needed.

    Escaped characters: ``\\``, ``:``, ``'``, ``[``, ``]``, ``;``, ``,``.
    """
    s = str(path)
    # Order matters: escape backslash first to avoid double-escaping
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    s = s.replace("[", "\\[")
    s = s.replace("]", "\\]")
    s = s.replace(";", "\\;")
    s = s.replace(",", "\\,")
    return s


def build_subtitle_filter(subtitle_path: Path) -> str:
    """Build an ASS subtitle overlay filter.

    Uses the ``subtitles`` filter (not ``ass``) for broader ffmpeg
    compatibility — homebrew and other builds sometimes omit the ``ass``
    filter alias.  The explicit ``f=`` option key avoids positional
    argument issues in multi-segment ``-filter_complex`` graphs.
    """
    return f"subtitles=f={_escape_filter_path(subtitle_path)}"


# ---------------------------------------------------------------------------
# Variable-speed segment filters
# ---------------------------------------------------------------------------


def _build_atempo_chain(speed: float) -> str:
    """Build chained atempo filters for speeds outside [0.5, 100.0].

    ffmpeg's ``atempo`` filter accepts values in [0.5, 100.0].  For speeds
    below 0.5, chain multiple ``atempo=0.5`` filters to reach the target.
    """
    if 0.5 <= speed <= 100.0:
        return f"atempo={speed}"
    parts: list[str] = []
    remaining = speed
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining}")
    return ",".join(parts)


def compute_speed_segments_duration(
    segments: tuple[SpeedSegment, ...],
    source_duration: float,
) -> float:
    """Compute output duration after applying speed segments to a source clip.

    Each segment's source-time span is divided by its speed to get the output
    duration.  The last segment (``until=None``) runs to *source_duration*.
    """
    total = 0.0
    prev = 0.0
    for seg in segments:
        end = seg.until if seg.until is not None else source_duration
        span = max(0.0, end - prev)
        total += span / seg.speed
        prev = end
    return total


def build_speed_segments_filters(
    segments: tuple[SpeedSegment, ...],
) -> tuple[str, str]:
    """Build video and audio filter graph fragments for variable-speed segments.

    Returns ``(video_fragment, audio_fragment)`` — both are semicolon-separated
    filter_complex fragments with stream labels.

    Video pattern:
      [_vsrc]split=N[v0]...[vN-1];
      [v0]trim=0:5,setpts=PTS-STARTPTS,setpts=PTS/speed[sv0]; ...
      [sv0]...[svN-1]concat=n=N:v=1:a=0[_vout]

    Audio pattern:
      [_asrc]asplit=N[a0]...[aN-1];
      [a0]atrim=0:5,asetpts=PTS-STARTPTS,atempo=speed[sa0]; ...
      [sa0]...[saN-1]concat=n=N:v=0:a=1[_aout]
    """
    n = len(segments)

    # Build time boundaries
    boundaries: list[tuple[float | None, float | None]] = []
    prev = 0.0
    for seg in segments:
        boundaries.append((prev, seg.until))
        prev = seg.until if seg.until is not None else prev

    # Video split
    v_labels = [f"[v{i}]" for i in range(n)]
    sv_labels = [f"[sv{i}]" for i in range(n)]
    video_parts: list[str] = [f"[_vsrc]split={n}{''.join(v_labels)}"]

    for i, (seg, (start, end)) in enumerate(zip(segments, boundaries, strict=True)):
        trim = f"trim={start}" if end is None else f"trim={start}:{end}"
        chain = [trim, "setpts=PTS-STARTPTS"]
        if seg.speed != 1.0:
            chain.append(f"setpts=PTS/{seg.speed}")
        video_parts.append(f"{v_labels[i]}{',' .join(chain)}{sv_labels[i]}")

    video_parts.append(f"{''.join(sv_labels)}concat=n={n}:v=1:a=0[_vout]")

    # Audio split
    a_labels = [f"[a{i}]" for i in range(n)]
    sa_labels = [f"[sa{i}]" for i in range(n)]
    audio_parts: list[str] = [f"[_asrc]asplit={n}{''.join(a_labels)}"]

    for i, (seg, (start, end)) in enumerate(zip(segments, boundaries, strict=True)):
        atrim = f"atrim={start}" if end is None else f"atrim={start}:{end}"
        chain = [atrim, "asetpts=PTS-STARTPTS"]
        if seg.speed != 1.0:
            chain.append(_build_atempo_chain(seg.speed))
        audio_parts.append(f"{a_labels[i]}{',' .join(chain)}{sa_labels[i]}")

    audio_parts.append(f"{''.join(sa_labels)}concat=n={n}:v=0:a=1[_aout]")

    return ";".join(video_parts), ";".join(audio_parts)


# ---------------------------------------------------------------------------
# Filter chain assembly
# ---------------------------------------------------------------------------


def _resolve_smart(crop_mode: CropMode, smart: bool) -> tuple[CropMode, bool]:
    """Translate deprecated SMART/SMART_PAD enums to effective mode + smart flag.

    Returns ``(effective_crop_mode, is_smart)`` where *effective_crop_mode* is
    always ``PAD`` or ``CROP``.
    """
    if crop_mode == CropMode.SMART:
        return CropMode.CROP, True
    if crop_mode == CropMode.SMART_PAD:
        return CropMode.PAD, True
    return crop_mode, smart


def build_filter_chain(
    config: ShortConfig,
    *,
    zoom_path: ZoomPath | None = None,
    source_fps: float = 30.0,
) -> tuple[str, str | None]:
    """Assemble the full video filter chain and optional audio filter.

    Filter ordering: LUT -> speed -> scale -> overflow_crop -> pad/crop -> final_scale -> subtitle.

    The chain is driven by two orthogonal axes:
    - **Framing:** ``PAD`` or ``CROP`` (deprecated ``SMART``/``SMART_PAD`` are translated).
    - **Scale:** multiplier applied to the initial scale dimensions (1.0 = no zoom).

    When *zoom_path* is provided and smart mode is active, dynamic crop/pad
    expressions replace the static anchor-based alternatives.

    Returns ``(filter_complex_string, audio_filter_or_none)``.
    """
    from reeln.core.zoom import build_smart_crop_filter, build_smart_pad_graph

    effective_crop, is_smart = _resolve_smart(config.crop_mode, config.smart)

    if is_smart and zoom_path is None:
        raise RenderError(
            "Smart crop mode requires a zoom path from a vision plugin. "
            "Ensure a plugin providing ON_FRAMES_EXTRACTED analysis is enabled."
        )

    # Variable-speed path: uses split/concat with stream labels
    if config.speed_segments is not None:
        return _build_speed_segments_chain(
            config,
            zoom_path=zoom_path if is_smart else None,
            source_fps=source_fps,
        )

    filters: list[str] = []

    # 1. LUT (color grade source first)
    if config.lut is not None:
        filters.append(build_lut_filter(config.lut))

    # 2. Speed (setpts before spatial transforms)
    if config.speed != 1.0:
        filters.append(build_speed_filter(config.speed))

    # 3. Scale (with scale factor)
    # Smart pad scales by height (like crop) so the video is wider than
    # the target — this gives the overlay horizontal room to pan.
    scale_mode = CropMode.CROP if (effective_crop == CropMode.PAD and is_smart) else effective_crop
    filters.append(
        build_scale_filter(
            crop_mode=scale_mode,
            target_width=config.width,
            target_height=config.height,
            scale=config.scale,
        )
    )

    # 4. Overflow crop (pad + scale > 1.0 only, not smart pad)
    if effective_crop == CropMode.PAD and not is_smart and config.scale > 1.0:
        filters.append(
            build_overflow_crop_filter(
                target_width=config.width,
                target_height=config.height,
            )
        )

    # 5. Crop or pad (static or smart)
    if effective_crop == CropMode.PAD and is_smart:
        # Smart pad uses overlay on a colour background because ffmpeg's
        # pad filter does not support the ``t`` variable in expressions.
        # build_smart_pad_graph returns a complete filter_complex string
        # with stream labels, so we return it directly instead of joining.
        assert zoom_path is not None  # guarded above
        post_filters: list[str] = []
        if config.subtitle is not None:
            post_filters.append(build_subtitle_filter(config.subtitle))
        if config.branding is not None:
            post_filters.append(build_subtitle_filter(config.branding))

        audio_filter: str | None = None
        if config.speed != 1.0:
            audio_filter = build_audio_speed_filter(config.speed)

        filter_complex = build_smart_pad_graph(
            pre_filters=filters,
            zoom_path=zoom_path,
            target_width=config.width,
            target_height=config.height,
            pad_color=config.pad_color,
            post_filters=post_filters or None,
            source_fps=source_fps,
        )
        return filter_complex, audio_filter

    if effective_crop == CropMode.PAD:
        filters.append(
            build_pad_filter(
                target_width=config.width,
                target_height=config.height,
                pad_color=config.pad_color,
            )
        )
    else:
        if is_smart:
            assert zoom_path is not None  # guarded above
            filters.append(build_smart_crop_filter(zoom_path, config.width, config.height))
        else:
            filters.append(
                build_crop_filter(
                    target_width=config.width,
                    target_height=config.height,
                    anchor_x=config.anchor_x,
                    anchor_y=config.anchor_y,
                )
            )
        # 6. Final scale (crop mode only — ensures exact output dimensions)
        filters.append(build_final_scale_filter(target_width=config.width, target_height=config.height))

    # 7. Subtitle (render at output resolution)
    if config.subtitle is not None:
        filters.append(build_subtitle_filter(config.subtitle))

    # 8. Branding (after subtitle)
    if config.branding is not None:
        filters.append(build_subtitle_filter(config.branding))

    filter_complex = ",".join(filters)

    # Audio filter
    audio_filter = None
    if config.speed != 1.0:
        audio_filter = build_audio_speed_filter(config.speed)

    return filter_complex, audio_filter


def _build_speed_segments_chain(
    config: ShortConfig,
    *,
    zoom_path: ZoomPath | None = None,
    source_fps: float = 30.0,
) -> tuple[str, str | None]:
    """Build a full filter_complex for speed_segments rendering.

    When speed_segments are active, video and audio both go through
    ``-filter_complex`` (audio_filter returns ``None``).

    When *zoom_path* is provided (smart pad mode), the post-concat video
    uses ``overlay`` on a colour background with ``t``-based panning
    expressions — the same approach as ``build_smart_pad_graph`` but
    wired after the speed-segments concat instead of directly from
    ``[0:v]``.

    Graph structure (static):
      [0:v]{pre},split=N... → trim/speed → concat → {post} [vfinal]
      [0:a]asplit=N... → atrim/atempo → concat [afinal]

    Graph structure (smart pad):
      [0:v]{pre},split=N... → trim/speed → concat → scale [_fg]
      color=...[_bg]; [_bg][_fg]overlay=...[vfinal]  (or with subtitle)
      [0:a]asplit=N... → atrim/atempo → concat [afinal]
    """
    from reeln.core.zoom import build_smart_pad_filter

    assert config.speed_segments is not None
    effective_crop, is_smart = _resolve_smart(config.crop_mode, config.smart)
    use_smart_pad = effective_crop == CropMode.PAD and is_smart and zoom_path is not None

    # Pre-speed filters (applied to source before split)
    pre: list[str] = []
    if config.lut is not None:
        pre.append(build_lut_filter(config.lut))

    # Post-speed filters (applied after concat)
    post: list[str] = []

    # Scale — PAD mode uses height-based scaling (same as smart pad) so
    # landscape sources fill the frame vertically.  After scale, overflow
    # crop clips the horizontal excess to target_width.
    if effective_crop == CropMode.PAD:
        post.append(
            build_scale_filter(
                crop_mode=CropMode.CROP,
                target_width=config.width,
                target_height=config.height,
                scale=config.scale,
            )
        )
        if not use_smart_pad:
            post.append(
                build_overflow_crop_filter(
                    target_width=config.width,
                    target_height=config.height,
                )
            )
    else:
        post.append(
            build_scale_filter(
                crop_mode=effective_crop,
                target_width=config.width,
                target_height=config.height,
                scale=config.scale,
            )
        )

    if use_smart_pad:
        # Smart pad after speed_segments: overlay on colour background.
        # Post-filters so far contain only scale (height-based).
        # We label the scaled output [_fg], generate a colour source [_bg],
        # and overlay with t-based expressions.
        assert zoom_path is not None

        video_segs, audio_segs = build_speed_segments_filters(config.speed_segments)

        # Wire pre-filters into the video source label
        if pre:
            video_graph = video_segs.replace("[_vsrc]", f"[0:v]{','.join(pre)},", 1)
        else:
            video_graph = video_segs.replace("[_vsrc]", "[0:v]", 1)

        # Wire post-filters (scale) after concat, label [_fg]
        video_graph = video_graph.replace(
            "[_vout]", f"[_vout];[_vout]{','.join(post)}[_fg]",
        )

        # Colour background and overlay
        from reeln.core.zoom import _fps_to_fraction

        fps_frac = _fps_to_fraction(source_fps)
        overlay_expr = build_smart_pad_filter(
            zoom_path, config.width, config.height, config.pad_color,
        )

        color_part = f"color=c={config.pad_color}:s={config.width}x{config.height}:r={fps_frac}[_bg]"
        overlay_part = f"[_bg][_fg]{overlay_expr}"

        post_overlay: list[str] = []
        if config.subtitle is not None:
            post_overlay.append(build_subtitle_filter(config.subtitle))
        if config.branding is not None:
            post_overlay.append(build_subtitle_filter(config.branding))

        if post_overlay:
            overlay_part = f"{overlay_part}[_ov];[_ov]format=yuv420p,{','.join(post_overlay)}[vfinal]"
        else:
            overlay_part = f"{overlay_part}[vfinal]"

        video_graph = f"{video_graph};{color_part};{overlay_part}"

        # Audio
        audio_graph = audio_segs.replace("[_asrc]", "[0:a]", 1)
        audio_graph = audio_graph.replace("[_aout]", "[afinal]")

        return f"{video_graph};{audio_graph}", None

    # Crop or pad (static)
    if effective_crop == CropMode.PAD:
        post.append(
            build_pad_filter(
                target_width=config.width,
                target_height=config.height,
                pad_color=config.pad_color,
            )
        )
    else:
        if is_smart and zoom_path is not None:
            from reeln.core.zoom import build_smart_crop_filter

            post.append(build_smart_crop_filter(zoom_path, config.width, config.height))
        else:
            post.append(
                build_crop_filter(
                    target_width=config.width,
                    target_height=config.height,
                    anchor_x=config.anchor_x,
                    anchor_y=config.anchor_y,
                )
            )
        post.append(build_final_scale_filter(target_width=config.width, target_height=config.height))

    # Subtitle
    if config.subtitle is not None:
        post.append(build_subtitle_filter(config.subtitle))

    # Branding (after subtitle)
    if config.branding is not None:
        post.append(build_subtitle_filter(config.branding))

    video_segs, audio_segs = build_speed_segments_filters(config.speed_segments)

    # Wire pre-filters into the video source label
    if pre:
        # Replace [_vsrc] with [0:v]pre_filters
        video_graph = video_segs.replace("[_vsrc]", f"[0:v]{','.join(pre)},", 1)
    else:
        video_graph = video_segs.replace("[_vsrc]", "[0:v]", 1)

    # Wire post-filters after the concat output label
    # post always has at least scale + crop/pad
    video_graph = video_graph.replace("[_vout]", f"[_vout];[_vout]{','.join(post)}[vfinal]")

    # Wire audio source label — keep [afinal] for explicit mapping
    audio_graph = audio_segs.replace("[_asrc]", "[0:a]", 1)
    audio_graph = audio_graph.replace("[_aout]", "[afinal]")

    filter_complex = f"{video_graph};{audio_graph}"
    return filter_complex, None


# ---------------------------------------------------------------------------
# Plan builders
# ---------------------------------------------------------------------------


def plan_short(
    config: ShortConfig,
    *,
    zoom_path: ZoomPath | None = None,
    source_fps: float = 30.0,
) -> RenderPlan:
    """Create a RenderPlan for a short-form render."""
    validate_short_config(config)
    filter_complex, audio_filter = build_filter_chain(config, zoom_path=zoom_path, source_fps=source_fps)
    return RenderPlan(
        inputs=[config.input],
        output=config.output,
        codec=config.codec,
        preset=config.preset,
        crf=config.crf,
        width=config.width,
        height=config.height,
        audio_codec=config.audio_codec,
        audio_bitrate=config.audio_bitrate,
        filter_complex=filter_complex,
        audio_filter=audio_filter,
    )


def plan_preview(config: ShortConfig) -> RenderPlan:
    """Create a RenderPlan for a fast preview render.

    Uses half resolution, ultrafast preset, and crf=28 for speed.
    """
    validate_short_config(config)
    preview_width = config.width // 2
    preview_height = config.height // 2
    # Ensure even dimensions
    preview_width += preview_width % 2
    preview_height += preview_height % 2
    preview = ShortConfig(
        input=config.input,
        output=config.output,
        width=preview_width,
        height=preview_height,
        crop_mode=config.crop_mode,
        anchor_x=config.anchor_x,
        anchor_y=config.anchor_y,
        scale=config.scale,
        smart=config.smart,
        pad_color=config.pad_color,
        speed=config.speed,
        speed_segments=config.speed_segments,
        lut=config.lut,
        subtitle=config.subtitle,
        codec=config.codec,
        preset="ultrafast",
        crf=28,
        audio_codec=config.audio_codec,
        audio_bitrate=config.audio_bitrate,
        branding=config.branding,
    )
    filter_complex, audio_filter = build_filter_chain(preview)
    return RenderPlan(
        inputs=[preview.input],
        output=preview.output,
        codec=preview.codec,
        preset=preview.preset,
        crf=preview.crf,
        width=preview.width,
        height=preview.height,
        audio_codec=preview.audio_codec,
        audio_bitrate=preview.audio_bitrate,
        filter_complex=filter_complex,
        audio_filter=audio_filter,
    )
