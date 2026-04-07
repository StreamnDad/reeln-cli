# reeln render

Video rendering commands — transform clips into short-form formats for social media.

## Commands

### `reeln render short`

Render a 9:16 vertical short from a clip.

```bash
reeln render short [CLIP] [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `CLIP` | Input video file (optional — defaults to latest file matching `source_glob` in `source_dir`) |
| `--output`, `-o` | Output file path (default: `{stem}_short.mp4`) |
| `--format`, `-f` | Output format preset: `vertical`, `square` |
| `--size` | Custom WxH (e.g. `1080x1920`) — overrides `--format` |
| `--crop`, `-c` | Crop mode: `pad` (fit with bars) or `crop` (fill and trim). Default: `pad` |
| `--anchor`, `-a` | Crop anchor: `center`, `top`, `bottom`, `left`, `right`, or custom `x,y` (0.0–1.0). Default: `center` |
| `--pad-color` | Pad bar color (default: `black`) |
| `--scale` | Content scale, 0.5–3.0 (default: `1.0`). Values > 1.0 zoom in on the source. |
| `--smart` | Enable smart tracking via vision plugin (requires an `ON_FRAMES_EXTRACTED` handler). |
| `--zoom-frames` | Number of frames to extract for smart zoom analysis, 1–20 (default: `5`). |
| `--speed` | Playback speed, 0.5–2.0 (default: `1.0`) |
| `--lut` | LUT file for color grading (`.cube` or `.3dl`) |
| `--subtitle` | ASS subtitle overlay file (`.ass`) |
| `--game-dir` | Game directory for render tracking |
| `--event` | Link to event ID (auto-detected from clip path if omitted) |
| `--render-profile`, `-r` | Named render profile from config |
| `--player` | Player name for overlay (populates `{{player}}` / `{{goal_scorer_text}}` in subtitle templates) |
| `--assists` | Assists, comma-separated (populates `{{goal_assist_1}}` / `{{goal_assist_2}}` in subtitle templates) |
| `--player-numbers`, `-n` | Jersey numbers: `scorer[,assist1[,assist2]]`. Looked up from team roster CSV. |
| `--event-type` | Event type for scoring team resolution (`HOME_GOAL`, `AWAY_GOAL`). Used with `--player-numbers`. |
| `--iterate` | Multi-iteration mode — apply iteration profiles from config |
| `--debug` | Write debug artifacts (ffmpeg commands, metadata) to `{game_dir}/debug/` |
| `--no-branding` | Disable the default branding overlay |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Show render plan without executing |

When `--render-profile` is provided, the named profile's fields are overlaid onto the base ShortConfig before rendering. This lets you apply pre-configured speed, LUT, subtitle, crop, and encoding settings from config rather than specifying them on every invocation.

When `--iterate` is provided, reeln looks up the iteration profile list for the event type (from the `iterations` config section) and runs the clip through each profile in sequence, concatenating the results into a single output. This is useful for creating multi-pass renders — for example, full speed followed by slow motion followed by a goal overlay.

When `--player` and/or `--assists` are provided, they populate the overlay template context — useful for rendering goal overlays without going through the game event tagging system. These flags override any player/assists data from linked game events. They require a `--render-profile` with a `subtitle_template` to take effect.

#### Player number roster lookup

When `--player-numbers` is provided (e.g. `--player-numbers 48,24,2`), reeln looks up player names from the team roster CSV:

1. The first number is the **goal scorer**, remaining numbers are **assists**
2. The **scoring team** is determined from `--event-type`: `HOME_GOAL`/`home_goal` → home team, `AWAY_GOAL`/`away_goal` → away team, anything else defaults to home
3. The team profile is loaded using `level` and team slug from `game.json`
4. Player names are formatted as `#48 Smith` (number + last name)
5. Unknown numbers fall back to `#48` with a warning

Requirements:
- A game directory (`--game-dir` or auto-detected)
- The game must have been initialized with `--level` (to store team profile references)
- The team profile must have a `roster_path` pointing to a valid CSV file

If `--player` or `--assists` are also provided, they take precedence over the roster lookup.

Builds an ffmpeg filter graph to reframe the input clip as a vertical short suitable for social media platforms (YouTube Shorts, Instagram Reels, TikTok).

#### Auto-discovery

When `CLIP` is omitted, reeln finds the most recently modified file matching `paths.source_glob` in `paths.source_dir`. Both are configured via the config file or environment variables.

#### Render tracking

When `--game-dir` is provided, the render is recorded in `game.json`. If `--game-dir` is not provided, reeln auto-detects the game directory from `paths.output_dir` (looking for the most recently modified `game.json`). If no game directory is found, the render proceeds without tracking.

#### Event linking

Renders are automatically linked to events when the input clip path matches a registered event's `clip` field. Use `--event EVENT_ID` to explicitly link to a specific event (overrides auto-detection).

#### Encoding settings

Encoding parameters (codec, preset, CRF, audio codec, audio bitrate) flow from the config system — not from CLI flags. Override via config file, `--profile`, or `REELN_VIDEO_*` env vars.

#### Crop modes

- **`pad`** — Fits the entire source frame into the target dimensions with letterbox/pillarbox bars. Nothing is cropped. The `--pad-color` option controls bar color.
- **`crop`** — Fills the target dimensions by cropping the source. The `--anchor` option controls which region of the source is kept.

#### Smart tracking

Rendering has three orthogonal axes that compose independently:

- **Framing** (`--crop pad|crop`) — how the source fits the target dimensions
- **Scale** (`--scale`) — content zoom level
- **Tracking** (`--smart`) — dynamic crop/pan following the action

When `--smart` is enabled, reeln extracts frames from the clip and emits the `ON_FRAMES_EXTRACTED` hook. A vision plugin (e.g. `reeln-plugin-openai`) analyzes the frames and returns a zoom path — a sequence of (timestamp, center_x, center_y) points describing where the action is. The render filter chain then dynamically adjusts the crop or pad position to follow the action.

- **Smart crop** (`--crop crop --smart`) — fills the target by cropping, with the crop window tracking the action point.
- **Smart pad** (`--crop pad --smart`) — fits the source with pillarbox bars, panning horizontally to keep the action centered. Vertical position stays fixed (vertical panning is disorienting in pad mode).

If no vision plugin handles `ON_FRAMES_EXTRACTED`, `--smart` falls back to static center positioning with a warning.

:::{note}
The legacy crop modes `--crop smart` and `--crop smart_pad` still work but are deprecated. Use `--crop crop --smart` and `--crop pad --smart` instead.
:::

```bash
# Smart crop — fills 9:16, tracking the action
reeln render short clip.mkv --crop crop --smart

# Smart pad — fits with bars, panning horizontally
reeln render short clip.mkv --crop pad --smart

# Smart crop with zoom
reeln render short clip.mkv --crop crop --smart --scale 1.5

# More frames for finer tracking
reeln render short clip.mkv --smart --zoom-frames 10
```

#### Variable speed segments

For variable speed within a single clip (e.g., normal → slow motion → normal), use `speed_segments` in a render profile. This is a profile-only feature — there is no CLI flag. See {doc}`/guide/configuration` for details.

:::{note}
`speed_segments` cannot be combined with `--smart` tracking. Static crop/pad with speed segments works.
:::

#### Filter chain order

LUT (color grade) → speed (`setpts`) → scale → overflow crop (pad + scale > 1.0) → crop/pad → final scale (crop only) → subtitle overlay.

**Examples:**

```bash
# Render latest clip as a vertical short (auto-discovers from source_dir)
reeln render short

# Render a specific clip
reeln render short ~/replay.mkv

# Square format with crop mode, anchored to the right third
reeln render short replay.mkv --format square --crop crop --anchor right

# Custom size with speed adjustment and color grading
reeln render short replay.mkv --size 720x1280 --speed 0.5 --lut warm.cube

# Goal overlay short with player name (no game state needed)
reeln render short goal.mkv -r player-overlay --player "#17 Smith" --assists "#22, #5"

# Preview the plan without rendering
reeln render short replay.mkv --dry-run

# Track render in a specific game directory
reeln render short replay.mkv --game-dir ~/games/2026-02-26_roseville_vs_mahtomedi
```

### `reeln render preview`

Generate a fast low-resolution preview of a clip.

```bash
reeln render preview [CLIP] [OPTIONS]
```

Accepts the same options as `render short` (including `--render-profile`, `--iterate`, `--scale`, `--smart`, `--zoom-frames`, and `--debug`). Produces a scaled-down, lower-quality version for quick review before committing to a full render.

Preview differences:
- Uses `ultrafast` preset (vs `medium`)
- Higher CRF of 28 (vs 18) for smaller files
- Half the target resolution

Output is named `{stem}_preview.mp4` by default.

**Examples:**

```bash
# Quick preview of the latest clip
reeln render preview

# Preview a specific clip
reeln render preview replay.mkv

# Preview with crop mode
reeln render preview replay.mkv --crop crop --anchor top
```

### `reeln render apply`

Apply a named render profile to a video clip, preserving original resolution.

```bash
reeln render apply <CLIP> --render-profile <NAME> [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `CLIP` | Input video file (required) |
| `--render-profile`, `-r` | Named render profile (required unless `--iterate`) |
| `--iterate` | Multi-iteration mode — apply iteration profiles from config |
| `--debug` | Write debug artifacts (ffmpeg commands, metadata) to `{game_dir}/debug/` |
| `--output`, `-o` | Output file path (default: `{stem}_{profile}.mp4`) |
| `--game-dir` | Game directory for template context |
| `--event` | Event ID for template variable substitution |
| `--player` | Player name for overlay (overrides event-sourced player) |
| `--assists` | Assists, comma-separated (overrides event-sourced assists) |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Show plan without executing |

General-purpose profile application for full-frame rendering. Applies speed changes, LUT color grading, and `.ass` subtitle templates from the named profile — no crop or scale. The original resolution is preserved.

When `--iterate` is provided, the command uses the iteration profile list from config instead of a single profile.

When `--game-dir` is provided, game metadata (teams, date, sport) is available for template variable substitution in `.ass` subtitle files. Add `--event` to also include event-specific variables (type, player, metadata).

**Examples:**

```bash
# Apply slow motion profile to a clip
reeln render apply highlight.mkv --render-profile slowmo

# Apply a profile with subtitle template (game context for variables)
reeln render apply goal.mkv --render-profile goal-overlay --game-dir .

# Custom output path
reeln render apply clip.mkv --render-profile slowmo -o clip_slow.mp4

# Goal overlay with player name and assists (no game state needed)
reeln render apply goal.mkv --render-profile player-overlay --player "#17 Smith" --assists "#22 Jones, #5 Brown"

# Preview without rendering
reeln render apply clip.mkv --render-profile slowmo --dry-run
```

### `reeln render reel`

Assemble rendered shorts into a concatenated reel.

```bash
reeln render reel [OPTIONS]
```

| Option | Description |
|---|---|
| `--game-dir` | Game directory (required) |
| `--segment`, `-s` | Filter by segment number (optional) |
| `--event-type` | Filter by linked event type (optional) |
| `--output`, `-o` | Output file path |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Show plan without executing |

Reads the render entries from `game.json` and concatenates the rendered short files into a single reel video. Uses stream copy when all files share the same format; re-encodes when formats are mixed.

#### Default output naming

- All segments: `{home}_vs_{away}_{date}_reel.mp4`
- Single segment: `{home}_vs_{away}_{date}_{segment_alias}_reel.mp4`

**Examples:**

```bash
# Assemble all rendered shorts into a reel
reeln render reel --game-dir ~/games/2026-02-26_roseville_vs_mahtomedi

# Reel from period 1 only
reeln render reel --game-dir ~/games/2026-02-26_roseville_vs_mahtomedi --segment 1

# Preview without assembling
reeln render reel --game-dir ~/games/2026-02-26_roseville_vs_mahtomedi --dry-run

# Custom output path
reeln render reel --game-dir ~/games/2026-02-26_roseville_vs_mahtomedi -o highlights_reel.mp4
```

## Render workflows

Two workflows are supported for producing short-form content from a game:

### Workflow A: Render then concat

Render individual replays as shorts, then assemble into a reel:

```bash
reeln render short period-1/replay1.mkv --game-dir .
reeln render short period-1/replay2.mkv --game-dir .
reeln render reel --game-dir .
```

### Workflow B: Concat then render

Merge raw replays first (existing `game segment`), then render the merged landscape file:

```bash
reeln game segment 1
reeln render short period-1/period-1_2026-02-26.mkv
```

### Workflow C: Queue, review, and publish

Render clips and queue them for selective publishing across platforms:

```bash
# Render and queue instead of publishing immediately
reeln render short clip.mkv --queue
reeln render apply clip.mkv -r slowmo --queue

# Review queued items
reeln queue list
reeln queue show <ID>

# Edit metadata before publishing
reeln queue edit <ID> --title "Custom Title" --description "Updated description"

# Publish to specific targets
reeln queue publish <ID> --target youtube
reeln queue publish <ID> --target instagram

# Or publish all pending items
reeln queue publish-all
```

The `--queue` flag is supported on both `render short` and `render apply`. When used,
the render completes but output is queued for review instead of triggering `POST_RENDER`
plugin hooks. The `ON_QUEUE` hook fires instead, allowing plugins to prepare metadata
without uploading. Each queue item tracks per-target publish status independently.
