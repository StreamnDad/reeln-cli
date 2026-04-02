# Smart Zoom

Smart zoom uses AI vision to track the action in your clips and dynamically
adjust the crop or pan position throughout the video.

## Prerequisites

Smart zoom requires a vision plugin. Install the OpenAI plugin:

```bash
reeln plugins install openai
```

Configure it in your config file:

```json
{
  "plugins": {
    "enabled": ["openai"],
    "settings": {
      "openai": {
        "api_key": "sk-...",
        "smart_zoom_enabled": true,
        "smart_zoom_model": "gpt-4o"
      }
    }
  }
}
```

## Basic usage

Add `--smart` to any render command:

```bash
reeln render short clip.mkv --smart
```

## How it works

1. reeln extracts frames from the clip (default: 5 keyframes)
2. The vision plugin analyzes each frame to find the action point
3. A zoom path is built from the detected positions
4. ffmpeg uses dynamic expressions to smoothly track the action

## Smart + crop

The crop window follows the action — both horizontally and vertically:

```bash
reeln render short clip.mkv --crop crop --smart
```

## Smart + pad

Pillarbox bars pan horizontally to center the action. Vertical position stays
fixed:

```bash
reeln render short clip.mkv --crop pad --smart
```

## Control keyframe density

More keyframes = smoother tracking but more API calls:

```bash
# Fewer keyframes (faster, cheaper)
reeln render short clip.mkv --smart --zoom-frames 3

# More keyframes (smoother tracking)
reeln render short clip.mkv --smart --zoom-frames 15
```

Default is 5 keyframes. Maximum is 20.

## Combine with other options

Smart zoom composes with all other render options:

```bash
reeln render short clip.mkv \
  --crop crop \
  --smart \
  --speed 0.5 \
  --scale 1.3 \
  --lut cinematic.cube
```

## Debug mode

See exactly what the AI detected and how the zoom path was built:

```bash
reeln render short clip.mkv --smart --debug
```

This creates a `debug/zoom/` directory with:

- `frame_NNNN.png` — extracted source frames
- `annotated_NNNN.png` — frames with crosshair and crop box overlay
- `zoom_path.json` — full zoom data and generated ffmpeg expressions

## Smart zoom with profiles

Enable smart tracking in a render profile:

```json
{
  "render_profiles": {
    "smart-crop": {
      "crop_mode": "crop",
      "smart": true,
      "speed": 0.5
    }
  }
}
```

```bash
reeln render short clip.mkv --render-profile smart-crop
```

## Smart zoom with iterations

When `--smart` is used with `--iterate`, the vision analysis runs once and the
zoom path is reused (and remapped for speed changes) across all iterations:

```bash
reeln render short clip.mkv --smart --iterate --game-dir . --event abc123
```

## Without a vision plugin

If you use `--smart` without a vision plugin installed, reeln falls back to
static center positioning and logs a warning. No error — just no tracking.

## Next steps

- [Rendering Shorts](05-rendering-shorts.md) — all render options reference
- [Profiles & Iterations](07-profiles-and-iterations.md) — save smart zoom settings in profiles
- [Plugins](09-plugins.md) — install and manage the OpenAI plugin
