"""Filter graph builders and render planning for short-form video."""

from __future__ import annotations

from pathlib import Path

from reeln.core.errors import RenderError
from reeln.models.render_plan import RenderPlan
from reeln.models.short import CropMode, ShortConfig

_VALID_LUT_SUFFIXES: set[str] = {".cube", ".3dl"}
_VALID_SUBTITLE_SUFFIXES: set[str] = {".ass"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_short_config(config: ShortConfig) -> None:
    """Validate a ShortConfig, raising ``RenderError`` on invalid values."""
    if config.width <= 0:
        raise RenderError(f"Width must be positive, got {config.width}")
    if config.width % 2 != 0:
        raise RenderError(f"Width must be even, got {config.width}")
    if config.height <= 0:
        raise RenderError(f"Height must be positive, got {config.height}")
    if config.height % 2 != 0:
        raise RenderError(f"Height must be even, got {config.height}")
    if not 0.5 <= config.speed <= 2.0:
        raise RenderError(f"Speed must be 0.5-2.0, got {config.speed}")
    if not 0.0 <= config.anchor_x <= 1.0:
        raise RenderError(f"Anchor X must be 0.0-1.0, got {config.anchor_x}")
    if not 0.0 <= config.anchor_y <= 1.0:
        raise RenderError(f"Anchor Y must be 0.0-1.0, got {config.anchor_y}")
    if config.lut is not None and config.lut.suffix.lower() not in _VALID_LUT_SUFFIXES:
        raise RenderError(f"LUT file must be .cube or .3dl, got {config.lut.suffix!r}")
    if config.subtitle is not None and config.subtitle.suffix.lower() not in _VALID_SUBTITLE_SUFFIXES:
        raise RenderError(f"Subtitle file must be .ass, got {config.subtitle.suffix!r}")


# ---------------------------------------------------------------------------
# Individual filter builders
# ---------------------------------------------------------------------------


def build_scale_filter(*, crop_mode: CropMode, target_width: int, target_height: int) -> str:
    """Build the initial scale filter for pad or crop mode.

    Pad mode scales to target width (content fits within frame).
    Crop mode scales to target height (content fills the frame).
    """
    if crop_mode == CropMode.PAD:
        return f"scale={target_width}:-2:flags=lanczos"
    return f"scale=-2:{target_height}:flags=lanczos"


def build_pad_filter(*, target_width: int, target_height: int, pad_color: str) -> str:
    """Build a pad filter to center content within the target frame."""
    return f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:{pad_color}"


def build_crop_filter(*, target_width: int, target_height: int, anchor_x: float, anchor_y: float) -> str:
    """Build a crop filter to extract a region from the scaled frame.

    Uses the anchor_x position for horizontal crop offset.
    The anchor_y is reserved for future vertical crop scenarios.
    """
    return f"crop=w=ih*{target_width}/{target_height}:h=ih:x=(iw-ih*{target_width}/{target_height})*{anchor_x}:y=0"


def build_final_scale_filter(*, target_width: int, target_height: int) -> str:
    """Build a final scale filter to ensure exact output dimensions after crop."""
    return f"scale={target_width}:{target_height}:flags=lanczos"


def build_speed_filter(speed: float) -> str:
    """Build a video speed (setpts) filter."""
    return f"setpts=PTS/{speed}"


def build_audio_speed_filter(speed: float) -> str:
    """Build an audio speed (atempo) filter."""
    return f"atempo={speed}"


def build_lut_filter(lut_path: Path) -> str:
    """Build a LUT color grading filter."""
    return f"lut3d='{lut_path}'"


def build_subtitle_filter(subtitle_path: Path) -> str:
    """Build an ASS subtitle overlay filter."""
    return f"ass='{subtitle_path}'"


# ---------------------------------------------------------------------------
# Filter chain assembly
# ---------------------------------------------------------------------------


def build_filter_chain(config: ShortConfig) -> tuple[str, str | None]:
    """Assemble the full video filter chain and optional audio filter.

    Filter ordering: LUT -> speed -> scale -> pad/crop+final_scale -> subtitle.

    Returns ``(filter_complex_string, audio_filter_or_none)``.
    """
    filters: list[str] = []

    # 1. LUT (color grade source first)
    if config.lut is not None:
        filters.append(build_lut_filter(config.lut))

    # 2. Speed (setpts before spatial transforms)
    if config.speed != 1.0:
        filters.append(build_speed_filter(config.speed))

    # 3. Scale + pad/crop
    filters.append(
        build_scale_filter(
            crop_mode=config.crop_mode,
            target_width=config.width,
            target_height=config.height,
        )
    )
    if config.crop_mode == CropMode.PAD:
        filters.append(
            build_pad_filter(
                target_width=config.width,
                target_height=config.height,
                pad_color=config.pad_color,
            )
        )
    else:
        filters.append(
            build_crop_filter(
                target_width=config.width,
                target_height=config.height,
                anchor_x=config.anchor_x,
                anchor_y=config.anchor_y,
            )
        )
        filters.append(build_final_scale_filter(target_width=config.width, target_height=config.height))

    # 4. Subtitle (render at output resolution)
    if config.subtitle is not None:
        filters.append(build_subtitle_filter(config.subtitle))

    filter_complex = ",".join(filters)

    # Audio filter
    audio_filter: str | None = None
    if config.speed != 1.0:
        audio_filter = build_audio_speed_filter(config.speed)

    return filter_complex, audio_filter


# ---------------------------------------------------------------------------
# Plan builders
# ---------------------------------------------------------------------------


def plan_short(config: ShortConfig) -> RenderPlan:
    """Create a RenderPlan for a short-form render."""
    validate_short_config(config)
    filter_complex, audio_filter = build_filter_chain(config)
    return RenderPlan(
        inputs=[config.input],
        output=config.output,
        codec=config.codec,
        preset=config.preset,
        crf=config.crf,
        width=config.width,
        height=config.height,
        audio_codec=config.audio_codec,
        audio_bitrate=config.audio_bitrate,
        filter_complex=filter_complex,
        audio_filter=audio_filter,
    )


def plan_preview(config: ShortConfig) -> RenderPlan:
    """Create a RenderPlan for a fast preview render.

    Uses half resolution, ultrafast preset, and crf=28 for speed.
    """
    validate_short_config(config)
    preview_width = config.width // 2
    preview_height = config.height // 2
    # Ensure even dimensions
    preview_width += preview_width % 2
    preview_height += preview_height % 2
    preview = ShortConfig(
        input=config.input,
        output=config.output,
        width=preview_width,
        height=preview_height,
        crop_mode=config.crop_mode,
        anchor_x=config.anchor_x,
        anchor_y=config.anchor_y,
        pad_color=config.pad_color,
        speed=config.speed,
        lut=config.lut,
        subtitle=config.subtitle,
        codec=config.codec,
        preset="ultrafast",
        crf=28,
        audio_codec=config.audio_codec,
        audio_bitrate=config.audio_bitrate,
    )
    filter_complex, audio_filter = build_filter_chain(preview)
    return RenderPlan(
        inputs=[preview.input],
        output=preview.output,
        codec=preview.codec,
        preset=preview.preset,
        crf=preview.crf,
        width=preview.width,
        height=preview.height,
        audio_codec=preview.audio_codec,
        audio_bitrate=preview.audio_bitrate,
        filter_complex=filter_complex,
        audio_filter=audio_filter,
    )
