"""Tests for plugin capability protocols."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reeln.models.auth import AuthCheckResult, AuthStatus
from reeln.models.plugin import GeneratorResult
from reeln.plugins.capabilities import Authenticator, Generator, MetadataEnricher, Notifier, Uploader

# ---------------------------------------------------------------------------
# Uploader protocol
# ---------------------------------------------------------------------------


class _StubUploader:
    name: str = "stub"

    def upload(self, path: Path, *, metadata: dict[str, Any] | None = None) -> str:
        return f"https://example.com/{path.name}"


def test_uploader_protocol_satisfied() -> None:
    uploader: Uploader = _StubUploader()
    result = uploader.upload(Path("clip.mp4"))
    assert result == "https://example.com/clip.mp4"


def test_uploader_protocol_with_metadata() -> None:
    uploader: Uploader = _StubUploader()
    result = uploader.upload(Path("clip.mp4"), metadata={"title": "Goal"})
    assert result == "https://example.com/clip.mp4"


def test_uploader_has_name() -> None:
    uploader: Uploader = _StubUploader()
    assert uploader.name == "stub"


# ---------------------------------------------------------------------------
# MetadataEnricher protocol
# ---------------------------------------------------------------------------


class _StubEnricher:
    name: str = "enricher"

    def enrich(self, event_data: dict[str, Any]) -> dict[str, Any]:
        return {**event_data, "enriched": True}


def test_metadata_enricher_protocol_satisfied() -> None:
    enricher: MetadataEnricher = _StubEnricher()
    result = enricher.enrich({"event_type": "goal"})
    assert result == {"event_type": "goal", "enriched": True}


def test_metadata_enricher_has_name() -> None:
    enricher: MetadataEnricher = _StubEnricher()
    assert enricher.name == "enricher"


# ---------------------------------------------------------------------------
# Notifier protocol
# ---------------------------------------------------------------------------


class _StubNotifier:
    name: str = "notifier"

    def __init__(self) -> None:
        self.last_message: str = ""

    def notify(self, message: str, *, metadata: dict[str, Any] | None = None) -> None:
        self.last_message = message


def test_notifier_protocol_satisfied() -> None:
    notifier: Notifier = _StubNotifier()
    notifier.notify("Game started")


def test_notifier_with_metadata() -> None:
    notifier: Notifier = _StubNotifier()
    notifier.notify("Goal scored!", metadata={"player": "#17"})


def test_notifier_has_name() -> None:
    notifier: Notifier = _StubNotifier()
    assert notifier.name == "notifier"


# ---------------------------------------------------------------------------
# Generator protocol
# ---------------------------------------------------------------------------


class _StubGenerator:
    name: str = "generator"

    def generate(self, context: dict[str, Any]) -> GeneratorResult:
        return GeneratorResult(path=Path("/out/image.png"), metadata={"from": "stub"})


def test_generator_protocol_satisfied() -> None:
    gen: Generator = _StubGenerator()
    result = gen.generate({"game_dir": "/tmp/game"})
    assert result.path == Path("/out/image.png")
    assert result.success is True


def test_generator_has_name() -> None:
    gen: Generator = _StubGenerator()
    assert gen.name == "generator"


# ---------------------------------------------------------------------------
# Authenticator protocol
# ---------------------------------------------------------------------------


class _StubAuthenticator:
    name: str = "auth-stub"

    def auth_check(self) -> list[AuthCheckResult]:
        return [
            AuthCheckResult(
                service="TestService",
                status=AuthStatus.OK,
                message="Connected",
                identity="test-user",
            )
        ]

    def auth_refresh(self) -> list[AuthCheckResult]:
        return [
            AuthCheckResult(
                service="TestService",
                status=AuthStatus.OK,
                message="Refreshed",
                identity="test-user",
            )
        ]


def test_authenticator_protocol_satisfied() -> None:
    auth: Authenticator = _StubAuthenticator()
    results = auth.auth_check()
    assert len(results) == 1
    assert results[0].service == "TestService"
    assert results[0].status == AuthStatus.OK


def test_authenticator_refresh() -> None:
    auth: Authenticator = _StubAuthenticator()
    results = auth.auth_refresh()
    assert len(results) == 1
    assert results[0].message == "Refreshed"


def test_authenticator_has_name() -> None:
    auth: Authenticator = _StubAuthenticator()
    assert auth.name == "auth-stub"
