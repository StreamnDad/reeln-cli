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
    # CRF 16 (down from 18) for short-form output — high-motion sports
    # footage loses visible detail above 18 once it's been cropped/scaled
    # for vertical aspect. The trade-off is roughly +30% file size for
    # noticeably crisper motion.
    crf: int = 16
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"
    # libx264 tune flag. ``film`` is correct for live-action sports;
    # set to empty string ``""`` to skip the flag entirely (useful for
    # animation, screen capture, or codecs that don't accept it).
    tune: str = "film"
    # H.264 pixel format. ``yuv420p`` is the only format every consumer
    # player decodes reliably (browsers, iOS, Android, social platforms);
    # libx264's default of ``yuv444p`` for high-bit-depth inputs causes
    # silent compatibility failures on web embeds. Set to empty string to
    # let libx264 pick.
    pix_fmt: str = "yuv420p"
    # ``+faststart`` moves the MP4 moov atom to the front of the file so
    # streamers / browsers can begin playback before the full file
    # downloads. No effect for non-MP4 outputs; set to empty string to
    # opt out.
    movflags: str = "+faststart"


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
class EventTypeEntry:
    """A configured event type with optional team-specific flag."""

    name: str
    team_specific: bool = False


@dataclass
class AppConfig:
    """Top-level application configuration."""

    config_version: int = 1
    sport: str = "generic"
    event_types: list[EventTypeEntry] = field(default_factory=list)
    video: VideoConfig = field(default_factory=VideoConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    render_profiles: dict[str, RenderProfile] = field(default_factory=dict)
    iterations: IterationConfig = field(default_factory=IterationConfig)
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    orchestration: OrchestrationConfig = field(default_factory=OrchestrationConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
