"""Tests for centralized metadata generation."""

from __future__ import annotations

from reeln.core.metadata import (
    build_publish_metadata,
    generate_description,
    generate_title,
)
from reeln.models.game import GameEvent, GameInfo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _game_info(**overrides: object) -> GameInfo:
    defaults = {
        "date": "2026-04-06",
        "home_team": "North",
        "away_team": "South",
        "sport": "hockey",
    }
    defaults.update(overrides)
    return GameInfo(**defaults)  # type: ignore[arg-type]


def _game_event(**overrides: object) -> GameEvent:
    defaults: dict[str, object] = {
        "id": "evt_001",
        "clip": "/tmp/clip.mp4",
        "segment_number": 1,
        "event_type": "goal",
        "player": "John Smith",
    }
    defaults.update(overrides)
    return GameEvent(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# generate_title
# ---------------------------------------------------------------------------


def test_title_full_context() -> None:
    title = generate_title(_game_info(), _game_event(), player="John Smith")
    assert title == "John Smith Goal - North vs South"


def test_title_player_from_event() -> None:
    title = generate_title(_game_info(), _game_event())
    assert title == "John Smith Goal - North vs South"


def test_title_no_player() -> None:
    event = _game_event(player="")
    title = generate_title(_game_info(), event)
    assert title == "Goal - North vs South"


def test_title_no_event_type() -> None:
    event = _game_event(event_type="")
    title = generate_title(_game_info(), event, player="John Smith")
    assert title == "John Smith Highlight - North vs South"


def test_title_no_game_info() -> None:
    title = generate_title(None, _game_event(), player="John Smith")
    assert title == "John Smith Goal"


def test_title_no_context() -> None:
    title = generate_title()
    assert title == "Highlight"


def test_title_game_info_only() -> None:
    title = generate_title(_game_info())
    assert title == "North vs South"


def test_title_player_override() -> None:
    """Explicit player overrides event.player."""
    event = _game_event(player="Event Player")
    title = generate_title(_game_info(), event, player="CLI Player")
    assert "CLI Player" in title


# ---------------------------------------------------------------------------
# generate_description
# ---------------------------------------------------------------------------


def test_description_full_context() -> None:
    desc = generate_description(
        _game_info(level="2016", tournament="Spring Cup"),
        _game_event(),
        assists="Jane Doe, Bob Jones",
    )
    assert "North vs South (2026-04-06)" in desc
    assert "Hockey | 2016 | Spring Cup" in desc
    assert "Assists: Jane Doe, Bob Jones" in desc


def test_description_no_game_info() -> None:
    desc = generate_description(assists="Jane Doe")
    assert desc == "Assists: Jane Doe"


def test_description_no_assists() -> None:
    desc = generate_description(_game_info())
    assert "North vs South" in desc
    assert "Assists" not in desc


def test_description_assists_from_event_metadata() -> None:
    event = _game_event(metadata={"assists": "From Event"})
    desc = generate_description(game_event=event)
    assert "Assists: From Event" in desc


def test_description_explicit_assists_over_event() -> None:
    """Explicit assists parameter overrides event metadata."""
    event = _game_event(metadata={"assists": "From Event"})
    desc = generate_description(game_event=event, assists="Explicit")
    assert "Assists: Explicit" in desc


def test_description_empty() -> None:
    desc = generate_description()
    assert desc == ""


def test_description_sport_only() -> None:
    desc = generate_description(_game_info(level="", tournament=""))
    lines = desc.strip().split("\n")
    assert len(lines) == 2
    assert "Hockey" in lines[1]


# ---------------------------------------------------------------------------
# build_publish_metadata
# ---------------------------------------------------------------------------


def test_publish_metadata_full() -> None:
    meta = build_publish_metadata(
        title="My Title",
        description="My Desc",
        game_info=_game_info(level="2016", tournament="Cup"),
        game_event=_game_event(metadata={"score": "3-1"}),
        player="John",
        assists="Jane",
        plugin_inputs={"thumb": "/tmp/t.png"},
    )
    assert meta["title"] == "My Title"
    assert meta["description"] == "My Desc"
    assert meta["home_team"] == "North"
    assert meta["away_team"] == "South"
    assert meta["date"] == "2026-04-06"
    assert meta["sport"] == "hockey"
    assert meta["level"] == "2016"
    assert meta["tournament"] == "Cup"
    assert meta["event_type"] == "goal"
    assert meta["event_id"] == "evt_001"
    assert meta["event_metadata"]["score"] == "3-1"
    assert meta["player"] == "John"
    assert meta["assists"] == "Jane"
    assert meta["plugin_inputs"]["thumb"] == "/tmp/t.png"


def test_publish_metadata_minimal() -> None:
    meta = build_publish_metadata(title="T", description="D")
    assert meta["title"] == "T"
    assert meta["description"] == "D"
    assert "home_team" not in meta
    assert "player" not in meta
    assert "plugin_inputs" not in meta


def test_publish_metadata_no_optional_game_fields() -> None:
    meta = build_publish_metadata(
        title="T", description="D", game_info=_game_info()
    )
    assert "level" not in meta  # empty string not included
    assert "tournament" not in meta


def test_description_no_date() -> None:
    """Cover branch where date is empty."""
    info = _game_info(date="")
    desc = generate_description(info)
    assert "North vs South" in desc
    assert "()" not in desc


def test_description_level_no_sport() -> None:
    """Cover branches where sport is empty but level/tournament are set."""
    info = _game_info(sport="", level="2016", tournament="Cup")
    desc = generate_description(info)
    assert "2016" in desc
    assert "Cup" in desc


def test_description_no_sport_level_tournament() -> None:
    """Cover branch where context_parts is empty (sport/level/tournament all empty)."""
    info = _game_info(sport="", level="", tournament="")
    desc = generate_description(info)
    # Only matchup line, no context line
    lines = desc.strip().split("\n")
    assert len(lines) == 1
    assert "North vs South" in lines[0]


def test_publish_metadata_with_event_no_metadata() -> None:
    """Cover branch where game_event has no metadata dict."""
    event = _game_event(metadata={})
    meta = build_publish_metadata(
        title="T", description="D", game_event=event
    )
    assert "event_metadata" not in meta
