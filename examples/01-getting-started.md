# Getting Started

This guide walks through setting up reeln from scratch on a fresh machine.
All commands work on macOS, Linux, and Windows.

## 1. Open a terminal

| Platform | How |
|----------|-----|
| macOS | Spotlight (`Cmd+Space`) → type "Terminal" → Enter |
| Windows | Start menu → "Terminal" or "PowerShell" |
| Linux | `Ctrl+Alt+T` (most distros) or find "Terminal" in your app launcher |

## 2. Check Python

reeln requires **Python 3.11 or later**.

```bash
python3 --version
```

If you see `3.11.x` or higher, you're good — skip to [step 3](#3-install-ffmpeg).

### Install or upgrade Python

**Option A — Official installer** (all platforms):

Download from [python.org/downloads](https://www.python.org/downloads/) and run
the installer. Make sure "Add Python to PATH" is checked on Windows.

**Option B — Package manager:**

```bash
# macOS (Homebrew)
brew install python@3.13

# Ubuntu / Debian
sudo apt update && sudo apt install python3.13

# Windows (winget)
winget install Python.Python.3.13
```

**Option C — pyenv** (manage multiple versions):

```bash
# Install pyenv (macOS/Linux)
curl https://pyenv.run | bash

# Install Python
pyenv install 3.13
pyenv global 3.13
```

After installing, verify:

```bash
python3 --version
# Python 3.13.x
```

## 3. Install ffmpeg

reeln uses ffmpeg for all video processing. You need version **5.0 or later**
with these capabilities:

- **libx264** — H.264 video encoding
- **aac** — audio encoding
- **libass** — subtitle/overlay rendering

Most standard ffmpeg packages include all of these.

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows
winget install ffmpeg
# or: choco install ffmpeg
```

Verify your install:

```bash
ffmpeg -version
```

Look for the version number in the first line — it should be `5.x` or higher.

## 4. Install reeln

### With pip

```bash
pip install reeln
```

### With uv (recommended)

[uv](https://docs.astral.sh/uv/) is a fast Python package installer. If you
don't have it:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install reeln as a tool:

```bash
uv tool install reeln
```

### Verify

```bash
reeln --version
```

This prints the reeln version and detected ffmpeg info.

## 5. Run health checks

```bash
reeln doctor
```

`doctor` checks everything reeln needs to run:

- ffmpeg discovery and version
- Codec availability (libx264, aac, libass)
- Hardware acceleration support
- Config file validity
- Directory permissions
- Plugin health (if any are installed)

Each check reports **PASS**, **WARN**, or **FAIL** with actionable hints.

## 6. Set up shell completion (optional)

```bash
# zsh (default on macOS)
reeln --install-completion zsh

# bash
reeln --install-completion bash

# fish
reeln --install-completion fish
```

Restart your shell after installing completion.

## Next steps

- [Configuration & OBS Setup](02-configuration.md) — connect reeln to your OBS replay buffer
- [Starting a Game](03-starting-a-game.md) — jump straight into a game workflow
