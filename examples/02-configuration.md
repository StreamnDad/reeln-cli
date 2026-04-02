# Configuration & OBS Setup

reeln uses a layered JSON config system. This guide covers initial setup and
connecting reeln to OBS for automatic replay collection.

## View your config

```bash
reeln config show
```

This displays the fully resolved configuration after merging:
bundled defaults → user config → environment variable overrides.

## Config file location

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/reeln/config.json` |
| Linux | `~/.config/reeln/config.json` |
| Windows | `%APPDATA%\reeln\config.json` |

The file is created automatically with defaults on first run. Edit it directly
or override individual values with environment variables.

## Connecting to OBS

If you use OBS for livestreaming or recording, you likely have a **Replay Buffer**
that saves clips when you press a hotkey. reeln can automatically pick up those
clips.

### 1. Find your OBS output directory

In OBS: **Settings → Output → Recording → Recording Path**

Common defaults:

| Platform | Typical path |
|----------|-------------|
| macOS | `~/Movies` or `~/Videos/OBS` |
| Linux | `~/Videos` |
| Windows | `C:\Users\<you>\Videos` |

For the Replay Buffer specifically, check:
**Settings → Output → Replay Buffer** — the output path is usually the same
as your recording path.

### 2. Configure reeln paths

Edit your config file and set `source_dir` to your OBS output directory:

```json
{
  "config_version": 1,
  "sport": "hockey",
  "paths": {
    "source_dir": "~/Movies",
    "source_glob": "Replay_*.mkv",
    "output_dir": "~/Movies/games"
  }
}
```

| Key | What it does |
|-----|-------------|
| `source_dir` | Directory where OBS saves replay clips |
| `source_glob` | Pattern to match replay files (default: `Replay_*.mkv`) |
| `output_dir` | Where reeln creates game directories and writes output |

### 3. Match your replay file pattern

OBS names replay files based on your settings. Check what pattern your replays
use and adjust `source_glob` to match:

```json
"source_glob": "Replay_*.mkv"
```

Common patterns:
- `Replay_*.mkv` — OBS default with MKV container
- `Replay_*.mp4` — if you record to MP4
- `*.mkv` — match all MKV files in the directory

### 4. Verify the connection

```bash
# Check config is valid
reeln config doctor

# Show resolved paths
reeln config show
```

Now when you run `reeln game segment 1`, reeln will automatically find and
collect replay clips from your OBS output directory.

## Environment variable overrides

Any config value can be overridden with `REELN_<SECTION>_<KEY>`:

```bash
export REELN_SPORT=hockey
export REELN_VIDEO_CRF=22
export REELN_PATHS_SOURCE_DIR=~/Videos/OBS
```

This is useful for CI, automation, or per-session overrides without editing the
config file.

## Named profiles

Create alternate configs for different setups (e.g., tournament vs. league):

```bash
# Default config
~/Library/Application Support/reeln/config.json

# Tournament profile
~/Library/Application Support/reeln/config.tournament.json
```

Use a profile:

```bash
reeln game init --sport hockey --home east --away west --profile tournament

# Or set it for the whole session
export REELN_PROFILE=tournament
```

## Validate your setup

```bash
# Full health check (ffmpeg, config, permissions, plugins)
reeln doctor

# Config-only validation
reeln config doctor
```

## Next steps

- [Starting a Game](03-starting-a-game.md) — initialize your first game workspace
- [Rendering Shorts](05-rendering-shorts.md) — render clips without a game context
