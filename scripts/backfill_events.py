#!/usr/bin/env python3
"""Backfill events in game.json for existing replay clips.

Scans each game folder's period-N directories (and root) for Replay_* files,
creates GameEvent entries for any clips not already in the events list,
and updates segments_processed.

Usage:
    python scripts/backfill_events.py [--dry-run]
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

MOVIES_DIR = Path.home() / "Movies"

# Match period-N directory names
PERIOD_RE = re.compile(r"^period-(\d+)$")


def find_replay_files(directory: Path) -> list[Path]:
    """Find all Replay_* video files in a directory, sorted by name."""
    replays = []
    for ext in ("*.mkv", "*.mp4"):
        replays.extend(directory.glob(f"Replay_*{ext[1:]}"))
    return sorted(replays, key=lambda p: p.name)


def backfill_game(game_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Backfill events for a single game. Returns (events_added, segments_found)."""
    game_json_path = game_dir / "game.json"
    if not game_json_path.exists():
        return 0, 0

    data = json.loads(game_json_path.read_text(encoding="utf-8"))
    existing_clips = {e["clip"] for e in data.get("events", [])}

    now = datetime.now(UTC).isoformat()
    new_events: list[dict] = []
    segments_found: set[int] = set()

    # Scan period-N directories
    for child in sorted(game_dir.iterdir()):
        match = PERIOD_RE.match(child.name)
        if match and child.is_dir():
            seg_num = int(match.group(1))
            replays = find_replay_files(child)
            if replays:
                segments_found.add(seg_num)
            for replay in replays:
                rel_path = str(replay.relative_to(game_dir))
                if rel_path not in existing_clips:
                    new_events.append({
                        "id": uuid.uuid4().hex,
                        "clip": rel_path,
                        "segment_number": seg_num,
                        "event_type": "",
                        "player": "",
                        "created_at": now,
                        "metadata": {},
                    })

    # Also scan root for replay files (e.g., roseville-bemidji)
    root_replays = find_replay_files(game_dir)
    if root_replays and not segments_found:
        # Root-level replays with no period dirs — assign to segment 1
        segments_found.add(1)
        for replay in root_replays:
            rel_path = replay.name
            if rel_path not in existing_clips:
                new_events.append({
                    "id": uuid.uuid4().hex,
                    "clip": rel_path,
                    "segment_number": 1,
                    "event_type": "",
                    "player": "",
                    "created_at": now,
                    "metadata": {},
                })

    if not new_events:
        return 0, len(segments_found)

    if not dry_run:
        data.setdefault("events", []).extend(new_events)
        data["segments_processed"] = sorted(segments_found)
        game_json_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    return len(new_events), len(segments_found)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    total_events = 0
    total_games = 0

    for game_dir in sorted(MOVIES_DIR.iterdir()):
        if not game_dir.is_dir():
            continue
        game_json = game_dir / "game.json"
        if not game_json.exists():
            continue

        events_added, segments = backfill_game(game_dir, dry_run)
        if events_added > 0:
            prefix = "DRY-RUN" if dry_run else "UPDATED"
            print(f"  {prefix}: {game_dir.name} — {events_added} events, {segments} segments")
            total_events += events_added
            total_games += 1
        else:
            existing = len(json.loads(game_json.read_text())["events"])
            if existing:
                print(f"  SKIP (has events): {game_dir.name} — {existing} existing")
            else:
                print(f"  SKIP (no clips):   {game_dir.name}")

    label = "would create" if dry_run else "created"
    print(f"\nDone: {label} {total_events} events across {total_games} games")


if __name__ == "__main__":
    main()
