"""FFmpeg discovery, version checking, probe helpers, and command builders."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from reeln.core.errors import FFmpegError
from reeln.core.log import get_logger
from reeln.models.render_plan import RenderPlan

log: logging.Logger = get_logger(__name__)

MIN_MAJOR_VERSION: int = 5

_VIDEO_EXTENSIONS: set[str] = {".mkv", ".mp4", ".mov", ".avi", ".webm", ".ts", ".flv"}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_ffmpeg() -> Path:
    """Find the ffmpeg binary on the system.

    Search order: PATH → platform-specific locations.

    Raises ``FFmpegError`` if ffmpeg is not found.
    """
    # 1. Check PATH
    found = shutil.which("ffmpeg")
    if found:
        return Path(found)

    # 2. Platform-specific locations
    platform = sys.platform
    if platform == "darwin":
        candidates = [Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")]
    elif platform == "linux":
        candidates = [Path("/usr/bin/ffmpeg"), Path("/snap/bin/ffmpeg")]
    elif platform == "win32":
        candidates = [
            Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"),
            Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        ]
    else:
        candidates = []

    for candidate in candidates:
        if candidate.is_file():
            return candidate  # pragma: no cover

    raise FFmpegError(
        "ffmpeg not found. Install it via your package manager:\n"
        "  macOS:   brew install ffmpeg\n"
        "  Linux:   sudo apt install ffmpeg\n"
        "  Windows: winget install ffmpeg"
    )


def derive_ffprobe(ffmpeg_path: Path) -> Path:
    """Derive the ffprobe path from the ffmpeg path."""
    if ffmpeg_path.name.startswith("ffmpeg"):
        ffprobe_name = ffmpeg_path.name.replace("ffmpeg", "ffprobe", 1)
        return ffmpeg_path.with_name(ffprobe_name)
    return ffmpeg_path.parent / "ffprobe"


# ---------------------------------------------------------------------------
# Version checking
# ---------------------------------------------------------------------------


def get_version(ffmpeg_path: Path) -> str:
    """Return the ffmpeg version string (e.g. ``'7.1'``).

    Raises ``FFmpegError`` on failure.
    """
    try:
        proc = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"ffmpeg binary not found at {ffmpeg_path}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffmpeg -version timed out at {ffmpeg_path}") from exc

    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg -version failed (exit {proc.returncode})")

    first_line = (proc.stdout or "").split("\n", maxsplit=1)[0].strip()
    match = re.search(r"ffmpeg version (\S+)", first_line)
    if not match:
        raise FFmpegError(f"Could not parse ffmpeg version from: {first_line!r}")

    return match.group(1)


def parse_major_version(version_string: str) -> int:
    """Extract the major version number from a version string like ``'7.1'`` or ``'n7.1'``."""
    cleaned = version_string.lstrip("nN")
    match = re.match(r"(\d+)", cleaned)
    if not match:
        raise FFmpegError(f"Cannot parse major version from: {version_string!r}")
    return int(match.group(1))


def check_version(ffmpeg_path: Path) -> str:
    """Verify ffmpeg meets the minimum version requirement (5.0+).

    Returns the version string on success, raises ``FFmpegError`` otherwise.
    """
    version = get_version(ffmpeg_path)
    major = parse_major_version(version)
    if major < MIN_MAJOR_VERSION:
        raise FFmpegError(
            f"ffmpeg {version} is too old (need {MIN_MAJOR_VERSION}.0+). Please upgrade your ffmpeg installation."
        )
    log.debug("ffmpeg version %s OK (>= %d.0)", version, MIN_MAJOR_VERSION)
    return version


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------


def probe_duration(ffmpeg_path_or_input: Path, input_path: Path | None = None) -> float | None:
    """Probe the duration of a media file in seconds.

    Can be called as ``probe_duration(input)`` (auto-discovers ffmpeg)
    or ``probe_duration(ffmpeg_path, input)`` for backwards compatibility.
    """
    if input_path is None:
        actual_input = ffmpeg_path_or_input
        ffprobe = derive_ffprobe(discover_ffmpeg())
    else:
        actual_input = input_path
        ffprobe = derive_ffprobe(ffmpeg_path_or_input)
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(actual_input),
    ]
    return _run_probe_float(cmd)


def probe_fps(ffmpeg_path: Path, input_path: Path) -> float | None:
    """Probe the average frame rate of the first video stream."""
    ffprobe = derive_ffprobe(ffmpeg_path)
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=avg_frame_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    proc = _run_probe(cmd)
    if proc is None:
        return None
    value = proc.stdout.strip()
    if not value or value == "0/0":
        return None
    if "/" in value:
        num_str, denom_str = value.split("/", 1)
        try:
            num = float(num_str)
            denom = float(denom_str)
            if denom == 0:
                return None
            return num / denom
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def probe_resolution(ffmpeg_path: Path, input_path: Path) -> tuple[int, int] | None:
    """Probe the resolution (width, height) of the first video stream."""
    ffprobe = derive_ffprobe(ffmpeg_path)
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(input_path),
    ]
    proc = _run_probe(cmd)
    if proc is None:
        return None
    output = proc.stdout.strip()
    if "x" not in output:
        return None
    width_str, height_str = output.split("x", 1)
    try:
        return int(width_str), int(height_str)
    except ValueError:
        return None


def _run_probe(cmd: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a probe command, returning None on any failure."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc


def _run_probe_float(cmd: list[str]) -> float | None:
    """Run a probe command and parse the output as a float."""
    proc = _run_probe(cmd)
    if proc is None:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Codec and hardware acceleration discovery
# ---------------------------------------------------------------------------


def list_codecs(ffmpeg_path: Path) -> list[str]:
    """Return a list of encoding-capable codec names and encoder names.

    Parses ``ffmpeg -codecs`` output.  Each encoding-capable line yields
    the codec family name (e.g. ``h264``) **and** any specific encoder
    names listed in ``(encoders: ...)``.  Returns an empty list on error.
    """
    proc = _run_probe([str(ffmpeg_path), "-codecs"])
    if proc is None:
        return []

    codecs: list[str] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        # Codec lines have 6-char flags then a space then the codec name.
        # Encoding-capable codecs have 'E' at position 1 (0-indexed).
        # Example: "DEV.LS h264  ... (encoders: libx264 libx264rgb h264_videotoolbox)"
        if len(stripped) < 8:
            continue
        flags = stripped[:6]
        if len(flags) >= 2 and flags[1] == "E":
            rest = stripped[6:].strip()
            codec_name = rest.split()[0]
            codecs.append(codec_name)
            # Extract encoder names from "(encoders: name1 name2 ...)"
            idx = rest.find("(encoders:")
            if idx != -1:
                close = rest.find(")", idx)
                if close != -1:
                    encoder_str = rest[idx + len("(encoders:") : close].strip()
                    codecs.extend(encoder_str.split())
    return codecs


def list_hwaccels(ffmpeg_path: Path) -> list[str]:
    """Return a list of available hardware acceleration methods.

    Parses ``ffmpeg -hwaccels`` output.  Returns an empty list on error.
    """
    proc = _run_probe([str(ffmpeg_path), "-hwaccels"])
    if proc is None:
        return []

    hwaccels: list[str] = []
    past_header = False
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped == "Hardware acceleration methods:":
            past_header = True
            continue
        if past_header and stripped:
            hwaccels.append(stripped)
    return hwaccels


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------


def build_concat_command(
    ffmpeg_path: Path,
    concat_file: Path,
    output: Path,
    *,
    copy: bool = True,
    video_codec: str = "libx264",
    crf: int = 18,
    fps: str = "60000/1001",
    audio_codec: str = "aac",
    audio_rate: int = 48000,
) -> list[str]:
    """Build an ffmpeg concat demuxer command."""
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
    ]
    if copy:
        cmd.extend(["-c", "copy"])
    else:
        cmd.extend(
            [
                "-c:v",
                video_codec,
                "-crf",
                str(crf),
                "-r",
                fps,
                "-c:a",
                audio_codec,
                "-ar",
                str(audio_rate),
            ]
        )
    cmd.append(str(output))
    return cmd


# ---------------------------------------------------------------------------
# Concat file + subprocess runner
# ---------------------------------------------------------------------------


def build_xfade_command(
    ffmpeg_path: Path,
    files: list[Path],
    durations: list[float],
    output: Path,
    *,
    fade_duration: float = 0.5,
    video_codec: str = "libx264",
    crf: int = 18,
    audio_codec: str = "aac",
    audio_rate: int = 48000,
) -> list[str]:
    """Build an ffmpeg command that concatenates files with cross-fade transitions.

    Uses the ``xfade`` video filter and ``acrossfade`` audio filter to
    create smooth fade transitions between adjacent clips.

    *durations* must have the same length as *files* — each entry is the
    duration of the corresponding input in seconds.
    """
    if len(files) != len(durations):
        raise FFmpegError(
            f"files and durations must have the same length: {len(files)} vs {len(durations)}"
        )
    if len(files) < 2:
        raise FFmpegError("xfade requires at least 2 input files")

    cmd: list[str] = [str(ffmpeg_path), "-y"]
    for f in files:
        cmd.extend(["-i", str(f)])

    n = len(files)
    fade = min(fade_duration, min(durations) / 2)

    # Build xfade chain: [0:v][1:v]xfade=...=offset[xf0];[xf0][2:v]xfade=...[xf1]...
    v_parts: list[str] = []
    a_parts: list[str] = []

    # Track the cumulative offset (accounting for fade overlap)
    offset = durations[0] - fade
    for i in range(1, n):
        v_in = f"[{i - 1}:v]" if i == 1 else f"[xf{i - 2}]"
        v_out = f"[xf{i - 1}]" if i < n - 1 else "[vout]"
        v_parts.append(
            f"{v_in}[{i}:v]xfade=transition=fade:duration={fade}:offset={offset:.6f}{v_out}"
        )

        a_in = f"[{i - 1}:a]" if i == 1 else f"[af{i - 2}]"
        a_out = f"[af{i - 1}]" if i < n - 1 else "[aout]"
        a_parts.append(
            f"{a_in}[{i}:a]acrossfade=d={fade}:c1=tri:c2=tri{a_out}"
        )

        if i < n - 1:
            offset += durations[i] - fade

    filter_complex = ";".join(v_parts + a_parts)

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", video_codec,
        "-crf", str(crf),
        "-c:a", audio_codec,
        "-ar", str(audio_rate),
        str(output),
    ])
    return cmd


def write_concat_file(files: list[Path], output_dir: Path) -> Path:
    """Write an ffmpeg concat demuxer list to a temp file.

    Each line has the format ``file 'escaped_path'``.
    The caller is responsible for cleaning up the returned file.
    """
    fd, tmp_name = tempfile.mkstemp(suffix=".txt", dir=output_dir, text=True)
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            for f in files:
                escaped = str(f).replace("'", "'\\''")
                fh.write(f"file '{escaped}'\n")
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return Path(tmp_name)


def run_ffmpeg(cmd: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Run an ffmpeg command, raising ``FFmpegError`` on failure.

    Captures stdout/stderr, enforces a timeout, and wraps common errors.
    """
    log.debug("Running ffmpeg: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"ffmpeg binary not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffmpeg timed out after {timeout}s") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise FFmpegError(f"ffmpeg exited with code {proc.returncode}: {stderr}")

    return proc


def concat_files(
    files: list[Path],
    output: Path,
    *,
    copy: bool = True,
    video_codec: str = "libx264",
    crf: int = 18,
    audio_codec: str = "aac",
) -> None:
    """Concatenate media files via the ffmpeg concat demuxer.

    Convenience wrapper around ``build_concat_command`` + ``write_concat_file``
    + ``run_ffmpeg``.
    """
    ffmpeg_path = discover_ffmpeg()
    concat_file = write_concat_file(files, output.parent)
    try:
        cmd = build_concat_command(
            ffmpeg_path,
            concat_file,
            output,
            copy=copy,
            video_codec=video_codec,
            crf=crf,
            audio_codec=audio_codec,
        )
        run_ffmpeg(cmd)
    finally:
        concat_file.unlink(missing_ok=True)



def build_extract_frame_command(
    ffmpeg_path: Path,
    input_path: Path,
    timestamp: float,
    output_path: Path,
) -> list[str]:
    """Build an ffmpeg command to extract a single frame at a given timestamp.

    Uses seek-then-decode for accurate frame extraction.
    """
    return [
        str(ffmpeg_path),
        "-y",
        "-v",
        "error",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(output_path),
    ]


def build_short_command(ffmpeg_path: Path, plan: RenderPlan) -> list[str]:
    """Build an ffmpeg command for short-form rendering with filter chains.

    Uses ``-filter_complex`` for the video filter chain and ``-af`` for audio.
    """
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-v",
        "error",
        "-i",
        str(plan.inputs[0]),
    ]
    if plan.filter_complex:
        cmd.extend(["-filter_complex", plan.filter_complex])
        # When audio is embedded in filter_complex (speed_segments), add
        # explicit stream mapping so ffmpeg picks the correct output pads.
        if "[vfinal]" in plan.filter_complex and "[afinal]" in plan.filter_complex:
            cmd.extend(["-map", "[vfinal]", "-map", "[afinal]"])
    if plan.audio_filter:
        cmd.extend(["-af", plan.audio_filter])
    cmd.extend(
        [
            "-c:v",
            plan.codec,
            "-preset",
            plan.preset,
            "-crf",
            str(plan.crf),
            "-c:a",
            plan.audio_codec,
            "-b:a",
            plan.audio_bitrate,
        ]
    )
    if plan.extra_args:
        cmd.extend(plan.extra_args)
    cmd.append(str(plan.output))
    return cmd


def build_render_command(
    ffmpeg_path: Path,
    input_path: Path,
    output: Path,
    *,
    video_codec: str = "libx264",
    preset: str = "medium",
    crf: int = 18,
    width: int | None = None,
    height: int | None = None,
    audio_codec: str = "aac",
    audio_bitrate: str = "128k",
    extra_args: list[str] | None = None,
) -> list[str]:
    """Build a general ffmpeg render command."""
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-v",
        "error",
        "-i",
        str(input_path),
    ]
    if width and height:
        cmd.extend(["-vf", f"scale={width}:{height}"])
    cmd.extend(
        [
            "-c:v",
            video_codec,
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-c:a",
            audio_codec,
            "-b:a",
            audio_bitrate,
        ]
    )
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(str(output))
    return cmd
