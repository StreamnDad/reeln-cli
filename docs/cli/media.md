# reeln media

Media management and cleanup commands.

## Commands

### `reeln media prune`

Remove generated artifacts from all finished games under a base directory.

```bash
reeln media prune [OPTIONS]
```

| Option | Description |
|---|---|
| `--output-dir`, `-o` | Base directory to scan for games (default: `paths.output_dir` from config, or cwd) |
| `--all` | Also remove raw event clips (default: keep source clips) |
| `--profile` | Named config profile |
| `--config` | Explicit config file path |
| `--dry-run` | Show what would be removed without deleting |

Discovers game directories under the base path (directories containing `game.json`), then prunes each **finished** game. Unfinished games are skipped with a message.

For each finished game, removes generated files (segment merges, highlight reels, rendered shorts, compilations, temp files) while preserving raw event clips and `game.json`. With `--all`, also removes raw event clips.

Reports per-game results and an aggregate summary of files removed and bytes freed.

**Examples:**

```bash
# Prune all finished games in the default output directory
reeln media prune

# Prune games in a specific directory
reeln media prune -o ~/games

# Also remove raw event clips
reeln media prune --all -o ~/games

# Preview without deleting
reeln media prune --dry-run -o ~/games
```

:::{tip}
Use `reeln game prune` to prune a single game directory instead of scanning all games.
:::
