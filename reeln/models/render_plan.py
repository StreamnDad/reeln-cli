"""Data structures for render planning and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RenderPlan:
    """Describes what to render — inspectable and testable before execution."""

    inputs: list[Path]
    output: Path
    codec: str = "libx264"
    preset: str = "medium"
    crf: int = 18
    width: int | None = None
    height: int | None = None
    fps: str | None = None
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"
    filter_complex: str | None = None
    audio_filter: str | None = None
    extra_args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RenderResult:
    """Outcome of a render operation."""

    output: Path
    duration_seconds: float | None = None
    file_size_bytes: int | None = None
    ffmpeg_command: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SegmentResult:
    """Outcome of a segment merge operation."""

    segment_number: int
    segment_dir: Path
    input_files: list[Path]
    output: Path
    copy: bool  # True = stream copy, False = re-encoded
    events_created: int = 0
    ffmpeg_command: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HighlightsResult:
    """Outcome of a full-game highlights merge."""

    output: Path
    segment_files: list[Path]
    copy: bool
    ffmpeg_command: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompilationResult:
    """Outcome of an event compilation."""

    output: Path
    event_ids: list[str]
    input_files: list[Path]
    copy: bool
    ffmpeg_command: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IterationResult:
    """Outcome of a multi-iteration render."""

    output: Path
    iteration_outputs: list[Path]
    profile_names: list[str]
    concat_copy: bool


@dataclass
class PruneResult:
    """Outcome of a prune operation."""

    removed_paths: list[Path] = field(default_factory=list)
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)
