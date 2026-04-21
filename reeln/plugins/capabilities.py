"""Capability protocols for plugin extensions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from reeln.models.auth import AuthCheckResult
from reeln.models.plugin import GeneratorResult


class UploaderSkipped(Exception):
    """Raised by ``Uploader.upload()`` to signal an intentional skip.

    Distinct from a generic failure — the publish orchestration layer
    treats this as ``PublishStatus.SKIPPED`` rather than ``FAILED``.
    The exception message should carry a human-readable reason
    (e.g. "upload_video disabled in plugin config").
    """


class Uploader(Protocol):
    """Protocol for plugins that upload rendered media to external services."""

    name: str

    def upload(  # pragma: no cover
        self, path: Path, *, metadata: dict[str, Any] | None = None
    ) -> str: ...


class MetadataEnricher(Protocol):
    """Protocol for plugins that enrich event metadata."""

    name: str

    def enrich(  # pragma: no cover
        self, event_data: dict[str, Any]
    ) -> dict[str, Any]: ...


class Notifier(Protocol):
    """Protocol for plugins that send notifications."""

    name: str

    def notify(  # pragma: no cover
        self, message: str, *, metadata: dict[str, Any] | None = None
    ) -> None: ...


class Generator(Protocol):
    """Protocol for plugins that generate media assets."""

    name: str

    def generate(  # pragma: no cover
        self, context: dict[str, Any]
    ) -> GeneratorResult: ...


class Authenticator(Protocol):
    """Protocol for plugins that support auth testing and reauthentication."""

    name: str

    def auth_check(  # pragma: no cover
        self,
    ) -> list[AuthCheckResult]: ...

    def auth_refresh(  # pragma: no cover
        self,
    ) -> list[AuthCheckResult]: ...
