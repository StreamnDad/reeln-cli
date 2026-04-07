"""Tests for ffmpeg discovery, version checking, probes, and command builders."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from reeln.core.errors import FFmpegError
from reeln.core.ffmpeg import (
    _VIDEO_EXTENSIONS,
    build_concat_command,
    build_extract_frame_command,
    build_render_command,
    build_short_command,
    build_xfade_command,
    check_version,
    derive_ffprobe,
    discover_ffmpeg,
    get_version,
    list_codecs,
    list_hwaccels,
    parse_major_version,
    probe_duration,
    probe_fps,
    probe_resolution,
    run_ffmpeg,
    write_concat_file,
)
from reeln.models.render_plan import RenderPlan

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discover_ffmpeg_found_in_path() -> None:
    with patch("reeln.core.ffmpeg.shutil.which", return_value="/usr/local/bin/ffmpeg"):
        result = discover_ffmpeg()
    assert result == Path("/usr/local/bin/ffmpeg")


def test_discover_ffmpeg_not_found_raises() -> None:
    with (
        patch("reeln.core.ffmpeg.shutil.which", return_value=None),
        patch("reeln.core.ffmpeg.sys") as mock_sys,
        patch.object(Path, "is_file", return_value=False),
    ):
        mock_sys.platform = "darwin"
        with pytest.raises(FFmpegError, match="ffmpeg not found"):
            discover_ffmpeg()


def test_discover_ffmpeg_linux_not_found() -> None:
    with (
        patch("reeln.core.ffmpeg.shutil.which", return_value=None),
        patch("reeln.core.ffmpeg.sys") as mock_sys,
        patch.object(Path, "is_file", return_value=False),
    ):
        mock_sys.platform = "linux"
        with pytest.raises(FFmpegError, match="ffmpeg not found"):
            discover_ffmpeg()


def test_discover_ffmpeg_win32_not_found() -> None:
    with (
        patch("reeln.core.ffmpeg.shutil.which", return_value=None),
        patch("reeln.core.ffmpeg.sys") as mock_sys,
        patch.object(Path, "is_file", return_value=False),
    ):
        mock_sys.platform = "win32"
        with pytest.raises(FFmpegError, match="ffmpeg not found"):
            discover_ffmpeg()


def test_discover_ffmpeg_unknown_platform_not_found() -> None:
    with (
        patch("reeln.core.ffmpeg.shutil.which", return_value=None),
        patch("reeln.core.ffmpeg.sys") as mock_sys,
        pytest.raises(FFmpegError, match="ffmpeg not found"),
    ):
        mock_sys.platform = "freebsd"
        discover_ffmpeg()


# ---------------------------------------------------------------------------
# derive_ffprobe
# ---------------------------------------------------------------------------


def test_derive_ffprobe_from_ffmpeg() -> None:
    assert derive_ffprobe(Path("/usr/bin/ffmpeg")) == Path("/usr/bin/ffprobe")


def test_derive_ffprobe_from_ffmpeg_exe() -> None:
    assert derive_ffprobe(Path("C:/bin/ffmpeg.exe")) == Path("C:/bin/ffprobe.exe")


def test_derive_ffprobe_non_ffmpeg_name() -> None:
    assert derive_ffprobe(Path("/usr/bin/avconv")) == Path("/usr/bin/ffprobe")


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


def test_get_version_parses_output() -> None:
    mock_proc = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="ffmpeg version 7.1 Copyright (c) ...\n", stderr=""
    )
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=mock_proc):
        assert get_version(Path("/usr/bin/ffmpeg")) == "7.1"


def test_get_version_with_n_prefix() -> None:
    mock_proc = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="ffmpeg version n7.1-abc Copyright\n", stderr=""
    )
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=mock_proc):
        assert get_version(Path("/usr/bin/ffmpeg")) == "n7.1-abc"


def test_get_version_file_not_found() -> None:
    with (
        patch("reeln.core.ffmpeg.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(FFmpegError, match="not found"),
    ):
        get_version(Path("/bad/path"))


def test_get_version_timeout() -> None:
    with (
        patch(
            "reeln.core.ffmpeg.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="", timeout=5),
        ),
        pytest.raises(FFmpegError, match="timed out"),
    ):
        get_version(Path("/usr/bin/ffmpeg"))


def test_get_version_nonzero_exit() -> None:
    mock_proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error")
    with (
        patch("reeln.core.ffmpeg.subprocess.run", return_value=mock_proc),
        pytest.raises(FFmpegError, match="failed"),
    ):
        get_version(Path("/usr/bin/ffmpeg"))


def test_get_version_unparseable() -> None:
    mock_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="garbage output\n", stderr="")
    with (
        patch("reeln.core.ffmpeg.subprocess.run", return_value=mock_proc),
        pytest.raises(FFmpegError, match="Could not parse"),
    ):
        get_version(Path("/usr/bin/ffmpeg"))


def test_parse_major_version_simple() -> None:
    assert parse_major_version("7.1") == 7


def test_parse_major_version_n_prefix() -> None:
    assert parse_major_version("n7.1-abc") == 7


def test_parse_major_version_just_digits() -> None:
    assert parse_major_version("5") == 5


def test_parse_major_version_invalid() -> None:
    with pytest.raises(FFmpegError, match="Cannot parse"):
        parse_major_version("abc")


def test_check_version_ok() -> None:
    with patch("reeln.core.ffmpeg.get_version", return_value="7.1"):
        result = check_version(Path("/usr/bin/ffmpeg"))
    assert result == "7.1"


def test_check_version_too_old() -> None:
    with (
        patch("reeln.core.ffmpeg.get_version", return_value="4.4"),
        pytest.raises(FFmpegError, match="too old"),
    ):
        check_version(Path("/usr/bin/ffmpeg"))


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------


def _mock_probe_proc(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_probe_duration_success() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("123.45\n")):
        result = probe_duration(Path("/usr/bin/ffmpeg"), Path("video.mkv"))
    assert result == 123.45


def test_probe_duration_failure() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("", returncode=1)):
        assert probe_duration(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_duration_invalid_output() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("not-a-number\n")):
        assert probe_duration(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_duration_file_not_found() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", side_effect=FileNotFoundError):
        assert probe_duration(Path("/bad/ffmpeg"), Path("video.mkv")) is None


def test_probe_duration_timeout() -> None:
    with patch(
        "reeln.core.ffmpeg.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="", timeout=10),
    ):
        assert probe_duration(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_duration_single_arg() -> None:
    """Single-arg form auto-discovers ffmpeg."""
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("42.5\n")),
    ):
        result = probe_duration(Path("video.mkv"))
    assert result == 42.5


def test_probe_fps_fractional() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("60000/1001\n")):
        result = probe_fps(Path("/usr/bin/ffmpeg"), Path("video.mkv"))
    assert result is not None
    assert abs(result - 59.94) < 0.01


def test_probe_fps_integer() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("30\n")):
        result = probe_fps(Path("/usr/bin/ffmpeg"), Path("video.mkv"))
    assert result == 30.0


def test_probe_fps_zero_zero() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("0/0\n")):
        assert probe_fps(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_fps_empty() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("\n")):
        assert probe_fps(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_fps_failure() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("", returncode=1)):
        assert probe_fps(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_fps_invalid_fraction() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("abc/def\n")):
        assert probe_fps(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_fps_invalid_float() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("not-a-number\n")):
        assert probe_fps(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_fps_zero_denominator() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("60/0\n")):
        assert probe_fps(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_resolution_success() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("1920x1080\n")):
        result = probe_resolution(Path("/usr/bin/ffmpeg"), Path("video.mkv"))
    assert result == (1920, 1080)


def test_probe_resolution_failure() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("", returncode=1)):
        assert probe_resolution(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_resolution_no_x() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("1920\n")):
        assert probe_resolution(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


def test_probe_resolution_invalid_values() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("abcxdef\n")):
        assert probe_resolution(Path("/usr/bin/ffmpeg"), Path("video.mkv")) is None


# ---------------------------------------------------------------------------
# Codec and hardware acceleration discovery
# ---------------------------------------------------------------------------


_CODECS_OUTPUT = """\
Codecs:
 D..... = Decoding supported
 .E.... = Encoding supported
 -------
 DEV.LS h264                 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (encoders: libx264 libx264rgb h264_videotoolbox)
 DEV.L. hevc                 H.265 / HEVC (High Efficiency Video Coding) (encoders: libx265 hevc_videotoolbox)
 DEA.LS aac                  AAC (Advanced Audio Coding)
 D.A.LS mp3                  MP3 (MPEG audio layer 3)
"""


def test_list_codecs_success() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc(_CODECS_OUTPUT)):
        result = list_codecs(Path("/usr/bin/ffmpeg"))
    assert "libx264" in result
    assert "libx264rgb" in result
    assert "h264_videotoolbox" in result
    assert "libx265" in result
    assert "hevc_videotoolbox" in result
    assert "aac" in result
    # h264 is the codec family — included because it has 'E' flag
    assert "h264" in result
    # mp3 is decode-only — should NOT be included
    assert "mp3" not in result


def test_list_codecs_failure() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("", returncode=1)):
        result = list_codecs(Path("/usr/bin/ffmpeg"))
    assert result == []


def test_list_codecs_error() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", side_effect=FileNotFoundError):
        result = list_codecs(Path("/usr/bin/ffmpeg"))
    assert result == []


def test_list_codecs_empty_output() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("")):
        result = list_codecs(Path("/usr/bin/ffmpeg"))
    assert result == []


def test_list_codecs_without_encoders_section() -> None:
    """Codec lines without (encoders: ...) still return the codec name."""
    output = """\
Codecs:
 -------
 DEA.LS aac                  AAC (Advanced Audio Coding)
"""
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc(output)):
        result = list_codecs(Path("/usr/bin/ffmpeg"))
    assert result == ["aac"]


def test_list_codecs_malformed_encoders_no_close_paren() -> None:
    """Malformed line with (encoders: but no closing ) still returns the codec name."""
    output = """\
Codecs:
 -------
 DEV.LS h264                 H.264 (encoders: libx264
"""
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc(output)):
        result = list_codecs(Path("/usr/bin/ffmpeg"))
    assert result == ["h264"]


_HWACCELS_OUTPUT = """\
Hardware acceleration methods:
videotoolbox
"""


def test_list_hwaccels_success() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc(_HWACCELS_OUTPUT)):
        result = list_hwaccels(Path("/usr/bin/ffmpeg"))
    assert result == ["videotoolbox"]


_HWACCELS_MULTI_OUTPUT = """\
Hardware acceleration methods:
videotoolbox
cuda
vaapi
"""


def test_list_hwaccels_multiple() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc(_HWACCELS_MULTI_OUTPUT)):
        result = list_hwaccels(Path("/usr/bin/ffmpeg"))
    assert result == ["videotoolbox", "cuda", "vaapi"]


def test_list_hwaccels_none() -> None:
    output = "Hardware acceleration methods:\n"
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc(output)):
        result = list_hwaccels(Path("/usr/bin/ffmpeg"))
    assert result == []


def test_list_hwaccels_blank_lines() -> None:
    """Blank lines after header should be ignored."""
    output = "Hardware acceleration methods:\n\nvideotoolbox\n\n"
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc(output)):
        result = list_hwaccels(Path("/usr/bin/ffmpeg"))
    assert result == ["videotoolbox"]


def test_list_hwaccels_failure() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=_mock_probe_proc("", returncode=1)):
        result = list_hwaccels(Path("/usr/bin/ffmpeg"))
    assert result == []


def test_list_hwaccels_error() -> None:
    with patch("reeln.core.ffmpeg.subprocess.run", side_effect=FileNotFoundError):
        result = list_hwaccels(Path("/usr/bin/ffmpeg"))
    assert result == []


# ---------------------------------------------------------------------------
# Command builders — golden assertions
# ---------------------------------------------------------------------------


def test_build_concat_command_copy(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    concat_file = tmp_path / "filelist.txt"
    output = tmp_path / "output.mkv"
    cmd = build_concat_command(ffmpeg, concat_file, output)
    assert cmd == [
        "/usr/bin/ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        str(output),
    ]


def test_build_concat_command_reencode(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    concat_file = tmp_path / "filelist.txt"
    output = tmp_path / "output.mkv"
    cmd = build_concat_command(ffmpeg, concat_file, output, copy=False, crf=22)
    assert cmd == [
        "/usr/bin/ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:v",
        "libx264",
        "-crf",
        "22",
        "-r",
        "60000/1001",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        str(output),
    ]


def test_build_xfade_command_two_files(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    output = tmp_path / "out.mp4"
    cmd = build_xfade_command(ffmpeg, [a, b], [10.0, 8.0], output)
    assert str(ffmpeg) in cmd
    assert "-filter_complex" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade" in fc
    assert "acrossfade" in fc
    assert "[vout]" in fc
    assert "[aout]" in fc
    assert "-map" in cmd


def test_build_xfade_command_three_files(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    files = [tmp_path / f"{i}.mp4" for i in range(3)]
    output = tmp_path / "out.mp4"
    cmd = build_xfade_command(ffmpeg, files, [10.0, 8.0, 6.0], output)
    fc = cmd[cmd.index("-filter_complex") + 1]
    # Should have 2 xfade and 2 acrossfade stages
    assert fc.count("xfade=") == 2
    assert fc.count("acrossfade=") == 2
    # Intermediate labels
    assert "[xf0]" in fc
    assert "[af0]" in fc


def test_build_xfade_command_mismatched_lengths(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    a = tmp_path / "a.mp4"
    with pytest.raises(FFmpegError, match="same length"):
        build_xfade_command(ffmpeg, [a], [10.0, 8.0], tmp_path / "out.mp4")


def test_build_xfade_command_too_few_files(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    a = tmp_path / "a.mp4"
    with pytest.raises(FFmpegError, match="at least 2"):
        build_xfade_command(ffmpeg, [a], [10.0], tmp_path / "out.mp4")


def test_build_xfade_command_clamps_fade_duration(tmp_path: Path) -> None:
    """Fade duration is clamped to half the shortest clip."""
    ffmpeg = Path("/usr/bin/ffmpeg")
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    output = tmp_path / "out.mp4"
    cmd = build_xfade_command(ffmpeg, [a, b], [10.0, 0.6], output, fade_duration=5.0)
    fc = cmd[cmd.index("-filter_complex") + 1]
    # fade should be clamped to 0.3 (half of 0.6)
    assert "duration=0.3:" in fc


def test_build_render_command_basic(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    input_path = tmp_path / "clip.mkv"
    output = tmp_path / "out.mp4"
    cmd = build_render_command(ffmpeg, input_path, output)
    assert cmd == [
        "/usr/bin/ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output),
    ]


def test_build_render_command_with_scale(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    input_path = tmp_path / "clip.mkv"
    output = tmp_path / "out.mp4"
    cmd = build_render_command(ffmpeg, input_path, output, width=1080, height=1920)
    assert "-vf" in cmd
    idx = cmd.index("-vf")
    assert cmd[idx + 1] == "scale=1080:1920"


def test_build_render_command_with_extra_args(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    input_path = tmp_path / "clip.mkv"
    output = tmp_path / "out.mp4"
    cmd = build_render_command(ffmpeg, input_path, output, extra_args=["-movflags", "+faststart"])
    assert "-movflags" in cmd
    assert "+faststart" in cmd
    # output is always last
    assert cmd[-1] == str(output)


# ---------------------------------------------------------------------------
# _VIDEO_EXTENSIONS
# ---------------------------------------------------------------------------


def test_video_extensions_contains_common_formats() -> None:
    for ext in (".mkv", ".mp4", ".mov", ".avi", ".webm", ".ts", ".flv"):
        assert ext in _VIDEO_EXTENSIONS


# ---------------------------------------------------------------------------
# write_concat_file
# ---------------------------------------------------------------------------


def test_write_concat_file_correct_format(tmp_path: Path) -> None:
    files = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    result = write_concat_file(files, tmp_path)
    try:
        content = result.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert lines[0] == f"file '{files[0]}'"
        assert lines[1] == f"file '{files[1]}'"
    finally:
        result.unlink(missing_ok=True)


def test_write_concat_file_escapes_single_quotes(tmp_path: Path) -> None:
    file_with_quote = tmp_path / "it's a file.mkv"
    result = write_concat_file([file_with_quote], tmp_path)
    try:
        content = result.read_text(encoding="utf-8")
        assert "'\\''" in content
    finally:
        result.unlink(missing_ok=True)


def test_write_concat_file_created_in_output_dir(tmp_path: Path) -> None:
    result = write_concat_file([tmp_path / "a.mkv"], tmp_path)
    try:
        assert result.parent == tmp_path
        assert result.suffix == ".txt"
    finally:
        result.unlink(missing_ok=True)


def test_write_concat_file_cleans_up_on_write_error(tmp_path: Path) -> None:
    with (
        patch("builtins.open", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        write_concat_file([tmp_path / "a.mkv"], tmp_path)
    # Temp file should be cleaned up
    txt_files = list(tmp_path.glob("*.txt"))
    assert txt_files == []


# ---------------------------------------------------------------------------
# run_ffmpeg
# ---------------------------------------------------------------------------


def test_run_ffmpeg_success() -> None:
    mock_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="done\n", stderr="")
    with patch("reeln.core.ffmpeg.subprocess.run", return_value=mock_proc):
        result = run_ffmpeg(["ffmpeg", "-y", "out.mkv"])
    assert result.returncode == 0


def test_run_ffmpeg_nonzero_exit_raises() -> None:
    mock_proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Error opening file")
    with (
        patch("reeln.core.ffmpeg.subprocess.run", return_value=mock_proc),
        pytest.raises(FFmpegError, match="exited with code 1"),
    ):
        run_ffmpeg(["ffmpeg", "-y", "out.mkv"])


def test_run_ffmpeg_file_not_found_raises() -> None:
    with (
        patch("reeln.core.ffmpeg.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(FFmpegError, match="not found"),
    ):
        run_ffmpeg(["ffmpeg", "-y", "out.mkv"])


def test_run_ffmpeg_timeout_raises() -> None:
    with (
        patch(
            "reeln.core.ffmpeg.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="", timeout=600),
        ),
        pytest.raises(FFmpegError, match="timed out"),
    ):
        run_ffmpeg(["ffmpeg", "-y", "out.mkv"])


def test_run_ffmpeg_empty_stderr_on_error() -> None:
    mock_proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
    with (
        patch("reeln.core.ffmpeg.subprocess.run", return_value=mock_proc),
        pytest.raises(FFmpegError, match="exited with code 1"),
    ):
        run_ffmpeg(["ffmpeg"])


# ---------------------------------------------------------------------------
# build_short_command — golden assertions
# ---------------------------------------------------------------------------


def test_build_short_command_with_filters(tmp_path: Path) -> None:
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv"],
        output=tmp_path / "out.mp4",
        filter_complex="scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        audio_filter="atempo=0.5",
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    assert cmd == [
        "/usr/bin/ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(tmp_path / "clip.mkv"),
        "-filter_complex",
        "scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        "-af",
        "atempo=0.5",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(tmp_path / "out.mp4"),
    ]


def test_build_short_command_no_audio_filter(tmp_path: Path) -> None:
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv"],
        output=tmp_path / "out.mp4",
        filter_complex="scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    assert "-af" not in cmd
    assert "-filter_complex" in cmd


def test_build_short_command_speed_segments_maps_outputs(tmp_path: Path) -> None:
    """When filter_complex contains [vfinal] and [afinal], -map flags are added."""
    fc = (
        "[0:v]split=2[v0][v1];"
        "[v0]trim=0:5,setpts=PTS-STARTPTS[sv0];"
        "[v1]trim=5,setpts=PTS-STARTPTS[sv1];"
        "[sv0][sv1]concat=n=2:v=1:a=0[_vout];"
        "[_vout]scale=756:-2:flags=lanczos[vfinal];"
        "[0:a]asplit=2[a0][a1];"
        "[a0]atrim=0:5,asetpts=PTS-STARTPTS[sa0];"
        "[a1]atrim=5,asetpts=PTS-STARTPTS[sa1];"
        "[sa0][sa1]concat=n=2:v=0:a=1[afinal]"
    )
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv"],
        output=tmp_path / "out.mp4",
        filter_complex=fc,
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    assert "-map" in cmd
    map_indices = [i for i, v in enumerate(cmd) if v == "-map"]
    assert len(map_indices) == 2
    assert cmd[map_indices[0] + 1] == "[vfinal]"
    assert cmd[map_indices[1] + 1] == "[afinal]"
    assert "-af" not in cmd


def test_build_short_command_no_filters(tmp_path: Path) -> None:
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv"],
        output=tmp_path / "out.mp4",
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    assert "-filter_complex" not in cmd
    assert "-af" not in cmd
    assert cmd[-1] == str(tmp_path / "out.mp4")


def test_build_short_command_with_extra_args(tmp_path: Path) -> None:
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv"],
        output=tmp_path / "out.mp4",
        filter_complex="scale=1080:-2:flags=lanczos",
        extra_args=["-movflags", "+faststart"],
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    assert "-movflags" in cmd
    assert "+faststart" in cmd
    assert cmd[-1] == str(tmp_path / "out.mp4")


def test_build_short_command_custom_encoding(tmp_path: Path) -> None:
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv"],
        output=tmp_path / "out.mp4",
        codec="libx265",
        preset="fast",
        crf=22,
        audio_codec="opus",
        audio_bitrate="192k",
        filter_complex="scale=540:-2:flags=lanczos",
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    assert "-c:v" in cmd
    idx = cmd.index("-c:v")
    assert cmd[idx + 1] == "libx265"
    idx = cmd.index("-preset")
    assert cmd[idx + 1] == "fast"
    idx = cmd.index("-crf")
    assert cmd[idx + 1] == "22"
    idx = cmd.index("-c:a")
    assert cmd[idx + 1] == "opus"
    idx = cmd.index("-b:a")
    assert cmd[idx + 1] == "192k"


# ---------------------------------------------------------------------------
# build_short_command — logo (multi-input)
# ---------------------------------------------------------------------------


def test_build_short_command_logo_two_inputs(tmp_path: Path) -> None:
    """Logo as second input: -loop 1 -i logo.png + -map 0:a?."""
    logo = tmp_path / "logo.png"
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv", logo],
        output=tmp_path / "out.mp4",
        filter_complex=(
            "[0:v]scale=1080:-2:flags=lanczos[_prelogo];"
            "[1:v]scale=-1:202:flags=lanczos[_logo];"
            "[_prelogo][_logo]overlay=x=1070-w:y=1583-h/2:format=auto:shortest=1"
        ),
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    # First input (video)
    assert cmd[4] == "-i"
    assert cmd[5] == str(tmp_path / "clip.mkv")
    # Second input (logo) prefixed with -loop 1
    assert cmd[6] == "-loop"
    assert cmd[7] == "1"
    assert cmd[8] == "-i"
    assert cmd[9] == str(logo)
    # Audio mapping from video input
    assert "-map" in cmd
    map_idx = cmd.index("-map")
    assert cmd[map_idx + 1] == "0:a?"


def test_build_short_command_logo_with_vfinal(tmp_path: Path) -> None:
    """Logo + speed segments: has [vfinal]/[afinal] so uses those maps, not 0:a?."""
    logo = tmp_path / "logo.png"
    fc = (
        "[0:v]split=2[v0][v1];"
        "[v0]trim=0:5,setpts=PTS-STARTPTS[sv0];"
        "[v1]trim=5,setpts=PTS-STARTPTS,setpts=PTS/0.5[sv1];"
        "[sv0][sv1]concat=n=2:v=1:a=0[_prelogo];"
        "[1:v]scale=-1:202:flags=lanczos[_logo];"
        "[_prelogo][_logo]overlay=x=1070-w:y=1583-h/2[vfinal];"
        "[0:a]asplit=2[a0][a1];"
        "[a0]atrim=0:5,asetpts=PTS-STARTPTS[sa0];"
        "[a1]atrim=5,asetpts=PTS-STARTPTS,atempo=0.5[sa1];"
        "[sa0][sa1]concat=n=2:v=0:a=1[afinal]"
    )
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv", logo],
        output=tmp_path / "out.mp4",
        filter_complex=fc,
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    # Should use [vfinal]/[afinal] maps, not 0:a?
    assert "-map" in cmd
    map_indices = [i for i, v in enumerate(cmd) if v == "-map"]
    assert len(map_indices) == 2
    assert cmd[map_indices[0] + 1] == "[vfinal]"
    assert cmd[map_indices[1] + 1] == "[afinal]"


def test_build_short_command_no_logo_single_input(tmp_path: Path) -> None:
    """Without logo: no -loop, no extra -i, no -map 0:a?."""
    plan = RenderPlan(
        inputs=[tmp_path / "clip.mkv"],
        output=tmp_path / "out.mp4",
        filter_complex="scale=1080:-2:flags=lanczos",
    )
    cmd = build_short_command(Path("/usr/bin/ffmpeg"), plan)
    assert cmd.count("-i") == 1
    assert "-loop" not in cmd
    assert "0:a?" not in cmd


# ---------------------------------------------------------------------------
# build_extract_frame_command — golden assertions
# ---------------------------------------------------------------------------


def test_build_extract_frame_command_basic(tmp_path: Path) -> None:
    ffmpeg = Path("/usr/bin/ffmpeg")
    input_path = tmp_path / "clip.mkv"
    output_path = tmp_path / "frame_0000.png"
    cmd = build_extract_frame_command(ffmpeg, input_path, 5.0, output_path)
    assert cmd == [
        "/usr/bin/ffmpeg",
        "-y",
        "-v",
        "error",
        "-ss",
        "5.000",
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(output_path),
    ]


def test_build_extract_frame_command_zero_timestamp(tmp_path: Path) -> None:
    cmd = build_extract_frame_command(Path("/usr/bin/ffmpeg"), tmp_path / "clip.mkv", 0.0, tmp_path / "f.png")
    assert "-ss" in cmd
    idx = cmd.index("-ss")
    assert cmd[idx + 1] == "0.000"


def test_build_extract_frame_command_fractional_timestamp(tmp_path: Path) -> None:
    cmd = build_extract_frame_command(Path("/usr/bin/ffmpeg"), tmp_path / "clip.mkv", 3.141, tmp_path / "f.png")
    idx = cmd.index("-ss")
    assert cmd[idx + 1] == "3.141"
