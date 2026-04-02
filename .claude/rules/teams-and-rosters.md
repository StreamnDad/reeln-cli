---
globs: ["reeln/models/team.py", "reeln/core/teams.py", "reeln/commands/game.py", "tests/**/test_team*.py", "tests/**/test_game*.py"]
---

# Team Profiles & Rosters

Teams are managed as reusable JSON profiles stored in the config directory, organized by level.

## Storage Layout

```
~/Library/Application Support/reeln/teams/  (macOS) or ~/.config/reeln/teams/ (Linux)
├── 2016/                    # level = birth year tournament
│   ├── north.json
│   ├── south.json
│   ├── east.json
│   └── west.json
├── bantam/                  # level = league division
│   ├── roseville.json
│   └── mahtomedi.json
└── varsity/
    └── ...
```

## TeamProfile Model (`reeln/models/team.py`)

```python
@dataclass
class TeamProfile:
    team_name: str                          # Full name (e.g., "North")
    short_name: str                         # Abbreviation (e.g., "NOR")
    level: str                              # Competition level / birth year
    logo_path: str = ""                     # Path to team logo PNG
    roster_path: str = ""                   # Path to roster JSON file
    colors: list[str] = []                  # Brand colors (hex, e.g., ["#C8102E"])
    jersey_colors: list[str] = []           # Jersey colors (e.g., ["white", "red"])
    metadata: dict[str, Any] = {}           # Free-form (conference, mascot, etc.)
```

## Team Management (`reeln/core/teams.py`)

- `slugify(name)` — team name -> filesystem slug (e.g., "St. Louis Park" -> `st_louis_park`)
- `save_team_profile(profile, slug)` — atomic write to `{config_dir}/teams/{level}/{slug}.json`
- `load_team_profile(level, slug)` — load from disk, raises `ConfigError` on missing/invalid
- `list_team_profiles(level)` — sorted slugs for a level
- `list_levels()` — all available levels
- `delete_team_profile(level, slug)` — remove a profile

## Roster Files

Roster files are **external to reeln core** — the `roster_path` field in `TeamProfile` is a pointer to a CSV file. Rosters are consumed by plugins and rendering overlays, not by core logic.

**Roster CSV format** (all three columns required, `position` may be empty):

```csv
number,name,position
10,First Last,C
22,First Last,D
7,First Last,
```

Rosters commonly come from screenshots (game sheets, tournament apps, etc.) that need to be transcribed into CSV.

## Common Workflow: Tournament Setup

Tournaments often use birth-year levels (e.g., "2016") with multiple teams. Typical setup:

1. Create team profiles for each team in the tournament level
2. Set `logo_path` to point to each team's logo PNG
3. Create roster JSON files (often transcribed from screenshots of game sheets)
4. Set `roster_path` in each profile to point to the roster file
5. Use `reeln game init <home> <away> --level 2016` to init games with profiles

## CLI Usage

```bash
reeln game init north south --sport hockey --level 2016
```

When `--level` is specified, team names are slugified and profiles are loaded from disk. Profiles (including logo and roster paths) are passed to plugins via the `ON_GAME_INIT` hook context.
