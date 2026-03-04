"""Plugin system — hooks, capabilities, and registry."""

from __future__ import annotations

from reeln.models.plugin import GeneratorResult
from reeln.plugins.capabilities import Generator, MetadataEnricher, Notifier, Uploader
from reeln.plugins.hooks import Hook, HookContext, HookHandler
from reeln.plugins.loader import activate_plugins
from reeln.plugins.registry import HookRegistry, get_registry, reset_registry

__all__ = [
    "Generator",
    "GeneratorResult",
    "Hook",
    "HookContext",
    "HookHandler",
    "HookRegistry",
    "MetadataEnricher",
    "Notifier",
    "Uploader",
    "activate_plugins",
    "get_registry",
    "reset_registry",
]
