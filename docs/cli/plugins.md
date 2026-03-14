# reeln plugins

Plugin management commands.

## Commands

### `reeln plugins list`

List installed and available plugins with version information.

```bash
reeln plugins list
reeln plugins list --refresh
```

| Option | Description |
|---|---|
| `--refresh` | Force a registry refresh (bypass cache) |

Shows each plugin with version, status, and detected capabilities.

Example output:

```
  youtube  1.2.0 -> 1.3.0  enabled  [uploader]
  llm      0.5.1           enabled  [enricher, generator]
  meta     not installed            [uploader, notifier]
```

Plugins are discovered via Python entry points and the remote plugin registry. Status is determined by the `plugins.enabled` and `plugins.disabled` lists in your config.

### `reeln plugins search`

Search the plugin registry.

```bash
reeln plugins search
reeln plugins search youtube
reeln plugins search --refresh
```

| Argument | Description |
|---|---|
| `QUERY` | Search term — matches against name and description (empty = show all) |

| Option | Description |
|---|---|
| `--refresh` | Force a registry refresh |

### `reeln plugins info`

Show detailed information about a plugin.

```bash
reeln plugins info youtube
```

| Argument | Description |
|---|---|
| `NAME` | Plugin name |

| Option | Description |
|---|---|
| `--refresh` | Force a registry refresh |

Displays: name, package, description, capabilities, homepage, installed version, and available version.

### `reeln plugins install`

Install a plugin from the registry.

```bash
reeln plugins install youtube
reeln plugins install youtube --version 0.1.0
reeln plugins install youtube --version 0.1.0 --dry-run
reeln plugins install youtube --installer uv
```

| Argument | Description |
|---|---|
| `NAME` | Plugin name to install |

| Option | Description |
|---|---|
| `--version` / `-V` | Version to install (e.g. `0.1.0`, `v0.1.0`) |
| `--dry-run` | Preview the install command without executing |
| `--installer` | Force a specific installer (`pip` or `uv`) |

After installation, the plugin is automatically enabled in your config.

**Install source:** When a plugin's registry entry has a GitHub or GitLab homepage, the install uses `git+{homepage}` (e.g. `git+https://github.com/StreamnDad/reeln-plugin-streamn-scoreboard`). Plugins without a git homepage fall back to the PyPI package name.

The installer is auto-detected: `uv` is preferred when available, otherwise falls back to `pip`. On permission failures, the command auto-retries with `--user`.

### `reeln plugins update`

Update a plugin or all installed plugins.

```bash
reeln plugins update youtube
reeln plugins update youtube --version 2.0.0
reeln plugins update
reeln plugins update --dry-run
reeln plugins update --installer pip
```

| Argument | Description |
|---|---|
| `NAME` | Plugin to update (empty = update all installed plugins) |

| Option | Description |
|---|---|
| `--version` / `-V` | Version to update to (e.g. `0.1.0`, `v0.1.0`) |
| `--dry-run` | Preview the update command without executing |
| `--installer` | Force a specific installer (`pip` or `uv`) |

### `reeln plugins enable`

Enable a plugin.

```bash
reeln plugins enable <NAME>
```

| Argument | Description |
|---|---|
| `NAME` | Plugin name to enable |

Adds the plugin to the `plugins.enabled` list and removes it from `plugins.disabled` in your config file.

### `reeln plugins disable`

Disable a plugin.

```bash
reeln plugins disable <NAME>
```

| Argument | Description |
|---|---|
| `NAME` | Plugin name to disable |

Adds the plugin to the `plugins.disabled` list and removes it from `plugins.enabled` in your config file.

## Plugin registry

reeln maintains a remote plugin registry that lists available plugins, their packages, and capabilities. The registry is fetched from GitHub and cached locally for 1 hour.

### Cache behavior

- Registry data is cached in your XDG data directory under `registry/`
- Cache TTL is 1 hour — after expiry, the next command fetches fresh data
- On network failure, stale cache is used as a fallback
- Use `--refresh` on any registry command to force a fresh fetch

### Custom registry URL

You can point reeln at a custom registry by setting the `registry_url` in your config:

```json
{
  "plugins": {
    "registry_url": "https://example.com/my-registry/plugins.json"
  }
}
```

Or via environment variable:

```bash
export REELN_PLUGINS_REGISTRY_URL=https://example.com/my-registry/plugins.json
```

## Plugin extension points

reeln exposes lifecycle hooks that plugins can subscribe to:

| Hook | When it fires |
|---|---|
| `PRE_RENDER` | Before a render operation starts |
| `POST_RENDER` | After a render operation completes |
| `ON_CLIP_AVAILABLE` | After a segment merge produces a clip |
| `ON_EVENT_CREATED` | When a new event is registered |
| `ON_EVENT_TAGGED` | When an event is tagged or updated |
| `ON_GAME_INIT` | After a game directory is created |
| `ON_GAME_READY` | After all `ON_GAME_INIT` hooks complete (cross-plugin data flow) |
| `ON_GAME_FINISH` | After a game is marked as finished |
| `ON_POST_GAME_FINISH` | After all `ON_GAME_FINISH` hooks complete (cross-plugin data flow) |
| `ON_HIGHLIGHTS_MERGED` | After game highlights are merged |
| `ON_SEGMENT_START` | Before segment file I/O begins |
| `ON_SEGMENT_COMPLETE` | After segment merge and state update |
| `ON_ERROR` | When an error occurs in core operations |

Hooks receive a `HookContext` with three fields:

- `hook` — the hook type (e.g. `Hook.ON_GAME_INIT`)
- `data` — read-only data from core (game directory, team profiles, etc.)
- `shared` — writable dict for plugins to pass data back to core

```python
def on_game_init(context: HookContext) -> None:
    game_dir = context.data["game_dir"]
    # Write data back — core persists shared["livestreams"] to game.json
    context.shared["livestreams"] = {"youtube": "https://..."}
```

## Capability protocols

Plugins can implement typed capability interfaces:

- **Generator** — produce media assets (game images, bumper videos, vertical crops)
- **Uploader** — upload rendered media to external services (YouTube, social media, cloud storage)
- **MetadataEnricher** — enrich event metadata with additional information (LLM descriptions, statistics)
- **Notifier** — send notifications when events occur (Slack, Discord, email)

## Orchestration pipeline

When plugins are loaded, the orchestrator runs them through a sequential pipeline:

1. **Generators** — produce assets from context
2. **MetadataEnrichers** — enrich metadata (LLM titles, descriptions)
3. **Uploaders** — upload files with enriched metadata (serialized via upload lock)
4. **Notifiers** — send notifications

Each step is exception-safe — a failing plugin never breaks the pipeline or core operations.

## Plugin discovery

Plugins are discovered via Python entry points in `pyproject.toml`:

```toml
[project.entry-points."reeln.plugins"]
my-plugin = "my_package.plugin:MyPlugin"
```

## Plugin configuration

Per-plugin settings can be provided in the config file:

```json
{
  "plugins": {
    "enabled": ["youtube", "llm"],
    "disabled": ["meta"],
    "settings": {
      "youtube": {
        "api_key": "...",
        "playlist_id": "..."
      }
    }
  }
}
```
