"""Tests for DebugArtifact data model and serialization."""

from __future__ import annotations

import pytest

from reeln.models.debug import (
    DebugArtifact,
    debug_artifact_to_dict,
    dict_to_debug_artifact,
)

# ---------------------------------------------------------------------------
# DebugArtifact defaults
# ---------------------------------------------------------------------------


def test_debug_artifact_defaults() -> None:
    art = DebugArtifact(operation="segment_merge", timestamp="2026-03-02T12:00:00+00:00")
    assert art.operation == "segment_merge"
    assert art.timestamp == "2026-03-02T12:00:00+00:00"
    assert art.ffmpeg_command == []
    assert art.filter_complex == ""
    assert art.input_files == []
    assert art.output_file == ""
    assert art.input_metadata == []
    assert art.output_metadata == {}
    assert art.extra == {}


def test_debug_artifact_custom_values() -> None:
    art = DebugArtifact(
        operation="render_short",
        timestamp="2026-03-02T12:00:00+00:00",
        ffmpeg_command=["ffmpeg", "-i", "in.mkv", "out.mp4"],
        filter_complex="scale=1080:-2",
        input_files=["period-1/replay.mkv"],
        output_file="period-1/short.mp4",
        input_metadata=[{"file": "replay.mkv", "duration": 30.0}],
        output_metadata={"duration": 30.0, "resolution": "1080x1920"},
        extra={"crop_mode": "pad"},
    )
    assert art.operation == "render_short"
    assert len(art.ffmpeg_command) == 4
    assert art.filter_complex == "scale=1080:-2"
    assert art.input_files == ["period-1/replay.mkv"]
    assert art.output_file == "period-1/short.mp4"
    assert len(art.input_metadata) == 1
    assert art.output_metadata["resolution"] == "1080x1920"
    assert art.extra["crop_mode"] == "pad"


def test_debug_artifact_is_frozen() -> None:
    art = DebugArtifact(operation="test", timestamp="t")
    with pytest.raises(AttributeError):
        art.operation = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Serialization roundtrip
# ---------------------------------------------------------------------------


def test_debug_artifact_to_dict() -> None:
    art = DebugArtifact(
        operation="compile",
        timestamp="2026-03-02T12:00:00+00:00",
        ffmpeg_command=["ffmpeg", "-i", "a.mkv"],
        filter_complex="",
        input_files=["a.mkv"],
        output_file="out.mkv",
        input_metadata=[{"file": "a.mkv"}],
        output_metadata={"duration": 10.0},
        extra={"copy": True},
    )
    d = debug_artifact_to_dict(art)
    assert d["operation"] == "compile"
    assert d["ffmpeg_command"] == ["ffmpeg", "-i", "a.mkv"]
    assert d["extra"] == {"copy": True}


def test_dict_to_debug_artifact() -> None:
    d = {
        "operation": "highlights_merge",
        "timestamp": "2026-03-02T13:00:00+00:00",
        "ffmpeg_command": ["ffmpeg", "-f", "concat"],
        "filter_complex": "",
        "input_files": ["s1.mkv", "s2.mkv"],
        "output_file": "game.mkv",
        "input_metadata": [{"file": "s1.mkv"}, {"file": "s2.mkv"}],
        "output_metadata": {"duration": 60.0},
        "extra": {},
    }
    art = dict_to_debug_artifact(d)
    assert art.operation == "highlights_merge"
    assert art.input_files == ["s1.mkv", "s2.mkv"]
    assert len(art.input_metadata) == 2


def test_roundtrip() -> None:
    art = DebugArtifact(
        operation="segment_merge",
        timestamp="2026-03-02T12:00:00+00:00",
        ffmpeg_command=["ffmpeg", "-i", "a.mkv", "-c", "copy", "out.mkv"],
        filter_complex="",
        input_files=["a.mkv"],
        output_file="out.mkv",
        input_metadata=[{"file": "a.mkv", "duration": 5.0}],
        output_metadata={"duration": 5.0},
        extra={"segment_number": 1},
    )
    d = debug_artifact_to_dict(art)
    recovered = dict_to_debug_artifact(d)
    assert recovered.operation == art.operation
    assert recovered.timestamp == art.timestamp
    assert recovered.ffmpeg_command == art.ffmpeg_command
    assert recovered.input_files == art.input_files
    assert recovered.output_file == art.output_file
    assert recovered.extra == art.extra


def test_dict_to_debug_artifact_missing_fields() -> None:
    """Gracefully handles a dict with missing keys."""
    art = dict_to_debug_artifact({})
    assert art.operation == ""
    assert art.timestamp == ""
    assert art.ffmpeg_command == []
    assert art.input_files == []


def test_dict_to_debug_artifact_extra_fields() -> None:
    """Extra keys in the dict are silently ignored."""
    d = {"operation": "test", "timestamp": "t", "unknown_key": "ignored"}
    art = dict_to_debug_artifact(d)
    assert art.operation == "test"
