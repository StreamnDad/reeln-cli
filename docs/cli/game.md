# reeln game

Game lifecycle management — from initialization through highlight assembly.

:::{note}
All game subcommands are implemented: `init`, `segment`, `highlights`, `compile`, `event`, `finish`, and `prune`.
:::

## Commands

### `reeln game init`

Set up a new game workspace with directories and metadata.

```bash
reeln game init [HOME] [AWAY] [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `HOME` | Home team name (optional — prompts interactively if omitted) |
| `AWAY` | Away team name (optional — prompts interactively if omitted) |
| `--sport`, `-s` | Sport type — hockey, basketball, soccer, etc. (default: generic) |
| `--date` | Game date in YYYY-MM-DD format (default: today) |
| `--venue` | Venue name (optional) |
| `--output-dir`, `-o` | Base output directory (default: current directory) |
| `--dry-run` | Preview what would be created without writing |

Creates a game directory named `{date}_{home}_vs_{away}/` with sport-specific segment subdirectories and a `game.json` state file. Automatically detects double-headers and appends `_g2`, `_g3`, etc.

#### Interactive mode

When `HOME` and/or `AWAY` are omitted, the command enters interactive mode and prompts for all game fields using [questionary](https://questionary.readthedocs.io/). Any options provided on the command line are used as defaults and skip the corresponding prompt.

Interactive mode requires the `interactive` extra:

```bash
pip install reeln[interactive]
```

**Examples:**

```bash
# Interactive mode — prompts for all fields
reeln game init

# Interactive with some options pre-filled (only missing fields are prompted)
reeln game init --sport hockey --venue "OVAL"

# Non-interactive — provide both team names
reeln game init roseville mahtomedi --sport hockey

# Basketball game — creates quarter-1/ through quarter-4/
reeln game init lakers celtics --sport basketball

# Preview without creating
reeln game init roseville mahtomedi --sport hockey --dry-run

# Custom date and output directory
reeln game init a b --date 2026-03-15 -o ~/games
```

### `reeln game segment`

Merge replays in a segment directory into a single highlight video.

```bash
reeln game segment <N> [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `N` | Segment number (1-indexed) |
| `--output-dir`, `-o` | Game directory (auto-discovered from `paths.output_dir` if omitted) |
| `--render-profile`, `-r` | Apply a named render profile after merge |
| `--iterate` | Multi-iteration mode — apply iteration profiles after merge |
| `--debug` | Write debug artifacts (ffmpeg commands, metadata) to `{game_dir}/debug/` |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Preview without merging |

When `--output-dir` is omitted, reeln checks the current directory for `game.json`. If not found, it searches `paths.output_dir` for the most recently modified game directory.

Encoding settings (codec, CRF, audio) are read from the config system. Override via config file, `--profile`, `--config`, or `REELN_VIDEO_*` env vars.

When `paths.source_dir` is configured, replay files matching `paths.source_glob` (default: `Replay_*.mkv`) are automatically **moved** from the source directory into the segment directory before merging. This means you don't need to manually copy files — just run the segment command after each period/quarter.

Finds all video files (`.mkv`, `.mp4`, `.mov`, `.avi`, `.webm`, `.ts`, `.flv`) in the segment directory and merges them via ffmpeg concat. Uses stream copy when all files share the same container format; re-encodes when containers are mixed.

The merged output is named `{segment_alias}_{date}.mkv` (e.g. `period-1_2026-02-26.mkv`) and placed in the segment directory. Previously merged outputs are excluded from subsequent runs.

**Examples:**

```bash
# Merge period 1 replays (run from the game directory)
reeln game segment 1

# Merge with explicit game directory
reeln game segment 2 -o ~/games/2026-02-26_roseville_vs_mahtomedi

# Preview without merging
reeln game segment 1 --dry-run

# Apply slow motion profile after merge
reeln game segment 1 --render-profile slowmo

# Write debug artifacts for troubleshooting
reeln game segment 1 --debug
```

### `reeln game highlights`

Merge all segment highlights into a full-game highlight reel.

```bash
reeln game highlights [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `--output-dir`, `-o` | Game directory (auto-discovered from `paths.output_dir` if omitted) |
| `--render-profile`, `-r` | Apply a named render profile after merge |
| `--iterate` | Multi-iteration mode — apply iteration profiles after merge |
| `--debug` | Write debug artifacts (ffmpeg commands, metadata) to `{game_dir}/debug/` |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Preview without merging |

When `--output-dir` is omitted, reeln checks the current directory for `game.json`. If not found, it searches `paths.output_dir` for the most recently modified game directory.

Encoding settings are read from the config system (same as `game segment`).

When `--render-profile` and `--iterate` are both provided, `--render-profile` takes precedence.

Concatenates all segment highlight videos in order to produce a "story of the game" highlight reel. Looks for segment merge outputs matching `{segment_alias}_{date}.mkv` in each segment directory.

The output is named `{home}_vs_{away}_{date}.mkv` (e.g. `roseville_vs_mahtomedi_2026-02-26.mkv`) and placed in the game directory.

**Examples:**

```bash
# Merge all segments (run from the game directory)
reeln game highlights

# Merge with explicit game directory
reeln game highlights -o ~/games/2026-02-26_roseville_vs_mahtomedi

# Preview without merging
reeln game highlights --dry-run

# Apply a render profile after merge
reeln game highlights --render-profile slowmo

# Write debug artifacts for troubleshooting
reeln game highlights --debug
```

### `reeln game compile`

Compile raw event clips into a single video.

```bash
reeln game compile [OPTIONS]
```

| Option | Description |
|---|---|
| `--type`, `-t` | Filter by event type |
| `--segment`, `-s` | Filter by segment number |
| `--player`, `-p` | Filter by player |
| `--output` | Output file path |
| `--output-dir`, `-o` | Game directory |
| `--debug` | Write debug artifacts (ffmpeg commands, metadata) to `{game_dir}/debug/` |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Preview without compiling |

Concatenates the raw replay clips for matching events into a single compilation video. Uses stream copy when all clips share the same container format; re-encodes when formats are mixed.

Default output: `{home}_vs_{away}_{date}_{filter}_compilation.mkv` in the game directory.

**Examples:**

```bash
# Compile all events
reeln game compile -o ~/games/2026-02-26_roseville_vs_mahtomedi

# Compile only goals
reeln game compile --type goal -o .

# Compile goals by a specific player
reeln game compile --type goal --player "#17" -o .

# Preview without creating
reeln game compile --type goal --dry-run -o .
```

### `reeln game event list`

List registered events in the current game.

```bash
reeln game event list [OPTIONS]
```

| Option | Description |
|---|---|
| `--segment`, `-s` | Filter by segment number |
| `--type`, `-t` | Filter by event type |
| `--untagged` | Show only untagged events |
| `--output-dir`, `-o` | Game directory |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |

Displays a table of events with ID (truncated), segment number, type, player, and clip path. Untagged events show `(untagged)` in the type column.

**Examples:**

```bash
# List all events
reeln game event list -o .

# List events in period 1
reeln game event list --segment 1

# List only goals
reeln game event list --type goal

# List events that haven't been tagged yet
reeln game event list --untagged
```

### `reeln game event tag`

Tag an event with type, player, and metadata.

```bash
reeln game event tag <EVENT_ID> [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `EVENT_ID` | Event ID or unique prefix |
| `--type`, `-t` | Event type (e.g. goal, save) |
| `--player`, `-p` | Player name/number |
| `--meta`, `-m` | Metadata key=value pair (repeatable) |
| `--output-dir`, `-o` | Game directory |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |

Supports UUID prefix matching — you only need enough of the ID to be unique.

**Examples:**

```bash
# Tag an event as a goal by player #17
reeln game event tag abc123 --type goal --player "#17"

# Tag with assists for the player overlay
reeln game event tag abc123 --type goal --player "#17 Smith" \
  --meta "assists=#22 Jones, #5 Brown"

# Add other metadata
reeln game event tag abc123 --meta "title=Great goal"
```

:::{tip}
When a goal event has `player` and `assists` metadata, the bundled `player-overlay` render profile displays a lower-third banner with scorer name, assists, and team info. Use `--render-profile player-overlay` or `--iterate` on render commands to apply it automatically.
:::

### `reeln game event tag-all`

Bulk-tag all events in a segment.

```bash
reeln game event tag-all <SEGMENT_N> [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `SEGMENT_N` | Segment number |
| `--type`, `-t` | Event type |
| `--player`, `-p` | Player name/number |
| `--output-dir`, `-o` | Game directory |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |

**Examples:**

```bash
# Tag all events in period 1 as goals
reeln game event tag-all 1 --type goal

# Tag all events in period 2 with a player
reeln game event tag-all 2 --player "#17"
```

### `reeln game finish`

Finalize a game — mark as finished and show a summary.

```bash
reeln game finish [OPTIONS]
```

| Option | Description |
|---|---|
| `--output-dir`, `-o` | Game directory |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Preview without updating state |

Sets `finished = true` and records a `finished_at` timestamp in `game.json`. Displays a summary including segments processed, event counts (tagged/untagged), render count, and highlight status.

A game can only be finished once — running `game finish` on an already-finished game produces an error.

**Examples:**

```bash
# Finish the current game
reeln game finish -o .

# Preview without updating state
reeln game finish --dry-run
```

### `reeln game prune`

Remove generated artifacts from a finished game directory.

```bash
reeln game prune [OPTIONS]
```

| Option | Description |
|---|---|
| `--output-dir`, `-o` | Game directory |
| `--all` | Also remove raw event clips (default: keep source clips) |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Show what would be removed without deleting |

By default, removes generated files (segment merges, highlight reels, rendered shorts, compilations, temp files) and the `debug/` directory while preserving raw event clips and `game.json`. With `--all`, also removes raw event clips — everything except `game.json`.

The game must be finished before pruning. Empty segment directories are cleaned up after file removal.

**Examples:**

```bash
# Remove generated files, keep event clips
reeln game prune -o .

# Remove everything except game.json
reeln game prune --all -o .

# Preview without deleting
reeln game prune --dry-run -o .
```
