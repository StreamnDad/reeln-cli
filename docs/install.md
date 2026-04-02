# Installation

## Requirements

- **Python 3.11+**
- **ffmpeg 5.0+** — reeln uses the ffmpeg binary for rendering video with complex filter chains, subtitle overlays (requires libass), and codec support (libx264, aac)

## Install reeln

### With pip

```bash
pip install reeln
```

### With uv

```bash
uv tool install reeln
```

This installs the `reeln` CLI and `reeln-native` (a Rust extension that handles media probing, concatenation, frame extraction, and overlay rendering using ffmpeg libraries). Pre-built wheels are available for Linux (x86_64) and macOS (arm64) — other platforms build from source and require ffmpeg development headers.

### Development install

```bash
git clone https://github.com/StreamnDad/reeln-cli.git
cd reeln-cli
make dev-install
```

This creates a virtual environment and installs reeln in editable mode with dev dependencies (pytest, ruff, mypy).

## Install ffmpeg

reeln requires the ffmpeg binary (5.0 or later) with at least these capabilities:

- **libx264** — h264 video encoding
- **aac** — audio encoding
- **libass** — ASS subtitle rendering (used for overlay templates)

Most standard ffmpeg packages include all of these. After installing, run `reeln doctor` to verify your setup.

### macOS

```bash
brew install ffmpeg
```

### Ubuntu / Debian

```bash
sudo apt install ffmpeg
```

### Windows

```bash
winget install ffmpeg
# or
choco install ffmpeg
```

### Verify

```bash
ffmpeg -version    # should show 5.0+
reeln doctor       # checks ffmpeg, codecs, config, permissions, plugins
```

## Shell completion

reeln supports tab completion for bash, zsh, and fish:

```bash
# zsh
reeln --install-completion zsh

# bash
reeln --install-completion bash

# fish
reeln --install-completion fish
```
