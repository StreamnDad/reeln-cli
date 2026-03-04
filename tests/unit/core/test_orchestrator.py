"""Tests for the central plugin orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reeln.core.orchestrator import OrchestrationResult, Orchestrator, _plugin_name
from reeln.models.plugin import GeneratorResult, OrchestrationConfig
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.registry import get_registry

# ---------------------------------------------------------------------------
# Stub plugins
# ---------------------------------------------------------------------------


class _StubGenerator:
    name = "gen"

    def generate(self, context: dict[str, Any]) -> GeneratorResult:
        return GeneratorResult(path=Path("/out/image.png"), metadata={"from": "gen"})


class _StubEnricher:
    name = "enricher"

    def enrich(self, event_data: dict[str, Any]) -> dict[str, Any]:
        return {**event_data, "enriched": True}


class _StubUploader:
    name = "uploader"

    def upload(self, path: Path, *, metadata: dict[str, Any] | None = None) -> str:
        return f"https://example.com/{path.name}"


class _StubNotifier:
    name = "notifier"

    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str, *, metadata: dict[str, Any] | None = None) -> None:
        self.messages.append(message)


class _FailingGenerator:
    name = "bad_gen"

    def generate(self, context: dict[str, Any]) -> GeneratorResult:
        raise RuntimeError("gen failed")


class _FailingEnricher:
    name = "bad_enricher"

    def enrich(self, event_data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("enrich failed")


class _FailingUploader:
    name = "bad_uploader"

    def upload(self, path: Path, *, metadata: dict[str, Any] | None = None) -> str:
        raise RuntimeError("upload failed")


class _FailingNotifier:
    name = "bad_notifier"

    def notify(self, message: str, *, metadata: dict[str, Any] | None = None) -> None:
        raise RuntimeError("notify failed")


class _MultiCapPlugin:
    name = "multi"

    def enrich(self, event_data: dict[str, Any]) -> dict[str, Any]:
        return {**event_data, "enriched": True}

    def upload(self, path: Path, *, metadata: dict[str, Any] | None = None) -> str:
        return "https://multi.example.com"


# ---------------------------------------------------------------------------
# OrchestrationResult
# ---------------------------------------------------------------------------


def test_orchestration_result_defaults() -> None:
    r = OrchestrationResult()
    assert r.generated == []
    assert r.enrichments == []
    assert r.upload_urls == []
    assert r.notifications_sent == 0
    assert r.errors == []


# ---------------------------------------------------------------------------
# Orchestrator — empty
# ---------------------------------------------------------------------------


def test_orchestrator_empty_plugins() -> None:
    orch = Orchestrator({})
    result = orch.run()
    assert result.generated == []
    assert result.upload_urls == []
    assert result.notifications_sent == 0
    assert result.errors == []


# ---------------------------------------------------------------------------
# Orchestrator — single capability types
# ---------------------------------------------------------------------------


def test_orchestrator_generator_only() -> None:
    orch = Orchestrator({"gen": _StubGenerator()})
    result = orch.run(context={"game": "test"})
    assert len(result.generated) == 1
    assert result.generated[0].path == Path("/out/image.png")


def test_orchestrator_enricher_only() -> None:
    orch = Orchestrator({"enricher": _StubEnricher()})
    result = orch.run(metadata={"title": "Goal"})
    assert len(result.enrichments) == 1
    assert result.enrichments[0]["enriched"] is True
    assert result.enrichments[0]["title"] == "Goal"


def test_orchestrator_uploader_only(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.touch()
    orch = Orchestrator({"uploader": _StubUploader()})
    result = orch.run(upload_path=clip)
    assert len(result.upload_urls) == 1
    assert "clip.mp4" in result.upload_urls[0]


def test_orchestrator_notifier_only() -> None:
    notifier = _StubNotifier()
    orch = Orchestrator({"notifier": notifier})
    result = orch.run(message="Game started!")
    assert result.notifications_sent == 1
    assert notifier.messages == ["Game started!"]


# ---------------------------------------------------------------------------
# Orchestrator — no upload without path, no notify without message
# ---------------------------------------------------------------------------


def test_orchestrator_no_upload_without_path() -> None:
    orch = Orchestrator({"uploader": _StubUploader()})
    result = orch.run()
    assert result.upload_urls == []


def test_orchestrator_no_notify_without_message() -> None:
    notifier = _StubNotifier()
    orch = Orchestrator({"notifier": notifier})
    result = orch.run()
    assert result.notifications_sent == 0
    assert notifier.messages == []


# ---------------------------------------------------------------------------
# Orchestrator — full pipeline
# ---------------------------------------------------------------------------


def test_orchestrator_full_pipeline(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.touch()
    notifier = _StubNotifier()
    plugins: dict[str, object] = {
        "gen": _StubGenerator(),
        "enricher": _StubEnricher(),
        "uploader": _StubUploader(),
        "notifier": notifier,
    }
    orch = Orchestrator(plugins)
    result = orch.run(
        context={"game": "test"},
        upload_path=clip,
        metadata={"title": "Goal"},
        message="Uploaded!",
    )
    assert len(result.generated) == 1
    assert len(result.enrichments) == 1
    assert len(result.upload_urls) == 1
    assert result.notifications_sent == 1
    assert result.errors == []


# ---------------------------------------------------------------------------
# Orchestrator — failure isolation
# ---------------------------------------------------------------------------


def test_orchestrator_generator_failure_continues() -> None:
    orch = Orchestrator(
        {
            "bad": _FailingGenerator(),
            "enricher": _StubEnricher(),
        }
    )
    result = orch.run(metadata={"title": "test"})
    assert len(result.errors) == 1
    assert "gen failed" in result.errors[0]
    assert len(result.enrichments) == 1  # enricher still ran


def test_orchestrator_enricher_failure_continues(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.touch()
    orch = Orchestrator(
        {
            "bad": _FailingEnricher(),
            "uploader": _StubUploader(),
        }
    )
    result = orch.run(upload_path=clip, metadata={"title": "test"})
    assert len(result.errors) == 1
    assert "enrich failed" in result.errors[0]
    assert len(result.upload_urls) == 1  # uploader still ran


def test_orchestrator_uploader_failure_continues(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.touch()
    notifier = _StubNotifier()
    orch = Orchestrator(
        {
            "bad": _FailingUploader(),
            "notifier": notifier,
        }
    )
    result = orch.run(upload_path=clip, message="test")
    assert len(result.errors) == 1
    assert "upload failed" in result.errors[0]
    assert result.notifications_sent == 1  # notifier still ran


def test_orchestrator_notifier_failure_continues() -> None:
    orch = Orchestrator({"bad": _FailingNotifier()})
    result = orch.run(message="test")
    assert len(result.errors) == 1
    assert "notify failed" in result.errors[0]
    assert result.notifications_sent == 0


# ---------------------------------------------------------------------------
# Orchestrator — multi-capability plugin
# ---------------------------------------------------------------------------


def test_orchestrator_multi_capability_classification(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.touch()
    orch = Orchestrator({"multi": _MultiCapPlugin()})
    result = orch.run(upload_path=clip, metadata={"title": "test"})
    assert len(result.enrichments) == 1
    assert len(result.upload_urls) == 1


# ---------------------------------------------------------------------------
# Orchestrator — ON_ERROR emission
# ---------------------------------------------------------------------------


def test_orchestrator_emits_on_error_for_failures() -> None:
    emitted: list[HookContext] = []
    get_registry().register(Hook.ON_ERROR, emitted.append)

    orch = Orchestrator({"bad": _FailingGenerator()})
    orch.run(context={})

    assert len(emitted) == 1
    assert emitted[0].data["operation"] == "generate"


# ---------------------------------------------------------------------------
# _plugin_name helper
# ---------------------------------------------------------------------------


def test_plugin_name_with_name_attr() -> None:
    assert _plugin_name(_StubGenerator()) == "gen"


def test_plugin_name_without_name_attr() -> None:
    class _NoName:
        pass

    assert _plugin_name(_NoName()) == "_NoName"


# ---------------------------------------------------------------------------
# Orchestrator — with config
# ---------------------------------------------------------------------------


def test_orchestrator_with_config() -> None:
    cfg = OrchestrationConfig(upload_bitrate_kbps=5000, sequential=True)
    orch = Orchestrator({}, config=cfg)
    assert orch._config.upload_bitrate_kbps == 5000
