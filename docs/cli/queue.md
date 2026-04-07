# reeln queue

Render queue management for staged render-then-publish workflows.

## Overview

The render queue decouples rendering from publishing. Instead of `POST_RENDER`
plugin hooks firing immediately after a render, the `--queue` flag on
`render short` or `render apply` saves the rendered output to a queue for
review. You can then edit metadata (title, description), selectively publish
to specific platforms, and track per-target publish status.

Queue files are stored per-game as `render_queue.json` alongside `game.json`.

## Commands

### `reeln queue list`

List queued render items.

```bash
reeln queue list [OPTIONS]
```

| Option | Description |
|---|---|
| `--game-dir`, `-g` | Game directory (default: cwd) |
| `--all`, `-a` | List across all games (uses central index) |
| `--status`, `-s` | Filter by status: rendered, published, partial, failed |

Removed items are hidden by default.

### `reeln queue show`

Show detailed info for a queue item.

```bash
reeln queue show <ID> [OPTIONS]
```

| Option | Description |
|---|---|
| `--game-dir`, `-g` | Game directory (default: cwd) |

Displays output path, duration, file size, game context, player info, render
profile, publish targets with status and URLs.

ID supports prefix matching (e.g., `abc` matches `abc123def456`).

### `reeln queue edit`

Edit title or description before publishing.

```bash
reeln queue edit <ID> [OPTIONS]
```

| Option | Description |
|---|---|
| `--title`, `-t` | New title |
| `--description`, `-d` | New description |
| `--game-dir`, `-g` | Game directory (default: cwd) |

At least one of `--title` or `--description` is required.

### `reeln queue publish`

Publish a queue item to one or all targets.

```bash
reeln queue publish <ID> [OPTIONS]
```

| Option | Description |
|---|---|
| `--target`, `-t` | Publish to specific target only (e.g., `google`, `meta`) |
| `--game-dir`, `-g` | Game directory (default: cwd) |
| `--profile` | Override config profile (default: profile stored at queue time) |
| `--config` | Explicit config file path |

Without `--target`, publishes to all pending targets. Each target is tracked
independently — you can publish to YouTube first, review, then push to
Instagram later.

The config profile stored in the queue item is used by default, ensuring the
same plugin settings (API keys, channel IDs, etc.) apply. Use `--profile` to
override.

### `reeln queue publish-all`

Publish all rendered items in the queue.

```bash
reeln queue publish-all [OPTIONS]
```

| Option | Description |
|---|---|
| `--game-dir`, `-g` | Game directory (default: cwd) |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |

Only items with status `rendered` are published. Items already published,
failed, or removed are skipped.

### `reeln queue remove`

Soft-delete a queue item.

```bash
reeln queue remove <ID> [OPTIONS]
```

| Option | Description |
|---|---|
| `--game-dir`, `-g` | Game directory (default: cwd) |

Marks the item as removed. Does not delete the rendered file.

### `reeln queue targets`

List available publish targets from loaded uploader plugins.

```bash
reeln queue targets [OPTIONS]
```

| Option | Description |
|---|---|
| `--profile` | Named config profile |
| `--config` | Explicit config file path |

Targets are discovered from installed plugins that implement the `Uploader`
capability protocol.

## Status lifecycle

Queue items progress through these statuses:

| Status | Meaning |
|---|---|
| `rendered` | Render complete, not yet published |
| `publishing` | Publish in progress |
| `published` | All targets published successfully |
| `partial` | Some targets published, others pending or failed |
| `failed` | All target publishes failed |
| `removed` | Soft-deleted |

Each publish target has its own status: `pending`, `published`, `failed`, or
`skipped`.

## Examples

```bash
# Render and queue
reeln render short clip.mkv --queue --profile tournament-stream

# Review what's queued
reeln queue list
reeln queue show abc123

# Fix the title
reeln queue edit abc123 --title "Smith Goal - North vs South"

# Publish to YouTube first
reeln queue publish abc123 --target google

# Review the YouTube upload, then push to Instagram
reeln queue publish abc123 --target meta

# See all available targets
reeln queue targets
```
