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


def _smooth_moving_average(
    values: list[tuple[float, float]],
    window: int = 3,
) -> list[tuple[float, float]]:
    """Smooth value coordinates with a centered moving average.

    Returns a new list with the original timestamps but averaged values.
    Per-frame vision detectors (e.g. OpenAI ``smart_zoom``) produce one
    independent prediction per frame; an outlier prediction can land in
    the downsampled keyframe set and create a visible jump between
    consecutive interpolation segments. A short moving average flattens
    isolated spikes while leaving smooth trajectories essentially
    unchanged.

    The first and last points are anchored unchanged so the path still
    covers the full time range exactly. Window must be odd and ≥ 3;
    asymmetric windows are used at edges so no value is dropped.
    """
    n = len(values)
    if n <= 2 or window < 3:
        return list(values)

    half = window // 2
    result: list[tuple[float, float]] = [values[0]]
    for i in range(1, n - 1):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        avg = sum(v for _, v in values[lo:hi]) / (hi - lo)
        result.append((values[i][0], avg))
    result.append(values[-1])
    return result


def _catmull_rom_resample(
    values: list[tuple[float, float]],
    num_samples: int,
) -> list[tuple[float, float]]:
    """Resample a path with uniform Catmull-Rom splines for smooth velocity.

    Returns *num_samples* points evenly spaced in time along the smooth
    spline through *values*. Endpoint timestamps are anchored exactly so
    the time range matches the input.

    Why this matters: linear interpolation between keyframes gives
    continuous position but discontinuous velocity — the camera kicks
    sideways at every keyframe. Catmull-Rom is C¹-continuous so velocity
    transitions smoothly through every interior keyframe, which is what
    eliminates the "choppy tracking" feel.

    Boundary segments duplicate the endpoint to fabricate the missing
    neighbour (standard "natural" Catmull-Rom). Inputs shorter than four
    points fall back to linear interpolation — Catmull-Rom needs four
    control points per segment.
    """
    n = len(values)
    if n < 2 or num_samples < 2:
        return list(values)

    t_start = values[0][0]
    t_end = values[-1][0]
    if t_end <= t_start:
        return list(values)

    # Pre-sort by timestamp defensively — pathologically ordered inputs
    # would otherwise return out-of-bounds segment indices.
    sorted_vals = sorted(values, key=lambda p: p[0])
    timestamps = [p[0] for p in sorted_vals]
    samples = [p[1] for p in sorted_vals]

    def _segment_value(i: int, u: float) -> float:
        """Evaluate the Catmull-Rom segment between samples[i] and samples[i+1]."""
        p0 = samples[i - 1] if i > 0 else samples[i]
        p1 = samples[i]
        p2 = samples[i + 1]
        p3 = samples[i + 2] if i + 2 < n else samples[i + 1]
        u2 = u * u
        u3 = u2 * u
        return 0.5 * (
            2 * p1
            + (-p0 + p2) * u
            + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2
            + (-p0 + 3 * p1 - 3 * p2 + p3) * u3
        )

    result: list[tuple[float, float]] = []
    seg_idx = 0
    for k in range(num_samples):
        # Anchor exact endpoints to avoid floating drift on the last sample.
        if k == 0:
            result.append((t_start, samples[0]))
            continue
        if k == num_samples - 1:
            result.append((t_end, samples[-1]))
            continue
        t = t_start + (t_end - t_start) * k / (num_samples - 1)
        # Advance segment pointer to the segment containing t. Monotone
        # walk because samples (k) move forward.
        while seg_idx + 1 < n - 1 and timestamps[seg_idx + 1] < t:
            seg_idx += 1
        t0 = timestamps[seg_idx]
        t1 = timestamps[seg_idx + 1]
        u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
        # Clamp u into [0,1] in case of float wiggle near segment boundary.
        if u < 0.0:
            u = 0.0
        elif u > 1.0:
            u = 1.0
        result.append((t, _segment_value(seg_idx, u)))
    return result


def _smooth_and_downsample_for_lerp(
    values: list[tuple[float, float]],
    max_points: int,
) -> list[tuple[float, float]]:
    """Pre-process a path for ``build_piecewise_lerp``.

    Pipeline: window-3 moving average → Catmull-Rom resample to a dense
    curve → evenly-spaced downsample to *max_points*. Result: the kept
    keypoints lie on a C¹-continuous spline, so ffmpeg's linear segments
    between them give smooth-feeling motion instead of the visible
    velocity kicks that the previous straight downsample produced.

    No-op when *values* already fits within the segment limit — explicit
    user keyframes pass through unchanged.
    """
    if len(values) <= max_points:
        return list(values)
    smoothed = _smooth_moving_average(values, window=3)
    # Dense enough that the downsampled 9 points land on a curve almost
    # indistinguishable from the full spline -- 5x max_points is plenty.
    dense_count = max(max_points * 5, 30)
    dense = _catmull_rom_resample(smoothed, dense_count)
    return _downsample(dense, max_points)


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

    # Smooth + Catmull-Rom resample before downsampling so the kept
    # keypoints lie on a C¹-continuous curve. Without this step the
    # output keeps raw keyframes whose velocity at junctions changes
    # abruptly — the "choppy tracking" feel users see at zoom_frames=16+.
    # ``_smooth_and_downsample_for_lerp`` is a no-op when the input
    # already fits the ffmpeg segment limit, so explicit short paths
    # are preserved exactly.
    values = _smooth_and_downsample_for_lerp(values, _MAX_LERP_SEGMENTS + 1)

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
