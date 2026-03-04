"""Tests for plugin-related data models."""

from __future__ import annotations

from pathlib import Path

import pytest

from reeln.models.plugin import (
    GeneratorResult,
    OrchestrationConfig,
    PluginInfo,
    PluginStatus,
    RegistryEntry,
    dict_to_registry_entry,
    registry_entry_to_dict,
)

# ---------------------------------------------------------------------------
# GeneratorResult
# ---------------------------------------------------------------------------


def test_generator_result_defaults() -> None:
    r = GeneratorResult()
    assert r.path is None
    assert r.metadata == {}
    assert r.success is True
    assert r.error_message == ""


def test_generator_result_custom() -> None:
    r = GeneratorResult(
        path=Path("/out/image.png"),
        metadata={"width": 1920},
        success=True,
    )
    assert r.path == Path("/out/image.png")
    assert r.metadata == {"width": 1920}


def test_generator_result_failure() -> None:
    r = GeneratorResult(success=False, error_message="API timeout")
    assert r.success is False
    assert r.error_message == "API timeout"


def test_generator_result_frozen() -> None:
    r = GeneratorResult()
    with pytest.raises(AttributeError):
        r.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PluginInfo
# ---------------------------------------------------------------------------


def test_plugin_info_defaults() -> None:
    info = PluginInfo()
    assert info.name == ""
    assert info.entry_point == ""
    assert info.capabilities == []
    assert info.enabled is False


def test_plugin_info_custom() -> None:
    info = PluginInfo(
        name="youtube",
        entry_point="reeln_youtube.plugin:YouTubePlugin",
        capabilities=["uploader", "notifier"],
        enabled=True,
    )
    assert info.name == "youtube"
    assert info.entry_point == "reeln_youtube.plugin:YouTubePlugin"
    assert info.capabilities == ["uploader", "notifier"]
    assert info.enabled is True


def test_plugin_info_frozen() -> None:
    info = PluginInfo(name="test")
    with pytest.raises(AttributeError):
        info.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# OrchestrationConfig
# ---------------------------------------------------------------------------


def test_orchestration_config_defaults() -> None:
    cfg = OrchestrationConfig()
    assert cfg.upload_bitrate_kbps == 0
    assert cfg.sequential is True


def test_orchestration_config_custom() -> None:
    cfg = OrchestrationConfig(upload_bitrate_kbps=5000, sequential=False)
    assert cfg.upload_bitrate_kbps == 5000
    assert cfg.sequential is False


def test_orchestration_config_mutable() -> None:
    cfg = OrchestrationConfig()
    cfg.upload_bitrate_kbps = 10000
    assert cfg.upload_bitrate_kbps == 10000


# ---------------------------------------------------------------------------
# RegistryEntry
# ---------------------------------------------------------------------------


def test_registry_entry_defaults() -> None:
    entry = RegistryEntry()
    assert entry.name == ""
    assert entry.package == ""
    assert entry.description == ""
    assert entry.capabilities == []
    assert entry.homepage == ""
    assert entry.min_reeln_version == ""
    assert entry.author == ""
    assert entry.license == ""


def test_registry_entry_custom() -> None:
    entry = RegistryEntry(
        name="youtube",
        package="reeln-youtube",
        description="YouTube uploader",
        capabilities=["uploader", "notifier"],
        homepage="https://github.com/example/reeln-youtube",
        min_reeln_version="0.1.0",
        author="StreamnDad",
        license="AGPL-3.0",
    )
    assert entry.name == "youtube"
    assert entry.package == "reeln-youtube"
    assert entry.description == "YouTube uploader"
    assert entry.capabilities == ["uploader", "notifier"]
    assert entry.homepage == "https://github.com/example/reeln-youtube"
    assert entry.min_reeln_version == "0.1.0"
    assert entry.author == "StreamnDad"
    assert entry.license == "AGPL-3.0"


def test_registry_entry_frozen() -> None:
    entry = RegistryEntry(name="test")
    with pytest.raises(AttributeError):
        entry.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PluginStatus
# ---------------------------------------------------------------------------


def test_plugin_status_defaults() -> None:
    status = PluginStatus()
    assert status.name == ""
    assert status.installed is False
    assert status.installed_version == ""
    assert status.available_version == ""
    assert status.package == ""
    assert status.description == ""
    assert status.capabilities == []
    assert status.enabled is False
    assert status.update_available is False
    assert status.homepage == ""


def test_plugin_status_custom() -> None:
    status = PluginStatus(
        name="youtube",
        installed=True,
        installed_version="1.2.0",
        available_version="1.3.0",
        package="reeln-youtube",
        description="YouTube uploader",
        capabilities=["uploader"],
        enabled=True,
        update_available=True,
        homepage="https://example.com",
    )
    assert status.name == "youtube"
    assert status.installed is True
    assert status.installed_version == "1.2.0"
    assert status.available_version == "1.3.0"
    assert status.update_available is True


def test_plugin_status_frozen() -> None:
    status = PluginStatus(name="test")
    with pytest.raises(AttributeError):
        status.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# dict_to_registry_entry
# ---------------------------------------------------------------------------


def test_dict_to_registry_entry_full() -> None:
    data: dict[str, object] = {
        "name": "youtube",
        "package": "reeln-youtube",
        "description": "YouTube uploader",
        "capabilities": ["uploader"],
        "homepage": "https://example.com",
        "min_reeln_version": "0.1.0",
        "author": "StreamnDad",
        "license": "AGPL-3.0",
    }
    entry = dict_to_registry_entry(data)
    assert entry.name == "youtube"
    assert entry.package == "reeln-youtube"
    assert entry.capabilities == ["uploader"]
    assert entry.author == "StreamnDad"
    assert entry.license == "AGPL-3.0"


def test_dict_to_registry_entry_missing_fields() -> None:
    entry = dict_to_registry_entry({"name": "minimal"})
    assert entry.name == "minimal"
    assert entry.package == ""
    assert entry.description == ""
    assert entry.capabilities == []


def test_dict_to_registry_entry_extra_fields_ignored() -> None:
    data: dict[str, object] = {
        "name": "test",
        "unknown_field": "ignored",
        "another": 42,
    }
    entry = dict_to_registry_entry(data)
    assert entry.name == "test"


def test_dict_to_registry_entry_empty() -> None:
    entry = dict_to_registry_entry({})
    assert entry.name == ""
    assert entry.package == ""


# ---------------------------------------------------------------------------
# registry_entry_to_dict
# ---------------------------------------------------------------------------


def test_registry_entry_to_dict_roundtrip() -> None:
    entry = RegistryEntry(
        name="youtube",
        package="reeln-youtube",
        description="YouTube uploader",
        capabilities=["uploader", "notifier"],
        homepage="https://example.com",
        min_reeln_version="0.1.0",
        author="StreamnDad",
        license="AGPL-3.0",
    )
    d = registry_entry_to_dict(entry)
    assert d["name"] == "youtube"
    assert d["package"] == "reeln-youtube"
    assert d["capabilities"] == ["uploader", "notifier"]
    assert d["author"] == "StreamnDad"
    assert d["license"] == "AGPL-3.0"

    # Round-trip
    restored = dict_to_registry_entry(d)
    assert restored == entry


def test_registry_entry_to_dict_defaults() -> None:
    entry = RegistryEntry()
    d = registry_entry_to_dict(entry)
    assert d["name"] == ""
    assert d["capabilities"] == []
    assert d["author"] == ""
    assert d["license"] == ""
