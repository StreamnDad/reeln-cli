"""Tests for render profile and iteration config models."""

from __future__ import annotations

import pytest

from reeln.models.profile import (
    IterationConfig,
    RenderProfile,
    dict_to_iteration_config,
    dict_to_render_profile,
    iteration_config_to_dict,
    render_profile_to_dict,
)

# ---------------------------------------------------------------------------
# RenderProfile
# ---------------------------------------------------------------------------


def test_render_profile_defaults() -> None:
    profile = RenderProfile(name="test")
    assert profile.name == "test"
    assert profile.width is None
    assert profile.height is None
    assert profile.crop_mode is None
    assert profile.speed is None
    assert profile.lut is None
    assert profile.subtitle_template is None
    assert profile.codec is None
    assert profile.crf is None


def test_render_profile_with_values() -> None:
    profile = RenderProfile(
        name="slowmo",
        speed=0.5,
        crop_mode="crop",
        codec="libx265",
        crf=22,
        lut="warm.cube",
        subtitle_template="goal.ass",
    )
    assert profile.speed == 0.5
    assert profile.crop_mode == "crop"
    assert profile.codec == "libx265"
    assert profile.crf == 22
    assert profile.lut == "warm.cube"
    assert profile.subtitle_template == "goal.ass"


def test_render_profile_all_fields() -> None:
    profile = RenderProfile(
        name="full",
        width=1080,
        height=1920,
        crop_mode="pad",
        anchor_x=0.3,
        anchor_y=0.7,
        pad_color="white",
        speed=2.0,
        lut="cinematic.cube",
        subtitle_template="overlay.ass",
        codec="libx264",
        preset="slow",
        crf=18,
        audio_codec="opus",
        audio_bitrate="192k",
    )
    assert profile.width == 1080
    assert profile.height == 1920
    assert profile.anchor_x == 0.3
    assert profile.anchor_y == 0.7
    assert profile.pad_color == "white"
    assert profile.preset == "slow"
    assert profile.audio_codec == "opus"
    assert profile.audio_bitrate == "192k"


def test_render_profile_is_frozen() -> None:
    profile = RenderProfile(name="test")
    with pytest.raises(AttributeError):
        profile.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IterationConfig
# ---------------------------------------------------------------------------


def test_iteration_config_defaults() -> None:
    config = IterationConfig()
    assert config.mappings == {}


def test_iteration_config_profiles_for_event_match() -> None:
    config = IterationConfig(
        mappings={
            "default": ["fullspeed"],
            "goal": ["fullspeed", "slowmo", "overlay"],
            "save": ["slowmo"],
        }
    )
    assert config.profiles_for_event("goal") == ["fullspeed", "slowmo", "overlay"]
    assert config.profiles_for_event("save") == ["slowmo"]


def test_iteration_config_profiles_for_event_default() -> None:
    config = IterationConfig(
        mappings={
            "default": ["fullspeed"],
            "goal": ["fullspeed", "slowmo"],
        }
    )
    assert config.profiles_for_event("penalty") == ["fullspeed"]
    assert config.profiles_for_event("") == ["fullspeed"]


def test_iteration_config_profiles_for_event_no_default() -> None:
    config = IterationConfig(mappings={"goal": ["slowmo"]})
    assert config.profiles_for_event("penalty") == []
    assert config.profiles_for_event("") == []


def test_iteration_config_profiles_for_event_empty() -> None:
    config = IterationConfig()
    assert config.profiles_for_event("goal") == []


def test_iteration_config_is_frozen() -> None:
    config = IterationConfig()
    with pytest.raises(AttributeError):
        config.mappings = {}  # type: ignore[misc]


def test_iteration_config_returns_copy() -> None:
    config = IterationConfig(mappings={"goal": ["slowmo"]})
    result = config.profiles_for_event("goal")
    result.append("extra")
    # Original should be unmodified
    assert config.profiles_for_event("goal") == ["slowmo"]


# ---------------------------------------------------------------------------
# Serialization: RenderProfile
# ---------------------------------------------------------------------------


def test_render_profile_to_dict_minimal() -> None:
    profile = RenderProfile(name="test")
    d = render_profile_to_dict(profile)
    assert d == {}


def test_render_profile_to_dict_with_values() -> None:
    profile = RenderProfile(name="slowmo", speed=0.5, codec="libx265", crf=22)
    d = render_profile_to_dict(profile)
    assert d == {"speed": 0.5, "codec": "libx265", "crf": 22}


def test_render_profile_to_dict_all_fields() -> None:
    profile = RenderProfile(
        name="full",
        width=1080,
        height=1920,
        crop_mode="pad",
        anchor_x=0.5,
        anchor_y=0.5,
        pad_color="black",
        speed=1.0,
        lut="warm.cube",
        subtitle_template="overlay.ass",
        codec="libx264",
        preset="medium",
        crf=18,
        audio_codec="aac",
        audio_bitrate="128k",
    )
    d = render_profile_to_dict(profile)
    assert len(d) == 14  # all fields except name


def test_dict_to_render_profile_minimal() -> None:
    profile = dict_to_render_profile("test", {})
    assert profile.name == "test"
    assert profile.speed is None
    assert profile.codec is None


def test_dict_to_render_profile_with_values() -> None:
    data = {"speed": 0.5, "codec": "libx265", "crf": 22}
    profile = dict_to_render_profile("slowmo", data)
    assert profile.name == "slowmo"
    assert profile.speed == 0.5
    assert profile.codec == "libx265"
    assert profile.crf == 22
    assert profile.width is None


def test_render_profile_round_trip() -> None:
    original = RenderProfile(
        name="full",
        width=1080,
        height=1920,
        crop_mode="pad",
        anchor_x=0.5,
        anchor_y=0.5,
        pad_color="black",
        speed=0.5,
        lut="warm.cube",
        subtitle_template="overlay.ass",
        codec="libx264",
        preset="slow",
        crf=18,
        audio_codec="opus",
        audio_bitrate="192k",
    )
    d = render_profile_to_dict(original)
    restored = dict_to_render_profile("full", d)
    assert restored == original


# ---------------------------------------------------------------------------
# Serialization: IterationConfig
# ---------------------------------------------------------------------------


def test_iteration_config_to_dict() -> None:
    config = IterationConfig(mappings={"default": ["fullspeed"], "goal": ["slowmo", "overlay"]})
    d = iteration_config_to_dict(config)
    assert d == {"default": ["fullspeed"], "goal": ["slowmo", "overlay"]}


def test_iteration_config_to_dict_empty() -> None:
    config = IterationConfig()
    d = iteration_config_to_dict(config)
    assert d == {}


def test_dict_to_iteration_config() -> None:
    data = {"default": ["fullspeed"], "goal": ["slowmo", "overlay"]}
    config = dict_to_iteration_config(data)
    assert config.mappings == {"default": ["fullspeed"], "goal": ["slowmo", "overlay"]}


def test_dict_to_iteration_config_empty() -> None:
    config = dict_to_iteration_config({})
    assert config.mappings == {}


def test_dict_to_iteration_config_non_list_values_skipped() -> None:
    data = {"goal": ["slowmo"], "invalid": "not_a_list"}
    config = dict_to_iteration_config(data)
    assert config.mappings == {"goal": ["slowmo"]}


def test_iteration_config_round_trip() -> None:
    original = IterationConfig(
        mappings={
            "default": ["fullspeed"],
            "goal": ["fullspeed", "slowmo", "overlay"],
            "save": ["slowmo"],
        }
    )
    d = iteration_config_to_dict(original)
    restored = dict_to_iteration_config(d)
    assert restored == original
