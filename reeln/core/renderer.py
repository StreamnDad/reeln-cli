"""Renderer protocol and FFmpeg implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from reeln.core.ffmpeg import (
    build_render_command,
    build_short_command,
    probe_duration,
    run_ffmpeg,
)
from reeln.core.log import get_logger
from reeln.models.render_plan import RenderPlan, RenderResult

log: logging.Logger = get_logger(__name__)


class Renderer(Protocol):
    """Protocol for video rendering backends."""

    def render(self, plan: RenderPlan) -> RenderResult: ...  # pragma: no cover

    def preview(self, plan: RenderPlan) -> RenderResult: ...  # pragma: no cover


class FFmpegRenderer:
    """FFmpeg-based renderer."""

    def __init__(self, ffmpeg_path: Path) -> None:
        self.ffmpeg_path = ffmpeg_path

    def render(self, plan: RenderPlan) -> RenderResult:
        """Render according to the plan.

        Dispatches to ``build_short_command`` when the plan has a filter chain,
        otherwise falls back to ``build_render_command``.
        """
        from reeln.plugins.hooks import Hook, HookContext
        from reeln.plugins.registry import get_registry

        registry = get_registry()
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
