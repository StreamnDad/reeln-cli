# Installation

## Requirements

- **Python 3.11+**
- **ffmpeg 5.0+** — reeln uses ffmpeg for all video processing

## Install reeln

### With pip

```bash
pip install reeln
```

### With uv

```bash
uv tool install reeln
```

### Development install

```bash
git clone https://github.com/StreamnDad/reeln-cli.git
cd reeln-cli
make dev-install
```

This creates a virtual environment and installs reeln in editable mode with dev dependencies (pytest, ruff, mypy).

## Install ffmpeg

reeln requires ffmpeg 5.0 or later. After installing, run `reeln doctor` to verify your setup.

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
reeln --version  # confirms reeln is installed
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
