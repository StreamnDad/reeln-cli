# CLI reference

reeln provides a hierarchical command structure organized by domain.

## Top-level commands

| Command | Description | Status | Reference |
|---|---|---|---|
| `reeln --version` | Show version | Available | |
| `reeln --help` | Show help and available commands | Available | |
| `reeln init` | Bootstrap config directories and default config | Planned | |
| `reeln doctor` | Health check: ffmpeg, config, permissions | Available | {doc}`doctor` |

## Command groups

| Group | Description | Status | Reference |
|---|---|---|---|
| `reeln config` | Configuration: show, doctor | Available | {doc}`config` |
| `reeln game` | Game lifecycle: init, segment, highlights, finish, prune | Available | {doc}`game` |
| `reeln render` | Video rendering: short, preview, reel | Available | {doc}`render` |
| `reeln media` | Media management: prune | Available | {doc}`media` |
| `reeln plugins` | Plugin management: list, enable, disable | Available | {doc}`plugins` |

## Global options

| Option | Description |
|---|---|
| `--help` | Show help for the command |
| `--version` | Show reeln version |
| `--log-format json\|human` | Output format (default: human) |
| `--log-level LEVEL` | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: WARNING) |
