"""Team profile management: load, save, list, delete."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from reeln.core.config import config_dir
from reeln.core.errors import ConfigError
from reeln.models.team import TeamProfile, dict_to_team_profile, team_profile_to_dict


def slugify(name: str) -> str:
    """Convert a team name to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric runs with ``_``, and strips
    leading/trailing underscores.
    """
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _teams_base_dir() -> Path:
    """Return the base directory for team profile storage."""
    return config_dir() / "teams"


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
