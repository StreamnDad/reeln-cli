#!/usr/bin/env python3
"""Backfill game.json files for existing video game folders.

Usage:
    python scripts/backfill_games.py [--dry-run]

Generates game.json for folders in ~/Movies/ that have video content
but no game.json yet. Games are defined in the GAMES list below.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class GameDef:
    """Definition of a game to backfill."""

    folder: str
    date: str
    home_team: str
    away_team: str
    level: str
    game_number: int = 1
    venue: str = ""
    tournament: str = ""
    home_slug: str = ""
    away_slug: str = ""


def slugify(name: str) -> str:
    """Convert a team name to a filesystem-safe slug."""
    return name.lower().replace(" ", "_").replace(".", "").replace("'", "")


def build_game_json(game: GameDef) -> dict:
    """Build a game.json dict matching reeln's GameState schema."""
    home_slug = game.home_slug or slugify(game.home_team)
    away_slug = game.away_slug or slugify(game.away_team)
    now = datetime.now(UTC).isoformat()

    return {
        "game_info": {
            "date": game.date,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "sport": "hockey",
            "game_number": game.game_number,
            "venue": game.venue,
            "game_time": "",
            "period_length": 20,
            "description": "",
            "thumbnail": "",
            "level": game.level,
            "home_slug": home_slug,
            "away_slug": away_slug,
            "tournament": game.tournament,
        },
        "segments_processed": [],
        "highlighted": False,
        "finished": False,
        "created_at": now,
        "finished_at": "",
        "renders": [],
        "events": [],
        "livestreams": {},
        "segment_outputs": [],
        "highlights_output": "",
    }


# ── Game definitions ─────────────────────────────────────────────────────

MOVIES_DIR = Path.home() / "Movies"

# Group 1: 2016 Selects
GROUP_1: list[GameDef] = [
    GameDef(
        folder="2026-03-21_East_vs_North",
        date="2026-03-21",
        home_team="East",
        away_team="North",
        level="2016",
        home_slug="east",
        away_slug="north",
    ),
]

# Group 2: 15u MN Elite
GROUP_2: list[GameDef] = [
    GameDef(
        folder="mn_elite-west",
        date="2026-01-11",
        home_team="MN Elite",
        away_team="West",
        level="15u",
        home_slug="mn_elite",
        away_slug="west",
    ),
    GameDef(
        folder="mn_elite-windy-city1",
        date="2026-01-10",
        home_team="MN Elite",
        away_team="Windy City Storm",
        level="15u",
        game_number=1,
        home_slug="mn_elite",
        away_slug="windy_city_storm",
    ),
    GameDef(
        folder="mn_elite-windy-city2",
        date="2026-01-10",
        home_team="MN Elite",
        away_team="Windy City Storm",
        level="15u",
        game_number=2,
        home_slug="mn_elite",
        away_slug="windy_city_storm",
    ),
    GameDef(
        folder="mn_elite-ice_cougars-0208",
        date="2026-02-08",
        home_team="MN Elite",
        away_team="Ice Cougars",
        level="15u",
        home_slug="mn_elite",
        away_slug="ice_cougars",
    ),
    GameDef(
        folder="mn_elite-madison-0214-1",
        date="2026-02-14",
        home_team="MN Elite",
        away_team="Madison",
        level="15u",
        game_number=1,
        home_slug="mn_elite",
        away_slug="madison",
    ),
    GameDef(
        folder="mn_elite-madison-0214-2",
        date="2026-02-14",
        home_team="MN Elite",
        away_team="Madison",
        level="15u",
        game_number=2,
        home_slug="mn_elite",
        away_slug="madison",
    ),
]

# Group 3: MN Elite vs Queens at Port Arthur Hockey Arena
GROUP_3: list[GameDef] = [
    GameDef(
        folder="2026-02-20_MN Elite_vs_Queens 18UA",
        date="2026-02-20",
        home_team="MN Elite",
        away_team="Queens",
        level="18u",
        venue="Port Arthur Hockey Arena",
        home_slug="mn_elite",
        away_slug="queens",
    ),
    # Skipping 2026-02-21_MN Elite_vs_Queens 18UA — empty folder
    GameDef(
        folder="2026-02-21_MN Elite_vs_Queens 18UA_g2",
        date="2026-02-21",
        home_team="MN Elite",
        away_team="Queens",
        level="18u",
        game_number=2,
        venue="Port Arthur Hockey Arena",
        home_slug="mn_elite",
        away_slug="queens",
    ),
    GameDef(
        folder="2026-02-21_MN Elite_vs_Queens 15UAA",
        date="2026-02-21",
        home_team="MN Elite",
        away_team="Queens",
        level="15u",
        venue="Port Arthur Hockey Arena",
        home_slug="mn_elite",
        away_slug="queens",
    ),
    GameDef(
        folder="2026-02-22_MN Elite_vs_Queens 15UAA",
        date="2026-02-22",
        home_team="MN Elite",
        away_team="Queens",
        level="15u",
        venue="Port Arthur Hockey Arena",
        home_slug="mn_elite",
        away_slug="queens",
    ),
]

# Group 4: Roseville legacy folders
GROUP_4: list[GameDef] = [
    GameDef(
        folder="roseville-eden_prairie-tourny",
        date="2025-12-26",
        home_team="Roseville",
        away_team="Eden Prairie",
        level="peewees",
        home_slug="roseville",
        away_slug="eden_prairie",
    ),
    GameDef(
        folder="roseville-shakopee-tourny",
        date="2025-12-26",
        home_team="Roseville",
        away_team="Shakopee",
        level="peewees",
        home_slug="roseville",
        away_slug="shakopee",
    ),
    GameDef(
        folder="roseville-mahtomedi-tourny",
        date="2025-12-27",
        home_team="Roseville",
        away_team="Mahtomedi",
        level="peewees",
        home_slug="roseville",
        away_slug="mahtomedi",
    ),
    GameDef(
        folder="roseville-stillwater-squirts",
        date="2025-12-27",
        home_team="Roseville",
        away_team="Stillwater",
        level="squirts",
        home_slug="roseville",
        away_slug="stillwater",
    ),
    GameDef(
        folder="roseville-buffalo",
        date="2025-12-28",
        home_team="Roseville",
        away_team="Buffalo",
        level="peewees",
        home_slug="roseville",
        away_slug="buffalo",
    ),
    GameDef(
        folder="roseville-mvi",
        date="2026-01-08",
        home_team="Roseville",
        away_team="Mounds View",
        level="peewees",
        home_slug="roseville",
        away_slug="mounds_view",
    ),
    GameDef(
        folder="roseville-white_bear",
        date="2026-01-09",
        home_team="Roseville",
        away_team="White Bear",
        level="peewees",
        home_slug="roseville",
        away_slug="white_bear",
    ),
    GameDef(
        folder="roseville-chisago_lakes",
        date="2026-01-11",
        home_team="Roseville",
        away_team="Chisago Lakes",
        level="squirts",
        home_slug="roseville",
        away_slug="chisago_lakes",
    ),
    GameDef(
        folder="roseville-mahtomedi3",
        date="2026-01-15",
        home_team="Roseville",
        away_team="Mahtomedi",
        level="peewees",
        home_slug="roseville",
        away_slug="mahtomedi",
    ),
    GameDef(
        folder="roseville-saint_paul",
        date="2026-01-16",
        home_team="Roseville",
        away_team="Saint Paul",
        level="squirts",
        home_slug="roseville",
        away_slug="saint_paul",
    ),
    GameDef(
        folder="roseville-champlin_park",
        date="2026-01-18",
        home_team="Roseville",
        away_team="Champlin Park",
        level="squirts",
        home_slug="roseville",
        away_slug="champlin_park",
    ),
    GameDef(
        folder="roseville-stillwater",
        date="2026-01-21",
        home_team="Roseville",
        away_team="Stillwater",
        level="peewees",
        home_slug="roseville",
        away_slug="stillwater",
    ),
    GameDef(
        folder="roseville-hibbing_chisholm",
        date="2026-01-23",
        home_team="Roseville",
        away_team="Hibbing/Chisholm",
        level="peewees",
        home_slug="roseville",
        away_slug="hibbing_chisholm",
    ),
    GameDef(
        folder="roseville-brainerd",
        date="2026-01-24",
        home_team="Roseville",
        away_team="Brainerd",
        level="peewees",
        home_slug="roseville",
        away_slug="brainerd",
    ),
    GameDef(
        folder="roseville-rock_ridge",
        date="2026-01-24",
        home_team="Roseville",
        away_team="Rock Ridge",
        level="peewees",
        home_slug="roseville",
        away_slug="rock_ridge",
    ),
    GameDef(
        folder="roseville-bemidji",
        date="2026-01-25",
        home_team="Roseville",
        away_team="Bemidji",
        level="peewees",
        home_slug="roseville",
        away_slug="bemidji",
    ),
    GameDef(
        folder="roseville-stillwater-squirts2",
        date="2026-01-30",
        home_team="Roseville",
        away_team="Stillwater",
        level="squirts",
        home_slug="roseville",
        away_slug="stillwater",
    ),
    GameDef(
        folder="roseville-mahtomedi-1-31-2026",
        date="2026-01-31",
        home_team="Roseville",
        away_team="Mahtomedi",
        level="peewees",
        home_slug="roseville",
        away_slug="mahtomedi",
    ),
    GameDef(
        folder="roseville-st_paul",
        date="2026-02-01",
        home_team="Roseville",
        away_team="St. Paul",
        level="squirts",
        home_slug="roseville",
        away_slug="st_paul",
    ),
    GameDef(
        folder="roseville-mounds_view-02-05-2026",
        date="2026-02-05",
        home_team="Roseville",
        away_team="Mounds View",
        level="peewees",
        home_slug="roseville",
        away_slug="mounds_view",
    ),
    GameDef(
        folder="roseville-wbl-0206",
        date="2026-02-06",
        home_team="Roseville",
        away_team="White Bear Lake",
        level="peewees",
        home_slug="roseville",
        away_slug="white_bear_lake",
    ),
    GameDef(
        folder="roseville-chisago_lakes-0207",
        date="2026-02-07",
        home_team="Roseville",
        away_team="Chisago Lakes",
        level="squirts",
        home_slug="roseville",
        away_slug="chisago_lakes",
    ),
    GameDef(
        folder="roseville-mounds_view-0212",
        date="2026-02-12",
        home_team="Roseville",
        away_team="Mounds View",
        level="squirts",
        home_slug="roseville",
        away_slug="mounds_view",
    ),
]

# Group 5: Roseville date-format folders
GROUP_5: list[GameDef] = [
    GameDef(
        folder="2026-02-18_Roseville_vs_Mahtomedi_g3",
        date="2026-02-18",
        home_team="Roseville",
        away_team="Mahtomedi",
        level="peewees",
        game_number=3,
        home_slug="roseville",
        away_slug="mahtomedi",
    ),
    GameDef(
        folder="2026-02-19_Roseville_vs_White Bear Lake",
        date="2026-02-19",
        home_team="Roseville",
        away_team="White Bear Lake",
        level="peewees",
        home_slug="roseville",
        away_slug="white_bear_lake",
    ),
    GameDef(
        folder="2026-02-23_Roseville_vs_Stillwater",
        date="2026-02-23",
        home_team="Roseville",
        away_team="Stillwater",
        level="squirts",
        home_slug="roseville",
        away_slug="stillwater",
    ),
    GameDef(
        folder="2026-02-23_Roseville_vs_Stillwater_g2",
        date="2026-02-23",
        home_team="Roseville",
        away_team="Stillwater",
        level="squirts",
        game_number=2,
        home_slug="roseville",
        away_slug="stillwater",
    ),
    GameDef(
        folder="2026-02-23_Roseville_vs_Stillwater_g3",
        date="2026-02-23",
        home_team="Roseville",
        away_team="Stillwater",
        level="squirts",
        game_number=3,
        home_slug="roseville",
        away_slug="stillwater",
    ),
    GameDef(
        folder="2026-02-23_Roseville_vs_Stillwater_g4",
        date="2026-02-23",
        home_team="Roseville",
        away_team="Stillwater",
        level="squirts",
        game_number=4,
        home_slug="roseville",
        away_slug="stillwater",
    ),
    GameDef(
        folder="2026-02-25_Roseville_vs_Mounds View",
        date="2026-02-25",
        home_team="Roseville",
        away_team="Mounds View",
        level="squirts",
        home_slug="roseville",
        away_slug="mounds_view",
    ),
]

ALL_GAMES = GROUP_1 + GROUP_2 + GROUP_3 + GROUP_4 + GROUP_5


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    created = 0
    skipped = 0
    errors = 0

    for game in ALL_GAMES:
        game_dir = MOVIES_DIR / game.folder
        game_json_path = game_dir / "game.json"

        if not game_dir.exists():
            print(f"  SKIP (dir missing): {game.folder}")
            skipped += 1
            continue

        if game_json_path.exists():
            print(f"  SKIP (exists):      {game.folder}")
            skipped += 1
            continue

        data = build_game_json(game)

        if dry_run:
            print(f"  DRY-RUN:            {game.folder}")
            print(f"    -> {json.dumps(data['game_info'], indent=2)[:200]}...")
            created += 1
            continue

        try:
            game_json_path.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
            print(f"  CREATED:            {game.folder}")
            created += 1
        except OSError as exc:
            print(f"  ERROR:              {game.folder} — {exc}")
            errors += 1

    print(f"\nDone: {created} created, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()
