"""Renderer protocol and FFmpeg implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from reeln.core.ffmpeg import (
    build_extract_frame_command,
    build_render_command,
    build_short_command,
    probe_duration,
    probe_fps,
    probe_resolution,
    run_ffmpeg,
)
from reeln.core.log import get_logger
from reeln.models.render_plan import RenderPlan, RenderResult
from reeln.models.zoom import ExtractedFrames

log: logging.Logger = get_logger(__name__)


class Renderer(Protocol):
    """Protocol for video rendering backends."""

    def render(self, plan: RenderPlan) -> RenderResult: ...  # pragma: no cover

    def preview(self, plan: RenderPlan) -> RenderResult: ...  # pragma: no cover

    def extract_frames(  # pragma: no cover
        self, input_path: Path, count: int, output_dir: Path
    ) -> ExtractedFrames: ...


class FFmpegRenderer:
    """FFmpeg-based renderer."""

    def __init__(self, ffmpeg_path: Path) -> None:
        self.ffmpeg_path = ffmpeg_path

    def render(self, plan: RenderPlan, *, emit_hooks: bool = True) -> RenderResult:
        """Render according to the plan.

        Dispatches to ``build_short_command`` when the plan has a filter chain,
        otherwise falls back to ``build_render_command``.

        When *emit_hooks* is ``False``, ``PRE_RENDER`` and ``POST_RENDER``
        hooks are suppressed.  Used by iteration rendering to avoid uploading
        intermediate files — the final concatenated output is emitted once.
        """
        from reeln.plugins.hooks import Hook, HookContext
        from reeln.plugins.registry import get_registry

        registry = get_registry()
        if emit_hooks:
            registry.emit(
                Hook.PRE_RENDER,
                HookContext(hook=Hook.PRE_RENDER, data={"plan": plan}),
            )

        if plan.filter_complex is not None:
            cmd = build_short_command(self.ffmpeg_path, plan)
        else:
            cmd = build_render_command(
                self.ffmpeg_path,
                plan.inputs[0],
                plan.output,
                video_codec=plan.codec,
                preset=plan.preset,
                crf=plan.crf,
                width=plan.width,
                height=plan.height,
                audio_codec=plan.audio_codec,
                audio_bitrate=plan.audio_bitrate,
                extra_args=list(plan.extra_args) if plan.extra_args else None,
            )
        try:
            run_ffmpeg(cmd)
        except Exception as exc:
            from reeln.core.errors import emit_on_error

            emit_on_error(exc, context={"operation": "render", "plan": plan})
            raise

        duration = probe_duration(self.ffmpeg_path, plan.output)
        file_size: int | None = None
        if plan.output.is_file():
            file_size = plan.output.stat().st_size

        result = RenderResult(
            output=plan.output,
            duration_seconds=duration,
            file_size_bytes=file_size,
            ffmpeg_command=list(cmd),
        )

        if emit_hooks:
            registry.emit(
                Hook.POST_RENDER,
                HookContext(hook=Hook.POST_RENDER, data={"plan": plan, "result": result}),
            )

        log.info("Render complete: %s", plan.output)
        return result

    def preview(self, plan: RenderPlan) -> RenderResult:
        """Generate a fast preview render.

        Delegates to ``render()`` — the plan already contains preview settings.
        """
        return self.render(plan)

    def extract_frames(self, input_path: Path, count: int, output_dir: Path) -> ExtractedFrames:
        """Extract evenly-spaced frames from a video for analysis.

        Probes duration, fps, and resolution, then extracts *count* frames
        at evenly-spaced timestamps via single-frame ffmpeg seeks.
        """
        from reeln.core.errors import RenderError

        duration = probe_duration(self.ffmpeg_path, input_path)
        if duration is None or duration <= 0:
            raise RenderError(f"Cannot probe duration of {input_path}")

        resolution = probe_resolution(self.ffmpeg_path, input_path)
        if resolution is None:
            raise RenderError(f"Cannot probe resolution of {input_path}")
        source_width, source_height = resolution

        fps = probe_fps(self.ffmpeg_path, input_path) or 30.0

        # Calculate evenly-spaced timestamps (avoid exact start/end)
        timestamps: tuple[float, ...]
        if count == 1:
            timestamps = (duration / 2.0,)
        else:
            step = duration / (count + 1)
            timestamps = tuple(step * (i + 1) for i in range(count))

        frame_paths: list[Path] = []
        for i, ts in enumerate(timestamps):
            frame_path = output_dir / f"frame_{i:04d}.png"
            cmd = build_extract_frame_command(self.ffmpeg_path, input_path, ts, frame_path)
            run_ffmpeg(cmd)
            frame_paths.append(frame_path)

        log.debug("Extracted %d frames from %s", len(frame_paths), input_path)
        return ExtractedFrames(
            frame_paths=tuple(frame_paths),
            timestamps=timestamps,
            source_width=source_width,
            source_height=source_height,
            duration=duration,
            fps=fps,
        )
