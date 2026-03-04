"""Team profile data model and serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TeamProfile:
    """Reusable team configuration with metadata for rendering and plugins."""

    team_name: str
    short_name: str
    level: str
    logo_path: str = ""
    roster_path: str = ""
    colors: list[str] = field(default_factory=list)
    jersey_colors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def team_profile_to_dict(profile: TeamProfile) -> dict[str, Any]:
    """Serialize a ``TeamProfile`` to a JSON-compatible dict."""
    return {
        "team_name": profile.team_name,
        "short_name": profile.short_name,
        "level": profile.level,
        "logo_path": profile.logo_path,
        "roster_path": profile.roster_path,
        "colors": list(profile.colors),
        "jersey_colors": list(profile.jersey_colors),
        "metadata": dict(profile.metadata),
    }


def dict_to_team_profile(data: dict[str, Any], level: str = "") -> TeamProfile:
    """Deserialize a dict into a ``TeamProfile``.

    The *level* parameter provides a fallback when the dict does not contain
    a ``level`` key (e.g. when the level is inferred from the directory path).
    """
    return TeamProfile(
        team_name=str(data["team_name"]),
        short_name=str(data["short_name"]),
        level=str(data.get("level", level)),
        logo_path=str(data.get("logo_path", "")),
        roster_path=str(data.get("roster_path", "")),
        colors=list(data.get("colors", [])),
        jersey_colors=list(data.get("jersey_colors", [])),
        metadata=dict(data.get("metadata", {})),
    )
