"""Tests for sport alias registry, segment resolution, validation, and directory naming."""

from __future__ import annotations

import pytest

from reeln.core.errors import SegmentError
from reeln.core.segment import (
    clear_custom_sports,
    get_sport,
    list_sports,
    make_segment,
    make_segments,
    register_sport,
    segment_dir_name,
    segment_display_name,
    sport_from_dict,
    unregister_sport,
    validate_segment_for_sport,
    validate_segment_number,
)
from reeln.models.segment import SportAlias


@pytest.fixture(autouse=True)
def _clean_custom_sports() -> None:
    """Ensure custom sports don't leak between tests."""
    clear_custom_sports()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_get_sport_builtin_hockey() -> None:
    sa = get_sport("hockey")
    assert sa.sport == "hockey"
    assert sa.segment_name == "period"
    assert sa.segment_count == 3
    assert sa.duration_minutes == 20


def test_get_sport_builtin_basketball() -> None:
    sa = get_sport("basketball")
    assert sa.segment_name == "quarter"
    assert sa.segment_count == 4


def test_get_sport_builtin_soccer() -> None:
    sa = get_sport("soccer")
    assert sa.segment_name == "half"
    assert sa.segment_count == 2
    assert sa.duration_minutes == 45


def test_get_sport_builtin_football() -> None:
    sa = get_sport("football")
    assert sa.segment_name == "half"
    assert sa.duration_minutes == 30


def test_get_sport_builtin_baseball() -> None:
    sa = get_sport("baseball")
    assert sa.segment_name == "inning"
    assert sa.segment_count == 9
    assert sa.duration_minutes is None


def test_get_sport_builtin_lacrosse() -> None:
    sa = get_sport("lacrosse")
    assert sa.segment_name == "quarter"
    assert sa.segment_count == 4


def test_get_sport_builtin_generic() -> None:
    sa = get_sport("generic")
    assert sa.segment_name == "segment"
    assert sa.segment_count == 1
    assert sa.duration_minutes is None


def test_get_sport_unknown_raises() -> None:
    with pytest.raises(SegmentError, match="Unknown sport"):
        get_sport("curling")


def test_register_custom_sport() -> None:
    custom = SportAlias(sport="cricket", segment_name="innings", segment_count=2, duration_minutes=None)
    register_sport(custom)
    assert get_sport("cricket") == custom


def test_custom_overrides_builtin() -> None:
    custom = SportAlias(sport="hockey", segment_name="period", segment_count=4, duration_minutes=15)
    register_sport(custom)
    assert get_sport("hockey").segment_count == 4


def test_unregister_sport() -> None:
    custom = SportAlias(sport="cricket", segment_name="innings", segment_count=2)
    register_sport(custom)
    unregister_sport("cricket")
    with pytest.raises(SegmentError, match="Unknown sport"):
        get_sport("cricket")


def test_unregister_nonexistent_is_noop() -> None:
    unregister_sport("nonexistent")  # should not raise


def test_clear_custom_sports() -> None:
    register_sport(SportAlias(sport="cricket", segment_name="innings", segment_count=2))
    clear_custom_sports()
    with pytest.raises(SegmentError, match="Unknown sport"):
        get_sport("cricket")


def test_list_sports_includes_builtins() -> None:
    sports = list_sports()
    names = [s.sport for s in sports]
    assert "hockey" in names
    assert "basketball" in names
    assert "generic" in names
    # Sorted alphabetically
    assert names == sorted(names)


def test_list_sports_includes_custom() -> None:
    register_sport(SportAlias(sport="cricket", segment_name="innings", segment_count=2))
    sports = list_sports()
    names = [s.sport for s in sports]
    assert "cricket" in names


def test_list_sports_custom_overrides_in_list() -> None:
    register_sport(SportAlias(sport="hockey", segment_name="period", segment_count=5))
    sports = list_sports()
    hockey = next(s for s in sports if s.sport == "hockey")
    assert hockey.segment_count == 5


# ---------------------------------------------------------------------------
# Directory naming
# ---------------------------------------------------------------------------


def test_segment_dir_name_hockey() -> None:
    assert segment_dir_name("hockey", 1) == "period-1"
    assert segment_dir_name("hockey", 3) == "period-3"


def test_segment_dir_name_basketball() -> None:
    assert segment_dir_name("basketball", 4) == "quarter-4"


def test_segment_dir_name_soccer() -> None:
    assert segment_dir_name("soccer", 2) == "half-2"


def test_segment_dir_name_baseball() -> None:
    assert segment_dir_name("baseball", 9) == "inning-9"


def test_segment_dir_name_generic() -> None:
    assert segment_dir_name("generic", 1) == "segment-1"


def test_segment_display_name() -> None:
    assert segment_display_name("hockey", 1) == "Period 1"
    assert segment_display_name("basketball", 3) == "Quarter 3"
    assert segment_display_name("soccer", 2) == "Half 2"
    assert segment_display_name("baseball", 7) == "Inning 7"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_segment_number_valid() -> None:
    validate_segment_number(1)
    validate_segment_number(99)


def test_validate_segment_number_zero_raises() -> None:
    with pytest.raises(SegmentError, match="must be >= 1"):
        validate_segment_number(0)


def test_validate_segment_number_negative_raises() -> None:
    with pytest.raises(SegmentError, match="must be >= 1"):
        validate_segment_number(-1)


def test_validate_segment_for_sport_ok() -> None:
    warnings = validate_segment_for_sport("hockey", 3)
    assert warnings == []


def test_validate_segment_for_sport_exceeds() -> None:
    warnings = validate_segment_for_sport("hockey", 4)
    assert len(warnings) == 1
    assert "exceeds" in warnings[0]


def test_validate_segment_for_sport_invalid_number() -> None:
    with pytest.raises(SegmentError, match="must be >= 1"):
        validate_segment_for_sport("hockey", 0)


# ---------------------------------------------------------------------------
# Segment creation
# ---------------------------------------------------------------------------


def test_make_segment() -> None:
    seg = make_segment("hockey", 2)
    assert seg.number == 2
    assert seg.alias == "period-2"
    assert seg.files == []
    assert seg.merged_path is None


def test_make_segments_default_count() -> None:
    segments = make_segments("hockey")
    assert len(segments) == 3
    assert segments[0].alias == "period-1"
    assert segments[2].alias == "period-3"


def test_make_segments_custom_count() -> None:
    segments = make_segments("hockey", count=5)
    assert len(segments) == 5
    assert segments[4].alias == "period-5"


def test_make_segments_basketball() -> None:
    segments = make_segments("basketball")
    assert len(segments) == 4
    assert all(s.alias.startswith("quarter-") for s in segments)


# ---------------------------------------------------------------------------
# sport_from_dict
# ---------------------------------------------------------------------------


def test_sport_from_dict_full() -> None:
    data = {"sport": "volleyball", "segment_name": "set", "segment_count": 5, "duration_minutes": None}
    sa = sport_from_dict(data)
    assert sa.sport == "volleyball"
    assert sa.segment_name == "set"
    assert sa.segment_count == 5
    assert sa.duration_minutes is None


def test_sport_from_dict_with_duration() -> None:
    data = {"sport": "rugby", "segment_name": "half", "segment_count": 2, "duration_minutes": 40}
    sa = sport_from_dict(data)
    assert sa.duration_minutes == 40


def test_sport_from_dict_minimal() -> None:
    data = {"sport": "custom"}
    sa = sport_from_dict(data)
    assert sa.segment_name == "segment"
    assert sa.segment_count == 1
    assert sa.duration_minutes is None


def test_sport_from_dict_missing_sport_raises() -> None:
    with pytest.raises(SegmentError, match="missing 'sport'"):
        sport_from_dict({})


def test_sport_from_dict_empty_sport_raises() -> None:
    with pytest.raises(SegmentError, match="missing 'sport'"):
        sport_from_dict({"sport": ""})
