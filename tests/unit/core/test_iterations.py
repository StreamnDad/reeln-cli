"""Tests for multi-iteration rendering orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reeln.core.errors import ConfigError, RenderError
from reeln.core.iterations import _iteration_temp, render_iterations
from reeln.models.config import AppConfig, VideoConfig
from reeln.models.profile import IterationConfig, RenderProfile
from reeln.models.render_plan import IterationResult, RenderPlan, RenderResult
from reeln.models.short import ShortConfig
from reeln.models.template import TemplateContext

_MOD = "reeln.core.iterations"


@pytest.fixture(autouse=True)
def _mock_hook_registry() -> object:  # type: ignore[misc]
    """Suppress POST_RENDER hook emission from render_iterations()."""
    with patch("reeln.plugins.registry.get_registry") as mock_get:
        mock_registry = MagicMock()
        mock_get.return_value = mock_registry
        yield mock_registry


def _make_config(**profile_overrides: RenderProfile) -> AppConfig:
    profiles: dict[str, RenderProfile] = {
        "fullspeed": RenderProfile(name="fullspeed", speed=1.0),
        "slowmo": RenderProfile(name="slowmo", speed=0.5),
    }
    profiles.update(profile_overrides)
    return AppConfig(
        video=VideoConfig(),
        render_profiles=profiles,
        iterations=IterationConfig(mappings={"default": ["fullspeed"]}),
    )


def _mock_render_result(output: Path) -> RenderResult:
    return RenderResult(output=output, duration_seconds=10.0, file_size_bytes=1024)


# ---------------------------------------------------------------------------
# _iteration_temp
# ---------------------------------------------------------------------------


def test_iteration_temp_index_0(tmp_path: Path) -> None:
    out = tmp_path / "clip.mp4"
    assert _iteration_temp(out, 0) == tmp_path / "clip_iter0.mp4"


def test_iteration_temp_index_5(tmp_path: Path) -> None:
    out = tmp_path / "my_video.mkv"
    assert _iteration_temp(out, 5) == tmp_path / "my_video_iter5.mkv"


# ---------------------------------------------------------------------------
# render_iterations — validation
# ---------------------------------------------------------------------------


def test_empty_profile_names_raises(tmp_path: Path) -> None:
    config = _make_config()
    with pytest.raises(RenderError, match="No profile names"):
        render_iterations(
            tmp_path / "clip.mkv",
            [],
            config,
            Path("/usr/bin/ffmpeg"),
            tmp_path / "out.mp4",
        )


def test_unknown_profile_raises(tmp_path: Path) -> None:
    config = _make_config()
    with pytest.raises(ConfigError, match="not found"):
        render_iterations(
            tmp_path / "clip.mkv",
            ["nonexistent"],
            config,
            Path("/usr/bin/ffmpeg"),
            tmp_path / "out.mp4",
        )


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------


def test_dry_run_single_profile(tmp_path: Path) -> None:
    config = _make_config()
    result, messages = render_iterations(
        tmp_path / "clip.mkv",
        ["fullspeed"],
        config,
        Path("/usr/bin/ffmpeg"),
        tmp_path / "out.mp4",
        dry_run=True,
    )
    assert isinstance(result, IterationResult)
    assert result.output == tmp_path / "out.mp4"
    assert result.profile_names == ["fullspeed"]
    assert result.iteration_outputs == []
    assert any("Dry run" in m for m in messages)


def test_dry_run_multiple_profiles(tmp_path: Path) -> None:
    config = _make_config()
    result, messages = render_iterations(
        tmp_path / "clip.mkv",
        ["fullspeed", "slowmo"],
        config,
        Path("/usr/bin/ffmpeg"),
        tmp_path / "out.mp4",
        dry_run=True,
    )
    assert result.profile_names == ["fullspeed", "slowmo"]
    assert any("2 profile(s)" in m for m in messages)


# ---------------------------------------------------------------------------
# Single profile full-frame (rename, no concat)
# ---------------------------------------------------------------------------


def test_single_profile_full_frame(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        result, messages = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
        )

    assert result.output == output
    assert result.profile_names == ["fullspeed"]
    assert not result.concat_copy
    assert any("complete" in m for m in messages)


# ---------------------------------------------------------------------------
# Multiple profiles full-frame (concat)
# ---------------------------------------------------------------------------


def test_multiple_profiles_full_frame_concat(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    call_count = [0]

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        temp = _iteration_temp(output, call_count[0])
        temp.write_bytes(b"rendered")
        call_count[0] += 1
        return _mock_render_result(temp)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.probe_duration", return_value=10.0),
        patch(f"{_MOD}.build_xfade_command", return_value=["ffmpeg"]),
        patch(f"{_MOD}.run_ffmpeg") as mock_run,
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        result, messages = render_iterations(
            clip,
            ["fullspeed", "slowmo"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
        )

    assert result.concat_copy is False
    assert len(result.iteration_outputs) == 2
    assert result.profile_names == ["fullspeed", "slowmo"]
    assert any("Concatenated 2 iterations" in m for m in messages)
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Single profile short-form
# ---------------------------------------------------------------------------


def test_single_profile_short_form(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    short_cfg = ShortConfig(
        input=clip,
        output=output,
        width=1080,
        height=1920,
    )

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        result, _messages = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,
            short_config=short_cfg,
        )

    assert result.output == output
    assert result.profile_names == ["fullspeed"]


# ---------------------------------------------------------------------------
# Multiple profiles short-form (concat)
# ---------------------------------------------------------------------------


def test_multiple_profiles_short_form_concat(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    short_cfg = ShortConfig(
        input=clip,
        output=output,
        width=1080,
        height=1920,
    )

    call_count = [0]

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        temp = _iteration_temp(output, call_count[0])
        temp.write_bytes(b"rendered")
        call_count[0] += 1
        return _mock_render_result(temp)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.write_concat_file") as mock_concat_file,
        patch(f"{_MOD}.build_concat_command", return_value=["ffmpeg"]),
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        concat_tmp = tmp_path / "concat.txt"
        concat_tmp.write_text("file list")
        mock_concat_file.return_value = concat_tmp

        result, _messages = render_iterations(
            clip,
            ["fullspeed", "slowmo"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,
            short_config=short_cfg,
        )

    assert result.concat_copy is False
    assert len(result.iteration_outputs) == 2


# ---------------------------------------------------------------------------
# Subtitle template resolution + cleanup
# ---------------------------------------------------------------------------


def test_subtitle_template_resolved_and_cleaned(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"

    template_path = tmp_path / "overlay.ass"
    template_path.write_text("[Script Info]\nTitle: {{home_team}}")

    config = _make_config(
        overlay=RenderProfile(
            name="overlay",
            subtitle_template=str(template_path),
        ),
    )

    iter0 = _iteration_temp(output, 0)
    rendered_sub_path: list[Path] = []

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    def track_resolve(profile, ctx, out_dir):  # type: ignore[no-untyped-def]
        sub = tmp_path / "temp_sub.ass"
        sub.write_text("[Script Info]\nTitle: roseville")
        rendered_sub_path.append(sub)
        return sub

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.resolve_subtitle_for_profile", side_effect=track_resolve),
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        ctx = TemplateContext(variables={"home_team": "roseville"})
        result, _messages = render_iterations(
            clip,
            ["overlay"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            context=ctx,
        )

    assert result.output == output
    # Temp subtitle should be cleaned up
    assert len(rendered_sub_path) == 1
    assert not rendered_sub_path[0].exists()


def test_subtitle_resolve_returns_none(tmp_path: Path) -> None:
    """When resolve_subtitle_for_profile returns None, no subtitle is tracked."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"

    config = _make_config(
        overlay=RenderProfile(
            name="overlay",
            subtitle_template="missing.ass",
        ),
    )

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.resolve_subtitle_for_profile", return_value=None),
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        ctx = TemplateContext(variables={"home_team": "roseville"})
        result, _messages = render_iterations(
            clip,
            ["overlay"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            context=ctx,
        )

    assert result.output == output


# ---------------------------------------------------------------------------
# Error cleanup (temps cleaned on failure)
# ---------------------------------------------------------------------------


def test_error_cleanup_on_render_failure(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render_fail(plan: object, **kwargs: object) -> RenderResult:
        if not iter0.exists():
            iter0.write_bytes(b"rendered")
            return _mock_render_result(iter0)
        raise RenderError("ffmpeg failed")

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render_fail
        MockRenderer.return_value = mock_instance

        with pytest.raises(RenderError, match="ffmpeg failed"):
            render_iterations(
                clip,
                ["fullspeed", "slowmo"],
                config,
                Path("/usr/bin/ffmpeg"),
                output,
            )

    # Temp file should be cleaned up
    assert not iter0.exists()


# ---------------------------------------------------------------------------
# Context defaults to empty TemplateContext
# ---------------------------------------------------------------------------


def test_default_context_used(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        result, _messages = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
        )

    assert result.output == output


# ---------------------------------------------------------------------------
# Profile validation happens before any rendering
# ---------------------------------------------------------------------------


def test_profile_validation_before_render(tmp_path: Path) -> None:
    """Second profile is invalid — error raised before any rendering."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    with patch(f"{_MOD}.FFmpegRenderer") as MockRenderer:
        mock_instance = MagicMock()
        MockRenderer.return_value = mock_instance

        with pytest.raises(ConfigError, match="not found"):
            render_iterations(
                clip,
                ["fullspeed", "unknown_profile"],
                config,
                Path("/usr/bin/ffmpeg"),
                output,
            )

        # Renderer should never be called
        mock_instance.render.assert_not_called()


# ---------------------------------------------------------------------------
# Short-form without short_config falls back to full-frame
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Event metadata overlay enrichment
# ---------------------------------------------------------------------------


def test_event_metadata_enriches_context(tmp_path: Path) -> None:
    """When event_metadata is provided, overlay variables are added to context."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    captured_plans: list[RenderPlan] = []

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        captured_plans.append(plan)  # type: ignore[arg-type]
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch("reeln.core.ffmpeg.probe_duration", return_value=8.0),
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        ctx = TemplateContext(variables={"home_team": "Roseville", "player": "#17 Smith"})
        result, _messages = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            context=ctx,
            event_metadata={"assists": ["#22 Jones"]},
        )

    assert result.output == output


def test_event_metadata_none_no_enrichment(tmp_path: Path) -> None:
    """When event_metadata is None, no overlay enrichment happens."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        ctx = TemplateContext(variables={"home_team": "Roseville"})
        result, _messages = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            context=ctx,
            event_metadata=None,
        )

    assert result.output == output


def test_event_metadata_probe_returns_none(tmp_path: Path) -> None:
    """When probe_duration returns None, default duration (10.0) is used."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch("reeln.core.ffmpeg.probe_duration", return_value=None),
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        ctx = TemplateContext(variables={"home_team": "Roseville"})
        result, _messages = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            context=ctx,
            event_metadata={"assists": []},
        )

    assert result.output == output


# ---------------------------------------------------------------------------
# Short-form without short_config falls back to full-frame
# ---------------------------------------------------------------------------


def test_short_form_without_short_config_uses_full_frame(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.plan_full_frame") as mock_plan,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_plan.return_value = RenderPlan(inputs=[clip], output=iter0)
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        result, _ = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,  # short but no short_config
        )

    # Should use plan_full_frame, not plan_short
    mock_plan.assert_called_once()
    assert result.output == output


# ---------------------------------------------------------------------------
# zoom_path and source_fps forwarded to plan_short
# ---------------------------------------------------------------------------


def test_zoom_path_forwarded_to_plan_short(tmp_path: Path) -> None:
    """zoom_path and source_fps are passed through to plan_short()."""
    from reeln.models.zoom import ZoomPath, ZoomPoint

    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    short_cfg = ShortConfig(
        input=clip,
        output=output,
        width=1080,
        height=1920,
        smart=True,
    )

    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.plan_short") as mock_plan,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_plan.return_value = RenderPlan(inputs=[clip], output=iter0)
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        result, _ = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,
            short_config=short_cfg,
            zoom_path=zoom,
            source_fps=59.94,
        )

    mock_plan.assert_called_once()
    call_kwargs = mock_plan.call_args
    assert call_kwargs.kwargs.get("zoom_path") is zoom
    assert call_kwargs.kwargs.get("source_fps") == 59.94
    assert result.output == output


def test_zoom_path_none_by_default(tmp_path: Path) -> None:
    """When zoom_path is not provided, plan_short gets None."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    short_cfg = ShortConfig(
        input=clip,
        output=output,
        width=1080,
        height=1920,
    )

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.plan_short") as mock_plan,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_plan.return_value = RenderPlan(inputs=[clip], output=iter0)
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        result, _ = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,
            short_config=short_cfg,
        )

    mock_plan.assert_called_once()
    call_kwargs = mock_plan.call_args
    assert call_kwargs.kwargs.get("zoom_path") is None
    assert call_kwargs.kwargs.get("source_fps") == 30.0
    assert result.output == output


# ---------------------------------------------------------------------------
# speed_segments + smart zoom path remapping
# ---------------------------------------------------------------------------


def test_speed_segments_profile_remaps_zoom_path(tmp_path: Path) -> None:
    """Profile with speed_segments remaps zoom path timestamps for smart tracking."""
    from reeln.models.profile import SpeedSegment
    from reeln.models.zoom import ZoomPath, ZoomPoint

    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"

    slowmo_profile = RenderProfile(
        name="slowmo",
        speed_segments=(
            SpeedSegment(speed=1.0, until=5.0),
            SpeedSegment(speed=0.5, until=8.0),
            SpeedSegment(speed=1.0, until=None),
        ),
    )
    config = _make_config(slowmo=slowmo_profile)

    short_cfg = ShortConfig(
        input=clip,
        output=output,
        width=1080,
        height=1920,
        smart=True,
    )

    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.plan_short") as mock_plan,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_plan.return_value = RenderPlan(inputs=[clip], output=iter0)
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        _result, _messages = render_iterations(
            clip,
            ["slowmo"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,
            short_config=short_cfg,
            zoom_path=zoom,
            source_fps=60.0,
        )

    # smart should be preserved, zoom_path should be remapped (not original)
    mock_plan.assert_called_once()
    call_args = mock_plan.call_args
    modified_cfg = call_args[0][0]
    assert modified_cfg.smart is True
    remapped_zoom = call_args.kwargs.get("zoom_path")
    assert remapped_zoom is not None
    assert remapped_zoom is not zoom  # should be a new remapped object
    # Duration should be stretched: 5/1 + 3/0.5 + 2/1 = 13.0
    assert remapped_zoom.duration == 13.0
    assert _result.output == output


def test_speed_segments_overlay_duration_adjusted(tmp_path: Path) -> None:
    """Overlay duration accounts for speed_segments time stretch."""
    from reeln.models.profile import SpeedSegment

    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"

    slowmo_profile = RenderProfile(
        name="slowmo",
        subtitle_template="builtin:goal_overlay",
        speed_segments=(
            SpeedSegment(speed=1.0, until=5.0),
            SpeedSegment(speed=0.5, until=8.0),
            SpeedSegment(speed=1.0, until=None),
        ),
    )
    config = _make_config(slowmo=slowmo_profile)

    short_cfg = ShortConfig(
        input=clip,
        output=output,
        width=1080,
        height=1920,
    )

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.plan_short") as mock_plan,
        patch(f"{_MOD}.run_ffmpeg"),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
        patch(f"{_MOD}.resolve_subtitle_for_profile") as mock_sub,
        patch("reeln.core.overlay.build_overlay_context") as mock_overlay,
    ):
        mock_overlay.return_value = TemplateContext()
        mock_sub.return_value = None
        mock_plan.return_value = RenderPlan(inputs=[clip], output=iter0)
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        render_iterations(
            clip,
            ["slowmo"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,
            short_config=short_cfg,
            event_metadata={"assists": "A, B"},
        )

    # speed_segments: 5s@1x + 3s@0.5x + 2s@1x = 5 + 6 + 2 = 13s
    mock_overlay.assert_called_once()
    call_kwargs = mock_overlay.call_args
    assert call_kwargs.kwargs["duration"] == pytest.approx(13.0)


def test_mixed_profiles_smart_preserved_for_non_speed_segments(tmp_path: Path) -> None:
    """Smart is preserved for profiles without speed_segments in multi-iteration."""
    from reeln.models.profile import SpeedSegment
    from reeln.models.zoom import ZoomPath, ZoomPoint

    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"

    plain_profile = RenderProfile(name="fullspeed", speed=1.0)
    slowmo_profile = RenderProfile(
        name="slowmo",
        speed_segments=(
            SpeedSegment(speed=1.0, until=5.0),
            SpeedSegment(speed=0.5, until=8.0),
            SpeedSegment(speed=1.0, until=None),
        ),
    )
    config = _make_config(fullspeed=plain_profile, slowmo=slowmo_profile)

    short_cfg = ShortConfig(
        input=clip,
        output=output,
        width=1080,
        height=1920,
        smart=True,
    )

    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    call_count = [0]

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        temp = _iteration_temp(output, call_count[0])
        temp.write_bytes(b"rendered")
        call_count[0] += 1
        return _mock_render_result(temp)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.plan_short") as mock_plan,
        patch(f"{_MOD}.write_concat_file") as mock_concat_file,
        patch(f"{_MOD}.build_concat_command", return_value=["ffmpeg"]),
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_plan.return_value = RenderPlan(inputs=[clip], output=output)
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        concat_tmp = tmp_path / "concat.txt"
        concat_tmp.write_text("file list")
        mock_concat_file.return_value = concat_tmp

        _result, _ = render_iterations(
            clip,
            ["fullspeed", "slowmo"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,
            short_config=short_cfg,
            zoom_path=zoom,
            source_fps=60.0,
        )

    assert mock_plan.call_count == 2
    # First call (fullspeed): smart preserved, zoom_path passed unchanged
    first_cfg = mock_plan.call_args_list[0][0][0]
    assert first_cfg.smart is True
    assert mock_plan.call_args_list[0].kwargs.get("zoom_path") is zoom
    # Second call (slowmo with speed_segments): smart preserved, zoom remapped
    second_cfg = mock_plan.call_args_list[1][0][0]
    assert second_cfg.smart is True
    remapped_zoom = mock_plan.call_args_list[1].kwargs.get("zoom_path")
    assert remapped_zoom is not None
    assert remapped_zoom is not zoom  # remapped, not original


def test_multiple_profiles_xfade_fallback_to_concat(tmp_path: Path) -> None:
    """When xfade fails, falls back to concat demuxer."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    call_count = [0]

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        temp = _iteration_temp(output, call_count[0])
        temp.write_bytes(b"rendered")
        call_count[0] += 1
        return _mock_render_result(temp)

    run_count = [0]

    def fake_run_ffmpeg(cmd: list[str], **kwargs: object) -> None:
        run_count[0] += 1
        if run_count[0] == 1:
            raise RuntimeError("xfade not supported")

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.probe_duration", return_value=10.0),
        patch(f"{_MOD}.build_xfade_command", return_value=["ffmpeg-xfade"]),
        patch(f"{_MOD}.write_concat_file") as mock_concat_file,
        patch(f"{_MOD}.build_concat_command", return_value=["ffmpeg-concat"]),
        patch(f"{_MOD}.run_ffmpeg", side_effect=fake_run_ffmpeg),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        concat_tmp = tmp_path / "concat.txt"
        concat_tmp.write_text("file list")
        mock_concat_file.return_value = concat_tmp

        result, messages = render_iterations(
            clip,
            ["fullspeed", "slowmo"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
        )

    assert result.concat_copy is False
    assert any("Concatenated 2 iterations" in m for m in messages)
    # run_ffmpeg called twice: xfade (fails) then concat (succeeds)
    assert run_count[0] == 2
    mock_concat_file.assert_called_once()


@patch(f"{_MOD}.run_ffmpeg")
@patch(f"{_MOD}.FFmpegRenderer")
@patch(f"{_MOD}.plan_short")
def test_render_iterations_branding_first_only(
    mock_plan: MagicMock,
    MockRenderer: MagicMock,
    mock_run: MagicMock,
    tmp_path: Path,
) -> None:
    """Branding should only appear on the first iteration."""
    config = _make_config()
    config = AppConfig(
        video=config.video,
        render_profiles={
            "a": RenderProfile(name="a", speed=1.0),
            "b": RenderProfile(name="b", speed=1.0),
        },
        iterations=config.iterations,
    )
    clip = tmp_path / "clip.mkv"
    clip.touch()
    output = tmp_path / "output.mp4"

    branding_file = tmp_path / "brand.ass"
    branding_file.write_text("[Script Info]\n")
    short_cfg = ShortConfig(
        input=clip,
        output=output,
        branding=branding_file,
    )

    mock_plan.return_value = RenderPlan(inputs=[clip], output=output, filter_complex="scale=1080:-2")
    mock_instance = MagicMock()
    mock_instance.render.side_effect = lambda plan, **kw: (
        plan.output.touch(),
        _mock_render_result(plan.output),
    )[1]
    MockRenderer.return_value = mock_instance

    render_iterations(
        clip,
        ["a", "b"],
        config,
        Path("/usr/bin/ffmpeg"),
        output,
        is_short=True,
        short_config=short_cfg,
    )

    assert mock_plan.call_count == 2
    first_cfg = mock_plan.call_args_list[0][0][0]
    assert first_cfg.branding == branding_file
    second_cfg = mock_plan.call_args_list[1][0][0]
    assert second_cfg.branding is None


# ---------------------------------------------------------------------------
# game_info in POST_RENDER hook data
# ---------------------------------------------------------------------------


def test_game_info_included_in_post_render_hook(
    tmp_path: Path,
    _mock_hook_registry: MagicMock,
) -> None:
    """When game_info is provided, it appears in POST_RENDER hook data."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    sentinel = object()

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            game_info=sentinel,
        )

    # Verify POST_RENDER was emitted with game_info in data
    _mock_hook_registry.emit.assert_called_once()
    call_args = _mock_hook_registry.emit.call_args
    ctx = call_args[0][1]
    assert ctx.data["game_info"] is sentinel


def test_game_info_omitted_when_none(
    tmp_path: Path,
    _mock_hook_registry: MagicMock,
) -> None:
    """When game_info is None, it is not included in POST_RENDER data."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
        )

    _mock_hook_registry.emit.assert_called_once()
    call_args = _mock_hook_registry.emit.call_args
    ctx = call_args[0][1]
    assert "game_info" not in ctx.data


def test_event_context_included_in_post_render_hook(
    tmp_path: Path,
    _mock_hook_registry: MagicMock,
) -> None:
    """When game_event/player/assists are provided, they appear in POST_RENDER data."""
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    event_sentinel = object()

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.run_ffmpeg"),
    ):
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            game_event=event_sentinel,
            player="#48 Remitz",
            assists="#7 Smith",
        )

    _mock_hook_registry.emit.assert_called_once()
    call_args = _mock_hook_registry.emit.call_args
    ctx = call_args[0][1]
    assert ctx.data["game_event"] is event_sentinel
    assert ctx.data["player"] == "#48 Remitz"
    assert ctx.data["assists"] == "#7 Smith"


# ---------------------------------------------------------------------------
# queue flag — render_iterations queues instead of emitting POST_RENDER
# ---------------------------------------------------------------------------


def test_queue_flag_emits_on_queue(tmp_path: Path, _mock_hook_registry: MagicMock) -> None:
    """When queue=True, render_iterations emits ON_QUEUE instead of POST_RENDER."""
    from reeln.models.game import GameInfo
    from reeln.plugins.hooks import Hook

    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")
    output = tmp_path / "out.mp4"
    config = _make_config()

    short_cfg = ShortConfig(input=clip, output=output, width=1080, height=1920)
    iter0 = _iteration_temp(output, 0)

    def fake_render(plan: object, **kwargs: object) -> RenderResult:
        iter0.write_bytes(b"rendered")
        return _mock_render_result(iter0)

    gi = GameInfo(date="2026-04-06", home_team="North", away_team="South", sport="hockey")

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.plan_short") as mock_plan,
        patch(f"{_MOD}.run_ffmpeg"),
        patch(f"{_MOD}.probe_duration", return_value=10.0),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.update_queue_index"),
    ):
        mock_plan.return_value = RenderPlan(inputs=[clip], output=iter0)
        mock_instance = MagicMock()
        mock_instance.render.side_effect = fake_render
        MockRenderer.return_value = mock_instance

        result, messages = render_iterations(
            clip,
            ["fullspeed"],
            config,
            Path("/usr/bin/ffmpeg"),
            output,
            is_short=True,
            short_config=short_cfg,
            game_info=gi,
            queue=True,
        )

    assert result.output == output
    assert any("Queued:" in m for m in messages)
    # Should have emitted ON_QUEUE, not POST_RENDER
    emit_calls = _mock_hook_registry.emit.call_args_list
    hooks_emitted = [call[0][0] for call in emit_calls]
    assert Hook.ON_QUEUE in hooks_emitted
    assert Hook.POST_RENDER not in hooks_emitted
