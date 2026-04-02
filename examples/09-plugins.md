# Plugins

Plugins extend reeln with integrations for platforms like YouTube, Instagram,
and cloud storage — plus AI-powered features like smart zoom.

## Browse the registry

```bash
# List all available plugins
reeln plugins search

# Search by keyword
reeln plugins search youtube
reeln plugins search upload

# Get detailed info about a plugin
reeln plugins info google
```

## Available plugins

| Plugin | Package | What it does |
|--------|---------|-------------|
| **google** | `reeln-plugin-google` | YouTube livestream creation, video uploads, playlists, comments |
| **meta** | `reeln-plugin-meta` | Facebook Live, Instagram Reels, Threads posting |
| **cloudflare** | `reeln-plugin-cloudflare` | R2 video uploads with CDN URL sharing |
| **openai** | `reeln-plugin-openai` | AI metadata generation, smart zoom via vision |
| **streamn-scoreboard** | `reeln-plugin-streamn-scoreboard` | OBS scoreboard text file bridge |

## Install a plugin

```bash
reeln plugins install google
```

This installs the package and enables the plugin. Plugin default settings are
automatically seeded into your config.

### Preview before installing

```bash
reeln plugins install google --dry-run
```

### Specify an installer

```bash
# Use uv instead of pip
reeln plugins install google --installer uv
```

## List installed plugins

```bash
reeln plugins list
```

Shows installed plugins with version info and enabled/disabled status.

## Enable and disable

```bash
reeln plugins disable google
reeln plugins enable google
```

## Update plugins

```bash
# Update a specific plugin
reeln plugins update google

# Update all installed plugins
reeln plugins update
```

## Configure a plugin

Plugin settings live in your config file under `plugins.settings`:

```json
{
  "plugins": {
    "enabled": ["google", "openai"],
    "settings": {
      "google": {
        "create_livestream": true,
        "upload_highlights": true,
        "playlist_id": "PLxxxxxxxx"
      },
      "openai": {
        "api_key": "sk-...",
        "smart_zoom_enabled": true
      }
    }
  }
}
```

Every plugin capability is **off by default** — you explicitly opt in to each
feature via config flags.

### View a plugin's config schema

```bash
reeln plugins info google
```

This shows all available settings, their types, defaults, and descriptions.

## How plugins hook into the game lifecycle

Plugins respond to lifecycle events. For example, with the google plugin
enabled and configured:

```bash
reeln game init roseville mahtomedi --sport hockey
# → google plugin creates a YouTube livestream

reeln game finish
# → google plugin updates the livestream status

reeln game highlights
# → google plugin uploads the highlight reel
```

The same CLI commands — plugins add behavior without changing the interface.

## Verify plugin health

```bash
reeln doctor
```

After installing plugins, `doctor` includes plugin-specific health checks
alongside the standard ffmpeg and config checks.

## Next steps

- [Smart Zoom](10-smart-zoom.md) — AI-powered tracking (requires openai plugin)
- [Configuration](02-configuration.md) — plugin settings reference
