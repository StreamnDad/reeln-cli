"""Tests for game-scoped pipeline debugging — core/debug.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from reeln.core.debug import (
    _extract_filter_complex,
    _probe_file_metadata,
    build_debug_artifact,
    collect_debug_artifacts,
    debug_dir,
    write_debug_artifact,
    write_debug_index,
)
from reeln.models.debug import DebugArtifact

# ---------------------------------------------------------------------------
# debug_dir
# ---------------------------------------------------------------------------


def test_debug_dir(tmp_path: Path) -> None:
    assert debug_dir(tmp_path) == tmp_path / "debug"


# ---------------------------------------------------------------------------
# _probe_file_metadata
# ---------------------------------------------------------------------------


def test_probe_file_metadata_success(tmp_path: Path) -> None:
    video = tmp_path / "clip.mkv"
    video.write_bytes(b"x" * 100)
    ffmpeg = Path("/usr/bin/ffmpeg")

    with (
        patch("reeln.core.ffmpeg.probe_duration", return_value=30.5),
        patch("reeln.core.ffmpeg.probe_fps", return_value=60.0),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=(1920, 1080)),
    ):
        meta = _probe_file_metadata(ffmpeg, video)

    assert meta["duration"] == 30.5
    assert meta["fps"] == 60.0
    assert meta["resolution"] == "1920x1080"
    assert meta["file"] == "clip.mkv"


def test_probe_file_metadata_missing_file(tmp_path: Path) -> None:
    meta = _probe_file_metadata(Path("/usr/bin/ffmpeg"), tmp_path / "nope.mkv")
    assert meta["duration"] is None
    assert meta["fps"] is None
    assert meta["resolution"] is None


def test_probe_file_metadata_probe_errors(tmp_path: Path) -> None:
    video = tmp_path / "clip.mkv"
    video.write_bytes(b"x" * 100)
    ffmpeg = Path("/usr/bin/ffmpeg")

    with (
        patch("reeln.core.ffmpeg.probe_duration", side_effect=Exception("fail")),
        patch("reeln.core.ffmpeg.probe_fps", side_effect=Exception("fail")),
        patch("reeln.core.ffmpeg.probe_resolution", side_effect=Exception("fail")),
    ):
        meta = _probe_file_metadata(ffmpeg, video)

    assert meta["duration"] is None
    assert meta["fps"] is None
    assert meta["resolution"] is None


def test_probe_file_metadata_resolution_none(tmp_path: Path) -> None:
    video = tmp_path / "clip.mkv"
    video.write_bytes(b"x" * 100)
    ffmpeg = Path("/usr/bin/ffmpeg")

    with (
        patch("reeln.core.ffmpeg.probe_duration", return_value=None),
        patch("reeln.core.ffmpeg.probe_fps", return_value=None),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=None),
    ):
        meta = _probe_file_metadata(ffmpeg, video)

    assert meta["resolution"] is None


# ---------------------------------------------------------------------------
# _extract_filter_complex
# ---------------------------------------------------------------------------


def test_extract_filter_complex_present() -> None:
    cmd = ["ffmpeg", "-i", "in.mkv", "-filter_complex", "scale=1080:-2", "out.mp4"]
    assert _extract_filter_complex(cmd) == "scale=1080:-2"


def test_extract_filter_complex_absent() -> None:
    cmd = ["ffmpeg", "-i", "in.mkv", "-c", "copy", "out.mkv"]
    assert _extract_filter_complex(cmd) == ""


def test_extract_filter_complex_at_end() -> None:
    """Edge case: -filter_complex as the last element (no value following)."""
    cmd = ["ffmpeg", "-i", "in.mkv", "-filter_complex"]
    assert _extract_filter_complex(cmd) == ""


# ---------------------------------------------------------------------------
# write_debug_artifact
# ---------------------------------------------------------------------------


def test_write_debug_artifact_creates_dir(tmp_path: Path) -> None:
    art = DebugArtifact(operation="test_op", timestamp="2026-03-02T12:00:00p00-00")
    path = write_debug_artifact(tmp_path, art)

    assert path.exists()
    assert path.parent == tmp_path / "debug"
    assert path.suffix == ".json"

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["operation"] == "test_op"


def test_write_debug_artifact_filename_format(tmp_path: Path) -> None:
    art = DebugArtifact(operation="segment_merge", timestamp="2026-03-02T12:30:00+00:00")
    path = write_debug_artifact(tmp_path, art)

    assert "segment_merge_" in path.name
    # Colons and plus signs should be replaced
    assert ":" not in path.name
    assert "+" not in path.name


def test_write_debug_artifact_valid_json(tmp_path: Path) -> None:
    art = DebugArtifact(
        operation="render_short",
        timestamp="2026-03-02T12:00:00+00:00",
        ffmpeg_command=["ffmpeg", "-i", "in.mkv"],
        extra={"mode": "pad"},
    )
    path = write_debug_artifact(tmp_path, art)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["ffmpeg_command"] == ["ffmpeg", "-i", "in.mkv"]
    assert data["extra"]["mode"] == "pad"


def test_write_debug_artifact_existing_dir(tmp_path: Path) -> None:
    (tmp_path / "debug").mkdir()
    art = DebugArtifact(operation="test", timestamp="t")
    path = write_debug_artifact(tmp_path, art)
    assert path.exists()


# ---------------------------------------------------------------------------
# build_debug_artifact
# ---------------------------------------------------------------------------


def test_build_debug_artifact(tmp_path: Path) -> None:
    inp = tmp_path / "period-1" / "replay.mkv"
    inp.parent.mkdir()
    inp.write_bytes(b"x" * 100)
    out = tmp_path / "period-1" / "merged.mkv"
    out.write_bytes(b"x" * 200)
    ffmpeg = Path("/usr/bin/ffmpeg")
    cmd = ["ffmpeg", "-f", "concat", "-i", "list.txt", "-c", "copy", str(out)]

    with (
        patch("reeln.core.ffmpeg.probe_duration", return_value=30.0),
        patch("reeln.core.ffmpeg.probe_fps", return_value=60.0),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=(1920, 1080)),
    ):
        art = build_debug_artifact(
            "segment_merge",
            cmd,
            [inp],
            out,
            tmp_path,
            ffmpeg,
            extra={"segment_number": 1},
        )

    assert art.operation == "segment_merge"
    assert art.ffmpeg_command == cmd
    assert art.input_files == ["period-1/replay.mkv"]
    assert art.output_file == "period-1/merged.mkv"
    assert len(art.input_metadata) == 1
    assert art.input_metadata[0]["duration"] == 30.0
    assert art.extra == {"segment_number": 1}


def test_build_debug_artifact_probe_failure(tmp_path: Path) -> None:
    inp = tmp_path / "clip.mkv"
    inp.write_bytes(b"x" * 50)
    out = tmp_path / "out.mkv"
    out.write_bytes(b"x" * 100)
    ffmpeg = Path("/usr/bin/ffmpeg")

    with (
        patch("reeln.core.ffmpeg.probe_duration", side_effect=Exception("fail")),
        patch("reeln.core.ffmpeg.probe_fps", side_effect=Exception("fail")),
        patch("reeln.core.ffmpeg.probe_resolution", side_effect=Exception("fail")),
    ):
        art = build_debug_artifact("test", [], [inp], out, tmp_path, ffmpeg)

    assert art.input_metadata[0]["duration"] is None


def test_build_debug_artifact_no_extra(tmp_path: Path) -> None:
    out = tmp_path / "out.mkv"
    ffmpeg = Path("/usr/bin/ffmpeg")

    with (
        patch("reeln.core.ffmpeg.probe_duration", return_value=None),
        patch("reeln.core.ffmpeg.probe_fps", return_value=None),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=None),
    ):
        art = build_debug_artifact("test", [], [], out, tmp_path, ffmpeg)

    assert art.extra == {}


def test_build_debug_artifact_filter_complex(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    ffmpeg = Path("/usr/bin/ffmpeg")
    cmd = ["ffmpeg", "-i", "in.mkv", "-filter_complex", "scale=1080:-2", str(out)]

    with (
        patch("reeln.core.ffmpeg.probe_duration", return_value=None),
        patch("reeln.core.ffmpeg.probe_fps", return_value=None),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=None),
    ):
        art = build_debug_artifact("render_short", cmd, [], out, tmp_path, ffmpeg)

    assert art.filter_complex == "scale=1080:-2"


def test_build_debug_artifact_absolute_paths(tmp_path: Path) -> None:
    """Files outside game_dir use absolute paths."""
    external = Path("/some/other/path/clip.mkv")
    out = tmp_path / "out.mkv"
    ffmpeg = Path("/usr/bin/ffmpeg")

    with (
        patch("reeln.core.ffmpeg.probe_duration", return_value=None),
        patch("reeln.core.ffmpeg.probe_fps", return_value=None),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=None),
    ):
        art = build_debug_artifact("test", [], [external], out, tmp_path, ffmpeg)

    assert art.input_files == ["/some/other/path/clip.mkv"]


# ---------------------------------------------------------------------------
# collect_debug_artifacts
# ---------------------------------------------------------------------------


def test_collect_debug_artifacts(tmp_path: Path) -> None:
    d = tmp_path / "debug"
    d.mkdir()

    art1 = DebugArtifact(operation="op1", timestamp="2026-03-02T12:00:00+00:00")
    art2 = DebugArtifact(operation="op2", timestamp="2026-03-02T12:01:00+00:00")
    write_debug_artifact(tmp_path, art1)
    write_debug_artifact(tmp_path, art2)

    collected = collect_debug_artifacts(tmp_path)
    assert len(collected) == 2
    assert collected[0].operation == "op1"
    assert collected[1].operation == "op2"


def test_collect_debug_artifacts_empty_dir(tmp_path: Path) -> None:
    (tmp_path / "debug").mkdir()
    assert collect_debug_artifacts(tmp_path) == []


def test_collect_debug_artifacts_no_dir(tmp_path: Path) -> None:
    assert collect_debug_artifacts(tmp_path) == []


def test_collect_debug_artifacts_ignores_non_json(tmp_path: Path) -> None:
    d = tmp_path / "debug"
    d.mkdir()
    (d / "index.html").write_text("<html></html>")
    (d / "notes.txt").write_text("some notes")

    art = DebugArtifact(operation="test", timestamp="t")
    write_debug_artifact(tmp_path, art)

    collected = collect_debug_artifacts(tmp_path)
    assert len(collected) == 1


def test_collect_debug_artifacts_handles_corrupt(tmp_path: Path) -> None:
    d = tmp_path / "debug"
    d.mkdir()
    (d / "bad.json").write_text("not valid json!!!")

    art = DebugArtifact(operation="good", timestamp="t")
    write_debug_artifact(tmp_path, art)

    collected = collect_debug_artifacts(tmp_path)
    assert len(collected) == 1
    assert collected[0].operation == "good"


def test_collect_debug_artifacts_skips_non_dict_json(tmp_path: Path) -> None:
    """JSON files that parse to non-dict (e.g. arrays) are silently skipped."""
    d = tmp_path / "debug"
    d.mkdir()
    (d / "array.json").write_text("[1, 2, 3]")

    art = DebugArtifact(operation="good", timestamp="t")
    write_debug_artifact(tmp_path, art)

    collected = collect_debug_artifacts(tmp_path)
    assert len(collected) == 1
    assert collected[0].operation == "good"


# ---------------------------------------------------------------------------
# write_debug_index
# ---------------------------------------------------------------------------


def test_write_debug_index_empty(tmp_path: Path) -> None:
    path = write_debug_index(tmp_path)
    assert path == tmp_path / "debug" / "index.html"
    assert path.exists()

    content = path.read_text(encoding="utf-8")
    assert "reeln Debug Index" in content
    assert "No debug artifacts found" in content


def test_write_debug_index_with_artifacts(tmp_path: Path) -> None:
    art = DebugArtifact(
        operation="segment_merge",
        timestamp="2026-03-02T12:00:00+00:00",
        ffmpeg_command=["ffmpeg", "-f", "concat", "-i", "list.txt", "out.mkv"],
        input_files=["period-1/replay.mkv"],
        output_file="period-1/merged.mkv",
        input_metadata=[{"file": "replay.mkv", "duration": 30.0, "fps": 60.0, "resolution": "1920x1080"}],
        output_metadata={"file": "merged.mkv", "duration": 30.0},
        extra={"segment_number": 1},
    )
    write_debug_artifact(tmp_path, art)

    path = write_debug_index(tmp_path)
    content = path.read_text(encoding="utf-8")

    assert "segment_merge" in content
    assert "period-1/replay.mkv" in content
    assert "period-1/merged.mkv" in content
    assert "ffmpeg -f concat -i list.txt out.mkv" in content


def test_write_debug_index_video_links(tmp_path: Path) -> None:
    art = DebugArtifact(
        operation="render_short",
        timestamp="2026-03-02T12:00:00+00:00",
        input_files=["period-1/clip.mkv"],
        output_file="period-1/short.mp4",
    )
    write_debug_artifact(tmp_path, art)

    path = write_debug_index(tmp_path)
    content = path.read_text(encoding="utf-8")

    # Video links use relative paths from debug/ dir
    assert "href='../period-1/clip.mkv'" in content
    assert "href='../period-1/short.mp4'" in content


def test_write_debug_index_multiple_operations(tmp_path: Path) -> None:
    for i, op in enumerate(["segment_merge", "highlights_merge", "render_short"]):
        art = DebugArtifact(
            operation=op,
            timestamp=f"2026-03-02T12:0{i}:00+00:00",
            output_file=f"out_{i}.mkv",
        )
        write_debug_artifact(tmp_path, art)

    path = write_debug_index(tmp_path)
    content = path.read_text(encoding="utf-8")

    assert "segment_merge" in content
    assert "highlights_merge" in content
    assert "render_short" in content
    # Summary table should have 3 rows
    assert content.count("<tr><td>") == 3


def test_write_debug_index_filter_complex(tmp_path: Path) -> None:
    art = DebugArtifact(
        operation="render_short",
        timestamp="2026-03-02T12:00:00+00:00",
        ffmpeg_command=["ffmpeg", "-filter_complex", "scale=1080:-2"],
        filter_complex="scale=1080:-2",
        output_file="out.mp4",
    )
    write_debug_artifact(tmp_path, art)

    path = write_debug_index(tmp_path)
    content = path.read_text(encoding="utf-8")
    assert "scale=1080:-2" in content


def test_write_debug_index_creates_dir(tmp_path: Path) -> None:
    """Index can be written even if debug dir doesn't exist yet."""
    path = write_debug_index(tmp_path)
    assert path.exists()
    assert (tmp_path / "debug").is_dir()


# ---------------------------------------------------------------------------
# Roundtrip: write → collect → verify
# ---------------------------------------------------------------------------


def test_roundtrip_write_collect(tmp_path: Path) -> None:
    art = DebugArtifact(
        operation="compile",
        timestamp="2026-03-02T14:00:00+00:00",
        ffmpeg_command=["ffmpeg", "-i", "a.mkv", "out.mkv"],
        input_files=["a.mkv"],
        output_file="out.mkv",
        extra={"copy": True},
    )
    write_debug_artifact(tmp_path, art)

    collected = collect_debug_artifacts(tmp_path)
    assert len(collected) == 1
    assert collected[0].operation == "compile"
    assert collected[0].ffmpeg_command == ["ffmpeg", "-i", "a.mkv", "out.mkv"]
    assert collected[0].extra == {"copy": True}


def test_roundtrip_multiple_artifacts(tmp_path: Path) -> None:
    for i in range(3):
        art = DebugArtifact(
            operation=f"op_{i}",
            timestamp=f"2026-03-02T12:0{i}:00+00:00",
        )
        write_debug_artifact(tmp_path, art)

    collected = collect_debug_artifacts(tmp_path)
    assert len(collected) == 3
    operations = [a.operation for a in collected]
    assert "op_0" in operations
    assert "op_1" in operations
    assert "op_2" in operations


# ---------------------------------------------------------------------------
# HTML content verification
# ---------------------------------------------------------------------------


def test_debug_index_html_structure(tmp_path: Path) -> None:
    art = DebugArtifact(
        operation="test",
        timestamp="2026-03-02T12:00:00+00:00",
        output_file="out.mkv",
    )
    write_debug_artifact(tmp_path, art)
    path = write_debug_index(tmp_path)
    content = path.read_text(encoding="utf-8")

    assert content.startswith("<!DOCTYPE html>")
    assert "</html>" in content
    assert "<title>reeln Debug Index</title>" in content
    assert str(tmp_path) in content  # game_dir path


def test_debug_index_escapes_html(tmp_path: Path) -> None:
    """Ensure special characters are escaped in HTML output."""
    art = DebugArtifact(
        operation="test<script>",
        timestamp="2026-03-02T12:00:00+00:00",
        ffmpeg_command=["ffmpeg", '-vf "scale=1080"'],
        output_file="out.mkv",
    )
    write_debug_artifact(tmp_path, art)
    path = write_debug_index(tmp_path)
    content = path.read_text(encoding="utf-8")

    # Script tag should be escaped
    assert "<script>" not in content
    assert "&lt;script&gt;" in content


def test_write_debug_artifact_atomic_write_error(tmp_path: Path) -> None:
    """Error during atomic write cleans up temp file and re-raises."""
    import pytest

    art = DebugArtifact(operation="test", timestamp="t")
    d = tmp_path / "debug"
    d.mkdir()

    with (
        patch("reeln.core.debug.tempfile.mkstemp", return_value=(999, str(d / "tmp_file"))),
        patch("builtins.open", side_effect=OSError("write failed")),
        pytest.raises(OSError, match="write failed"),
    ):
        write_debug_artifact(tmp_path, art)


def test_write_debug_index_atomic_write_error(tmp_path: Path) -> None:
    """Error during HTML atomic write cleans up temp file and re-raises."""
    import pytest

    d = tmp_path / "debug"
    d.mkdir()

    with (
        patch("reeln.core.debug.tempfile.mkstemp", return_value=(999, str(d / "tmp_idx"))),
        patch("builtins.open", side_effect=OSError("write failed")),
        pytest.raises(OSError, match="write failed"),
    ):
        write_debug_index(tmp_path)


def test_debug_index_extra_section(tmp_path: Path) -> None:
    art = DebugArtifact(
        operation="test",
        timestamp="2026-03-02T12:00:00+00:00",
        output_file="out.mkv",
        extra={"segment_number": 2, "copy": False},
    )
    write_debug_artifact(tmp_path, art)
    path = write_debug_index(tmp_path)
    content = path.read_text(encoding="utf-8")

    assert "segment_number" in content
    assert "Extra:" in content
