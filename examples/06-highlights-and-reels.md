# Highlights & Reels

After processing individual segments, reeln can merge them into a full-game
highlight reel or assemble rendered shorts into a compilation.

## Full-game highlights

Merge all processed segments into a single "story of the game" video:

```bash
reeln game highlights
```

This concatenates all segment highlight clips in order. The output is placed in
the game directory:

```
2026-04-02_roseville_vs_mahtomedi/
├── roseville_vs_mahtomedi_2026-04-02.mkv   ← full-game highlights
├── period-1/
│   └── period-1_2026-04-02.mkv             ← segment highlight
├── period-2/
│   └── period-2_2026-04-02.mkv
└── period-3/
    └── period-3_2026-04-02.mkv
```

### With iterations

Apply render profiles to the highlights merge:

```bash
# Apply a single profile
reeln game highlights --render-profile slowmo

# Apply iteration profiles
reeln game highlights --iterate
```

### Preview first

```bash
reeln game highlights --dry-run
```

## Assemble a reel from rendered shorts

After rendering individual shorts, combine them into a compilation reel:

```bash
reeln render reel --game-dir .
```

### Filter by segment or event type

```bash
# Only period 1 renders
reeln render reel --game-dir . --segment 1

# Only goal renders
reeln render reel --game-dir . --event-type goal

# Combine filters
reeln render reel --game-dir . --segment 2 --event-type goal
```

### Custom output path

```bash
reeln render reel --game-dir . --output my_reel.mkv
```

## Typical end-of-game workflow

```bash
# 1. Process all segments
reeln game segment 1
reeln game segment 2
reeln game segment 3

# 2. Merge into full-game highlights
reeln game highlights

# 3. Render individual event shorts
reeln render short period-1/clip1.mkv --crop crop --speed 0.5 --game-dir .
reeln render short period-2/clip2.mkv --crop crop --speed 0.5 --game-dir .

# 4. Assemble rendered shorts into a reel
reeln render reel --game-dir .

# 5. Finish the game
reeln game finish
```

## Next steps

- [Game Finish & Cleanup](08-game-finish-and-cleanup.md) — finalize and clean up
- [Profiles & Iterations](07-profiles-and-iterations.md) — automate render settings
