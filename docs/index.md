# reeln

**Platform-agnostic CLI toolkit for livestreamers.**

reeln handles video manipulation, segment/highlight management, and media lifecycle. It's generic by default and sport-specific through configuration — hockey periods, basketball quarters, soccer halves, and more all work out of the box.

## What reeln does

- **FFmpeg foundation** — cross-platform ffmpeg discovery, version checking, probe helpers, deterministic command building
- **Flexible configuration** — JSON config with XDG-compliant paths, env var overrides, named profiles
- **Sport-agnostic segment model** — built-in support for 7 sports with custom sport registration
- **Game lifecycle management** — initialize game directories, process segments, merge highlights, finalize *(in progress)*
- **Short-form rendering** — crop, scale, and reframe clips into vertical/square formats with speed control, LUT grading, and subtitle overlays
- **Plugin-ready architecture** — lifecycle hooks and capability interfaces for future extensions

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

## Project

```{toctree}
:maxdepth: 1

changelog
```
