"""Tests for config data models."""

from __future__ import annotations

from pathlib import Path

from reeln.models.config import AppConfig, PathConfig, PluginsConfig, VideoConfig
from reeln.models.plugin import OrchestrationConfig
from reeln.models.profile import IterationConfig, RenderProfile


def test_video_config_defaults() -> None:
    vc = VideoConfig()
    assert vc.ffmpeg_path == "ffmpeg"
    assert vc.codec == "libx264"
    assert vc.preset == "medium"
    assert vc.crf == 18
    assert vc.audio_codec == "aac"
    assert vc.audio_bitrate == "128k"


def test_video_config_custom() -> None:
    vc = VideoConfig(codec="libx265", crf=22, preset="fast")
    assert vc.codec == "libx265"
    assert vc.crf == 22
    assert vc.preset == "fast"


def test_path_config_defaults() -> None:
    pc = PathConfig()
    assert pc.source_dir is None
    assert pc.source_glob == "Replay_*.mkv"
    assert pc.output_dir is None
    assert pc.temp_dir is None


def test_path_config_with_paths() -> None:
    pc = PathConfig(output_dir=Path("/out"), temp_dir=Path("/tmp/reeln"))
    assert pc.output_dir == Path("/out")
    assert pc.temp_dir == Path("/tmp/reeln")


def test_path_config_with_source_glob() -> None:
    pc = PathConfig(source_dir=Path("/replays"), source_glob="Replay_*.mkv")
    assert pc.source_dir == Path("/replays")
    assert pc.source_glob == "Replay_*.mkv"


def test_app_config_defaults() -> None:
    ac = AppConfig()
    assert ac.config_version == 1
    assert ac.sport == "generic"
    assert isinstance(ac.video, VideoConfig)
    assert isinstance(ac.paths, PathConfig)
    assert ac.render_profiles == {}
    assert ac.iterations.mappings == {}
    assert ac.orchestration.upload_bitrate_kbps == 0
    assert ac.orchestration.sequential is True
    assert ac.plugins.enabled == []
    assert ac.plugins.disabled == []
    assert ac.plugins.settings == {}


def test_app_config_custom() -> None:
    ac = AppConfig(
        config_version=1,
        sport="hockey",
        video=VideoConfig(crf=20),
        paths=PathConfig(output_dir=Path("/out")),
    )
    assert ac.sport == "hockey"
    assert ac.video.crf == 20
    assert ac.paths.output_dir == Path("/out")


def test_plugins_config_defaults() -> None:
    pc = PluginsConfig()
    assert pc.enabled == []
    assert pc.disabled == []
    assert pc.settings == {}
    assert pc.registry_url == ""
    assert pc.enforce_hooks is True


def test_plugins_config_custom() -> None:
    pc = PluginsConfig(
        enabled=["youtube", "meta"],
        disabled=["llm"],
        settings={"youtube": {"api_key": "test"}},
    )
    assert pc.enabled == ["youtube", "meta"]
    assert pc.disabled == ["llm"]
    assert pc.settings["youtube"]["api_key"] == "test"


def test_plugins_config_registry_url() -> None:
    pc = PluginsConfig(registry_url="https://example.com/reg.json")
    assert pc.registry_url == "https://example.com/reg.json"


def test_plugins_config_enforce_hooks_false() -> None:
    pc = PluginsConfig(enforce_hooks=False)
    assert pc.enforce_hooks is False


def test_app_config_with_orchestration() -> None:
    ac = AppConfig(
        orchestration=OrchestrationConfig(upload_bitrate_kbps=5000, sequential=False),
    )
    assert ac.orchestration.upload_bitrate_kbps == 5000
    assert ac.orchestration.sequential is False


def test_app_config_with_plugins() -> None:
    ac = AppConfig(
        plugins=PluginsConfig(enabled=["youtube"]),
    )
    assert ac.plugins.enabled == ["youtube"]


def test_app_config_with_profiles() -> None:
    ac = AppConfig(
        render_profiles={
            "slowmo": RenderProfile(name="slowmo", speed=0.5),
        },
        iterations=IterationConfig(mappings={"default": ["slowmo"]}),
    )
    assert "slowmo" in ac.render_profiles
    assert ac.render_profiles["slowmo"].speed == 0.5
    assert ac.iterations.profiles_for_event("anything") == ["slowmo"]
