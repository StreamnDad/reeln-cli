# Game Finish & Cleanup

After processing all segments and rendering shorts, finalize the game and
optionally clean up generated artifacts.

## Finish a game

```bash
reeln game finish
```

This marks the game as finished in `game.json` and shows a summary:

- Segments processed
- Events (tagged and untagged counts)
- Renders produced
- Highlight reel status

### Preview before finishing

```bash
reeln game finish --dry-run
```

### Specify the game directory

```bash
reeln game finish -o ~/Movies/games/2026-04-02_roseville_vs_mahtomedi
```

## Clean up artifacts

Remove generated files (merges, highlights, renders) while keeping raw event
clips:

```bash
reeln game prune -o .
```

Also remove raw event clips:

```bash
reeln game prune --all -o .
```

### Preview what would be deleted

```bash
reeln game prune --dry-run -o .
```

> **Note:** Prune only works on finished games. Run `game finish` first.

## Global cleanup

Clean up all finished games in a directory:

```bash
reeln media prune -o ~/Movies/games

# Preview
reeln media prune --dry-run -o ~/Movies/games
```

## Complete game lifecycle

Here's the full flow from start to finish:

```bash
# 1. Initialize
reeln game init roseville mahtomedi --sport hockey

# 2. Process segments as the game progresses
reeln game segment 1
reeln game segment 2
reeln game segment 3

# 3. Tag notable events
reeln game event tag abc123 --type goal --player "#17 Smith"

# 4. Merge full-game highlights
reeln game highlights

# 5. Render shorts for social media
reeln render short clip.mkv --crop crop --speed 0.5 --game-dir .

# 6. Assemble a reel
reeln render reel --game-dir .

# 7. Finish
reeln game finish

# 8. Clean up when done
reeln game prune -o .
```

## Next steps

- [Plugins](09-plugins.md) — automate uploads and metadata with plugins
- [Configuration](02-configuration.md) — customize paths and settings
