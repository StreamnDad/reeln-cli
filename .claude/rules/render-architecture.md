---
globs: ["reeln/core/shorts.py", "reeln/core/zoom.py", "reeln/core/zoom_debug.py", "reeln/core/ffmpeg.py", "reeln/core/profiles.py", "reeln/core/iterations.py", "reeln/core/branding.py", "reeln/models/short.py", "reeln/models/zoom.py", "reeln/models/profile.py", "reeln/models/branding.py", "reeln/commands/render.py", "reeln/data/templates/**", "tests/**/test_shorts.py", "tests/**/test_zoom*.py", "tests/**/test_ffmpeg.py", "tests/**/test_profiles.py", "tests/**/test_iterations.py", "tests/**/test_branding.py", "tests/**/test_overlay.py", "tests/**/test_render.py"]
---

# Render Architecture

Short-form rendering (`reeln render short`) converts landscape source clips into
portrait (9:16) output. The system has several independent axes that compose freely.

## CLI Flags vs Profile Config — Scope Rules

CLI flags and render profile fields fall into two categories:

- **CLI flags** apply globally to the entire render, including all iterations.
  They are set once on the command line and cannot be overridden per-iteration.
- **Profile fields** can vary per iteration. Each profile in the iteration list
  can set different values.

| Parameter | CLI flag | Profile field | Scope |
|-----------|----------|---------------|-------|
| Framing | `--crop pad\|crop` | `crop_mode` | Per-profile |
| Scale | `--scale 0.5-3.0` | `scale` | Per-profile |
| Tracking | `--smart` | `smart` | **Global** — applies to all iterations |
| Zoom frames | `--zoom-frames 1-20` | — | Global (frame extraction happens once) |
| Speed | `--speed 0.5-2.0` | `speed` | Per-profile |
| Speed segments | — | `speed_segments` | Per-profile (config only, no CLI flag) |
| LUT | `--lut path.cube` | `lut` | Per-profile |
| Subtitle | `--subtitle path.ass` | `subtitle_template` | Per-profile |
| Anchor | `--anchor center` | `anchor_x`, `anchor_y` | Per-profile |
| Pad colour | `--pad-color black` | `pad_color` | Per-profile |
| Encoding | — | `codec`, `preset`, `crf` | Per-profile |

**Key rule:** `--smart` is a CLI flag that enables smart tracking for the entire
render. When iterating, every iteration gets smart tracking if `--smart` is set,
regardless of what profiles are configured. The vision plugin runs once, produces
a single `ZoomPath`, and that path is used (possibly remapped) for each iteration.

## Framing Modes

Two framing modes control how landscape source fits the 9:16 target:

- **PAD** (default) — scale source to fit width, pad top/bottom with solid colour.
  Content is fully visible but letterboxed.
- **CROP** — scale source to fill height, crop sides. Content fills the frame but
  edges are lost.

## Scale

`--scale` (0.5-3.0, default 1.0) zooms the content before framing:

- **Crop + scale > 1.0** — zoom in further, then crop to target.
- **Pad + scale > 1.0** — zoom in, overflow crop to target, then pad remaining space.

## Smart Tracking

`--smart` enables vision-based tracking. A plugin analyses extracted frames
and returns a `ZoomPath` (ordered `(timestamp, center_x, center_y)` points).
The filter chain uses `t`-based ffmpeg expressions to dynamically follow
the action.

- **Smart crop** — dynamic `crop=w:h:x:y` with `t`-based x/y from piecewise lerp.
  Both horizontal and vertical axes track the action.
- **Smart pad** — `overlay` on a generated `color` background with `t`-based x
  positioning. Only horizontal (center_x) tracks; vertical stays centred.
  ffmpeg's `pad` filter cannot evaluate the `t` variable, so overlay is required.

**Piecewise lerp** (`build_piecewise_lerp()`) builds flat sum-of-products
ffmpeg expressions with pre-computed `A*t+B` coefficients, downsampled to
8 segments max to stay within ffmpeg's expression parser limits.

**Fallback:** `--smart` without a vision plugin falls back to static centre
with a warning.

**Deprecated crop modes:** `--crop smart` -> `--crop crop --smart`,
`--crop smart_pad` -> `--crop pad --smart`. Old values still work but emit
a deprecation warning.

**Debug output:** `--debug --smart` creates `debug/zoom/` with
`frame_NNNN.png`, `annotated_NNNN.png` (crosshair + crop box), and
`zoom_path.json` (full zoom data + generated ffmpeg expressions).

## Filter Chain Order

Standard (single speed):
```
LUT -> speed (setpts) -> scale -> overflow_crop (pad + scale>1.0) -> crop/pad -> final_scale (crop only) -> subtitle
```

Smart pad replaces the crop/pad step with a multi-stream graph:
```
[0:v] LUT, speed, scale [_fg]
color=... [_bg]
[_bg][_fg] overlay(t-based x) -> subtitle
```

## Speed Segments

Variable speed within a single clip — e.g., normal for 5s, slowmo at 0.5x
for 3s, then back to normal. Configured as a profile field (no CLI flag):

```json
{
  "render_profiles": {
    "slowmo-middle": {
      "speed_segments": [
        {"until": 5.0, "speed": 1.0},
        {"until": 8.0, "speed": 0.5},
        {"speed": 1.0}
      ]
    }
  }
}
```

**Validation rules:**
- At least 2 segments (otherwise use scalar `speed`)
- All except last must have `until` set; last must have `until=None`
- `until` values strictly increasing and positive
- All speeds in [0.25, 4.0]
- Mutually exclusive with scalar `speed` (cannot use both)

**ffmpeg pattern:** `split=N -> trim per segment -> setpts=PTS-STARTPTS ->
setpts=PTS/{speed} -> concat`. Audio uses `asplit -> atrim -> asetpts ->
atempo -> concat`. Both video and audio go through `-filter_complex`
(no separate `-af`). Output streams labelled `[vfinal]` and `[afinal]`
with explicit `-map` flags.

**Audio atempo:** ffmpeg's `atempo` accepts [0.5, 100.0]. Speeds below 0.5
chain multiple `atempo=0.5` filters (e.g., 0.25 = `atempo=0.5,atempo=0.5`).

**Speed segments + smart tracking:** Fully supported. The zoom path timestamps
(in source time) are remapped to output time via `remap_zoom_path_for_speed_segments()`
so `t`-based ffmpeg expressions align with the stretched timeline. For smart pad,
the overlay is wired after the speed-segments concat:
```
[0:v] LUT, split=N -> trim/speed -> concat -> scale [_fg]
color=... [_bg]
[_bg][_fg] overlay(t-based x, remapped timestamps) [vfinal]
[0:a] asplit=N -> atrim/atempo -> concat [afinal]
```

**Speed segments + pad (static):** Uses height-based scaling (same as smart pad)
so landscape sources fill the frame vertically, then overflow crop + static pad.

**`compute_speed_segments_duration()`** calculates the output duration after
applying speed segments — used for per-iteration subtitle timing.

## Iterations

Multi-iteration rendering runs a single clip through N profiles sequentially
and concatenates the results. Configured via `iterations` in config:

```json
{
  "iterations": {
    "default": ["player-overlay", "slowmo-ten-second-clip"]
  }
}
```

Triggered with `--iterate` CLI flag. `render_iterations()` orchestrates:

1. Resolve all profiles up-front (fail fast on missing)
2. For each profile: apply overrides to ShortConfig, plan render, execute
3. Concatenate outputs (re-encode, not stream-copy, for filter compatibility)

**Per-iteration behaviour:**
- Subtitle templates are resolved per-iteration with duration adjusted for
  speed_segments (`compute_speed_segments_duration()`)
- Zoom path is remapped per-iteration when speed_segments are present
- Smart tracking applies to all iterations (CLI flag scope)
- Each profile can independently set crop_mode, scale, speed, LUT, subtitle

**Concatenation:** Uses `copy=False` (re-encode) because iterations may have
different filter chains (e.g., smart pad overlay vs speed_segments split/concat)
that produce incompatible codec parameters for stream-copy concat.

## Overlay / Subtitle Timing

Subtitle templates (`.ass` files) use absolute timestamps. When rendering:

- **Single render:** Duration probed from source clip
- **Iterations:** Duration computed per-iteration, accounting for speed_segments
  time stretch. `build_overlay_context()` sets `end_time = duration + 1.0`
  to ensure the overlay covers the full output.

## ZoomPath and fps

- `ZoomPath` — `(points, duration, source_width, source_height)`. Points are
  `(timestamp, center_x, center_y)` where x/y are normalised 0-1.
- Source fps is probed from extracted frames. Used for the `color` filter's
  `r=` parameter in smart pad to avoid fps mismatch (which causes black output).
- `_fps_to_fraction()` converts float fps to exact fractions via
  `Fraction.limit_denominator(10000)` — recovers NTSC rates like 60000/1001.

## Key Files

| File | Role |
|------|------|
| `reeln/models/short.py` | `ShortConfig`, `CropMode`, `OutputFormat` |
| `reeln/models/profile.py` | `RenderProfile`, `SpeedSegment`, `IterationConfig` |
| `reeln/models/zoom.py` | `ZoomPath`, `ZoomPoint`, `ExtractedFrames` |
| `reeln/core/shorts.py` | Filter builders, validation, `plan_short()`, `plan_preview()` |
| `reeln/core/zoom.py` | Piecewise lerp, smart crop/pad filters, zoom path remapping |
| `reeln/core/profiles.py` | Profile resolution, `apply_profile_to_short()`, `plan_full_frame()` |
| `reeln/core/iterations.py` | `render_iterations()` — multi-profile orchestration |
| `reeln/core/ffmpeg.py` | ffmpeg command builder, `-map` handling for `[vfinal]`/`[afinal]` |
| `reeln/commands/render.py` | CLI entry point, flag parsing, `_do_short()` |
