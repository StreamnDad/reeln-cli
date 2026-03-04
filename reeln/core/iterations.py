"""Multi-iteration rendering — run a clip through N profiles and concatenate."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from reeln.core.errors import RenderError
from reeln.core.ffmpeg import (
    build_concat_command,
    run_ffmpeg,
    write_concat_file,
)
from reeln.core.log import get_logger
from reeln.core.profiles import (
    apply_profile_to_short,
    plan_full_frame,
    resolve_profile,
    resolve_subtitle_for_profile,
)
from reeln.core.renderer import FFmpegRenderer
from reeln.core.shorts import plan_short
from reeln.models.config import AppConfig
from reeln.models.render_plan import IterationResult
from reeln.models.short import ShortConfig
from reeln.models.template import TemplateContext

log: logging.Logger = get_logger(__name__)


def _iteration_temp(output: Path, index: int) -> Path:
    """Build a temp filename for iteration *index*."""
    return output.with_stem(f"{output.stem}_iter{index}")


def render_iterations(
    clip: Path,
    profile_names: list[str],
    config: AppConfig,
    ffmpeg_path: Path,
    output: Path,
    *,
    context: TemplateContext | None = None,
    event_metadata: dict[str, Any] | None = None,
    is_short: bool = False,
    short_config: ShortConfig | None = None,
    dry_run: bool = False,
) -> tuple[IterationResult, list[str]]:
    """Render *clip* through multiple profiles and concatenate the results.

    For each profile in *profile_names*:

    1. Resolve the profile from config
    2. Optionally render a subtitle template
    3. Plan a render (short-form or full-frame)
    4. Execute via ``FFmpegRenderer``

    When more than one iteration produces output, the results are
    concatenated (stream copy) into the final *output*.  A single
    iteration simply renames its temp file.

    Returns ``(IterationResult, messages)``.
    """
    if not profile_names:
        raise RenderError("No profile names provided for iteration rendering")

    messages: list[str] = []
    messages.append(f"Iterations: {len(profile_names)} profile(s)")
    for name in profile_names:
        messages.append(f"  {name}")

    # Validate all profiles up-front before any work
    profiles = []
    for name in profile_names:
        profiles.append(resolve_profile(config, name))

    if dry_run:
        messages.insert(0, "Dry run — no files written")
        result = IterationResult(
            output=output,
            iteration_outputs=[],
            profile_names=list(profile_names),
            concat_copy=True,
        )
        return result, messages

    ctx = context or TemplateContext()

    # Enrich context with overlay variables when event metadata is available
    if event_metadata is not None:
        from reeln.core.ffmpeg import probe_duration
        from reeln.core.overlay import build_overlay_context

        dur = probe_duration(ffmpeg_path, clip) or 10.0
        ctx = build_overlay_context(ctx, duration=dur, event_metadata=event_metadata)

    renderer = FFmpegRenderer(ffmpeg_path)

    temp_outputs: list[Path] = []
    temp_subtitles: list[Path] = []

    try:
        for i, profile in enumerate(profiles):
            temp_out = _iteration_temp(output, i)

            # Resolve subtitle template
            rendered_subtitle: Path | None = None
            if profile.subtitle_template is not None:
                rendered_subtitle = resolve_subtitle_for_profile(profile, ctx, output.parent)
                if rendered_subtitle is not None:
                    temp_subtitles.append(rendered_subtitle)

            # Plan render
            if is_short and short_config is not None:
                modified = apply_profile_to_short(short_config, profile, rendered_subtitle=rendered_subtitle)
                modified = replace(
                    modified,
                    input=clip if i == 0 else temp_outputs[-1],
                    output=temp_out,
                )
                plan = plan_short(modified)
            else:
                input_file = clip if i == 0 else temp_outputs[-1]
                plan = plan_full_frame(
                    input_file,
                    temp_out,
                    profile,
                    config,
                    rendered_subtitle=rendered_subtitle,
                )

            renderer.render(plan)
            temp_outputs.append(temp_out)

        # Concatenate or rename
        if len(temp_outputs) == 1:
            temp_outputs[0].rename(output)
            messages.append(f"Output: {output}")
        else:
            concat_file = write_concat_file(temp_outputs, output.parent)
            try:
                cmd = build_concat_command(ffmpeg_path, concat_file, output, copy=True)
                run_ffmpeg(cmd)
            finally:
                concat_file.unlink(missing_ok=True)
            messages.append(f"Concatenated {len(temp_outputs)} iterations")
            messages.append(f"Output: {output}")

        messages.append("Iteration rendering complete")
        result = IterationResult(
            output=output,
            iteration_outputs=list(temp_outputs),
            profile_names=list(profile_names),
            concat_copy=len(temp_outputs) > 1,
        )
        return result, messages

    finally:
        # Clean up temp subtitle files
        for sub in temp_subtitles:
            sub.unlink(missing_ok=True)
        # Clean up iteration temp files (already renamed or intermediate)
        for tmp in temp_outputs:
            tmp.unlink(missing_ok=True)
