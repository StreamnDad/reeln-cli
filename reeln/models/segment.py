"""Segment and sport alias data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SportAlias:
    """Maps a sport to its segment metadata."""

    sport: str
    segment_name: str
    segment_count: int
    duration_minutes: int | None = None


@dataclass
class Segment:
    """A single segment within a game."""

    number: int
    alias: str
    files: list[Path] = field(default_factory=list)
    merged_path: Path | None = None
