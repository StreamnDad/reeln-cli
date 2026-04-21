"""Plugin system — hooks, capabilities, and registry."""

from __future__ import annotations

from reeln.models.auth import AuthCheckResult, AuthStatus, PluginAuthReport
from reeln.models.plugin import GeneratorResult
from reeln.models.plugin_input import InputField, PluginInputSchema
from reeln.plugins.capabilities import (
    Authenticator,
    Generator,
    MetadataEnricher,
    Notifier,
    Uploader,
    UploaderSkipped,
)
from reeln.plugins.hooks import Hook, HookContext, HookHandler
from reeln.plugins.inputs import InputCollector, get_input_collector, reset_input_collector
from reeln.plugins.loader import activate_plugins
from reeln.plugins.registry import HookRegistry, get_registry, reset_registry

__all__ = [
    "AuthCheckResult",
    "AuthStatus",
    "Authenticator",
    "Generator",
    "GeneratorResult",
    "Hook",
    "HookContext",
    "HookHandler",
    "HookRegistry",
    "InputCollector",
    "InputField",
    "MetadataEnricher",
    "Notifier",
    "PluginAuthReport",
    "PluginInputSchema",
    "Uploader",
    "UploaderSkipped",
    "activate_plugins",
    "get_input_collector",
    "get_registry",
    "reset_input_collector",
    "reset_registry",
]
