"""Tests for team profile management, roster loading, and player lookup."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from reeln.core.errors import ConfigError
from reeln.core.teams import (
    _teams_base_dir,
    delete_team_profile,
    list_levels,
    list_team_profiles,
    load_roster,
    load_team_profile,
    lookup_players,
    resolve_scoring_team,
    save_team_profile,
    slugify,
)
from reeln.models.game import GameInfo
from reeln.models.team import RosterEntry, TeamProfile

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


def test_slugify_simple() -> None:
    assert slugify("Roseville") == "roseville"


def test_slugify_spaces() -> None:
    assert slugify("St. Louis Park") == "st_louis_park"


def test_slugify_special_chars() -> None:
    assert slugify("Team #1 (A)") == "team_1_a"


def test_slugify_leading_trailing_underscores() -> None:
    assert slugify("---Eagles---") == "eagles"


def test_slugify_multiple_special_runs() -> None:
    assert slugify("a & b @ c") == "a_b_c"


def test_slugify_already_clean() -> None:
    assert slugify("eagles") == "eagles"


def test_slugify_numbers() -> None:
    assert slugify("Team99") == "team99"


# ---------------------------------------------------------------------------
# _teams_base_dir
# ---------------------------------------------------------------------------


def test_teams_base_dir_uses_config_base_dir(tmp_path: Path) -> None:
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        assert _teams_base_dir() == tmp_path / "teams"


# ---------------------------------------------------------------------------
# save_team_profile
# ---------------------------------------------------------------------------


def test_save_team_profile_creates_file(tmp_path: Path) -> None:
    profile = TeamProfile(team_name="Roseville", short_name="ROS", level="bantam")
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = save_team_profile(profile, "roseville")

    assert result == tmp_path / "teams" / "bantam" / "roseville.json"
    assert result.is_file()

    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["team_name"] == "Roseville"
    assert data["short_name"] == "ROS"
    assert data["level"] == "bantam"


def test_save_team_profile_creates_directories(tmp_path: Path) -> None:
    profile = TeamProfile(team_name="A", short_name="A", level="varsity")
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = save_team_profile(profile, "a")

    assert (tmp_path / "teams" / "varsity").is_dir()
    assert result.is_file()


def test_save_team_profile_overwrites_existing(tmp_path: Path) -> None:
    profile1 = TeamProfile(team_name="Old", short_name="OLD", level="jv")
    profile2 = TeamProfile(team_name="New", short_name="NEW", level="jv")
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        save_team_profile(profile1, "team")
        save_team_profile(profile2, "team")

    path = tmp_path / "teams" / "jv" / "team.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["team_name"] == "New"


def test_save_team_profile_atomic_write_cleanup(tmp_path: Path) -> None:
    """If write fails, temp file is cleaned up."""
    profile = TeamProfile(team_name="A", short_name="A", level="bantam")
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        # Create the directory first
        (tmp_path / "teams" / "bantam").mkdir(parents=True)
        with (
            patch("builtins.open", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            save_team_profile(profile, "a")

    # No leftover .tmp files
    bantam_dir = tmp_path / "teams" / "bantam"
    tmp_files = list(bantam_dir.glob("*.tmp"))
    assert tmp_files == []


# ---------------------------------------------------------------------------
# load_team_profile
# ---------------------------------------------------------------------------


def test_load_team_profile_success(tmp_path: Path) -> None:
    profile = TeamProfile(
        team_name="Roseville",
        short_name="ROS",
        level="bantam",
        colors=["red"],
    )
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        save_team_profile(profile, "roseville")
        loaded = load_team_profile("bantam", "roseville")

    assert loaded == profile


def test_load_team_profile_missing_raises(tmp_path: Path) -> None:
    with (
        patch("reeln.core.teams._config_base_dir", return_value=tmp_path),
        pytest.raises(ConfigError, match="not found"),
    ):
        load_team_profile("bantam", "nonexistent")


def test_load_team_profile_invalid_json(tmp_path: Path) -> None:
    level_dir = tmp_path / "teams" / "bantam"
    level_dir.mkdir(parents=True)
    (level_dir / "bad.json").write_text("not json!", encoding="utf-8")

    with (
        patch("reeln.core.teams._config_base_dir", return_value=tmp_path),
        pytest.raises(ConfigError, match="Failed to read"),
    ):
        load_team_profile("bantam", "bad")


def test_load_team_profile_not_a_dict(tmp_path: Path) -> None:
    level_dir = tmp_path / "teams" / "bantam"
    level_dir.mkdir(parents=True)
    (level_dir / "list.json").write_text('["not", "a", "dict"]', encoding="utf-8")

    with (
        patch("reeln.core.teams._config_base_dir", return_value=tmp_path),
        pytest.raises(ConfigError, match="must be a JSON object"),
    ):
        load_team_profile("bantam", "list")


def test_load_team_profile_level_fallback(tmp_path: Path) -> None:
    """Level is inferred from directory when not in the JSON data."""
    level_dir = tmp_path / "teams" / "bantam"
    level_dir.mkdir(parents=True)
    data = {"team_name": "Roseville", "short_name": "ROS"}
    (level_dir / "roseville.json").write_text(json.dumps(data), encoding="utf-8")

    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        loaded = load_team_profile("bantam", "roseville")

    assert loaded.level == "bantam"


# ---------------------------------------------------------------------------
# list_team_profiles
# ---------------------------------------------------------------------------


def test_list_team_profiles_returns_sorted_slugs(tmp_path: Path) -> None:
    level_dir = tmp_path / "teams" / "bantam"
    level_dir.mkdir(parents=True)
    (level_dir / "roseville.json").write_text("{}")
    (level_dir / "mahtomedi.json").write_text("{}")
    (level_dir / "white_bear.json").write_text("{}")

    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = list_team_profiles("bantam")

    assert result == ["mahtomedi", "roseville", "white_bear"]


def test_list_team_profiles_empty_dir(tmp_path: Path) -> None:
    level_dir = tmp_path / "teams" / "bantam"
    level_dir.mkdir(parents=True)

    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = list_team_profiles("bantam")

    assert result == []


def test_list_team_profiles_missing_dir(tmp_path: Path) -> None:
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = list_team_profiles("nonexistent")

    assert result == []


def test_list_team_profiles_ignores_non_json(tmp_path: Path) -> None:
    level_dir = tmp_path / "teams" / "bantam"
    level_dir.mkdir(parents=True)
    (level_dir / "roseville.json").write_text("{}")
    (level_dir / "notes.txt").write_text("some notes")
    (level_dir / "subdir").mkdir()

    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = list_team_profiles("bantam")

    assert result == ["roseville"]


# ---------------------------------------------------------------------------
# list_levels
# ---------------------------------------------------------------------------


def test_list_levels_returns_sorted(tmp_path: Path) -> None:
    base = tmp_path / "teams"
    (base / "varsity").mkdir(parents=True)
    (base / "bantam").mkdir()
    (base / "jv").mkdir()

    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = list_levels()

    assert result == ["bantam", "jv", "varsity"]


def test_list_levels_empty(tmp_path: Path) -> None:
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = list_levels()

    assert result == []


def test_list_levels_ignores_files(tmp_path: Path) -> None:
    base = tmp_path / "teams"
    base.mkdir(parents=True)
    (base / "bantam").mkdir()
    (base / "config.json").write_text("{}")

    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = list_levels()

    assert result == ["bantam"]


# ---------------------------------------------------------------------------
# delete_team_profile
# ---------------------------------------------------------------------------


def test_delete_team_profile_success(tmp_path: Path) -> None:
    level_dir = tmp_path / "teams" / "bantam"
    level_dir.mkdir(parents=True)
    (level_dir / "roseville.json").write_text("{}")

    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = delete_team_profile("bantam", "roseville")

    assert result is True
    assert not (level_dir / "roseville.json").exists()


def test_delete_team_profile_not_found(tmp_path: Path) -> None:
    with patch("reeln.core.teams._config_base_dir", return_value=tmp_path):
        result = delete_team_profile("bantam", "nonexistent")

    assert result is False


# ---------------------------------------------------------------------------
# load_roster
# ---------------------------------------------------------------------------


def test_load_roster_happy_path(tmp_path: Path) -> None:
    roster_csv = tmp_path / "roster.csv"
    roster_csv.write_text("number,name,position\n48,John Smith,C\n24,Jane Doe,D\n2,Bob Jones,RW\n")

    roster = load_roster(roster_csv)

    assert len(roster) == 3
    assert roster["48"] == RosterEntry(number="48", name="John Smith", position="C")
    assert roster["24"] == RosterEntry(number="24", name="Jane Doe", position="D")
    assert roster["2"] == RosterEntry(number="2", name="Bob Jones", position="RW")


def test_load_roster_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Roster file not found"):
        load_roster(tmp_path / "nonexistent.csv")


def test_load_roster_empty_file(tmp_path: Path) -> None:
    roster_csv = tmp_path / "empty.csv"
    roster_csv.write_text("")

    with pytest.raises(ConfigError, match="empty or has no header"):
        load_roster(roster_csv)


def test_load_roster_missing_columns(tmp_path: Path) -> None:
    roster_csv = tmp_path / "bad.csv"
    roster_csv.write_text("number,name\n48,John Smith\n")

    with pytest.raises(ConfigError, match="missing required columns"):
        load_roster(roster_csv)


def test_load_roster_skips_empty_numbers(tmp_path: Path) -> None:
    roster_csv = tmp_path / "roster.csv"
    roster_csv.write_text("number,name,position\n48,John Smith,C\n,,\n24,Jane Doe,D\n")

    roster = load_roster(roster_csv)

    assert len(roster) == 2
    assert "48" in roster
    assert "24" in roster


def test_load_roster_unreadable_file(tmp_path: Path) -> None:
    roster_csv = tmp_path / "unreadable.csv"
    roster_csv.write_text("number,name,position\n48,John Smith,C\n")
    with (
        patch.object(Path, "read_text", side_effect=OSError("permission denied")),
        pytest.raises(ConfigError, match="Failed to read roster file"),
    ):
        load_roster(roster_csv)


def test_load_roster_strips_whitespace(tmp_path: Path) -> None:
    roster_csv = tmp_path / "roster.csv"
    roster_csv.write_text("number , name , position\n 48 , John Smith , C \n")

    roster = load_roster(roster_csv)

    assert roster["48"] == RosterEntry(number="48", name="John Smith", position="C")


# ---------------------------------------------------------------------------
# lookup_players
# ---------------------------------------------------------------------------


def test_lookup_players_happy_path() -> None:
    roster = {
        "48": RosterEntry(number="48", name="John Smith", position="C"),
        "24": RosterEntry(number="24", name="Jane Doe", position="D"),
        "2": RosterEntry(number="2", name="Bob Jones", position="RW"),
    }

    scorer, assists = lookup_players(roster, ["48", "24", "2"], "Eagles")

    assert scorer == "#48 John Smith"
    assert assists == ["#24 Jane Doe", "#2 Bob Jones"]


def test_lookup_players_missing_number() -> None:
    roster = {
        "48": RosterEntry(number="48", name="John Smith", position="C"),
    }

    scorer, assists = lookup_players(roster, ["48", "99"], "Eagles")

    assert scorer == "#48 John Smith"
    assert assists == ["#99"]


def test_lookup_players_single_number() -> None:
    roster = {
        "48": RosterEntry(number="48", name="John Smith", position="C"),
    }

    scorer, assists = lookup_players(roster, ["48"], "Eagles")

    assert scorer == "#48 John Smith"
    assert assists == []


def test_lookup_players_empty_roster() -> None:
    scorer, assists = lookup_players({}, ["48", "24"], "Eagles")

    assert scorer == "#48"
    assert assists == ["#24"]


def test_lookup_players_empty_numbers() -> None:
    roster = {"48": RosterEntry(number="48", name="John Smith", position="C")}

    scorer, assists = lookup_players(roster, [], "Eagles")

    assert scorer == ""
    assert assists == []


def test_lookup_players_all_missing() -> None:
    scorer, assists = lookup_players({}, ["99", "88"], "Eagles")

    assert scorer == "#99"
    assert assists == ["#88"]


# ---------------------------------------------------------------------------
# resolve_scoring_team
# ---------------------------------------------------------------------------


def _game_info_with_teams() -> GameInfo:
    return GameInfo(
        date="2026-03-04",
        home_team="Eagles",
        away_team="Bears",
        sport="hockey",
        level="bantam",
        home_slug="eagles",
        away_slug="bears",
    )


def test_resolve_scoring_team_home_goal() -> None:
    gi = _game_info_with_teams()
    name, slug, level = resolve_scoring_team("HOME_GOAL", gi)
    assert name == "Eagles"
    assert slug == "eagles"
    assert level == "bantam"


def test_resolve_scoring_team_away_goal() -> None:
    gi = _game_info_with_teams()
    name, slug, level = resolve_scoring_team("AWAY_GOAL", gi)
    assert name == "Bears"
    assert slug == "bears"
    assert level == "bantam"


def test_resolve_scoring_team_lowercase_home() -> None:
    gi = _game_info_with_teams()
    name, slug, _level = resolve_scoring_team("home_goal", gi)
    assert name == "Eagles"
    assert slug == "eagles"


def test_resolve_scoring_team_lowercase_away() -> None:
    gi = _game_info_with_teams()
    name, slug, _level = resolve_scoring_team("away_goal", gi)
    assert name == "Bears"
    assert slug == "bears"


def test_resolve_scoring_team_generic_defaults_home() -> None:
    gi = _game_info_with_teams()
    name, slug, _level = resolve_scoring_team("goal", gi)
    assert name == "Eagles"
    assert slug == "eagles"


def test_resolve_scoring_team_empty_defaults_home() -> None:
    gi = _game_info_with_teams()
    name, slug, _level = resolve_scoring_team("", gi)
    assert name == "Eagles"
    assert slug == "eagles"
