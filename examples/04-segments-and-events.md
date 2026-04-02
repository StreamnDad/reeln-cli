# Segments & Events

After initializing a game, you process segments (periods, quarters, halves) and
tag events within them. This guide covers the full workflow.

## Process a segment

When a period ends, merge the replay clips for that segment:

```bash
reeln game segment 1
```

If you configured `paths.source_dir` (see [Configuration](02-configuration.md)),
reeln automatically finds matching replay files, moves them into the segment
directory, and merges them into a single highlight clip.

If `source_dir` is not set, place your replay files in the segment directory
first (e.g., `period-1/`) and then run the command.

The merged output is saved as: `period-1/period-1_2026-04-02.mkv`

### Process all segments in a game

```bash
reeln game segment 1
reeln game segment 2
reeln game segment 3
```

### Preview without merging

```bash
reeln game segment 1 --dry-run
```

## How merging works

reeln uses ffmpeg to concatenate segment clips:

- **Same container format** → stream copy (fast, no re-encoding)
- **Mixed containers** → re-encode to match (slower, ensures compatibility)

## Events

Each replay clip collected during segment processing is automatically registered
as an **event** in `game.json`. Events track clips, tags, and metadata throughout
the game lifecycle.

### List events

```bash
reeln game event list -o .
```

The `-o .` flag tells reeln where the game directory is. Use the path to your
game directory, or run from within it.

Filter by segment or type:

```bash
# Events in period 1 only
reeln game event list -o . --segment 1

# Only goal events
reeln game event list -o . --type goal

# Untagged events
reeln game event list -o . --untagged
```

### Tag an event

Add type, player, and metadata to an event:

```bash
reeln game event tag abc123 --type goal --player "#17 Smith"
```

Add assists or other metadata:

```bash
reeln game event tag abc123 \
  --type goal \
  --player "#17 Smith" \
  --meta "assists=#22 Jones, #5 Brown"
```

### Bulk-tag events

Tag all events in a segment at once:

```bash
reeln game event tag-all 1 --type goal
```

## Configure event types

See what event types are available:

```bash
# Show configured event types
reeln config event-types list

# Show defaults for your sport
reeln config event-types defaults
```

Add or remove event types:

```bash
reeln config event-types add save
reeln config event-types remove penalty
```

## Compile clips by criteria

Combine raw event clips matching specific criteria into a single video:

```bash
# All goals
reeln game compile --type goal -o .

# All of one player's clips
reeln game compile --player "#17" -o .

# Clips from period 2
reeln game compile --segment 2 -o .

# Preview without compiling
reeln game compile --type goal --dry-run -o .
```

## Next steps

- [Rendering Shorts](05-rendering-shorts.md) — turn event clips into short-form video
- [Highlights & Reels](06-highlights-and-reels.md) — merge segments into a full-game reel
