"""Tests for team profile data model."""

from __future__ import annotations

from reeln.models.team import (
    RosterEntry,
    TeamProfile,
    dict_to_team_profile,
    team_profile_to_dict,
)

# ---------------------------------------------------------------------------
# TeamProfile defaults
# ---------------------------------------------------------------------------


def test_team_profile_required_fields() -> None:
    tp = TeamProfile(team_name="Roseville", short_name="ROS", level="bantam")
    assert tp.team_name == "Roseville"
    assert tp.short_name == "ROS"
    assert tp.level == "bantam"


def test_team_profile_defaults() -> None:
    tp = TeamProfile(team_name="A", short_name="A", level="varsity")
    assert tp.logo_path == ""
    assert tp.roster_path == ""
    assert tp.colors == []
    assert tp.jersey_colors == []
    assert tp.metadata == {}


def test_team_profile_custom_fields() -> None:
    tp = TeamProfile(
        team_name="Roseville",
        short_name="ROS",
        level="bantam",
        logo_path="/logos/ros.png",
        roster_path="/rosters/ros.csv",
        colors=["#C8102E", "#000000"],
        jersey_colors=["white", "red"],
        metadata={"conference": "SEC 4AA"},
    )
    assert tp.logo_path == "/logos/ros.png"
    assert tp.roster_path == "/rosters/ros.csv"
    assert tp.colors == ["#C8102E", "#000000"]
    assert tp.jersey_colors == ["white", "red"]
    assert tp.metadata == {"conference": "SEC 4AA"}


# ---------------------------------------------------------------------------
# Serialization: team_profile_to_dict
# ---------------------------------------------------------------------------


def test_team_profile_to_dict() -> None:
    tp = TeamProfile(
        team_name="Roseville",
        short_name="ROS",
        level="bantam",
        logo_path="/logos/ros.png",
        colors=["red"],
        metadata={"conference": "SEC"},
    )
    d = team_profile_to_dict(tp)
    assert d == {
        "team_name": "Roseville",
        "short_name": "ROS",
        "level": "bantam",
        "logo_path": "/logos/ros.png",
        "roster_path": "",
        "colors": ["red"],
        "jersey_colors": [],
        "metadata": {"conference": "SEC"},
    }


def test_team_profile_to_dict_defaults() -> None:
    tp = TeamProfile(team_name="A", short_name="A", level="jv")
    d = team_profile_to_dict(tp)
    assert d["logo_path"] == ""
    assert d["roster_path"] == ""
    assert d["colors"] == []
    assert d["jersey_colors"] == []
    assert d["metadata"] == {}


# ---------------------------------------------------------------------------
# Serialization: dict_to_team_profile
# ---------------------------------------------------------------------------


def test_dict_to_team_profile_full() -> None:
    d = {
        "team_name": "Mahtomedi",
        "short_name": "MAH",
        "level": "varsity",
        "logo_path": "/logos/mah.png",
        "roster_path": "/rosters/mah.csv",
        "colors": ["blue", "white"],
        "jersey_colors": ["home_blue", "away_white"],
        "metadata": {"mascot": "Zephyrs"},
    }
    tp = dict_to_team_profile(d)
    assert tp.team_name == "Mahtomedi"
    assert tp.short_name == "MAH"
    assert tp.level == "varsity"
    assert tp.logo_path == "/logos/mah.png"
    assert tp.roster_path == "/rosters/mah.csv"
    assert tp.colors == ["blue", "white"]
    assert tp.jersey_colors == ["home_blue", "away_white"]
    assert tp.metadata == {"mascot": "Zephyrs"}


def test_dict_to_team_profile_defaults() -> None:
    d = {"team_name": "A", "short_name": "A", "level": "jv"}
    tp = dict_to_team_profile(d)
    assert tp.logo_path == ""
    assert tp.roster_path == ""
    assert tp.colors == []
    assert tp.jersey_colors == []
    assert tp.metadata == {}


def test_dict_to_team_profile_ignores_legacy_period_length() -> None:
    """Old JSON files with period_length are silently ignored."""
    d = {"team_name": "A", "short_name": "A", "level": "jv", "period_length": 17}
    tp = dict_to_team_profile(d)
    assert not hasattr(tp, "period_length") or "period_length" not in vars(tp)


def test_dict_to_team_profile_level_fallback() -> None:
    """When dict has no 'level' key, the fallback param is used."""
    d = {"team_name": "B", "short_name": "B"}
    tp = dict_to_team_profile(d, level="bantam")
    assert tp.level == "bantam"


def test_dict_to_team_profile_level_in_dict_overrides_fallback() -> None:
    """When dict contains 'level', it takes precedence over fallback."""
    d = {"team_name": "B", "short_name": "B", "level": "varsity"}
    tp = dict_to_team_profile(d, level="bantam")
    assert tp.level == "varsity"


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_team_profile_round_trip() -> None:
    tp = TeamProfile(
        team_name="Roseville",
        short_name="ROS",
        level="bantam",
        logo_path="/logos/ros.png",
        roster_path="/rosters/ros.csv",
        colors=["#C8102E", "#000000"],
        jersey_colors=["white", "red"],
        metadata={"conference": "SEC 4AA"},
    )
    assert dict_to_team_profile(team_profile_to_dict(tp)) == tp


def test_team_profile_round_trip_defaults() -> None:
    tp = TeamProfile(team_name="X", short_name="X", level="jv")
    assert dict_to_team_profile(team_profile_to_dict(tp)) == tp


# ---------------------------------------------------------------------------
# RosterEntry
# ---------------------------------------------------------------------------


def test_roster_entry_fields() -> None:
    entry = RosterEntry(number="48", name="John Smith", position="C")
    assert entry.number == "48"
    assert entry.name == "John Smith"
    assert entry.position == "C"


def test_roster_entry_equality() -> None:
    a = RosterEntry(number="10", name="Jane Doe", position="D")
    b = RosterEntry(number="10", name="Jane Doe", position="D")
    assert a == b
