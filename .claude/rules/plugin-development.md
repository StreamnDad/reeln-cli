---
globs: ["reeln/plugins/**", "reeln/models/plugin_schema.py", "registry/**", "tests/**/test_plugin*.py", "tests/**/test_registry.py", "tests/**/test_hooks.py", "tests/**/test_capabilities.py"]
---

# Plugin Development

Complete reference for building reeln-cli plugins.

## Plugin Anatomy

A plugin is a Python package with an entry point in the `reeln.plugins` group.

```python
# pyproject.toml
[project.entry-points."reeln.plugins"]
myplugin = "reeln_myplugin:MyPlugin"
```

The plugin class must expose these attributes and a `register()` method:

```python
class MyPlugin:
    name: str = "myplugin"           # unique plugin name
    version: str = "0.1.0"          # semver, kept in sync with __init__.__version__
    api_version: int = 1            # plugin API version (currently 1)
    config_schema: PluginConfigSchema = PluginConfigSchema(fields=(...))

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = config or {}

    def register(self, registry: HookRegistry) -> None:
        registry.register(Hook.ON_GAME_INIT, self.on_game_init)

    def on_game_init(self, context: HookContext) -> None:
        ...
```

## Hook System

**Hook enum** (`reeln.plugins.hooks.Hook`) — 13 lifecycle hooks:

| Hook | Emitted when |
|------|-------------|
| `PRE_RENDER` | Before a render operation starts |
| `POST_RENDER` | After a render completes |
| `ON_CLIP_AVAILABLE` | A new clip file is ready |
| `ON_EVENT_CREATED` | A new event is created |
| `ON_EVENT_TAGGED` | An event is tagged/categorized |
| `ON_GAME_INIT` | `reeln game init` sets up a new game |
| `ON_GAME_READY` | After all `ON_GAME_INIT` handlers complete — plugins read shared context from init phase |
| `ON_GAME_FINISH` | `reeln game finish` finalizes a game |
| `ON_HIGHLIGHTS_MERGED` | Segment highlights are merged into a reel |
| `ON_SEGMENT_START` | A new segment begins |
| `ON_SEGMENT_COMPLETE` | A segment finishes |
| `ON_FRAMES_EXTRACTED` | Frames extracted from a clip for smart zoom analysis |
| `ON_ERROR` | An error occurs during any operation |

**HookContext** — frozen dataclass passed to every handler:

```python
@dataclass(frozen=True)
class HookContext:
    hook: Hook                              # which hook fired
    data: dict[str, Any] = field(...)       # hook-specific payload (e.g. game_info)
    shared: dict[str, Any] = field(...)     # mutable cross-plugin communication
```

**Handler signature:** `def on_<hook>(self, context: HookContext) -> None`

Handlers are auto-discovered by `on_<hook_name>` naming convention (e.g., `on_game_init` for `ON_GAME_INIT`).

## Shared Context Convention

Plugins communicate via `context.shared` — a mutable dict on the frozen dataclass:

```python
# Writer (e.g., google plugin)
context.shared["livestreams"] = context.shared.get("livestreams", {})
context.shared["livestreams"]["google"] = "https://youtube.com/live/abc123"

# Reader (e.g., OBS plugin)
url = context.shared.get("livestreams", {}).get("google")
```

## Capability Protocols

Plugins can implement typed protocols for specific capabilities (`reeln.plugins.capabilities`):

| Protocol | Method | Purpose |
|----------|--------|---------|
| `Uploader` | `upload(path, *, metadata) -> str` | Upload rendered media to external services |
| `MetadataEnricher` | `enrich(event_data) -> dict` | Enrich event metadata |
| `Notifier` | `notify(message, *, metadata) -> None` | Send notifications |
| `Generator` | `generate(context) -> GeneratorResult` | Generate media assets |

## Config Schema

Declare plugin config with `PluginConfigSchema` and `ConfigField` (`reeln.models.plugin_schema`):

```python
from reeln.models.plugin_schema import ConfigField, PluginConfigSchema

config_schema = PluginConfigSchema(
    fields=(
        ConfigField(
            name="api_key",
            field_type="str",     # str, int, float, bool, list
            required=True,
            description="API key for the service",
            secret=True,          # masked in `reeln config show`
        ),
        ConfigField(
            name="timeout",
            field_type="int",
            default=30,
            description="Request timeout in seconds",
        ),
    )
)
```

## Plugin Discovery

The plugin loader discovers plugins via `importlib.metadata` entry points in the `reeln.plugins` group. Each entry point maps a plugin name to a class:

```toml
[project.entry-points."reeln.plugins"]
google = "reeln_google_plugin:GooglePlugin"
```

Users enable/disable plugins via `reeln plugins enable <name>` / `reeln plugins disable <name>`.

## Registry

Plugin registry lives at `registry/plugins.json`. Format:

```json
{
  "registry_version": 1,
  "plugins": [
    {
      "name": "myplugin",
      "package": "reeln-plugin-myplugin",
      "description": "What the plugin does",
      "capabilities": ["hook:ON_GAME_INIT"],
      "homepage": "https://github.com/StreamnDad/reeln-plugin-myplugin",
      "min_reeln_version": "0.0.19",
      "author": "StreamnDad",
      "license": "AGPL-3.0",
      "ui_contributions": { ... }
    }
  ]
}
```

When adding a new plugin, append to the `plugins` array.

## UI Contributions (reeln-dock)

Plugins can declare UI fields that appear in the reeln-dock desktop app. Fields only
render when the plugin is installed **and** enabled. Add `ui_contributions` to the
registry entry.

### Screens

| Screen | Where it appears |
|--------|-----------------|
| `render_options` | ClipReviewPanel overrides section (below crop/scale/speed) |
| `settings` | Settings > Rendering > Plugin Defaults section |
| `clip_review` | ClipReviewPanel metadata section |

### Field Schema

```json
{
  "ui_contributions": {
    "render_options": {
      "fields": [
        {
          "id": "smart",
          "label": "Smart Zoom",
          "type": "boolean",
          "default": false,
          "description": "AI-powered smart crop tracking",
          "maps_to": "smart"
        },
        {
          "id": "zoom_frames",
          "label": "Zoom Frames",
          "type": "number",
          "min": 1,
          "max": 30,
          "step": 1,
          "description": "Keyframes for smart zoom path",
          "maps_to": "zoom_frames"
        }
      ]
    }
  }
}
```

### Field Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | string | yes | Unique field identifier |
| `label` | string | yes | Display label |
| `type` | string | yes | `boolean`, `number`, `string`, or `select` |
| `default` | any | no | Default value |
| `description` | string | no | Help text shown below the field |
| `min` | number | no | Minimum (number fields) |
| `max` | number | no | Maximum (number fields) |
| `step` | number | no | Step increment (number fields) |
| `options` | array | no | `[{value, label}]` for select fields |
| `maps_to` | string | no | Key in `RenderOverrides` this value maps to. Defaults to `id` |

### How Values Flow

- **`render_options`** fields → `RenderOverrides` object → passed to render backend
- **`settings`** fields → `DockSettings.rendering.plugin_field_defaults` → auto-applied as override defaults
- **`clip_review`** fields → event metadata

The `maps_to` field controls which override key the value is stored under. For example,
`"maps_to": "smart"` maps to `RenderOverrides.smart`. Use this when the backend already
has a named field. For new plugin-specific fields, the value passes through via the
`RenderOverrides` index signature (TS) / `serde(flatten)` (Rust).

## Standard Boilerplate

Use the reeln-plugin-template repo to scaffold new plugins. It provides:

- `Makefile` — dev-install, test, lint, format, check targets
- `.github/workflows/ci.yml` — Python 3.11/3.12/3.13 matrix CI
- `.github/workflows/release.yml` — tag-triggered OIDC PyPI publish
- `pyproject.toml` — hatchling build, ruff/mypy config
- Plugin skeleton with `__init__.py` and `plugin.py`
- Test skeleton with conftest fixtures and basic tests
- `CHANGELOG.md`, `README.md`, `CLAUDE.md`

## Feature Flags

Every capability a plugin provides **must** be feature-flagged in the plugin config and **default to `false`**. Users explicitly opt in to each capability. Hook handlers check the flag before executing.

```python
ConfigField(name="create_livestream", field_type="bool", default=False, description="Enable livestream creation on game init"),
```

```python
def on_game_init(self, context: HookContext) -> None:
    if not self._config.get("create_livestream", False):
        return
    ...
```

## Plugin Conventions

- **Feature flags:** every capability defaults to `false` — users opt in explicitly
- **Coverage:** 100% line + branch — no exceptions
- **Versioning:** semver, update `__version__` (in `__init__.py`), `version` (in `plugin.py`), and `CHANGELOG.md` in lockstep
- **Style:** `from __future__ import annotations` in every module, 4-space indent, snake_case, type hints on all signatures
- **Paths:** `pathlib.Path` everywhere
- **License:** AGPL-3.0-only
- **Tests:** use `tmp_path` for file I/O, mock external API clients
- **Package naming:** `reeln-plugin-<name>` (PyPI), `reeln_<name>_plugin` (Python package)
- **Entry point:** `reeln.plugins` group, plugin name as key
- **No CLI arg registration:** plugins do not register CLI arguments. Use feature flags in plugin config (`smart_zoom_enabled`, etc.). Core CLI flags (`--smart`) trigger hooks; plugins decide behavior via their own config
