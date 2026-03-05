# Configuration

reeln uses a layered JSON configuration system with XDG-compliant paths and environment variable overrides.

## Config file locations

| Platform | Config directory |
|---|---|
| macOS | `~/Library/Application Support/reeln/` |
| Linux | `~/.config/reeln/` |
| Windows | `%APPDATA%\reeln\` |

The main config file is `config.json` within the config directory.

## Loading order

Configuration is merged in this order (later values win):

1. **Bundled defaults** — shipped with the package, always valid
2. **User config** — `config.json` in your config directory
3. **Game override** — `game.json` in the current game directory
4. **Environment variables** — `REELN_<SECTION>_<KEY>`

## Example config

```json
{
  "config_version": 1,
  "sport": "hockey",
  "video": {
    "ffmpeg_path": null,
    "default_container": "mkv",
    "merge_strategy": "concat",
    "codec": "libx264",
    "preset": "medium",
    "crf": 18,
    "audio_codec": "aac",
    "audio_bitrate": "128k"
  },
  "paths": {
    "source_dir": "~/Videos/OBS",
    "source_glob": "Replay_*.mkv",
    "output_dir": "~/Movies",
    "temp_dir": null
  }
}
```

### Paths section

| Key | Default | Description |
|---|---|---|
| `source_dir` | `null` | Directory where replay files are captured (e.g. OBS output folder) |
| `source_glob` | `Replay_*.mkv` | Glob pattern for matching replay files in `source_dir` |
| `output_dir` | `null` | Base directory for game directories and output |
| `temp_dir` | `null` | Temporary file directory (default: system temp) |

`source_dir` is used by both `game segment` (to collect replays) and `render short` (to auto-discover the latest clip when no argument is given).

### Video section

| Key | Default | Description |
|---|---|---|
| `ffmpeg_path` | `null` | Explicit path to ffmpeg binary (auto-discovered if null) |
| `default_container` | `mkv` | Default output container format |
| `merge_strategy` | `concat` | Merge strategy for segment processing |
| `codec` | `libx264` | Video codec for encoding |
| `preset` | `medium` | Encoder preset (ultrafast → veryslow) |
| `crf` | `18` | Constant Rate Factor — lower is higher quality |
| `audio_codec` | `aac` | Audio codec |
| `audio_bitrate` | `128k` | Audio bitrate |

Video encoding settings apply to both `game segment` (when re-encoding mixed containers) and `render short`/`render preview`.

### Render profiles section

Named render profiles define reusable rendering parameter overrides. Add a `render_profiles` section to your config:

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
      "subtitle_template": "~/.config/reeln/templates/goal_overlay.ass"
    },
    "vertical-slowmo": {
      "width": 1080,
      "height": 1920,
      "crop_mode": "pad",
      "speed": 0.5
    }
  }
}
```

| Key | Type | Description |
|---|---|---|
| `speed` | float | Playback speed (e.g. 0.5 for slow motion) |
| `lut` | string | Path to `.cube` LUT file for color grading |
| `subtitle_template` | string | Path to `.ass` subtitle template, or `builtin:<name>` for bundled templates |
| `width` | int | Target width (short-form only, ignored for full-frame) |
| `height` | int | Target height (short-form only, ignored for full-frame) |
| `crop_mode` | string | `"pad"` or `"crop"` (short-form only) |
| `anchor_x` | float | Crop anchor X position, 0.0–1.0 (short-form only) |
| `anchor_y` | float | Crop anchor Y position, 0.0–1.0 (short-form only) |
| `pad_color` | string | Pad bar color (short-form only) |
| `codec` | string | Video codec override |
| `preset` | string | Encoder preset override |
| `crf` | int | CRF override |
| `audio_codec` | string | Audio codec override |
| `audio_bitrate` | string | Audio bitrate override |

All fields are optional — `null` or omitted means "inherit from base config".

Profiles are used with `--render-profile` on `render short`, `render preview`, `render apply`, `game segment`, and `game highlights`.

#### Builtin templates

reeln ships with a bundled `goal_overlay` template. Reference it with the `builtin:` prefix instead of a file path:

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

The `goal_overlay` template renders a lower-third banner showing the scorer name, up to two assists, and the team name. Font size scales dynamically for long names, and assists are hidden when not present.

A default `player-overlay` profile (native speed + goal overlay) and `goal` iteration mapping are included in the bundled config, so goal events render with the overlay out of the box:

```bash
# Tag a goal with player and assists
reeln game event tag <event-id> --type goal --player "#17 Smith" \
  --meta "assists=#22 Jones, #5 Brown"

# Render with the overlay
reeln render short clip.mkv --render-profile player-overlay \
  --game-dir . --event <event-id>

# Or use iterations (auto-applies player-overlay for goals)
reeln render short clip.mkv --iterate --game-dir . --event <event-id>
```

### Iterations section

The `iterations` section maps event types to ordered lists of profile names. This is used for multi-iteration rendering where each event type gets a different sequence of render passes:

```json
{
  "iterations": {
    "default": ["fullspeed"],
    "goal": ["fullspeed", "slowmo", "goal-overlay"],
    "save": ["slowmo"]
  }
}
```

When rendering an event, the `iterations` config determines which profiles to apply based on the event type. Events without a matching type fall back to the `"default"` key.

Use `--iterate` on render or game commands to activate multi-iteration rendering:

```bash
# Render a short through iteration profiles
reeln render short clip.mkv --iterate

# Apply iterations after segment merge
reeln game segment 1 --iterate

# Apply iterations after highlights merge
reeln game highlights --iterate
```

Each profile in the list is applied in order, and the iteration outputs are concatenated end-to-end into a single final file. For example, a goal event with profiles `["fullspeed", "slowmo", "goal-overlay"]` produces a video that plays the clip at full speed, then slow motion, then with the goal overlay — all stitched together automatically.

### Orchestration section

The `orchestration` section controls the plugin pipeline behavior:

```json
{
  "orchestration": {
    "upload_bitrate_kbps": 5000,
    "sequential": true
  }
}
```

| Key | Default | Description |
|---|---|---|
| `upload_bitrate_kbps` | `0` | Maximum upload rate in KB/s (0 = unlimited) |
| `sequential` | `true` | Run all plugin operations sequentially |

### Plugins section

The `plugins` section controls plugin discovery and per-plugin settings:

```json
{
  "plugins": {
    "enabled": ["youtube", "llm"],
    "disabled": ["meta"],
    "settings": {
      "youtube": {
        "api_key": "...",
        "playlist_id": "..."
      }
    }
  }
}
```

| Key | Default | Description |
|---|---|---|
| `enabled` | `[]` | List of plugin names to enable (empty = all discovered) |
| `disabled` | `[]` | List of plugin names to disable |
| `settings` | `{}` | Per-plugin configuration passed during instantiation |
| `registry_url` | `""` | Custom plugin registry URL (empty = default GitHub URL) |

When `enabled` is empty, all discovered plugins are loaded except those in `disabled`. When `enabled` is non-empty, only those named plugins are loaded (minus any in `disabled`).

## Plugin config schemas

Plugins can declare the configuration fields they accept via a `config_schema` class attribute. When a plugin declares a schema:

- **Default seeding** — running `reeln plugins enable <name>` or `reeln plugins install <name>` writes the plugin's default values into `plugins.settings` automatically, so `reeln config show` reflects them immediately.
- **Validation** — `reeln config doctor` checks plugin settings against declared schemas and warns about missing required fields or type mismatches.
- **Discovery** — `reeln plugins info <name>` displays the schema (field names, types, required/optional, defaults, descriptions).

Default seeding only adds missing keys — it never overwrites values you've already set. Plugins without a schema are unaffected; they continue to work with opaque settings dicts.

### Supported field types

| Type | JSON equivalent | Notes |
|---|---|---|
| `str` | string | Default |
| `int` | number (integer) | Rejects booleans |
| `float` | number | Accepts `int` values |
| `bool` | boolean | |
| `list` | array | |

### Example schema output

```
$ reeln plugins info youtube
Name:         youtube
Package:      reeln-youtube
...
Config schema:
  api_key: str (required)  — YouTube Data API key
  playlist_id: str  — Default playlist for uploads
  privacy: str [default: unlisted]  — Video privacy setting
```

## Environment variable overrides

Any config value can be overridden with an environment variable using the convention `REELN_<SECTION>_<KEY>`:

```bash
export REELN_VIDEO_CRF=22
export REELN_VIDEO_CODEC=libx265
export REELN_VIDEO_AUDIO_CODEC=opus
export REELN_SPORT=hockey
```

### Config file path via environment

You can also set which config file to load via environment variables:

| Variable | Description |
|---|---|
| `REELN_CONFIG` | Absolute or `~`-relative path to a config file |
| `REELN_PROFILE` | Named profile (loads `config.<profile>.json`) |

Priority order (highest wins):
1. `--config` CLI flag
2. `REELN_CONFIG` env var
3. `--profile` CLI flag
4. `REELN_PROFILE` env var
5. Default XDG path (`config.json`)

This priority applies to both reading and writing. When a command modifies config (e.g. `reeln plugins enable`), the changes are written back to the same resolved path.

```bash
# Use a specific config file
export REELN_CONFIG=~/projects/tournament/reeln.json

# Or select a named profile
export REELN_PROFILE=tournament
```

## Named profiles

In addition to the default `config.json`, you can create named profiles:

- Default: `config.json`
- Named: `config.<profile>.json`

Select a profile with the `--profile` flag or `REELN_PROFILE` env var:

```bash
reeln game init --sport hockey --home team-a --away team-b --profile tournament

# Or via env var
export REELN_PROFILE=tournament
reeln game segment 1
```

Profiles inherit from the default config and override specific keys.

## Debug artifacts

When any command is run with `--debug`, pipeline debug artifacts are written to `{game_dir}/debug/`. This includes:

- **Per-operation JSON files** — ffmpeg command, filter chain, input/output file metadata (duration, fps, resolution, codec)
- **HTML index** (`debug/index.html`) — browsable summary linking to all debug artifacts and processed videos

Debug artifacts are automatically removed by `game prune` (no `--all` flag needed). Open `debug/index.html` in a browser for a quick overview of all operations performed on a game.

## Schema versioning

Every config file includes a `config_version` field. When the schema changes, reeln provides migration functions to upgrade configs automatically.

## Viewing and validating config

```bash
# Show the fully resolved config
reeln config show

# Validate config and check for issues
reeln config doctor
```
