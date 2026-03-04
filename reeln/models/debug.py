"""Data structures for pipeline debug artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DebugArtifact:
    """A single debug record for one pipeline operation."""

    operation: str  # "segment_merge", "highlights_merge", "render_short", "compile"
    timestamp: str  # ISO 8601
    ffmpeg_command: list[str] = field(default_factory=list)
    filter_complex: str = ""
    input_files: list[str] = field(default_factory=list)
    output_file: str = ""
    input_metadata: list[dict[str, object]] = field(default_factory=list)
    output_metadata: dict[str, object] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)


def debug_artifact_to_dict(artifact: DebugArtifact) -> dict[str, Any]:
    """Serialize a ``DebugArtifact`` to a plain dict."""
    return {
        "operation": artifact.operation,
        "timestamp": artifact.timestamp,
        "ffmpeg_command": list(artifact.ffmpeg_command),
        "filter_complex": artifact.filter_complex,
        "input_files": list(artifact.input_files),
        "output_file": artifact.output_file,
        "input_metadata": [dict(m) for m in artifact.input_metadata],
        "output_metadata": dict(artifact.output_metadata),
        "extra": dict(artifact.extra),
    }


def dict_to_debug_artifact(data: dict[str, Any]) -> DebugArtifact:
    """Deserialize a ``DebugArtifact`` from a plain dict."""
    return DebugArtifact(
        operation=data.get("operation", ""),
        timestamp=data.get("timestamp", ""),
        ffmpeg_command=list(data.get("ffmpeg_command", [])),
        filter_complex=data.get("filter_complex", ""),
        input_files=list(data.get("input_files", [])),
        output_file=data.get("output_file", ""),
        input_metadata=[dict(m) for m in data.get("input_metadata", [])],
        output_metadata=dict(data.get("output_metadata", {})),
        extra=dict(data.get("extra", {})),
    )
