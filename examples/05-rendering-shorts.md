# Rendering Shorts

reeln's render commands transform landscape clips into portrait (9:16) or square
(1:1) short-form video — ready for Instagram Reels, TikTok, YouTube Shorts, etc.

## Basic render

```bash
reeln render short clip.mkv
```

This produces a 1080x1920 vertical video using the default **pad** framing mode.

If you have `paths.source_dir` configured, you can omit the clip path — reeln
auto-discovers the most recent replay:

```bash
reeln render short
```

## Quick preview

Generate a fast, low-resolution preview before committing to a full render:

```bash
reeln render preview clip.mkv
```

Preview accepts all the same options as `render short`.

## Framing modes

### Pad (default)

Scales the source to fit the width, then adds bars top and bottom. The full
frame is visible but letterboxed.

```bash
reeln render short clip.mkv --crop pad
```

### Crop

Scales the source to fill the height, then trims the sides. The frame is fully
filled but edges are lost.

```bash
reeln render short clip.mkv --crop crop
```

### Anchor

Control where the crop window is positioned:

```bash
# Center (default)
reeln render short clip.mkv --crop crop --anchor center

# Follow the left side of the frame
reeln render short clip.mkv --crop crop --anchor left

# Custom position (x,y from 0.0 to 1.0)
reeln render short clip.mkv --crop crop --anchor 0.3,0.5
```

## Output formats

```bash
# Vertical — 1080x1920 (default)
reeln render short clip.mkv --format vertical

# Square — 1080x1080
reeln render short clip.mkv --format square

# Custom size
reeln render short clip.mkv --size 720x1280
```

## Speed

```bash
# Half speed (slow motion)
reeln render short clip.mkv --speed 0.5

# Double speed
reeln render short clip.mkv --speed 2.0
```

## Scale / zoom

Zoom into the content before framing:

```bash
# 1.5x zoom with crop — tighter on the action
reeln render short clip.mkv --crop crop --scale 1.5

# 2x zoom with pad — zoomed in, remaining space padded
reeln render short clip.mkv --crop pad --scale 2.0
```

## Color grading

Apply a LUT (Look-Up Table) for color grading:

```bash
reeln render short clip.mkv --lut warm.cube
```

LUT files (`.cube` or `.3dl`) are standard color grading files supported by
most video tools.

## Subtitle overlays

Overlay an ASS subtitle file:

```bash
reeln render short clip.mkv --subtitle overlay.ass
```

## Pad color

Change the letterbox bar color (pad mode only):

```bash
reeln render short clip.mkv --crop pad --pad-color "#1a1a1a"
```

## Combining options

Options compose freely:

```bash
reeln render short clip.mkv \
  --crop crop \
  --scale 1.3 \
  --speed 0.5 \
  --lut cinematic.cube \
  --format vertical
```

## Render within a game context

When you provide a game directory, renders are tracked in `game.json`:

```bash
reeln render short clip.mkv --game-dir .
reeln render short clip.mkv --game-dir . --event abc123
```

## Dry run

Preview the render plan without producing output:

```bash
reeln render short clip.mkv --crop crop --speed 0.5 --dry-run
```

## Debug mode

See the full ffmpeg command and filter chain:

```bash
reeln render short clip.mkv --debug
```

This writes debug artifacts to `debug/` including the ffmpeg command, filter
graph, and input/output metadata.

## Next steps

- [Profiles & Iterations](07-profiles-and-iterations.md) — save render settings as reusable profiles
- [Highlights & Reels](06-highlights-and-reels.md) — combine rendered shorts into reels
- [Smart Zoom](10-smart-zoom.md) — AI-powered tracking that follows the action
