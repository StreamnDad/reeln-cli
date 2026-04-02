# reeln

**Platform-agnostic CLI toolkit for livestreamers.**

reeln handles video manipulation, segment/highlight management, and media lifecycle. It's generic by default and sport-specific through configuration — hockey periods, basketball quarters, soccer halves, and more all work out of the box.

## What reeln does

- **FFmpeg foundation** — cross-platform ffmpeg discovery, version checking, probe helpers, deterministic command building
- **Flexible configuration** — JSON config with XDG-compliant paths, env var overrides, named profiles
- **Sport-agnostic segment model** — built-in support for 7 sports with custom sport registration
- **Game lifecycle management** — initialize game directories, process segments, merge highlights, tag events, finalize
- **Short-form rendering** — crop, scale, speed, LUT, overlays — landscape to vertical/square
- **Render profiles & iterations** — save and reuse render settings, chain them for multi-pass output
- **Smart zoom** — AI-powered tracking that follows the action (via plugin)
- **Player overlays** — roster-aware goal overlays with jersey number lookup
- **Plugin architecture** — lifecycle hooks for YouTube, Instagram, cloud uploads, and more
- **Cross-platform** — macOS, Linux, Windows

:::{important}
reeln requires **ffmpeg 5.0+** installed on your system for all video processing.
See {doc}`install` for setup instructions, then run `reeln doctor` to verify.
:::

## Getting started

```{toctree}
:maxdepth: 2

install
quickstart
```

## User guide

```{toctree}
:maxdepth: 2

guide/configuration
guide/overlay-templates
guide/sports
```

## CLI reference

```{toctree}
:maxdepth: 2

cli/index
cli/doctor
cli/game
cli/render
cli/media
cli/config
cli/plugins
```

## Examples

```{toctree}
:maxdepth: 1

examples/index
```

## Project

```{toctree}
:maxdepth: 1

changelog
```
