"""Configuration data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reeln.models.branding import BrandingConfig
from reeln.models.plugin import OrchestrationConfig
from reeln.models.profile import IterationConfig, RenderProfile


@dataclass
class VideoConfig:
    """Video encoding defaults."""

    ffmpeg_path: str = "ffmpeg"
    codec: str = "libx264"
    preset: str = "medium"
    crf: int = 18
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"


@dataclass
class PathConfig:
    """Directory paths for reeln data."""

    source_dir: Path | None = None
    source_glob: str = "Replay_*.mkv"
    output_dir: Path | None = None
    temp_dir: Path | None = None


@dataclass
class PluginsConfig:
    """Plugin enable/disable lists and per-plugin settings."""

    enabled: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    settings: dict[str, dict[str, Any]] = field(default_factory=dict)
    registry_url: str = ""
    enforce_hooks: bool = True


@dataclass
class AppConfig:
    """Top-level application configuration."""

    config_version: int = 1
    sport: str = "generic"
    video: VideoConfig = field(default_factory=VideoConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    render_profiles: dict[str, RenderProfile] = field(default_factory=dict)
    iterations: IterationConfig = field(default_factory=IterationConfig)
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    orchestration: OrchestrationConfig = field(default_factory=OrchestrationConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
