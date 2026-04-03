"""Multi-iteration rendering — run a clip through N profiles and concatenate."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from reeln.core.errors import RenderError
from reeln.core.ffmpeg import (
    build_concat_command,
    build_xfade_command,
    probe_duration,
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
from reeln.models.zoom import ZoomPath

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
    zoom_path: ZoomPath | None = None,
    source_fps: float = 30.0,
    dry_run: bool = False,
    game_info: object | None = None,
    game_event: object | None = None,
    player: str | None = None,
    assists: str | None = None,
) -> tuple[IterationResult, list[str]]:
    """Render *clip* through multiple profiles and concatenate the results.

    For each profile in *profile_names*:

    1. Resolve the profile from config
    2. Optionally render a subtitle template
    3. Plan a render (short-form or full-frame)
    4. Execute via ``FFmpegRenderer``

    When *zoom_path* is provided (from smart zoom frame extraction), it is
    passed through to ``plan_short()`` so smart crop/pad works within
    iterations.

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

    base_ctx = context or TemplateContext()

    # Probe source duration once for overlay timing
    source_dur: float | None = None
    if event_metadata is not None:
        source_dur = probe_duration(ffmpeg_path, clip) or 10.0

    renderer = FFmpegRenderer(ffmpeg_path)

    temp_outputs: list[Path] = []
    temp_subtitles: list[Path] = []

    try:
        for i, profile in enumerate(profiles):
            temp_out = _iteration_temp(output, i)

            # Build per-iteration overlay context — speed_segments change
            # the effective output duration, so subtitle timing must match.
            ctx = base_ctx
            if source_dur is not None and event_metadata is not None:
                from reeln.core.overlay import build_overlay_context
                from reeln.core.shorts import compute_speed_segments_duration

                iter_dur = source_dur
                if profile.speed_segments is not None:
                    iter_dur = compute_speed_segments_duration(
                        profile.speed_segments,
                        source_dur,
                    )
                ctx = build_overlay_context(
                    base_ctx,
                    duration=iter_dur,
                    event_metadata=event_metadata,
                )

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
                    input=clip,
                    output=temp_out,
                )
                # Branding only on the first iteration
                if i > 0:
                    modified = replace(modified, branding=None)
                # When speed_segments and smart tracking combine, remap
                # zoom path timestamps from source time to output time so
                # the t-based ffmpeg expressions align with the stretched
                # timeline.
                iter_zoom = zoom_path
                if modified.speed_segments is not None and iter_zoom is not None:
                    from reeln.core.zoom import remap_zoom_path_for_speed_segments

                    iter_zoom = remap_zoom_path_for_speed_segments(
                        iter_zoom,
                        modified.speed_segments,
                    )
                plan = plan_short(modified, zoom_path=iter_zoom, source_fps=source_fps)
            else:
                input_file = clip
                plan = plan_full_frame(
                    input_file,
                    temp_out,
                    profile,
                    config,
                    rendered_subtitle=rendered_subtitle,
                )

            renderer.render(plan, emit_hooks=False)
            temp_outputs.append(temp_out)

        # Concatenate or rename
        if len(temp_outputs) == 1:
            temp_outputs[0].rename(output)
            messages.append(f"Output: {output}")
        else:
            # Probe durations for xfade transitions
            iter_durations: list[float] = []
            for tmp in temp_outputs:
                dur = probe_duration(ffmpeg_path, tmp)
                iter_durations.append(dur if dur is not None else 10.0)

            try:
                cmd = build_xfade_command(
                    ffmpeg_path,
                    temp_outputs,
                    iter_durations,
                    output,
                    fade_duration=0.5,
                )
                run_ffmpeg(cmd)
            except Exception:
                # Fall back to concat demuxer if xfade fails
                log.warning("xfade failed, falling back to concat demuxer")
                concat_file = write_concat_file(temp_outputs, output.parent)
                try:
                    cmd = build_concat_command(ffmpeg_path, concat_file, output, copy=False)
                    run_ffmpeg(cmd)
                finally:
                    concat_file.unlink(missing_ok=True)
            messages.append(f"Concatenated {len(temp_outputs)} iterations")
            messages.append(f"Output: {output}")

        # Emit POST_RENDER once for the final concatenated output
        from reeln.plugins.hooks import Hook
        from reeln.plugins.hooks import HookContext as PluginContext
        from reeln.plugins.registry import get_registry

        final_duration = probe_duration(ffmpeg_path, output)
        file_size: int | None = None
        if output.is_file():
            file_size = output.stat().st_size
        from reeln.models.render_plan import RenderResult

        final_result = RenderResult(
            output=output,
            duration_seconds=final_duration,
            file_size_bytes=file_size,
        )
        # Use the last iteration's plan for filter_complex detection
        final_plan = plan
        hook_data: dict[str, Any] = {"plan": final_plan, "result": final_result}
        if game_info is not None:
            hook_data["game_info"] = game_info
        if game_event is not None:
            hook_data["game_event"] = game_event
        if player is not None:
            hook_data["player"] = player
        if assists is not None:
            hook_data["assists"] = assists
        get_registry().emit(
            Hook.POST_RENDER,
            PluginContext(hook=Hook.POST_RENDER, data=hook_data),
        )

        messages.append("Iteration rendering complete")
        result = IterationResult(
            output=output,
            iteration_outputs=list(temp_outputs),
            profile_names=list(profile_names),
            concat_copy=False,
        )
        return result, messages

    finally:
        # Clean up temp subtitle files
        for sub in temp_subtitles:
            sub.unlink(missing_ok=True)
        # Clean up iteration temp files (already renamed or intermediate)
        for tmp in temp_outputs:
            tmp.unlink(missing_ok=True)
