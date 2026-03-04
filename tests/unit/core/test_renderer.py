"""Tests for the Renderer protocol and FFmpegRenderer."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from reeln.core.renderer import FFmpegRenderer
from reeln.models.render_plan import RenderPlan, RenderResult
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.registry import get_registry


def _make_plan(tmp_path: Path, **kwargs: object) -> RenderPlan:
    defaults: dict[str, object] = {
        "inputs": [tmp_path / "clip.mkv"],
        "output": tmp_path / "out.mp4",
    }
    defaults.update(kwargs)
    return RenderPlan(**defaults)  # type: ignore[arg-type]


def _mock_ffmpeg_success() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


# ---------------------------------------------------------------------------
# FFmpegRenderer init
# ---------------------------------------------------------------------------


def test_ffmpeg_renderer_init() -> None:
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    assert renderer.ffmpeg_path == Path("/usr/bin/ffmpeg")


# ---------------------------------------------------------------------------
# Renderer protocol
# ---------------------------------------------------------------------------


def test_ffmpeg_renderer_satisfies_protocol() -> None:
    """Verify FFmpegRenderer is structurally compatible with Renderer protocol."""
    from reeln.core.renderer import Renderer

    def _accept_renderer(r: Renderer) -> None:
        pass

    _accept_renderer(FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg")))


# ---------------------------------------------------------------------------
# render() with filter_complex (short command path)
# ---------------------------------------------------------------------------


def test_render_with_filter_complex(tmp_path: Path) -> None:
    plan = _make_plan(
        tmp_path,
        filter_complex="scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
    )
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg") as mock_run,
        patch("reeln.core.renderer.probe_duration", return_value=30.5),
    ):
        mock_run.return_value = _mock_ffmpeg_success()
        result = renderer.render(plan)

    assert result.output == tmp_path / "out.mp4"
    assert result.duration_seconds == 30.5
    # File doesn't exist in test, so file_size is None
    assert result.file_size_bytes is None
    # Verify build_short_command was used (filter_complex in cmd)
    call_args = mock_run.call_args[0][0]
    assert "-filter_complex" in call_args


def test_render_with_filter_complex_and_audio(tmp_path: Path) -> None:
    plan = _make_plan(
        tmp_path,
        filter_complex="setpts=PTS/0.5,scale=1080:-2:flags=lanczos",
        audio_filter="atempo=0.5",
    )
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg") as mock_run,
        patch("reeln.core.renderer.probe_duration", return_value=60.0),
    ):
        mock_run.return_value = _mock_ffmpeg_success()
        renderer.render(plan)

    call_args = mock_run.call_args[0][0]
    assert "-af" in call_args
    assert "atempo=0.5" in call_args


# ---------------------------------------------------------------------------
# render() without filter_complex (render command path)
# ---------------------------------------------------------------------------


def test_render_without_filter_complex(tmp_path: Path) -> None:
    plan = _make_plan(tmp_path)
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg") as mock_run,
        patch("reeln.core.renderer.probe_duration", return_value=120.0),
    ):
        mock_run.return_value = _mock_ffmpeg_success()
        result = renderer.render(plan)

    assert result.output == tmp_path / "out.mp4"
    assert result.duration_seconds == 120.0
    # Uses build_render_command — no -filter_complex
    call_args = mock_run.call_args[0][0]
    assert "-filter_complex" not in call_args


def test_render_without_filter_complex_with_scale(tmp_path: Path) -> None:
    plan = _make_plan(tmp_path, width=1280, height=720)
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg") as mock_run,
        patch("reeln.core.renderer.probe_duration", return_value=None),
    ):
        mock_run.return_value = _mock_ffmpeg_success()
        result = renderer.render(plan)

    call_args = mock_run.call_args[0][0]
    assert "-vf" in call_args
    assert result.duration_seconds is None


# ---------------------------------------------------------------------------
# render() file size probing
# ---------------------------------------------------------------------------


def test_render_probes_file_size(tmp_path: Path) -> None:
    output = tmp_path / "out.mp4"
    output.write_bytes(b"x" * 2048)
    plan = _make_plan(tmp_path, output=output)
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg"),
        patch("reeln.core.renderer.probe_duration", return_value=10.0),
    ):
        result = renderer.render(plan)

    assert result.file_size_bytes == 2048


def test_render_no_file_size_when_output_missing(tmp_path: Path) -> None:
    plan = _make_plan(tmp_path)
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg"),
        patch("reeln.core.renderer.probe_duration", return_value=None),
    ):
        result = renderer.render(plan)

    assert result.file_size_bytes is None


# ---------------------------------------------------------------------------
# render() with extra_args
# ---------------------------------------------------------------------------


def test_render_without_filter_complex_with_extra_args(tmp_path: Path) -> None:
    plan = _make_plan(tmp_path, extra_args=["-movflags", "+faststart"])
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg") as mock_run,
        patch("reeln.core.renderer.probe_duration", return_value=None),
    ):
        mock_run.return_value = _mock_ffmpeg_success()
        renderer.render(plan)

    call_args = mock_run.call_args[0][0]
    assert "-movflags" in call_args


def test_render_without_filter_complex_no_extra_args(tmp_path: Path) -> None:
    plan = _make_plan(tmp_path)
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg") as mock_run,
        patch("reeln.core.renderer.probe_duration", return_value=None),
    ):
        mock_run.return_value = _mock_ffmpeg_success()
        renderer.render(plan)

    call_args = mock_run.call_args[0][0]
    assert "-movflags" not in call_args


# ---------------------------------------------------------------------------
# preview() delegates to render()
# ---------------------------------------------------------------------------


def test_preview_delegates_to_render(tmp_path: Path) -> None:
    plan = _make_plan(
        tmp_path,
        preset="ultrafast",
        crf=28,
        filter_complex="scale=540:-2:flags=lanczos",
    )
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))
    with (
        patch("reeln.core.renderer.run_ffmpeg"),
        patch("reeln.core.renderer.probe_duration", return_value=15.0),
    ):
        result = renderer.preview(plan)

    assert isinstance(result, RenderResult)
    assert result.duration_seconds == 15.0


# ---------------------------------------------------------------------------
# Hook emissions
# ---------------------------------------------------------------------------


def test_render_emits_on_error_on_failure(tmp_path: Path) -> None:
    plan = _make_plan(tmp_path)
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))

    emitted: list[HookContext] = []
    registry = get_registry()
    registry.register(Hook.ON_ERROR, emitted.append)

    from reeln.core.errors import FFmpegError

    with (
        patch("reeln.core.renderer.run_ffmpeg", side_effect=FFmpegError("render failed")),
        pytest.raises(FFmpegError, match="render failed"),
    ):
        renderer.render(plan)

    assert len(emitted) == 1
    assert emitted[0].hook is Hook.ON_ERROR
    assert emitted[0].data["operation"] == "render"


def test_render_emits_pre_and_post_render_hooks(tmp_path: Path) -> None:
    plan = _make_plan(tmp_path)
    renderer = FFmpegRenderer(ffmpeg_path=Path("/usr/bin/ffmpeg"))

    emitted: list[HookContext] = []
    registry = get_registry()
    registry.register(Hook.PRE_RENDER, emitted.append)
    registry.register(Hook.POST_RENDER, emitted.append)

    with (
        patch("reeln.core.renderer.run_ffmpeg"),
        patch("reeln.core.renderer.probe_duration", return_value=10.0),
    ):
        renderer.render(plan)

    assert len(emitted) == 2
    assert emitted[0].hook is Hook.PRE_RENDER
    assert emitted[0].data["plan"] is plan
    assert emitted[1].hook is Hook.POST_RENDER
    assert emitted[1].data["plan"] is plan
    assert isinstance(emitted[1].data["result"], RenderResult)
