"""Profile resolution, application, and iteration planning."""

from __future__ import annotations

import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from reeln.core.errors import ConfigError, RenderError
from reeln.core.shorts import (
    build_audio_speed_filter,
    build_lut_filter,
    build_speed_filter,
    build_speed_segments_filters,
    build_subtitle_filter,
    validate_speed_segments,
)
from reeln.core.templates import render_template_file
from reeln.models.config import AppConfig
from reeln.models.game import GameEvent
from reeln.models.profile import RenderProfile
from reeln.models.render_plan import RenderPlan
from reeln.models.short import CropMode, ShortConfig
from reeln.models.template import TemplateContext

# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------


def resolve_profile(config: AppConfig, name: str) -> RenderProfile:
    """Look up a named profile from *config*.

    Raises ``ConfigError`` if the profile name is not found.
    """
    profile = config.render_profiles.get(name)
    if profile is None:
        available = ", ".join(sorted(config.render_profiles)) or "(none)"
        raise ConfigError(f"Render profile {name!r} not found. Available: {available}")
    return profile


def validate_iteration_config(config: AppConfig) -> list[str]:
    """Check that all profile names referenced in iterations exist.

    Returns a list of warning messages (empty if valid).
    """
    warnings: list[str] = []
    for event_type, profile_names in config.iterations.mappings.items():
        for pname in profile_names:
            if pname not in config.render_profiles:
                warnings.append(f"Iteration {event_type!r} references unknown profile {pname!r}")
    return warnings


# ---------------------------------------------------------------------------
# Short-form application
# ---------------------------------------------------------------------------


def apply_profile_to_short(
    base: ShortConfig,
    profile: RenderProfile,
    *,
    rendered_subtitle: Path | None = None,
) -> ShortConfig:
    """Overlay non-``None`` profile fields onto a ``ShortConfig``.

    Applies all profile fields (crop, speed, LUT, encoding, etc.).
    The *rendered_subtitle* is an already-rendered .ass file path.
    """
    overrides: dict[str, Any] = {}
    if profile.width is not None:
        overrides["width"] = profile.width
    if profile.height is not None:
        overrides["height"] = profile.height
    if profile.crop_mode is not None:
        overrides["crop_mode"] = CropMode(profile.crop_mode)
    if profile.anchor_x is not None:
        overrides["anchor_x"] = profile.anchor_x
    if profile.anchor_y is not None:
        overrides["anchor_y"] = profile.anchor_y
    if profile.pad_color is not None:
        overrides["pad_color"] = profile.pad_color
    if profile.scale is not None:
        overrides["scale"] = profile.scale
    if profile.smart is not None:
        overrides["smart"] = profile.smart
    if profile.speed is not None:
        overrides["speed"] = profile.speed
    if profile.speed_segments is not None:
        overrides["speed_segments"] = profile.speed_segments
    if profile.lut is not None:
        overrides["lut"] = Path(profile.lut)
    if profile.codec is not None:
        overrides["codec"] = profile.codec
    if profile.preset is not None:
        overrides["preset"] = profile.preset
    if profile.crf is not None:
        overrides["crf"] = profile.crf
    if profile.audio_codec is not None:
        overrides["audio_codec"] = profile.audio_codec
    if profile.audio_bitrate is not None:
        overrides["audio_bitrate"] = profile.audio_bitrate
    if rendered_subtitle is not None:
        overrides["subtitle"] = rendered_subtitle
    return replace(base, **overrides)


# ---------------------------------------------------------------------------
# Full-frame filter chain
# ---------------------------------------------------------------------------


def build_profile_filter_chain(
    profile: RenderProfile,
    *,
    rendered_subtitle: Path | None = None,
) -> tuple[str | None, str | None]:
    """Build filter_complex and audio_filter for full-frame rendering.

    Only applies: LUT -> speed (or speed_segments) -> subtitle. No crop/scale.
    Returns ``(filter_complex, audio_filter)`` — either may be ``None``.
    """
    has_speed = profile.speed is not None and profile.speed != 1.0
    has_segments = profile.speed_segments is not None

    if has_speed and has_segments:
        raise RenderError("Cannot use both speed and speed_segments — they are mutually exclusive")

    if has_segments:
        assert profile.speed_segments is not None
        validate_speed_segments(profile.speed_segments)
        return _build_profile_speed_segments_chain(
            profile, rendered_subtitle=rendered_subtitle
        )

    filters: list[str] = []

    if profile.lut is not None:
        filters.append(build_lut_filter(Path(profile.lut)))

    if has_speed:
        assert profile.speed is not None
        filters.append(build_speed_filter(profile.speed))

    if rendered_subtitle is not None:
        filters.append(build_subtitle_filter(rendered_subtitle))

    filter_complex = ",".join(filters) if filters else None

    audio_filter: str | None = None
    if has_speed:
        assert profile.speed is not None
        audio_filter = build_audio_speed_filter(profile.speed)

    return filter_complex, audio_filter


def _build_profile_speed_segments_chain(
    profile: RenderProfile,
    *,
    rendered_subtitle: Path | None = None,
) -> tuple[str, None]:
    """Build a full filter_complex for full-frame speed_segments rendering.

    Graph: [0:v]{pre} → split/trim/speed/concat → {post}
    Audio goes through filter_complex too (audio_filter returns None).
    """
    assert profile.speed_segments is not None

    pre: list[str] = []
    if profile.lut is not None:
        pre.append(build_lut_filter(Path(profile.lut)))

    post: list[str] = []
    if rendered_subtitle is not None:
        post.append(build_subtitle_filter(rendered_subtitle))

    video_segs, audio_segs = build_speed_segments_filters(profile.speed_segments)

    # Wire pre-filters
    if pre:
        video_graph = video_segs.replace("[_vsrc]", f"[0:v]{','.join(pre)},", 1)
    else:
        video_graph = video_segs.replace("[_vsrc]", "[0:v]", 1)

    # Wire post-filters
    if post:
        video_graph = video_graph.replace("[_vout]", f"[_vout];[_vout]{','.join(post)}")
    else:
        video_graph = video_graph.replace("[_vout]", "")

    # Wire audio
    audio_graph = audio_segs.replace("[_asrc]", "[0:a]", 1)
    audio_graph = audio_graph.replace("[_aout]", "")

    return f"{video_graph};{audio_graph}", None


def plan_full_frame(
    input_path: Path,
    output: Path,
    profile: RenderProfile,
    config: AppConfig,
    *,
    rendered_subtitle: Path | None = None,
) -> RenderPlan:
    """Build a ``RenderPlan`` for full-frame rendering with profile filters.

    No crop/scale — preserves original resolution.
    Applies speed, LUT, subtitle, and encoding overrides.
    """
    if profile.speed is not None and not 0.5 <= profile.speed <= 2.0:
        raise RenderError(f"Speed must be 0.5-2.0, got {profile.speed}")
    if profile.speed is not None and profile.speed != 1.0 and profile.speed_segments is not None:
        raise RenderError("Cannot use both speed and speed_segments — they are mutually exclusive")
    if profile.speed_segments is not None:
        validate_speed_segments(profile.speed_segments)

    filter_complex, audio_filter = build_profile_filter_chain(profile, rendered_subtitle=rendered_subtitle)

    return RenderPlan(
        inputs=[input_path],
        output=output,
        codec=profile.codec or config.video.codec,
        preset=profile.preset or config.video.preset,
        crf=profile.crf if profile.crf is not None else config.video.crf,
        audio_codec=profile.audio_codec or config.video.audio_codec,
        audio_bitrate=profile.audio_bitrate or config.video.audio_bitrate,
        filter_complex=filter_complex,
        audio_filter=audio_filter,
    )


# ---------------------------------------------------------------------------
# Subtitle resolution
# ---------------------------------------------------------------------------


def resolve_subtitle_for_profile(
    profile: RenderProfile,
    context: TemplateContext,
    output_dir: Path,
) -> Path | None:
    """If *profile* has a ``subtitle_template``, render it to a temp .ass file.

    Returns the temp file path, or ``None`` if no subtitle template is set.
    The caller is responsible for cleaning up the temp file.
    """
    if profile.subtitle_template is None:
        return None
    if profile.subtitle_template.startswith("builtin:"):
        from reeln.core.overlay import resolve_builtin_template

        template_path = resolve_builtin_template(profile.subtitle_template.removeprefix("builtin:"))
    else:
        template_path = Path(profile.subtitle_template).expanduser()
    rendered = render_template_file(template_path, context)
    fd, tmp_path = tempfile.mkstemp(suffix=".ass", dir=str(output_dir))
    os.close(fd)
    tmp = Path(tmp_path)
    try:
        tmp.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise RenderError(f"Failed to write rendered subtitle: {exc}") from exc
    return tmp


# ---------------------------------------------------------------------------
# Event-based profile lookup
# ---------------------------------------------------------------------------


def profiles_for_event(config: AppConfig, event: GameEvent | None) -> list[str]:
    """Determine profile names for an event.

    Returns an empty list if no iterations are configured.
    """
    if not config.iterations.mappings:
        return []
    event_type = event.event_type if event is not None else ""
    return config.iterations.profiles_for_event(event_type)
