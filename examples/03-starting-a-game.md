# Starting a Game

A "game" in reeln is a workspace directory that tracks segments, events, renders,
and game state. This guide covers creating one.

## Initialize a game

Provide the two team names and your sport:

```bash
reeln game init roseville mahtomedi --sport hockey
```

This creates a game directory in your configured `output_dir` (or current
directory):

```
2026-04-02_roseville_vs_mahtomedi/
├── game.json        # game state and metadata
├── period-1/        # segment directories
├── period-2/
└── period-3/
```

The segment directories use sport-specific names:

| Sport | Segments created |
|-------|-----------------|
| hockey | `period-1/` `period-2/` `period-3/` |
| basketball | `quarter-1/` `quarter-2/` `quarter-3/` `quarter-4/` |
| soccer | `half-1/` `half-2/` |
| football | `half-1/` `half-2/` |
| baseball | `inning-1/` through `inning-9/` |
| lacrosse | `quarter-1/` through `quarter-4/` |

## Preview before creating

Use `--dry-run` to see what would be created without writing anything:

```bash
reeln game init roseville mahtomedi --sport hockey --dry-run
```

## Additional options

```bash
reeln game init roseville mahtomedi \
  --sport hockey \
  --venue "Guidant John Rose Arena" \
  --game-time "7:00 PM" \
  --level 2016 \
  --tournament "Presidents Day Classic" \
  --description "Pool play round 1"
```

| Flag | Purpose |
|------|---------|
| `--venue` | Arena or field name |
| `--game-time` | Scheduled start time |
| `--level` | Competition level or birth year (loads team profiles) |
| `--tournament` | Tournament name |
| `--description` | Free-form game notes |
| `--date` | Override date (default: today) |
| `--output-dir` | Override where the game directory is created |

## Interactive mode

Run without arguments for guided prompts:

```bash
reeln game init
```

This walks you through each field interactively.

> **Note:** Interactive mode requires the `interactive` extra:
> `pip install reeln[interactive]`

## Double-headers

Running `game init` twice for the same teams on the same date automatically
creates a `_g2` suffix:

```bash
reeln game init roseville mahtomedi --sport hockey
# Creates: 2026-04-02_roseville_vs_mahtomedi/

reeln game init roseville mahtomedi --sport hockey
# Creates: 2026-04-02_roseville_vs_mahtomedi_g2/
```

## Team profiles

When `--level` is provided, reeln looks up team profiles from your config
directory. Profiles store team metadata — name, abbreviation, colors, logo,
and roster — so you don't have to re-enter them for each game.

```bash
reeln game init eagles bears --sport hockey --level bantam
```

Team profiles are stored at:

```
{config_dir}/teams/{level}/{team_slug}.json
```

See [Configuration](02-configuration.md) for config directory locations.

## Other sports

The same workflow applies to any supported sport:

```bash
# Basketball
reeln game init lakers celtics --sport basketball

# Soccer
reeln game init city united --sport soccer

# Baseball
reeln game init twins yankees --sport baseball
```

## Next steps

- [Segments & Events](04-segments-and-events.md) — process game segments and tag events
- [Rendering Shorts](05-rendering-shorts.md) — render clips into short-form video
