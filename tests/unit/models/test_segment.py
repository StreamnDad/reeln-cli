"""Tests for segment data models."""

from __future__ import annotations

from pathlib import Path

from reeln.models.segment import Segment, SportAlias


def test_sport_alias_with_duration() -> None:
    sa = SportAlias(sport="hockey", segment_name="period", segment_count=3, duration_minutes=20)
    assert sa.sport == "hockey"
    assert sa.segment_name == "period"
    assert sa.segment_count == 3
    assert sa.duration_minutes == 20


def test_sport_alias_without_duration() -> None:
    sa = SportAlias(sport="baseball", segment_name="inning", segment_count=9)
    assert sa.duration_minutes is None


def test_sport_alias_is_frozen() -> None:
    sa = SportAlias(sport="hockey", segment_name="period", segment_count=3)
    import pytest

    with pytest.raises(AttributeError):
        sa.sport = "basketball"  # type: ignore[misc]


def test_segment_defaults() -> None:
    seg = Segment(number=1, alias="period-1")
    assert seg.number == 1
    assert seg.alias == "period-1"
    assert seg.files == []
    assert seg.merged_path is None


def test_segment_with_files() -> None:
    seg = Segment(
        number=2,
        alias="quarter-2",
        files=[Path("/a.mkv"), Path("/b.mkv")],
        merged_path=Path("/merged.mkv"),
    )
    assert len(seg.files) == 2
    assert seg.merged_path == Path("/merged.mkv")


def test_segment_is_mutable() -> None:
    seg = Segment(number=1, alias="period-1")
    seg.merged_path = Path("/out.mkv")
    assert seg.merged_path == Path("/out.mkv")
