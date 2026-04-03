"""Piecewise linear interpolation and smart crop filter builders for zoom paths."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from reeln.models.profile import SpeedSegment
from reeln.models.zoom import ZoomPath

# ffmpeg's expression parser has a hard limit on total expression complexity.
# With pre-computed A*t+B coefficients, 8 segments is safe; beyond that the
# parser fails with "Missing ')' or too many args".
_MAX_LERP_SEGMENTS = 8


def _downsample(
    values: list[tuple[float, float]],
    max_points: int,
) -> list[tuple[float, float]]:
    """Reduce *values* to at most *max_points* by selecting evenly spaced entries.

    Always preserves the first and last points so interpolation covers the
    full time range.  Returns the original list unchanged when it is already
    within the limit.
    """
    if len(values) <= max_points:
        return values

    # Always keep first and last; distribute remaining slots evenly
    result: list[tuple[float, float]] = [values[0]]
    inner_slots = max_points - 2
    step = (len(values) - 1) / (inner_slots + 1)
    for i in range(1, inner_slots + 1):
        idx = round(i * step)
        result.append(values[idx])
    result.append(values[-1])
    return result


def build_piecewise_lerp(
    values: list[tuple[float, float]],
    total_duration: float,
    time_expr: str = "t",
) -> str:
    """Build a flat ffmpeg expression for piecewise linear interpolation.

    *values* is a list of ``(timestamp, value)`` pairs, sorted by timestamp.
    Returns an ffmpeg expression that linearly interpolates between consecutive
    pairs, clamping to the last value after the final timestamp.

    Uses a sum-of-products approach (``lt()*lerp + gte()*lt()*lerp + ...``)
    instead of nested ``if()`` calls to avoid hitting ffmpeg's expression
    parser nesting depth limit with many zoom points.

    For a single point, returns the constant value.
    """
    if not values:
        return "0"

    if len(values) == 1:
        return str(values[0][1])

    # Downsample to stay within ffmpeg expression parser limits.
    # _MAX_LERP_SEGMENTS segments need _MAX_LERP_SEGMENTS + 1 points.
    values = _downsample(values, _MAX_LERP_SEGMENTS + 1)

    terms: list[str] = []

    def _fmt(v: float) -> str:
        """Format a float, rounding to 6 decimal places and stripping trailing zeros."""
        return f"{v:.6f}".rstrip("0").rstrip(".")

    for i in range(len(values) - 1):
        t_i, v_i = values[i]
        t_next, v_next = values[i + 1]
        dt = t_next - t_i

        if dt == 0:
            lerp = _fmt(v_i)
        else:
            # Pre-compute slope (A) and intercept (B) so lerp = A*t+B
            # instead of (V+DV*(t-T)/DT) — roughly halves expression length.
            a = (v_next - v_i) / dt
            b = v_i - a * t_i
            lerp = f"({_fmt(a)}*{time_expr}+{_fmt(b)})"

        if i == 0:
            # First segment: covers t < t_next (includes extrapolation before t0)
            terms.append(f"lt({time_expr},{_fmt(t_next)})*{lerp}")
        else:
            # Middle segments: gte(t, t_i) AND lt(t, t_next)
            terms.append(f"gte({time_expr},{_fmt(t_i)})*lt({time_expr},{_fmt(t_next)})*{lerp}")

    # Clamp to last value after final timestamp
    terms.append(f"gte({time_expr},{_fmt(values[-1][0])})*{_fmt(values[-1][1])}")

    return "+".join(terms)


def build_smart_crop_filter(
    zoom_path: ZoomPath,
    target_width: int,
    target_height: int,
) -> str:
    """Build a dynamic crop filter expression from a zoom path.

    Generates an ffmpeg ``crop=w:h:x:y`` filter where x and y use
    piecewise-lerp expressions derived from the zoom points. The crop
    region is clamped to source bounds.

    The input is assumed to already be scaled so that its height matches
    the source aspect (scale=-2:source_height). The crop extracts a
    vertical slice of width ``ih*target_width/target_height``.
    """
    crop_w = f"ih*{target_width}/{target_height}"
    crop_h = "ih"

    # Build x interpolation from center_x values
    # center_x is normalized 0-1. Map to pixel x offset:
    #   x = center_x * (iw - crop_w) clamped to [0, iw - crop_w]
    x_values = [(p.timestamp, p.center_x) for p in zoom_path.points]
    x_lerp = build_piecewise_lerp(x_values, zoom_path.duration)
    x_expr = f"max(0,min(iw-{crop_w},({x_lerp})*(iw-{crop_w})))"

    # Build y interpolation from center_y values
    y_values = [(p.timestamp, p.center_y) for p in zoom_path.points]
    y_lerp = build_piecewise_lerp(y_values, zoom_path.duration)
    y_expr = f"max(0,min(ih-{crop_h},({y_lerp})*(ih-{crop_h})))"

    # Single-quote each value so ffmpeg's filter parser doesn't split on
    # the commas inside if()/max()/min() function arguments.
    return f"crop=w='{crop_w}':h='{crop_h}':x='{x_expr}':y='{y_expr}'"


def build_smart_pad_filter(
    zoom_path: ZoomPath,
    target_width: int,
    target_height: int,
    pad_color: str = "black",
) -> str:
    """Build a dynamic overlay-based pad filter that follows the action.

    The ``pad`` filter's expression evaluator does not support the ``t``
    variable even with ``eval=frame``, so we use ``overlay`` on a generated
    colour background instead.  The returned string is an **overlay
    expression** (not a pad filter) that expects the scaled video as its
    second overlay input — callers must wire it into a multi-stream
    ``filter_complex`` graph.

    Only the horizontal axis (center_x) tracks the action — vertical
    position stays centered.  Vertical tracking would be disorienting
    in pad mode; it only makes sense when zooming in (crop mode).

    ``build_smart_pad_graph`` wraps this into the full multi-stream graph.
    """
    # Build x interpolation from center_x values.
    # center_x is 0-1 in the original frame.  We want the action point
    # centred horizontally: x = W/2 - center_x * w.
    # The video is wider than the background (scaled by height), so x
    # ranges from (W-w) to 0 (both ≤ 0).  Clamp accordingly.
    x_values = [(p.timestamp, p.center_x) for p in zoom_path.points]
    x_lerp = build_piecewise_lerp(x_values, zoom_path.duration)
    x_expr = f"min(0,max(W-w,W/2-({x_lerp})*w))"

    return f"overlay=x='{x_expr}':y='(H-h)/2':eval=frame:shortest=1"


def remap_zoom_path_for_speed_segments(
    zoom_path: ZoomPath,
    segments: tuple[SpeedSegment, ...],
) -> ZoomPath:
    """Remap zoom path timestamps from source time to output time.

    After speed_segments processing the output timeline differs from the
    source because segments run at different speeds.  This adjusts each
    zoom point's timestamp so ``t``-based ffmpeg expressions align with
    the rendered output.
    """

    def _source_to_output(source_t: float) -> float:
        output_t = 0.0
        prev = 0.0
        for seg in segments:
            end = seg.until if seg.until is not None else source_t
            if source_t <= end:
                output_t += (source_t - prev) / seg.speed
                return output_t
            output_t += (end - prev) / seg.speed
            prev = end
        return output_t

    remapped = tuple(replace(p, timestamp=_source_to_output(p.timestamp)) for p in zoom_path.points)
    new_duration = _source_to_output(zoom_path.duration)
    return replace(zoom_path, points=remapped, duration=new_duration)


def _fps_to_fraction(fps: float) -> str:
    """Convert an fps float to an exact fraction string for ffmpeg.

    Uses ``fractions.Fraction`` with a denominator limit to recover common
    NTSC rates (e.g. 59.94… → ``60000/1001``, 29.97… → ``30000/1001``)
    without floating-point truncation artifacts.
    """
    frac = Fraction(fps).limit_denominator(10000)
    return f"{frac.numerator}/{frac.denominator}"


def build_smart_pad_graph(
    pre_filters: list[str],
    zoom_path: ZoomPath,
    target_width: int,
    target_height: int,
    pad_color: str = "black",
    *,
    post_filters: list[str] | None = None,
    source_fps: float = 30.0,
) -> str:
    """Build a full ``filter_complex`` graph for smart pad mode.

    The ``pad`` filter cannot evaluate ``t``-based expressions, so we
    generate a colour background source and ``overlay`` the scaled video
    on top with per-frame y positioning.

    *pre_filters* are applied to ``[0:v]`` before the overlay (e.g. LUT,
    speed, scale).  *post_filters* are appended after the overlay (e.g.
    subtitle).

    Returns a complete ``filter_complex`` string with stream labels.
    """
    overlay_expr = build_smart_pad_filter(
        zoom_path,
        target_width,
        target_height,
        pad_color,
    )

    pre_chain = ",".join(pre_filters) if pre_filters else "null"
    fps_frac = _fps_to_fraction(source_fps)
    parts = [
        f"color=c={pad_color}:s={target_width}x{target_height}:r={fps_frac}[_bg]",
        f"[0:v]{pre_chain}[_fg]",
        f"[_bg][_fg]{overlay_expr}",
    ]

    if post_filters:
        # Pipe through format=yuv420p as a buffer between the overlay
        # and post-filters — directly comma-chaining or using stream
        # labels after the single-quoted overlay expression confuses
        # ffmpeg's graph-level parser.
        parts[-1] = f"{parts[-1]}[_ov]"
        parts.append(f"[_ov]format=yuv420p,{','.join(post_filters)}")

    return ";".join(parts)
