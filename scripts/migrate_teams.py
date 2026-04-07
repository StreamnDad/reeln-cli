#!/usr/bin/env python3
"""Migrate team profiles from streamn-cli to reeln config directory.

Reads profiles from ~/.config/streamn-cli/config/teams/{level}/
and writes them to ~/Library/Application Support/reeln/teams/{level}/
with format adjustments for the reeln TeamProfile schema.

Also copies roster CSV files to the new location.

Usage:
    python scripts/migrate_teams.py [--dry-run]
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

OLD_BASE = Path.home() / ".config" / "streamn-cli" / "config"
OLD_TEAMS = OLD_BASE / "teams"
NEW_BASE = Path.home() / "Library" / "Application Support" / "reeln" / "teams"

# Map old level dirs to new level dirs (same names)
LEVELS = ["peewees", "squirts"]


def transform_profile(data: dict, level: str, new_roster_dir: Path) -> dict:
    """Transform an old streamn-cli profile to reeln TeamProfile format."""
    # Collect extra fields into metadata
    metadata: dict = {}
    for key in ("hashtags", "is_home", "llm_context"):
        val = data.pop(key, None)
        if val and val != "" and val != []:
            metadata[key] = val

    # Keep period_length at top level (matches existing convention)
    # but also store in metadata so dict_to_team_profile can find it
    period_length = data.pop("period_length", None)
    if period_length:
        metadata["period_length"] = period_length

    # Update roster_path to new location if it exists
    old_roster_path = data.get("roster_path", "")
    if old_roster_path:
        old_roster = Path(old_roster_path)
        if old_roster.is_file():
            new_roster = new_roster_dir / old_roster.name
            data["roster_path"] = str(new_roster)
        else:
            data["roster_path"] = ""

    # Ensure metadata field exists
    data["metadata"] = metadata

    # Remove any fields not in TeamProfile schema (besides metadata)
    allowed = {
        "team_name", "short_name", "level", "logo_path",
        "roster_path", "colors", "jersey_colors", "metadata",
    }
    return {k: v for k, v in data.items() if k in allowed}


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    copied_profiles = 0
    copied_rosters = 0
    skipped = 0
    errors = 0

    for level in LEVELS:
        old_level_dir = OLD_TEAMS / level
        new_level_dir = NEW_BASE / level
        new_roster_dir = new_level_dir / "rosters"
        old_roster_dir = OLD_BASE / level

        if not old_level_dir.exists():
            print(f"  SKIP (not found): {old_level_dir}")
            continue

        # Create new directories
        if not dry_run:
            new_level_dir.mkdir(parents=True, exist_ok=True)
            new_roster_dir.mkdir(parents=True, exist_ok=True)

        # Copy team profiles
        for profile_path in sorted(old_level_dir.glob("*.json")):
            slug = profile_path.stem
            new_profile_path = new_level_dir / profile_path.name

            if new_profile_path.exists():
                print(f"  SKIP (exists):    {level}/{slug}.json")
                skipped += 1
                continue

            try:
                data = json.loads(profile_path.read_text(encoding="utf-8"))
                transformed = transform_profile(data, level, new_roster_dir)

                if dry_run:
                    print(f"  DRY-RUN profile:  {level}/{slug}.json")
                    print(f"    -> {json.dumps(transformed, indent=2)[:200]}...")
                else:
                    new_profile_path.write_text(
                        json.dumps(transformed, indent=2) + "\n", encoding="utf-8"
                    )
                    print(f"  COPIED profile:   {level}/{slug}.json")
                copied_profiles += 1
            except (json.JSONDecodeError, OSError) as exc:
                print(f"  ERROR profile:    {level}/{slug}.json — {exc}")
                errors += 1

        # Copy roster CSVs from the old level directory
        if old_roster_dir.exists():
            for roster_path in sorted(old_roster_dir.glob("*roster*.csv")):
                new_roster_path = new_roster_dir / roster_path.name

                if new_roster_path.exists():
                    print(f"  SKIP (exists):    {level}/rosters/{roster_path.name}")
                    skipped += 1
                    continue

                if dry_run:
                    print(f"  DRY-RUN roster:   {level}/rosters/{roster_path.name}")
                else:
                    shutil.copy2(roster_path, new_roster_path)
                    print(f"  COPIED roster:    {level}/rosters/{roster_path.name}")
                copied_rosters += 1

    print(
        f"\nDone: {copied_profiles} profiles, {copied_rosters} rosters copied, "
        f"{skipped} skipped, {errors} errors"
    )


if __name__ == "__main__":
    main()
