"""Tests for profile resolution, application, and iteration planning."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from reeln.core.errors import ConfigError, RenderError
from reeln.core.profiles import (
    apply_profile_to_short,
    build_profile_filter_chain,
    plan_full_frame,
    profiles_for_event,
    resolve_profile,
    resolve_subtitle_for_profile,
    validate_iteration_config,
)
from reeln.models.config import AppConfig
from reeln.models.game import GameEvent
from reeln.models.profile import IterationConfig, RenderProfile
from reeln.models.short import CropMode, ShortConfig
from reeln.models.template import TemplateContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_with_profiles(
    profiles: dict[str, RenderProfile] | None = None,
    iterations: IterationConfig | None = None,
) -> AppConfig:
    cfg = AppConfig()
    if profiles is not None:
        cfg.render_profiles = profiles
    if iterations is not None:
        cfg.iterations = iterations
    return cfg


def _base_short(tmp_path: Path) -> ShortConfig:
    return ShortConfig(
        input=tmp_path / "input.mkv",
        output=tmp_path / "output.mp4",
    )


# ---------------------------------------------------------------------------
# resolve_profile
# ---------------------------------------------------------------------------


class TestResolveProfile:
    def test_found(self) -> None:
        profile = RenderProfile(name="slowmo", speed=0.5)
        config = _config_with_profiles({"slowmo": profile})
        assert resolve_profile(config, "slowmo") is profile

    def test_not_found(self) -> None:
        config = _config_with_profiles({"slowmo": RenderProfile(name="slowmo")})
        with pytest.raises(ConfigError, match=r"fullspeed.*not found"):
            resolve_profile(config, "fullspeed")

    def test_not_found_empty(self) -> None:
        config = _config_with_profiles({})
        with pytest.raises(ConfigError, match="none"):
            resolve_profile(config, "anything")


# ---------------------------------------------------------------------------
# validate_iteration_config
# ---------------------------------------------------------------------------


class TestValidateIterationConfig:
    def test_valid(self) -> None:
        config = _config_with_profiles(
            profiles={
                "fullspeed": RenderProfile(name="fullspeed"),
                "slowmo": RenderProfile(name="slowmo"),
            },
            iterations=IterationConfig(mappings={"default": ["fullspeed"], "goal": ["slowmo"]}),
        )
        assert validate_iteration_config(config) == []

    def test_missing_profile(self) -> None:
        config = _config_with_profiles(
            profiles={"fullspeed": RenderProfile(name="fullspeed")},
            iterations=IterationConfig(mappings={"goal": ["fullspeed", "missing_profile"]}),
        )
        warnings = validate_iteration_config(config)
        assert len(warnings) == 1
        assert "missing_profile" in warnings[0]

    def test_empty_iterations(self) -> None:
        config = _config_with_profiles(
            profiles={"fullspeed": RenderProfile(name="fullspeed")},
            iterations=IterationConfig(),
        )
        assert validate_iteration_config(config) == []


# ---------------------------------------------------------------------------
# apply_profile_to_short
# ---------------------------------------------------------------------------


class TestApplyProfileToShort:
    def test_no_overrides(self, tmp_path: Path) -> None:
        base = _base_short(tmp_path)
        profile = RenderProfile(name="empty")
        result = apply_profile_to_short(base, profile)
        assert result == base

    def test_speed_override(self, tmp_path: Path) -> None:
        base = _base_short(tmp_path)
        profile = RenderProfile(name="slowmo", speed=0.5)
        result = apply_profile_to_short(base, profile)
        assert result.speed == 0.5
        assert result.width == base.width  # unchanged

    def test_all_overrides(self, tmp_path: Path) -> None:
        base = _base_short(tmp_path)
        sub = tmp_path / "sub.ass"
        profile = RenderProfile(
            name="full",
            width=720,
            height=1280,
            crop_mode="crop",
            anchor_x=0.3,
            anchor_y=0.7,
            pad_color="white",
            speed=0.5,
            lut="warm.cube",
            codec="libx265",
            preset="slow",
            crf=22,
            audio_codec="opus",
            audio_bitrate="192k",
        )
        result = apply_profile_to_short(base, profile, rendered_subtitle=sub)
        assert result.width == 720
        assert result.height == 1280
        assert result.crop_mode == CropMode.CROP
        assert result.anchor_x == 0.3
        assert result.anchor_y == 0.7
        assert result.pad_color == "white"
        assert result.speed == 0.5
        assert result.lut == Path("warm.cube")
        assert result.subtitle == sub
        assert result.codec == "libx265"
        assert result.preset == "slow"
        assert result.crf == 22
        assert result.audio_codec == "opus"
        assert result.audio_bitrate == "192k"

    def test_subtitle_without_profile_template(self, tmp_path: Path) -> None:
        base = _base_short(tmp_path)
        sub = tmp_path / "rendered.ass"
        profile = RenderProfile(name="nosub")
        result = apply_profile_to_short(base, profile, rendered_subtitle=sub)
        assert result.subtitle == sub

    def test_original_unchanged(self, tmp_path: Path) -> None:
        base = _base_short(tmp_path)
        profile = RenderProfile(name="fast", speed=2.0)
        apply_profile_to_short(base, profile)
        assert base.speed == 1.0  # original unchanged


# ---------------------------------------------------------------------------
# build_profile_filter_chain
# ---------------------------------------------------------------------------


class TestBuildProfileFilterChain:
    def test_no_filters(self) -> None:
        profile = RenderProfile(name="passthrough")
        fc, af = build_profile_filter_chain(profile)
        assert fc is None
        assert af is None

    def test_speed_only(self) -> None:
        profile = RenderProfile(name="slowmo", speed=0.5)
        fc, af = build_profile_filter_chain(profile)
        assert fc is not None
        assert "setpts" in fc
        assert af is not None
        assert "atempo" in af

    def test_speed_1_0_ignored(self) -> None:
        profile = RenderProfile(name="normal", speed=1.0)
        fc, af = build_profile_filter_chain(profile)
        assert fc is None
        assert af is None

    def test_lut_only(self) -> None:
        profile = RenderProfile(name="graded", lut="cinematic.cube")
        fc, af = build_profile_filter_chain(profile)
        assert fc is not None
        assert "lut3d" in fc
        assert "cinematic.cube" in fc
        assert af is None

    def test_subtitle_only(self) -> None:
        sub = Path("/tmp/overlay.ass")
        profile = RenderProfile(name="overlay")
        fc, af = build_profile_filter_chain(profile, rendered_subtitle=sub)
        assert fc is not None
        assert "ass=" in fc
        assert af is None

    def test_all_filters(self) -> None:
        sub = Path("/tmp/overlay.ass")
        profile = RenderProfile(name="full", speed=0.5, lut="warm.cube")
        fc, af = build_profile_filter_chain(profile, rendered_subtitle=sub)
        assert fc is not None
        parts = fc.split(",")
        assert len(parts) == 3  # lut, speed, subtitle
        assert "lut3d" in parts[0]
        assert "setpts" in parts[1]
        assert "ass=" in parts[2]
        assert af is not None

    def test_filter_order_lut_before_speed(self) -> None:
        profile = RenderProfile(name="ordered", speed=0.5, lut="warm.cube")
        fc, _ = build_profile_filter_chain(profile)
        assert fc is not None
        lut_pos = fc.index("lut3d")
        speed_pos = fc.index("setpts")
        assert lut_pos < speed_pos


# ---------------------------------------------------------------------------
# plan_full_frame
# ---------------------------------------------------------------------------


class TestPlanFullFrame:
    def test_passthrough(self, tmp_path: Path) -> None:
        inp = tmp_path / "clip.mkv"
        out = tmp_path / "out.mp4"
        profile = RenderProfile(name="passthrough")
        config = AppConfig()
        plan = plan_full_frame(inp, out, profile, config)
        assert plan.inputs == [inp]
        assert plan.output == out
        assert plan.codec == config.video.codec
        assert plan.filter_complex is None
        assert plan.audio_filter is None

    def test_speed_filter(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="slowmo", speed=0.5)
        config = AppConfig()
        plan = plan_full_frame(tmp_path / "clip.mkv", tmp_path / "out.mp4", profile, config)
        assert plan.filter_complex is not None
        assert "setpts" in plan.filter_complex
        assert plan.audio_filter is not None

    def test_encoding_overrides(self, tmp_path: Path) -> None:
        profile = RenderProfile(
            name="custom",
            codec="libx265",
            preset="slow",
            crf=22,
            audio_codec="opus",
            audio_bitrate="192k",
        )
        config = AppConfig()
        plan = plan_full_frame(tmp_path / "clip.mkv", tmp_path / "out.mp4", profile, config)
        assert plan.codec == "libx265"
        assert plan.preset == "slow"
        assert plan.crf == 22
        assert plan.audio_codec == "opus"
        assert plan.audio_bitrate == "192k"

    def test_inherits_video_config(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="default")
        config = AppConfig()
        config.video.codec = "libx265"
        config.video.preset = "slow"
        config.video.crf = 20
        plan = plan_full_frame(tmp_path / "clip.mkv", tmp_path / "out.mp4", profile, config)
        assert plan.codec == "libx265"
        assert plan.preset == "slow"
        assert plan.crf == 20

    def test_with_subtitle(self, tmp_path: Path) -> None:
        sub = tmp_path / "overlay.ass"
        sub.write_text("subtitle content")
        profile = RenderProfile(name="overlay")
        config = AppConfig()
        plan = plan_full_frame(
            tmp_path / "clip.mkv",
            tmp_path / "out.mp4",
            profile,
            config,
            rendered_subtitle=sub,
        )
        assert plan.filter_complex is not None
        assert "ass=" in plan.filter_complex

    def test_no_width_height_in_plan(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="full", width=1080, height=1920)
        config = AppConfig()
        plan = plan_full_frame(tmp_path / "clip.mkv", tmp_path / "out.mp4", profile, config)
        # Full-frame: no width/height in plan (preserves original)
        assert plan.width is None
        assert plan.height is None

    def test_invalid_speed(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="bad", speed=5.0)
        config = AppConfig()
        with pytest.raises(RenderError, match="Speed must be"):
            plan_full_frame(tmp_path / "clip.mkv", tmp_path / "out.mp4", profile, config)

    def test_invalid_speed_low(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="bad", speed=0.1)
        config = AppConfig()
        with pytest.raises(RenderError, match="Speed must be"):
            plan_full_frame(tmp_path / "clip.mkv", tmp_path / "out.mp4", profile, config)


# ---------------------------------------------------------------------------
# resolve_subtitle_for_profile
# ---------------------------------------------------------------------------


class TestResolveSubtitleForProfile:
    def test_no_template(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="notemplate")
        ctx = TemplateContext()
        result = resolve_subtitle_for_profile(profile, ctx, tmp_path)
        assert result is None

    def test_renders_template(self, tmp_path: Path) -> None:
        template = tmp_path / "overlay.ass"
        template.write_text("Team: {{home_team}}", encoding="utf-8")
        profile = RenderProfile(name="overlay", subtitle_template=str(template))
        ctx = TemplateContext(variables={"home_team": "Roseville"})
        result = resolve_subtitle_for_profile(profile, ctx, tmp_path)
        assert result is not None
        assert result.suffix == ".ass"
        content = result.read_text(encoding="utf-8")
        assert content == "Team: Roseville"
        result.unlink()  # cleanup

    def test_template_not_found(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="missing", subtitle_template=str(tmp_path / "nonexistent.ass"))
        ctx = TemplateContext()
        with pytest.raises(RenderError, match="not found"):
            resolve_subtitle_for_profile(profile, ctx, tmp_path)

    def test_write_error(self, tmp_path: Path) -> None:
        template = tmp_path / "overlay.ass"
        template.write_text("content", encoding="utf-8")
        profile = RenderProfile(name="overlay", subtitle_template=str(template))
        ctx = TemplateContext()
        with (
            patch.object(Path, "write_text", side_effect=OSError("disk full")),
            pytest.raises(RenderError, match="Failed to write"),
        ):
            resolve_subtitle_for_profile(profile, ctx, tmp_path)

    def test_builtin_prefix(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="overlay", subtitle_template="builtin:goal_overlay")
        ctx = TemplateContext(variables={"home_team": "Roseville"})
        result = resolve_subtitle_for_profile(profile, ctx, tmp_path)
        assert result is not None
        assert result.suffix == ".ass"
        content = result.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        result.unlink()  # cleanup

    def test_builtin_prefix_missing(self, tmp_path: Path) -> None:
        profile = RenderProfile(name="overlay", subtitle_template="builtin:nonexistent")
        ctx = TemplateContext()
        with pytest.raises(RenderError, match="Builtin template not found"):
            resolve_subtitle_for_profile(profile, ctx, tmp_path)


# ---------------------------------------------------------------------------
# profiles_for_event
# ---------------------------------------------------------------------------


class TestProfilesForEvent:
    def test_no_iterations(self) -> None:
        config = AppConfig()
        result = profiles_for_event(config, None)
        assert result == []

    def test_event_match(self) -> None:
        config = _config_with_profiles(
            iterations=IterationConfig(mappings={"goal": ["slowmo", "overlay"], "default": ["fullspeed"]})
        )
        event = GameEvent(id="e1", clip="c.mkv", segment_number=1, event_type="goal")
        assert profiles_for_event(config, event) == ["slowmo", "overlay"]

    def test_event_fallback_to_default(self) -> None:
        config = _config_with_profiles(
            iterations=IterationConfig(mappings={"goal": ["slowmo"], "default": ["fullspeed"]})
        )
        event = GameEvent(id="e1", clip="c.mkv", segment_number=1, event_type="penalty")
        assert profiles_for_event(config, event) == ["fullspeed"]

    def test_no_event(self) -> None:
        config = _config_with_profiles(iterations=IterationConfig(mappings={"default": ["fullspeed"]}))
        assert profiles_for_event(config, None) == ["fullspeed"]

    def test_no_event_no_default(self) -> None:
        config = _config_with_profiles(iterations=IterationConfig(mappings={"goal": ["slowmo"]}))
        assert profiles_for_event(config, None) == []
