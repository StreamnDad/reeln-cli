# Profiles & Iterations

Render profiles save reusable rendering settings. Iterations chain multiple
profiles together for multi-pass rendering from a single command.

## Render profiles

Add profiles to the `render_profiles` section of your config:

```json
{
  "render_profiles": {
    "fullspeed": {
      "speed": 1.0
    },
    "slowmo": {
      "speed": 0.5
    },
    "goal-overlay": {
      "speed": 0.5,
      "subtitle_template": "builtin:goal_overlay"
    },
    "cinematic": {
      "crop_mode": "crop",
      "scale": 1.3,
      "speed": 0.5,
      "lut": "~/.config/reeln/luts/cinematic.cube",
      "crf": 16
    }
  }
}
```

### Use a profile

```bash
reeln render short clip.mkv --render-profile slowmo
reeln render short clip.mkv --render-profile cinematic
```

### Available profile fields

| Field | Type | Description |
|-------|------|-------------|
| `speed` | float | Playback speed (0.5 = half, 2.0 = double) |
| `speed_segments` | array | Variable speed timeline (see below) |
| `crop_mode` | string | `"pad"` or `"crop"` |
| `scale` | float | Zoom level (0.5–3.0) |
| `anchor_x` | float | Horizontal crop anchor (0.0–1.0) |
| `anchor_y` | float | Vertical crop anchor (0.0–1.0) |
| `pad_color` | string | Letterbox bar color |
| `lut` | string | Path to LUT file |
| `subtitle_template` | string | Path to `.ass` file or `builtin:<name>` |
| `smart` | bool | Enable smart tracking |
| `codec` | string | Video codec override |
| `preset` | string | Encoder preset override |
| `crf` | int | Quality override |

All fields are optional — omitted fields inherit from the base config or CLI flags.

## Variable speed (speed segments)

Create variable-speed effects within a single clip — normal speed for the
approach, slow motion for the action, back to normal:

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

This plays:
1. First 5 seconds at normal speed
2. Seconds 5–8 at half speed
3. Remainder at normal speed

Rules:
- At least 2 segments required
- The last segment must omit `until` (runs to end of clip)
- `until` values must be strictly increasing
- Speeds must be in the range 0.25–4.0
- Cannot be combined with the scalar `speed` field

Speed segments are config-only — there is no CLI flag. Use
`--render-profile <name>` to apply them.

## Iterations

Iterations run a single clip through multiple profiles and concatenate the
results into one output. Configure them in the `iterations` section:

```json
{
  "iterations": {
    "default": ["fullspeed"],
    "goal": ["fullspeed", "slowmo", "goal-overlay"],
    "save": ["slowmo"]
  }
}
```

Activate with `--iterate`:

```bash
reeln render short clip.mkv --iterate --game-dir . --event abc123
```

reeln looks up the event type (e.g., "goal"), finds the matching profile list,
and runs the clip through each profile in sequence. The outputs are concatenated
into a single video.

A goal event with `["fullspeed", "slowmo", "goal-overlay"]` produces:
1. Full-speed playback of the clip
2. Slow-motion replay
3. Slow-motion with goal overlay

All stitched together automatically.

### Iterations on game commands

```bash
# Apply iterations after segment merge
reeln game segment 1 --iterate

# Apply iterations after highlights merge
reeln game highlights --iterate
```

### Single profile vs. iterations

`--render-profile` applies one profile. `--iterate` applies a sequence.
When both are provided, `--render-profile` takes precedence.

## Full-frame rendering

Apply profiles without cropping or scaling to the target aspect ratio:

```bash
reeln render apply clip.mkv --render-profile slowmo
```

This applies speed, LUT, subtitle, and encoding settings but keeps the
original frame dimensions.

## Builtin templates

reeln ships with a `goal_overlay` template that renders a lower-third banner
with scorer name, assists, and team. Reference it with the `builtin:` prefix:

```json
{
  "render_profiles": {
    "player-overlay": {
      "speed": 0.5,
      "subtitle_template": "builtin:goal_overlay"
    }
  }
}
```

### Player overlays with roster lookup

If you have team profiles with rosters configured (see
[Starting a Game](03-starting-a-game.md)), pass jersey numbers and reeln
resolves names automatically:

```bash
reeln render short clip.mkv \
  --render-profile player-overlay \
  --player-numbers 17,22,5 \
  --event-type HOME_GOAL \
  --game-dir .
```

This looks up jersey numbers from the home team roster and fills in the overlay:
`#17 Smith` (scorer), assists `#22 Jones` and `#5 Brown`.

## Next steps

- [Rendering Shorts](05-rendering-shorts.md) — individual render options reference
- [Smart Zoom](10-smart-zoom.md) — AI tracking composes with profiles
- [Plugins](09-plugins.md) — extend rendering with plugins
