"""Tests for reeln.plugins public API exports."""

from __future__ import annotations

import reeln.plugins as plugins


def test_exports_hook() -> None:
    assert hasattr(plugins, "Hook")


def test_exports_hook_context() -> None:
    assert hasattr(plugins, "HookContext")


def test_exports_hook_handler() -> None:
    assert hasattr(plugins, "HookHandler")


def test_exports_hook_registry() -> None:
    assert hasattr(plugins, "HookRegistry")


def test_exports_get_registry() -> None:
    assert callable(plugins.get_registry)


def test_exports_reset_registry() -> None:
    assert callable(plugins.reset_registry)


def test_exports_uploader() -> None:
    assert hasattr(plugins, "Uploader")


def test_exports_uploader_skipped() -> None:
    assert hasattr(plugins, "UploaderSkipped")
    assert issubclass(plugins.UploaderSkipped, Exception)


def test_exports_metadata_enricher() -> None:
    assert hasattr(plugins, "MetadataEnricher")


def test_exports_notifier() -> None:
    assert hasattr(plugins, "Notifier")


def test_exports_generator() -> None:
    assert hasattr(plugins, "Generator")


def test_exports_generator_result() -> None:
    assert hasattr(plugins, "GeneratorResult")


def test_all_matches_expected() -> None:
    expected = {
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
    }
    assert set(plugins.__all__) == expected
