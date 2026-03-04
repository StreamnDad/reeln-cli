# Quick start

This guide covers what's available now and previews the full game workflow that's being built.

## What works today

Phases 1–12 are implemented: the CLI skeleton, ffmpeg foundation, config system, segment model, game init, segment processing, game highlights merge, render commands, event tracking, game finish, media prune, health checks, render profiles with template support, multi-iteration rendering, plugin-ready seams, and the plugin orchestration system.

### 1. Verify your install

```bash
reeln --version
```

### 2. View your configuration

```bash
reeln config show
```

This shows the fully resolved config after merging bundled defaults, user config, and environment variable overrides.

### 3. Run health checks

```bash
reeln doctor
```

This runs comprehensive diagnostics: ffmpeg discovery and version, codec availability (libx264, libx265, aac), hardware acceleration, config validation, and directory permissions. Each check reports PASS, WARN, or FAIL with actionable hints.

For config-only validation, use:

```bash
reeln config doctor
```

### 4. Initialize a game

You can provide team names directly:

```bash
reeln game init roseville mahtomedi --sport hockey
```

Or run without arguments for an interactive prompt that walks you through each field:

```bash
reeln game init
```

:::{note}
Interactive mode requires the `interactive` extra: `pip install reeln[interactive]`
:::

This creates a game directory with sport-specific segment subdirectories:

```
2026-02-26_roseville_vs_mahtomedi/
├── game.json          # game state and metadata
├── period-1/          # segment directories (sport-specific naming)
├── period-2/
└── period-3/
```

The directory names match your sport — basketball uses `quarter-1/` through `quarter-4/`, soccer uses `half-1/` and `half-2/`, etc.

Use `--dry-run` to preview without creating anything:

```bash
reeln game init roseville mahtomedi --sport hockey --dry-run
```

Double-headers are detected automatically — running `game init` twice for the same teams and date creates a `_g2` directory.

### 5. Process segments

After each segment (period, quarter, half, etc.), merge your replay files:

```bash
reeln game segment 1
reeln game segment 2
reeln game segment 3
```

When `paths.source_dir` is configured, replays matching `paths.source_glob` (default: `Replay_*.mkv`) are automatically moved from the source directory into the segment directory before merging. Otherwise, place your replay files in the segment directory manually (e.g. `period-1/`).

Each command merges video files via ffmpeg concat. When all files share the same container format, stream copy is used (no re-encoding). Mixed containers trigger a re-encode. Events are automatically registered for each collected replay clip.

The merged output is placed in the segment directory: `period-1_2026-02-26.mkv`.

Use `--dry-run` to preview without merging:

```bash
reeln game segment 1 --dry-run
```

### 5b. Tag events

After processing segments, tag the auto-registered events:

```bash
# List events
reeln game event list -o .

# Tag a specific event
reeln game event tag abc123 --type goal --player "#17"

# Bulk-tag all events in a segment
reeln game event tag-all 1 --type goal
```

### 5c. Compile event clips

Compile raw clips by event criteria into a single video:

```bash
# Compile all goals
reeln game compile --type goal -o .

# Preview without compiling
reeln game compile --type goal --dry-run -o .
```

### 6. Merge full-game highlights

```bash
reeln game highlights
```

This produces a "story of the game" highlight reel combining all segment highlights in order. The output is placed in the game directory: `roseville_vs_mahtomedi_2026-02-26.mkv`.

### Other sports

The same workflow works for any supported sport:

```bash
# Basketball
reeln game init --sport basketball --home lakers --away celtics

# Soccer
reeln game init --sport soccer --home city --away united
```

### 7. Render shorts

Transform clips into short-form vertical or square formats:

```bash
# Render a vertical short from the latest clip
reeln render short

# Render a specific clip with crop mode
reeln render short period-1/period-1_2026-02-26.mkv --crop crop --anchor center

# Square format with slow motion and color grading
reeln render short replay.mkv --format square --speed 0.5 --lut warm.cube

# Quick low-res preview first
reeln render preview replay.mkv
```

When `--game-dir` is provided (or `paths.output_dir` points to a game directory), renders are tracked in `game.json`.

### 7b. Multi-iteration rendering

If you've configured iteration profiles in your config (see {doc}`guide/configuration`), you can run a clip through multiple render passes automatically. reeln uses ffmpeg under the hood — a free tool that handles all the video processing — you just need it installed.

```bash
# Render a short with iteration profiles (e.g. fullspeed → slowmo → overlay)
reeln render short replay.mkv --iterate

# Apply iterations to a full-frame clip
reeln render apply clip.mkv --iterate

# Apply iterations after segment merge
reeln game segment 1 --iterate
```

When `--iterate` is used, reeln looks up the iteration profile list for the event type and runs the clip through each profile in sequence, concatenating the results into a single output.

`--render-profile` (single profile) takes precedence over `--iterate` (multi-profile) when both are provided.

### 8. Assemble a reel

Combine rendered shorts into a single reel:

```bash
reeln render reel --game-dir ~/games/2026-02-26_roseville_vs_mahtomedi

# Or just period 1 renders
reeln render reel --game-dir . --segment 1

# Or only renders linked to goals
reeln render reel --game-dir . --event-type goal
```

### 9. Finish the game

```bash
reeln game finish
```

This marks the game as finished and shows a summary — segments processed, events (tagged/untagged), renders, and highlight status. Use `--dry-run` to preview without updating state.

### 10. Clean up

Remove generated artifacts (merges, highlights, renders) while keeping raw event clips:

```bash
# Per-game cleanup
reeln game prune -o .

# Also remove raw event clips
reeln game prune --all -o .

# Global cleanup — prune all finished games
reeln media prune -o ~/games

# Preview without deleting
reeln media prune --dry-run
```

Prune only works on finished games — run `game finish` first.

### 11. Manage plugins

Browse available plugins:

```bash
# Search the plugin registry
reeln plugins search

# Search for a specific plugin
reeln plugins search youtube

# View plugin details
reeln plugins info youtube
```

Install and manage plugins:

```bash
# Install a plugin (auto-enables it)
reeln plugins install youtube

# Preview what would be installed
reeln plugins install youtube --dry-run

# List installed plugins with version info
reeln plugins list

# Update a specific plugin
reeln plugins update youtube

# Update all installed plugins
reeln plugins update
```

Enable or disable plugins:

```bash
reeln plugins enable youtube
reeln plugins disable meta
```

Plugin settings are managed in your config file under the `plugins` section. See {doc}`cli/plugins` for details on the registry, orchestration pipeline, and capability protocols.

## Next steps

- {doc}`guide/configuration` — customize paths, video settings, profiles, and plugin settings
- {doc}`guide/sports` — see all built-in sports and register custom ones
- {doc}`cli/index` — full CLI reference
- {doc}`cli/plugins` — plugin system, orchestration pipeline, and extension points
