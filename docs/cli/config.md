# reeln config

Configuration management commands.

## Commands

### `reeln config show`

Display the current resolved configuration as JSON.

```bash
reeln config show [--profile <name>]
```

Shows the fully resolved config after merging all layers: bundled defaults, user config, game overrides, and environment variables.

### `reeln config doctor`

Validate configuration and report issues.

```bash
reeln config doctor
```

Checks for:
- Valid JSON syntax
- Known schema version
- Required fields present
- Path permissions
- Secrets accidentally stored in config files

Reports each check as pass, warn, or fail with actionable guidance.

## See also

- {doc}`/guide/configuration` — full guide to the config system
