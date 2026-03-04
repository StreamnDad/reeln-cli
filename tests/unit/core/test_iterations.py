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

    def fake_render(plan: object) -> RenderResult:
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

    def fake_render(plan: object) -> RenderResult:
        temp = _iteration_temp(output, call_count[0])
        temp.write_bytes(b"rendered")
        call_count[0] += 1
        return _mock_render_result(temp)

    with (
        patch(f"{_MOD}.FFmpegRenderer") as MockRenderer,
        patch(f"{_MOD}.write_concat_file") as mock_concat_file,
        patch(f"{_MOD}.build_concat_command", return_value=["ffmpeg"]),
        patch(f"{_MOD}.run_ffmpeg") as mock_run,
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

    assert result.concat_copy is True
    assert len(result.iteration_outputs) == 2
    assert result.profile_names == ["fullspeed", "slowmo"]
    assert any("Concatenated 2 iterations" in m for m in messages)
    mock_concat_file.assert_called_once()
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

    def fake_render(plan: object) -> RenderResult:
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

    def fake_render(plan: object) -> RenderResult:
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

    assert result.concat_copy is True
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

    def fake_render(plan: object) -> RenderResult:
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

    def fake_render(plan: object) -> RenderResult:
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

    def fake_render_fail(plan: object) -> RenderResult:
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

    def fake_render(plan: object) -> RenderResult:
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

    def fake_render(plan: object) -> RenderResult:
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

    def fake_render(plan: object) -> RenderResult:
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

    def fake_render(plan: object) -> RenderResult:
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

    def fake_render(plan: object) -> RenderResult:
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
