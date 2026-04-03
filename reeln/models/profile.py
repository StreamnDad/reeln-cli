"""Render profile and iteration configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SpeedSegment:
    """One segment in a variable-speed timeline.

    ``until`` is the source-time boundary in seconds (exclusive).
    The last segment must have ``until=None`` (runs to end of clip).
    """

    speed: float
    until: float | None = None


@dataclass(frozen=True)
class RenderProfile:
    """Named set of rendering parameter overrides.

    Fields set to ``None`` inherit from the base ShortConfig / VideoConfig.
    """

    name: str
    # Video transform (applied for short-form; ignored for full-frame)
    width: int | None = None
    height: int | None = None
    crop_mode: str | None = None
    anchor_x: float | None = None
    anchor_y: float | None = None
    pad_color: str | None = None
    scale: float | None = None
    smart: bool | None = None
    # Filters (applied to both short-form and full-frame)
    speed: float | None = None
    speed_segments: tuple[SpeedSegment, ...] | None = None
    lut: str | None = None
    subtitle_template: str | None = None
    # Encoding overrides
    codec: str | None = None
    preset: str | None = None
    crf: int | None = None
    audio_codec: str | None = None
    audio_bitrate: str | None = None


@dataclass(frozen=True)
class IterationConfig:
    """Maps event types to ordered lists of profile names.

    The ``default`` key is used when an event has no type or the type
    has no explicit mapping.
    """

    mappings: dict[str, list[str]] = field(default_factory=dict)

    def profiles_for_event(self, event_type: str) -> list[str]:
        """Return profile names for *event_type*, falling back to ``default``."""
        if event_type and event_type in self.mappings:
            return list(self.mappings[event_type])
        return list(self.mappings.get("default", []))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

_PROFILE_FIELDS: tuple[str, ...] = (
    "width",
    "height",
    "crop_mode",
    "anchor_x",
    "anchor_y",
    "pad_color",
    "scale",
    "smart",
    "speed",
    "lut",
    "subtitle_template",
    "codec",
    "preset",
    "crf",
    "audio_codec",
    "audio_bitrate",
)

# speed_segments is handled separately (not a simple scalar field)


def render_profile_to_dict(profile: RenderProfile) -> dict[str, Any]:
    """Serialize a ``RenderProfile``, omitting ``None`` fields."""
    result: dict[str, Any] = {}
    for field_name in _PROFILE_FIELDS:
        value = getattr(profile, field_name)
        if value is not None:
            result[field_name] = value
    if profile.speed_segments is not None:
        result["speed_segments"] = [
            {"speed": s.speed, **({"until": s.until} if s.until is not None else {})} for s in profile.speed_segments
        ]
    return result


def dict_to_render_profile(name: str, data: dict[str, Any]) -> RenderProfile:
    """Deserialize a dict into a ``RenderProfile``."""
    return RenderProfile(
        name=name,
        width=_opt_int(data, "width"),
        height=_opt_int(data, "height"),
        crop_mode=_opt_str(data, "crop_mode"),
        anchor_x=_opt_float(data, "anchor_x"),
        anchor_y=_opt_float(data, "anchor_y"),
        pad_color=_opt_str(data, "pad_color"),
        scale=_opt_float(data, "scale"),
        smart=_opt_bool(data, "smart"),
        speed=_opt_float(data, "speed"),
        speed_segments=_opt_speed_segments(data, "speed_segments"),
        lut=_opt_str(data, "lut"),
        subtitle_template=_opt_str(data, "subtitle_template"),
        codec=_opt_str(data, "codec"),
        preset=_opt_str(data, "preset"),
        crf=_opt_int(data, "crf"),
        audio_codec=_opt_str(data, "audio_codec"),
        audio_bitrate=_opt_str(data, "audio_bitrate"),
    )


def iteration_config_to_dict(config: IterationConfig) -> dict[str, Any]:
    """Serialize an ``IterationConfig``."""
    return dict(config.mappings)


def dict_to_iteration_config(data: dict[str, Any]) -> IterationConfig:
    """Deserialize an iterations config section."""
    mappings: dict[str, list[str]] = {}
    for key, value in data.items():
        if isinstance(value, list):
            mappings[key] = [str(v) for v in value]
    return IterationConfig(mappings=mappings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opt_int(data: dict[str, Any], key: str) -> int | None:
    v = data.get(key)
    return int(v) if v is not None else None


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    v = data.get(key)
    return float(v) if v is not None else None


def _opt_bool(data: dict[str, Any], key: str) -> bool | None:
    v = data.get(key)
    return bool(v) if v is not None else None


def _opt_str(data: dict[str, Any], key: str) -> str | None:
    v = data.get(key)
    return str(v) if v is not None else None


def _opt_speed_segments(data: dict[str, Any], key: str) -> tuple[SpeedSegment, ...] | None:
    v = data.get(key)
    if v is None or not isinstance(v, list):
        return None
    return tuple(SpeedSegment(speed=float(s["speed"]), until=s.get("until")) for s in v)
