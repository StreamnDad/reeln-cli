<p align="center">
  <img src="https://raw.githubusercontent.com/StreamnDad/reeln-cli/main/assets/logo.jpg" alt="reeln" width="200">
</p>

# reeln

[![CI](https://github.com/StreamnDad/reeln-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/StreamnDad/reeln-cli/actions/workflows/ci.yml)
[![Docs](https://readthedocs.org/projects/reeln-cli/badge/?version=latest)](https://reeln-cli.readthedocs.io/)
[![PyPI](https://img.shields.io/pypi/v/reeln)](https://pypi.org/project/reeln/)

**Platform-agnostic CLI toolkit for livestreamers.**

reeln handles video manipulation, segment/highlight management, and media lifecycle — generic by default, sport-specific through configuration. Built by [Streamn Dad](https://streamn.dad).

<p align="center">
  <img src="https://raw.githubusercontent.com/StreamnDad/reeln-cli/main/assets/reeln-example.webp" alt="reeln in action — youth hockey livestream with scoreboard overlay" width="700">
</p>

## Requirements

- **Python 3.11+**
- **ffmpeg 5.0+** with libx264, aac, and libass

> **Important:** reeln requires ffmpeg installed on your system. It is used for
> all video processing — merging, rendering, overlays, and encoding. Install it
> before using reeln, then run `reeln doctor` to verify.
>
> ```bash
> # macOS
> brew install ffmpeg
>
> # Ubuntu / Debian
> sudo apt install ffmpeg
>
> # Windows
> winget install ffmpeg
> ```

## Install

```bash
# With pip
pip install reeln

# With uv (recommended)
uv tool install reeln
```

Verify everything is working:

```bash
reeln --version
reeln doctor          # checks ffmpeg, codecs, config, permissions, plugins
```

## Features

- **Game lifecycle management** — init, segment processing, highlights, events, finish
- **Short-form rendering** — crop, scale, speed, LUT, overlays — landscape to vertical/square
- **FFmpeg-powered merging** — concat segments into highlight reels with smart re-encoding
- **Sport-agnostic segments** — hockey periods, basketball quarters, soccer halves, and more
- **Render profiles** — save and reuse rendering settings, chain them with iterations
- **Smart zoom** — AI-powered tracking that follows the action (via plugin)
- **Player overlays** — roster-aware goal overlays with jersey number lookup
- **Render queue** — stage renders for review, then selectively publish to YouTube, Instagram, TikTok
- **Team logo overlays** — automatic logo placement on goal shorts from team profiles
- **Plugin architecture** — lifecycle hooks for YouTube, Instagram, cloud uploads, and more
- **Flexible configuration** — JSON config, XDG paths, env var overrides, named profiles
- **Cross-platform** — macOS, Linux, Windows

## Quick start

```bash
# Initialize a hockey game
reeln game init roseville mahtomedi --sport hockey

# Process segments as the game progresses
reeln game segment 1
reeln game segment 2
reeln game segment 3

# Merge into a full-game highlight reel
reeln game highlights

# Render a vertical short for social media
reeln render short clip.mkv --crop crop --speed 0.5

# Finish the game
reeln game finish
```

See the [examples](examples/) for detailed walkthroughs of every workflow.

> Looking for a GUI? [reeln dock](https://github.com/StreamnDad/reeln-dock) is a cross-platform desktop companion for reeln — visual render profiles, clip review, and game management without touching the terminal. Coming soon.

## Supported sports

| Sport | Segment name | Count | Example directories |
|---|---|---|---|
| hockey | period | 3 | `period-1/`, `period-2/`, `period-3/` |
| basketball | quarter | 4 | `quarter-1/` through `quarter-4/` |
| soccer | half | 2 | `half-1/`, `half-2/` |
| football | half | 2 | `half-1/`, `half-2/` |
| baseball | inning | 9 | `inning-1/` through `inning-9/` |
| lacrosse | quarter | 4 | `quarter-1/` through `quarter-4/` |
| generic | segment | 1 | `segment-1/` |

## CLI reference

### System

| Command | Description |
|---|---|
| `reeln --version` | Show version and ffmpeg info |
| `reeln doctor` | Health check: ffmpeg, codecs, config, permissions, plugins |

### Game lifecycle

| Command | Description |
|---|---|
| `reeln game init` | Set up game directory with sport-specific segments |
| `reeln game segment <N>` | Collect replays and merge segment highlights |
| `reeln game highlights` | Merge all segments into full-game highlight reel |
| `reeln game compile` | Compile event clips by type, segment, or player |
| `reeln game finish` | Finalize game and show summary |
| `reeln game prune` | Remove generated artifacts |
| `reeln game event list` | List registered events |
| `reeln game event tag` | Tag an event with type, player, metadata |

### Rendering

| Command | Description |
|---|---|
| `reeln render short` | Render 9:16 or 1:1 short from clip |
| `reeln render preview` | Fast low-res preview render |
| `reeln render apply` | Apply a render profile (full-frame, no crop) |
| `reeln render reel` | Assemble rendered shorts into a reel |

### Queue

| Command | Description |
|---|---|
| `reeln queue list` | List queued render items |
| `reeln queue show <ID>` | Show detailed queue item info |
| `reeln queue edit <ID>` | Edit title/description before publishing |
| `reeln queue publish <ID>` | Publish to one or all targets (`--target <name>`) |
| `reeln queue publish-all` | Publish all rendered items |
| `reeln queue remove <ID>` | Soft-delete queue item |
| `reeln queue targets` | List available publish targets |

### Configuration

| Command | Description |
|---|---|
| `reeln config show` | Display resolved configuration |
| `reeln config doctor` | Validate config and warn on issues |
| `reeln config event-types` | Manage event types |

### Plugins

| Command | Description |
|---|---|
| `reeln plugins search` | Search the plugin registry |
| `reeln plugins info <name>` | Show plugin details and config schema |
| `reeln plugins install <name>` | Install a plugin from the registry |
| `reeln plugins update [name]` | Update a plugin or all installed |
| `reeln plugins list` | List installed plugins |
| `reeln plugins enable <name>` | Enable a plugin |
| `reeln plugins disable <name>` | Disable a plugin |
| `reeln plugins uninstall <name>` | Uninstall a plugin |
| `reeln plugins auth` | Test plugin authentication |

## Configuration

reeln uses a layered JSON config system:

1. **Bundled defaults** — shipped with the package
2. **User config** — `config.json` in your XDG config directory
3. **Game overrides** — `game.json` in the game directory
4. **Environment variables** — `REELN_<SECTION>_<KEY>`

```bash
reeln config show
```

## Smart zoom — AI-powered action tracking

`reeln render short --smart` uses the [OpenAI plugin](https://github.com/StreamnDad/reeln-plugin-openai) to analyse extracted frames and track the action — dynamically cropping and panning the camera to follow the play in your 9:16 short. Read [What happened when I let AI edit my youth hockey videos](https://streamn-dad.medium.com/what-happened-when-i-let-ai-edit-my-youth-hockey-videos-d7ece1883905) for the full story.

Add `--debug` to see exactly what the AI sees: annotated frames with crosshair tracking, crop regions, the full zoom path, and every ffmpeg filter chain.

[Live debug example](https://streamn.dad/examples/reeln-debug/) — real game clip with 16-frame smart zoom tracking.

<p align="center">
  <a href="https://streamn.dad/examples/reeln-debug/">
    <img src="https://raw.githubusercontent.com/StreamnDad/reeln-cli/main/assets/debug-preview.png" alt="Smart zoom debug — annotated frame showing crosshair tracking and crop region" width="600">
  </a>
</p>

## Documentation

- [Full documentation](https://reeln-cli.readthedocs.io) — install, guides, CLI reference
- [Examples](examples/) — step-by-step walkthroughs for common workflows

## License

[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0)

## Links

- [streamn.dad](https://streamn.dad) — project home
- [Documentation](https://reeln-cli.readthedocs.io) — full docs
- [@streamn_dad](https://www.instagram.com/streamn_dad/) — highlights on Instagram
- [YouTube](https://www.youtube.com/@streamn-dad) — livestreams and highlights
