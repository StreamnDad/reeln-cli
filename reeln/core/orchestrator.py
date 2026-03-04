"""Central plugin orchestrator — sequential capability pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reeln.core.errors import emit_on_error
from reeln.core.log import get_logger
from reeln.core.throttle import upload_lock
from reeln.models.plugin import GeneratorResult, OrchestrationConfig

log: logging.Logger = get_logger(__name__)


@dataclass
class OrchestrationResult:
    """Mutable result collecting outcomes from the orchestration pipeline."""

    generated: list[GeneratorResult] = field(default_factory=list)
    enrichments: list[dict[str, Any]] = field(default_factory=list)
    upload_urls: list[str] = field(default_factory=list)
    notifications_sent: int = 0
    errors: list[str] = field(default_factory=list)


class Orchestrator:
    """Run plugins through a sequential capability pipeline.

    Pipeline order: Generator → MetadataEnricher → Uploader → Notifier.
    Enriched metadata flows to uploaders (LLM → YouTube/Meta/X).
    All steps are exception-safe — failures are logged and collected.
    """

    def __init__(
        self,
        plugins: dict[str, object],
        config: OrchestrationConfig | None = None,
    ) -> None:
        self._config = config or OrchestrationConfig()
        self._generators: list[object] = []
        self._enrichers: list[object] = []
        self._uploaders: list[object] = []
        self._notifiers: list[object] = []
        self._classify(plugins)

    def _classify(self, plugins: dict[str, object]) -> None:
        """Sort plugins into capability buckets by duck-typing."""
        for _name, plugin in plugins.items():
            if callable(getattr(plugin, "generate", None)):
                self._generators.append(plugin)
            if callable(getattr(plugin, "enrich", None)):
                self._enrichers.append(plugin)
            if callable(getattr(plugin, "upload", None)):
                self._uploaders.append(plugin)
            if callable(getattr(plugin, "notify", None)):
                self._notifiers.append(plugin)

    def run(
        self,
        *,
        context: dict[str, Any] | None = None,
        upload_path: Path | None = None,
        metadata: dict[str, Any] | None = None,
        message: str = "",
    ) -> OrchestrationResult:
        """Execute the full orchestration pipeline.

        1. **Generators** — produce assets (images, bumpers)
        2. **Enrichers** — enrich metadata (LLM titles, descriptions)
        3. **Uploaders** — upload files (with upload_lock serialization)
        4. **Notifiers** — send notifications
        """
        result = OrchestrationResult()
        ctx = context or {}
        meta = dict(metadata) if metadata else {}

        # 1. Generators
        for gen in self._generators:
            try:
                gen_result = gen.generate(ctx)  # type: ignore[attr-defined]
                result.generated.append(gen_result)
            except Exception as exc:
                error_msg = f"Generator {_plugin_name(gen)} failed: {exc}"
                result.errors.append(error_msg)
                log.warning(error_msg)
                emit_on_error(exc, context={"operation": "generate", "plugin": _plugin_name(gen)})

        # 2. Enrichers
        for enricher in self._enrichers:
            try:
                enriched = enricher.enrich(meta)  # type: ignore[attr-defined]
                result.enrichments.append(enriched)
                meta.update(enriched)
            except Exception as exc:
                error_msg = f"Enricher {_plugin_name(enricher)} failed: {exc}"
                result.errors.append(error_msg)
                log.warning(error_msg)
                emit_on_error(exc, context={"operation": "enrich", "plugin": _plugin_name(enricher)})

        # 3. Uploaders (with lock for sequential uploads)
        if upload_path is not None:
            with upload_lock():
                for uploader in self._uploaders:
                    try:
                        url = uploader.upload(upload_path, metadata=meta)  # type: ignore[attr-defined]
                        result.upload_urls.append(url)
                    except Exception as exc:
                        error_msg = f"Uploader {_plugin_name(uploader)} failed: {exc}"
                        result.errors.append(error_msg)
                        log.warning(error_msg)
                        emit_on_error(exc, context={"operation": "upload", "plugin": _plugin_name(uploader)})

        # 4. Notifiers
        if message:
            for notifier in self._notifiers:
                try:
                    notifier.notify(message, metadata=meta)  # type: ignore[attr-defined]
                    result.notifications_sent += 1
                except Exception as exc:
                    error_msg = f"Notifier {_plugin_name(notifier)} failed: {exc}"
                    result.errors.append(error_msg)
                    log.warning(error_msg)
                    emit_on_error(exc, context={"operation": "notify", "plugin": _plugin_name(notifier)})

        return result


def _plugin_name(plugin: object) -> str:
    """Get a display name for a plugin instance."""
    return getattr(plugin, "name", type(plugin).__name__)
