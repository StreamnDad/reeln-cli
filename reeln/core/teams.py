"""Team profile management: load, save, list, delete, roster lookup."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import tempfile
from pathlib import Path

from reeln.core.config import _config_base_dir
from reeln.core.errors import ConfigError
from reeln.models.game import GameInfo
from reeln.models.team import RosterEntry, TeamProfile, dict_to_team_profile, team_profile_to_dict

logger = logging.getLogger(__name__)


def slugify(name: str) -> str:
    """Convert a team name to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric runs with ``_``, and strips
    leading/trailing underscores.
    """
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _teams_base_dir() -> Path:
    """Return the base directory for team profile storage."""
    return _config_base_dir() / "teams"


def load_team_profile(level: str, slug: str) -> TeamProfile:
    """Load a team profile from disk.

    Raises ``ConfigError`` if the file is missing or contains invalid JSON.
    """
    path = _teams_base_dir() / level / f"{slug}.json"
    if not path.is_file():
        raise ConfigError(f"Team profile not found: {level}/{slug}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"Failed to read team profile {level}/{slug}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Team profile must be a JSON object: {level}/{slug}")
    return dict_to_team_profile(raw, level=level)


def save_team_profile(profile: TeamProfile, slug: str) -> Path:
    """Atomically write a team profile to disk.

    Uses tempfile + ``Path.replace()`` to prevent corruption.
    Creates parent directories as needed.  Returns the written path.
    """
    dest = _teams_base_dir() / profile.level / f"{slug}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)

    data = team_profile_to_dict(profile)
    content = json.dumps(data, indent=2) + "\n"

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".tmp", dir=dest.parent, text=True)
    try:
        with open(tmp_fd, "w") as tmp:
            tmp.write(content)
            tmp.flush()
        Path(tmp_name).replace(dest)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

    return dest


def list_team_profiles(level: str) -> list[str]:
    """Return sorted slugs of all team profiles for a given level.

    Returns an empty list if the level directory does not exist.
    """
    level_dir = _teams_base_dir() / level
    if not level_dir.is_dir():
        return []
    return sorted(p.stem for p in level_dir.iterdir() if p.suffix == ".json" and p.is_file())


def list_levels() -> list[str]:
    """Return sorted level directory names.

    Returns an empty list if the teams base directory does not exist.
    """
    base = _teams_base_dir()
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir() if d.is_dir())


def delete_team_profile(level: str, slug: str) -> bool:
    """Delete a team profile from disk.

    Returns ``True`` if the file was deleted, ``False`` if it did not exist.
    """
    path = _teams_base_dir() / level / f"{slug}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# Roster loading and player lookup
# ---------------------------------------------------------------------------


def load_roster(roster_path: Path) -> dict[str, RosterEntry]:
    """Load a roster CSV and return a dict keyed by jersey number.

    CSV format: ``number,name,position`` (with header row).
    Raises ``ConfigError`` if the file is missing, unreadable, or malformed.
    """
    if not roster_path.is_file():
        raise ConfigError(f"Roster file not found: {roster_path}")
    try:
        text = roster_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read roster file {roster_path}: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ConfigError(f"Roster CSV is empty or has no header: {roster_path}")

    required = {"number", "name", "position"}
    missing = required - {f.strip().lower() for f in reader.fieldnames}
    if missing:
        raise ConfigError(f"Roster CSV missing required columns {sorted(missing)}: {roster_path}")

    roster: dict[str, RosterEntry] = {}
    for row in reader:
        # Normalize field names to lowercase and strip whitespace
        cleaned = {k.strip().lower(): v.strip() for k, v in row.items() if k is not None}
        number = cleaned.get("number", "").strip()
        if not number:
            continue
        roster[number] = RosterEntry(
            number=number,
            name=cleaned.get("name", ""),
            position=cleaned.get("position", ""),
        )
    return roster


def lookup_players(
    roster: dict[str, RosterEntry],
    numbers: list[str],
    team_name: str,
) -> tuple[str, list[str]]:
    """Look up player names by jersey numbers from a roster.

    First number is the primary player (goal scorer), rest are assists.
    Returns ``(scorer_display, [assist_displays])``.

    Format: ``"#48 LastName"`` — falls back to ``"#48"`` if number not in roster.
    Warns on missing numbers but does not error.
    """
    if not numbers:
        return ("", [])

    def _format(num: str) -> str:
        entry = roster.get(num)
        if entry is None:
            logger.warning("Warning: #%s not found in %s roster, using '#%s'", num, team_name, num)
            return f"#{num}"
        return f"#{num} {entry.name.strip()}"

    scorer = _format(numbers[0])
    assists = [_format(n) for n in numbers[1:]]
    return (scorer, assists)


def resolve_scoring_team(
    event_type: str,
    game_info: GameInfo,
) -> tuple[str, str, str]:
    """Determine which team scored from the event type.

    Returns ``(team_name, team_slug, level)`` for the scoring team.
    Uses prefix matching: ``home_*``/``HOME_*`` → home team,
    ``away_*``/``AWAY_*`` → away team.
    Defaults to home team when event type doesn't match either pattern.
    """
    lower = event_type.lower()
    if lower.startswith("away_"):
        return (game_info.away_team, game_info.away_slug, game_info.level)
    # home_* or anything else defaults to home
    return (game_info.home_team, game_info.home_slug, game_info.level)
