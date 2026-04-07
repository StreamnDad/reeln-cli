# Overlay templates

reeln supports ASS overlay templates for rendering text, graphics, and branding onto video clips. Templates use `{{variable}}` placeholders that are populated from the template context (game info, event data, player names, etc.).

## ASS templates

ASS (Advanced SubStation Alpha) is a subtitle format that ffmpeg can render directly. reeln loads the `.ass` file, substitutes `{{variables}}`, writes a temp file, and burns it into the video as part of the ffmpeg filter chain.

### How it works

1. A render profile sets `subtitle_template` to an `.ass` file path (or `builtin:<name>`)
2. reeln builds a template context from game info, event data, and CLI flags
3. The `overlay.py` context builder adds computed values: ASS-formatted colors, timestamps, font sizes, and pixel coordinates
4. Variables like `{{goal_scorer_text}}` and `{{ass_primary_color}}` are substituted into the `.ass` template
5. The rendered `.ass` file is applied via ffmpeg's `subtitles` filter

### Builtin ASS templates

reeln ships with two ASS templates:

- **`goal_overlay`** — a lower-third banner showing scorer name, up to two assists, team name, and team logo
- **`branding`** — a top-of-frame "reeln" watermark

Reference them with the `builtin:` prefix:

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

### Template variables (ASS)

The overlay context builder populates these variables for ASS templates:

| Variable | Description | Example |
|---|---|---|
| `goal_scorer_text` | Player name | `#17 Smith` |
| `goal_scorer_team` | Team name (uppercase) | `ROSEVILLE` |
| `team_level` | Level or division | `BANTAM` |
| `goal_assist_1` | First assist | `#22 Jones` |
| `goal_assist_2` | Second assist | `#5 Brown` |
| `goal_scorer_fs` | Computed font size for scorer | `46` |
| `goal_assist_fs` | Computed font size for assists | `24` |
| `scorer_start` / `scorer_end` | ASS timestamps | `0:00:00.00` |
| `assist_start` / `assist_end` | ASS timestamps (hidden when no assists) | `0:00:00.00` |
| `box_end` | ASS timestamp for overlay duration | `0:00:11.00` |
| `ass_primary_color` | Team primary color in ASS format | `&H001E1E1E` |
| `ass_secondary_color` | Team secondary color in ASS format | `&H00C8C8C8` |
| `ass_name_color` | Name text color | `&H00FFFFFF` |
| `ass_name_outline_color` | Name outline color | `&H00000000` |
| `goal_overlay_*_x` / `*_y` | Pixel coordinates for each element | `83` |

| `goal_overlay_text_right` | Right edge for text clipping (accommodates logo) | `1800` |

Plus all base context variables: `home_team`, `away_team`, `date`, `sport`, `player`, `event_type`, etc.

### Team logo overlay

When a `TeamProfile` has a `logo_path` set, the goal overlay automatically includes the team logo:

- Logo is scaled to 80% of the overlay box height
- Positioned right-aligned with a margin inside the box
- ASS text lines are clipped via `goal_overlay_text_right` so they don't overlap the logo
- Font sizes adapt to the reduced text area

The logo is composited via ffmpeg's `overlay` filter as a second input, using `-loop 1` for the static image. This works across all four filter chain paths: simple pad/crop, smart pad, speed segments, and speed segments + smart pad.

### Writing custom ASS templates

You can write your own `.ass` file using any `{{variable}}` from the context. Place it anywhere and reference it by path:

```json
{
  "render_profiles": {
    "my-overlay": {
      "subtitle_template": "~/.config/reeln/templates/my_overlay.ass"
    }
  }
}
```

Refer to the [ASS format specification](https://fileformats.fandom.com/wiki/SubStation_Alpha) for syntax. The bundled `goal_overlay.ass` in `reeln/data/templates/` is a good starting point.
