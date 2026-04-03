"""Tests for plugin discovery, capability detection, and loading."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from reeln.core.errors import PluginError
from reeln.models.config import PluginsConfig
from reeln.models.plugin import GeneratorResult
from reeln.plugins.hooks import Hook, HookContext
from reeln.plugins.loader import (
    _detect_capabilities,
    _fetch_registry_capabilities,
    _parse_allowed_hooks,
    _register_plugin_hooks,
    activate_plugins,
    collect_doctor_checks,
    discover_plugins,
    load_enabled_plugins,
    load_plugin,
    set_enforce_hooks_override,
)
from reeln.plugins.registry import HookRegistry, get_registry, reset_registry

# ---------------------------------------------------------------------------
# Helpers — stub plugins
# ---------------------------------------------------------------------------


class _FullPlugin:
    name = "full"

    def generate(self, context: dict[str, Any]) -> GeneratorResult:
        return GeneratorResult()

    def enrich(self, event_data: dict[str, Any]) -> dict[str, Any]:
        return event_data

    def upload(self, path: Path, *, metadata: dict[str, Any] | None = None) -> str:
        return "https://example.com"

    def notify(self, message: str, *, metadata: dict[str, Any] | None = None) -> None:
        pass


class _UploaderOnly:
    name = "uploader"

    def upload(self, path: Path, *, metadata: dict[str, Any] | None = None) -> str:
        return "url"


class _NoCaps:
    name = "nocaps"


class _ConfigPlugin:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config


class _NoConfigPlugin:
    def __init__(self) -> None:
        pass


def _make_entry_point(name: str, cls: type) -> MagicMock:
    ep = MagicMock()
    ep.name = name
    ep.value = f"test_module:{cls.__name__}"
    ep.load.return_value = cls
    return ep


# ---------------------------------------------------------------------------
# _detect_capabilities
# ---------------------------------------------------------------------------


def test_detect_capabilities_all() -> None:
    caps = _detect_capabilities(_FullPlugin())
    assert set(caps) == {"generator", "enricher", "uploader", "notifier"}


def test_detect_capabilities_partial() -> None:
    caps = _detect_capabilities(_UploaderOnly())
    assert caps == ["uploader"]


def test_detect_capabilities_none() -> None:
    caps = _detect_capabilities(_NoCaps())
    assert caps == []


# ---------------------------------------------------------------------------
# discover_plugins
# ---------------------------------------------------------------------------


def test_discover_empty() -> None:
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[]):
        result = discover_plugins()
    assert result == []


def test_discover_with_entries() -> None:
    ep1 = _make_entry_point("youtube", _UploaderOnly)
    ep2 = _make_entry_point("llm", _NoCaps)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep1, ep2]):
        result = discover_plugins()

    assert len(result) == 2
    assert result[0].name == "youtube"
    assert result[1].name == "llm"
    assert result[0].enabled is False


def test_discover_with_no_dist() -> None:
    """Entry points with dist=None still produce a PluginInfo with empty package."""
    ep = MagicMock()
    ep.name = "nodist"
    ep.value = "test:NoDist"
    ep.dist = None
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]):
        result = discover_plugins()
    assert len(result) == 1
    assert result[0].name == "nodist"
    assert result[0].package == ""


def test_discover_handles_exception() -> None:
    with patch(
        "reeln.plugins.loader.importlib.metadata.entry_points",
        side_effect=Exception("broken"),
    ):
        result = discover_plugins()
    assert result == []


# ---------------------------------------------------------------------------
# load_plugin
# ---------------------------------------------------------------------------


def test_load_plugin_success() -> None:
    ep = _make_entry_point("test", _NoConfigPlugin)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]):
        plugin = load_plugin("test")
    assert isinstance(plugin, _NoConfigPlugin)


def test_load_plugin_with_config() -> None:
    ep = _make_entry_point("test", _ConfigPlugin)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]):
        plugin = load_plugin("test", config={"key": "value"})
    assert isinstance(plugin, _ConfigPlugin)
    assert plugin.config == {"key": "value"}  # type: ignore[union-attr]


def test_load_plugin_config_not_accepted() -> None:
    """Plugin that doesn't accept config args falls back to no-arg init."""
    ep = _make_entry_point("test", _NoConfigPlugin)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]):
        plugin = load_plugin("test", config={"key": "value"})
    assert isinstance(plugin, _NoConfigPlugin)


def test_load_plugin_not_found() -> None:
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[]),
        pytest.raises(PluginError, match="Plugin not found"),
    ):
        load_plugin("nonexistent")


def test_load_plugin_load_failure() -> None:
    ep = MagicMock()
    ep.name = "broken"
    ep.load.side_effect = ImportError("module not found")
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        pytest.raises(PluginError, match="Failed to load"),
    ):
        load_plugin("broken")


def test_load_plugin_instantiation_failure() -> None:
    class _BadPlugin:
        def __init__(self) -> None:
            raise RuntimeError("init failed")

    ep = _make_entry_point("bad", _BadPlugin)
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        pytest.raises(PluginError, match="Failed to instantiate"),
    ):
        load_plugin("bad")


def test_load_plugin_entry_points_failure() -> None:
    with (
        patch(
            "reeln.plugins.loader.importlib.metadata.entry_points",
            side_effect=Exception("broken"),
        ),
        pytest.raises(PluginError, match="Failed to read"),
    ):
        load_plugin("test")


# ---------------------------------------------------------------------------
# load_enabled_plugins
# ---------------------------------------------------------------------------


def test_load_enabled_plugins_empty() -> None:
    with patch("reeln.plugins.loader.discover_plugins", return_value=[]):
        result = load_enabled_plugins([], [])
    assert result == {}


def test_load_enabled_plugins_filter_disabled() -> None:
    ep1 = _make_entry_point("youtube", _NoConfigPlugin)
    ep2 = _make_entry_point("llm", _NoConfigPlugin)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep1, ep2]):
        result = load_enabled_plugins(["youtube", "llm"], ["llm"])
    assert "youtube" in result
    assert "llm" not in result


def test_load_enabled_plugins_filter_by_enabled_list() -> None:
    ep1 = _make_entry_point("youtube", _NoConfigPlugin)
    ep2 = _make_entry_point("llm", _NoConfigPlugin)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep1, ep2]):
        result = load_enabled_plugins(["youtube"], [])
    assert "youtube" in result
    assert "llm" not in result


def test_load_enabled_plugins_all_discovered_when_no_enabled_list() -> None:
    from reeln.models.plugin import PluginInfo

    ep1 = _make_entry_point("youtube", _NoConfigPlugin)
    discovered = [PluginInfo(name="youtube", entry_point="test:Cls")]
    with (
        patch("reeln.plugins.loader.discover_plugins", return_value=discovered),
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep1]),
    ):
        result = load_enabled_plugins([], [])
    assert "youtube" in result


def test_load_enabled_plugins_error_continues() -> None:
    """A plugin that fails to load doesn't prevent others from loading."""
    ep_good = _make_entry_point("good", _NoConfigPlugin)
    ep_bad = MagicMock()
    ep_bad.name = "bad"
    ep_bad.load.side_effect = ImportError("broken")

    with patch(
        "reeln.plugins.loader.importlib.metadata.entry_points",
        return_value=[ep_good, ep_bad],
    ):
        result = load_enabled_plugins(["good", "bad"], [])

    assert "good" in result
    assert "bad" not in result


def test_load_enabled_plugins_not_installed_logs_debug(caplog: pytest.LogCaptureFixture) -> None:
    """Plugins that are not installed (no entry point) log at debug, not warning."""
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[]),
        caplog.at_level(logging.DEBUG, logger="reeln.plugins.loader"),
    ):
        result = load_enabled_plugins(["missing"], [])

    assert "missing" not in result
    # Should appear in debug log, not warning
    assert any("not installed" in r.message and r.levelno == logging.DEBUG for r in caplog.records)


def test_load_enabled_plugins_with_settings() -> None:
    ep = _make_entry_point("test", _ConfigPlugin)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]):
        result = load_enabled_plugins(["test"], [], settings={"test": {"api_key": "test123"}})
    assert "test" in result
    assert result["test"].config == {"api_key": "test123"}  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# _register_plugin_hooks / activate_plugins
# ---------------------------------------------------------------------------


class _ExplicitRegisterPlugin:
    """Plugin that has a register() method for explicit hook registration."""

    def __init__(self) -> None:
        self.registered = False

    def register(self, registry: HookRegistry) -> None:
        self.registered = True
        registry.register(Hook.ON_GAME_INIT, self._on_game_init)

    def _on_game_init(self, context: HookContext) -> None:
        pass  # pragma: no cover

    def on_game_finish(self, context: HookContext) -> None:
        """Should NOT be auto-discovered because register() takes precedence."""


class _AutoDiscoverPlugin:
    """Plugin with on_<hook> methods but no register()."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def on_game_init(self, context: HookContext) -> None:
        self.calls.append("on_game_init")

    def on_pre_render(self, context: HookContext) -> None:
        self.calls.append("on_pre_render")


class _BrokenRegisterPlugin:
    """Plugin whose register() raises an exception."""

    def register(self, registry: HookRegistry) -> None:
        raise RuntimeError("register exploded")


class _NoHooksPlugin:
    """Plugin with no register() and no on_<hook> methods."""

    pass


def test_register_plugin_hooks_explicit() -> None:
    """register() method is called and hooks are wired."""
    registry = HookRegistry()
    plugin = _ExplicitRegisterPlugin()
    _register_plugin_hooks("explicit", plugin, registry)

    assert plugin.registered is True
    assert registry.has_handlers(Hook.ON_GAME_INIT)
    # on_game_finish should NOT be auto-discovered
    assert not registry.has_handlers(Hook.ON_GAME_FINISH)


def test_register_plugin_hooks_auto_discover() -> None:
    """on_<hook> methods are auto-discovered when no register()."""
    registry = HookRegistry()
    plugin = _AutoDiscoverPlugin()
    _register_plugin_hooks("auto", plugin, registry)

    assert registry.has_handlers(Hook.ON_GAME_INIT)
    assert registry.has_handlers(Hook.PRE_RENDER)
    assert not registry.has_handlers(Hook.ON_ERROR)


def test_register_takes_precedence_over_auto_discover() -> None:
    """register() takes precedence — auto-discovery is skipped entirely."""
    registry = HookRegistry()
    plugin = _ExplicitRegisterPlugin()
    _register_plugin_hooks("explicit", plugin, registry)

    # register() wires ON_GAME_INIT but NOT ON_GAME_FINISH
    assert registry.has_handlers(Hook.ON_GAME_INIT)
    assert not registry.has_handlers(Hook.ON_GAME_FINISH)


def test_register_failure_logged_not_raised() -> None:
    """register() failure is logged, not raised — plugin crash doesn't break CLI."""
    registry = HookRegistry()
    plugin = _BrokenRegisterPlugin()
    # Should not raise
    _register_plugin_hooks("broken", plugin, registry)
    # Nothing should be registered
    assert not registry.has_handlers(Hook.ON_GAME_INIT)


def test_no_hooks_plugin_registers_nothing() -> None:
    """Plugin with no hooks registers nothing."""
    registry = HookRegistry()
    plugin = _NoHooksPlugin()
    _register_plugin_hooks("nohooks", plugin, registry)

    for hook in Hook:
        assert not registry.has_handlers(hook)


def test_activate_plugins_returns_loaded_dict() -> None:
    """activate_plugins returns the loaded plugins dict."""
    ep = _make_entry_point("test", _NoConfigPlugin)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]):
        result = activate_plugins(PluginsConfig(enabled=["test"]))

    assert "test" in result
    assert isinstance(result["test"], _NoConfigPlugin)
    reset_registry()


def test_activate_plugins_empty_config() -> None:
    """Empty config returns empty dict."""
    with patch("reeln.plugins.loader.discover_plugins", return_value=[]):
        result = activate_plugins(PluginsConfig())

    assert result == {}
    reset_registry()


# ---------------------------------------------------------------------------
# _parse_allowed_hooks
# ---------------------------------------------------------------------------


def test_parse_allowed_hooks_single() -> None:
    result = _parse_allowed_hooks(["hook:ON_GAME_INIT"])
    assert result == {Hook.ON_GAME_INIT}


def test_parse_allowed_hooks_multiple() -> None:
    result = _parse_allowed_hooks(["hook:ON_GAME_INIT", "hook:ON_GAME_READY"])
    assert result == {Hook.ON_GAME_INIT, Hook.ON_GAME_READY}


def test_parse_allowed_hooks_ignores_non_hook_caps() -> None:
    result = _parse_allowed_hooks(["generator", "uploader"])
    assert result is None


def test_parse_allowed_hooks_ignores_invalid_hook_name() -> None:
    result = _parse_allowed_hooks(["hook:DOES_NOT_EXIST"])
    assert result is None


def test_parse_allowed_hooks_empty_list() -> None:
    result = _parse_allowed_hooks([])
    assert result is None


def test_parse_allowed_hooks_mixed_valid_and_invalid() -> None:
    result = _parse_allowed_hooks(["hook:ON_GAME_INIT", "hook:FAKE", "generator"])
    assert result == {Hook.ON_GAME_INIT}


# ---------------------------------------------------------------------------
# _fetch_registry_capabilities
# ---------------------------------------------------------------------------


def test_fetch_registry_capabilities_success() -> None:
    from reeln.models.plugin import RegistryEntry

    entries = [
        RegistryEntry(name="google", capabilities=["hook:ON_GAME_INIT", "hook:ON_GAME_READY"]),
        RegistryEntry(name="meta", capabilities=["hook:ON_GAME_INIT"]),
    ]
    with patch("reeln.core.plugin_registry.fetch_registry", return_value=entries):
        result = _fetch_registry_capabilities("https://example.com/registry.json")
    assert result == {
        "google": ["hook:ON_GAME_INIT", "hook:ON_GAME_READY"],
        "meta": ["hook:ON_GAME_INIT"],
    }


def test_fetch_registry_capabilities_failure() -> None:
    with patch(
        "reeln.core.plugin_registry.fetch_registry",
        side_effect=Exception("network error"),
    ):
        result = _fetch_registry_capabilities("https://example.com/registry.json")
    assert result == {}


# ---------------------------------------------------------------------------
# _register_plugin_hooks with allowed_hooks
# ---------------------------------------------------------------------------


def test_register_plugin_hooks_with_allowed_hooks_blocks_undeclared() -> None:
    """Auto-discovered hooks not in allowed set are blocked."""
    registry = HookRegistry()
    plugin = _AutoDiscoverPlugin()
    _register_plugin_hooks("auto", plugin, registry, allowed_hooks={Hook.ON_GAME_INIT})

    # ON_GAME_INIT is allowed
    assert registry.has_handlers(Hook.ON_GAME_INIT)
    # PRE_RENDER is NOT allowed — should be blocked
    assert not registry.has_handlers(Hook.PRE_RENDER)


def test_register_plugin_hooks_with_allowed_hooks_explicit_register() -> None:
    """Explicit register() with allowed_hooks wraps registry in FilteredRegistry."""
    registry = HookRegistry()
    plugin = _ExplicitRegisterPlugin()
    _register_plugin_hooks("explicit", plugin, registry, allowed_hooks={Hook.ON_GAME_INIT})

    assert registry.has_handlers(Hook.ON_GAME_INIT)


# ---------------------------------------------------------------------------
# activate_plugins with capabilities
# ---------------------------------------------------------------------------


def test_activate_plugins_enforce_hooks_disabled() -> None:
    """When enforce_hooks=False, all hooks are allowed (no registry fetch)."""
    plugin = _AutoDiscoverPlugin()
    ep = _make_entry_point("auto", type(plugin))

    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        patch("reeln.plugins.loader._fetch_registry_capabilities") as mock_fetch,
    ):
        result = activate_plugins(PluginsConfig(enabled=["auto"], enforce_hooks=False))

    # Registry should NOT have been fetched
    mock_fetch.assert_not_called()
    assert "auto" in result
    reset_registry()


def test_activate_plugins_enforce_hooks_default_true() -> None:
    """enforce_hooks defaults to True — registry is fetched."""
    ep = _make_entry_point("test", _NoConfigPlugin)
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        patch("reeln.plugins.loader._fetch_registry_capabilities", return_value={}) as mock_fetch,
    ):
        activate_plugins(PluginsConfig(enabled=["test"]))

    mock_fetch.assert_called_once()
    reset_registry()


def test_activate_plugins_idempotent() -> None:
    """Double activation doesn't double-register handlers."""
    ep = _make_entry_point("auto", _AutoDiscoverPlugin)
    with patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]):
        activate_plugins(PluginsConfig(enabled=["auto"]))
        activate_plugins(PluginsConfig(enabled=["auto"]))

    registry = get_registry()
    # ON_GAME_INIT should have exactly 1 handler, not 2
    handlers = registry._handlers.get(Hook.ON_GAME_INIT, [])
    assert len(handlers) == 1
    reset_registry()


# ---------------------------------------------------------------------------
# collect_doctor_checks
# ---------------------------------------------------------------------------


def test_collect_doctor_checks_from_plugin() -> None:
    """Collects DoctorCheck instances from plugins that expose doctor_checks()."""
    from reeln.models.doctor import CheckResult, CheckStatus, DoctorCheck

    class MyCheck:
        name = "my_check"

        def run(self) -> list[CheckResult]:
            return [CheckResult(name="my_check", status=CheckStatus.PASS, message="ok")]

    class PluginWithDoctor:
        name = "test-plugin"

        def doctor_checks(self) -> list[DoctorCheck]:
            return [MyCheck()]

    loaded = {"test-plugin": PluginWithDoctor()}
    checks = collect_doctor_checks(loaded)

    assert len(checks) == 1
    results = checks[0].run()
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


def test_collect_doctor_checks_skips_plugins_without() -> None:
    """Plugins without doctor_checks() are silently skipped."""

    class PlainPlugin:
        name = "plain"

    loaded = {"plain": PlainPlugin()}
    checks = collect_doctor_checks(loaded)

    assert checks == []


def test_collect_doctor_checks_handles_failure(caplog: pytest.LogCaptureFixture) -> None:
    """Failures in doctor_checks() are logged and skipped."""

    class BadPlugin:
        name = "bad"

        def doctor_checks(self) -> list[object]:
            raise RuntimeError("boom")

    loaded = {"bad": BadPlugin()}
    with caplog.at_level(logging.WARNING):
        checks = collect_doctor_checks(loaded)

    assert checks == []
    assert "bad" in caplog.text
    assert "doctor_checks()" in caplog.text


def test_collect_doctor_checks_multiple_plugins() -> None:
    """Collects checks from multiple plugins."""
    from reeln.models.doctor import CheckResult, CheckStatus

    class CheckA:
        name = "check_a"

        def run(self) -> list[CheckResult]:
            return [CheckResult(name="check_a", status=CheckStatus.PASS, message="a ok")]

    class CheckB:
        name = "check_b"

        def run(self) -> list[CheckResult]:
            return [CheckResult(name="check_b", status=CheckStatus.WARN, message="b warn")]

    class PluginA:
        name = "plugin-a"

        def doctor_checks(self) -> list[object]:
            return [CheckA()]

    class PluginB:
        name = "plugin-b"

        def doctor_checks(self) -> list[object]:
            return [CheckB()]

    loaded = {"plugin-a": PluginA(), "plugin-b": PluginB()}
    checks = collect_doctor_checks(loaded)

    assert len(checks) == 2


def test_collect_doctor_checks_empty() -> None:
    """Empty loaded plugins returns empty list."""
    assert collect_doctor_checks({}) == []


# ---------------------------------------------------------------------------
# set_enforce_hooks_override (CLI --no-enforce-hooks)
# ---------------------------------------------------------------------------


def test_set_enforce_hooks_override_disables_enforcement() -> None:
    """CLI override disables hook enforcement even when config says True."""
    ep = _make_entry_point("auto", _AutoDiscoverPlugin)

    set_enforce_hooks_override(disable=True)
    try:
        with (
            patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
            patch("reeln.plugins.loader._fetch_registry_capabilities") as mock_fetch,
        ):
            result = activate_plugins(PluginsConfig(enabled=["auto"], enforce_hooks=True))

        # Registry fetch should NOT have been called despite enforce_hooks=True
        mock_fetch.assert_not_called()
        assert "auto" in result
    finally:
        set_enforce_hooks_override(disable=False)
        reset_registry()


def test_set_enforce_hooks_override_reset_restores_enforcement() -> None:
    """Re-enabling enforcement restores the default behavior."""
    ep = _make_entry_point("test", _NoConfigPlugin)

    set_enforce_hooks_override(disable=True)
    set_enforce_hooks_override(disable=False)

    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        patch("reeln.plugins.loader._fetch_registry_capabilities", return_value={}) as mock_fetch,
    ):
        activate_plugins(PluginsConfig(enabled=["test"], enforce_hooks=True))

    mock_fetch.assert_called_once()
    reset_registry()


def test_detect_capabilities_includes_doctor() -> None:
    """Plugins with doctor_checks() are detected as having the doctor capability."""

    class PluginWithDoctor:
        name = "test"

        def doctor_checks(self) -> list[object]:
            return []

    caps = _detect_capabilities(PluginWithDoctor())
    assert "doctor" in caps


def test_detect_capabilities_includes_inputs() -> None:
    """Plugins with input_schema are detected as having the inputs capability."""
    from reeln.models.plugin_input import InputField, PluginInputSchema

    class PluginWithInputs:
        name = "test"
        input_schema = PluginInputSchema(fields=(InputField(id="x", label="X", field_type="str", command="game_init"),))

    caps = _detect_capabilities(PluginWithInputs())
    assert "inputs" in caps


def test_detect_capabilities_no_inputs_without_schema() -> None:
    """input_schema that isn't a PluginInputSchema doesn't count."""

    class PluginBadSchema:
        name = "test"
        input_schema = "not a schema"

    caps = _detect_capabilities(PluginBadSchema())
    assert "inputs" not in caps


def test_activate_plugins_registry_input_fallback() -> None:
    """Plugins without input_schema get inputs from registry fallback."""
    from reeln.models.plugin import RegistryEntry
    from reeln.plugins.inputs import get_input_collector

    entries = [
        RegistryEntry(
            name="test",
            input_contributions={
                "game_init": [{"id": "thumb", "label": "Thumbnail", "type": "file"}]
            },
        ),
    ]

    ep = _make_entry_point("test", _NoConfigPlugin)
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        patch("reeln.core.plugin_registry.fetch_registry", return_value=entries),
    ):
        activate_plugins(PluginsConfig(enabled=["test"]))

    collector = get_input_collector()
    fields = collector.fields_for_command("game_init")
    assert len(fields) == 1
    assert fields[0].id == "thumb"
    assert fields[0].plugin_name == "test"
    reset_registry()


def test_activate_plugins_class_input_wins_over_registry() -> None:
    """Class-level input_schema takes precedence over registry fallback."""
    from reeln.models.plugin import RegistryEntry
    from reeln.models.plugin_input import InputField, PluginInputSchema
    from reeln.plugins.inputs import get_input_collector

    class PluginWithInputs:
        input_schema = PluginInputSchema(
            fields=(InputField(id="thumb", label="From Class", field_type="file", command="game_init"),)
        )

    entries = [
        RegistryEntry(
            name="google",
            input_contributions={
                "game_init": [{"id": "thumb", "label": "From Registry", "type": "file"}]
            },
        ),
    ]

    ep = _make_entry_point("google", type(PluginWithInputs()))
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        patch("reeln.core.plugin_registry.fetch_registry", return_value=entries),
    ):
        activate_plugins(PluginsConfig(enabled=["google"]))

    collector = get_input_collector()
    fields = collector.fields_for_command("game_init")
    assert len(fields) == 1
    assert fields[0].label == "From Class"
    reset_registry()


def test_activate_plugins_registry_input_skips_unloaded() -> None:
    """Registry input_contributions for unloaded plugins are skipped."""
    from reeln.models.plugin import RegistryEntry
    from reeln.plugins.inputs import get_input_collector

    entries = [
        RegistryEntry(
            name="not_loaded",
            input_contributions={
                "game_init": [{"id": "thumb", "label": "T", "type": "file"}]
            },
        ),
    ]

    with (
        patch("reeln.plugins.loader.discover_plugins", return_value=[]),
        patch("reeln.core.plugin_registry.fetch_registry", return_value=entries),
    ):
        activate_plugins(PluginsConfig())

    collector = get_input_collector()
    assert collector.fields_for_command("game_init") == []
    reset_registry()


def test_fetch_registry_input_contributions_failure() -> None:
    """Registry fetch failure returns empty dict."""
    from reeln.plugins.loader import _fetch_registry_input_contributions

    with patch(
        "reeln.core.plugin_registry.fetch_registry",
        side_effect=Exception("network error"),
    ):
        result = _fetch_registry_input_contributions("https://example.com/registry.json")
    assert result == {}


def test_fetch_registry_input_contributions_success() -> None:
    """Fetches and returns input_contributions from registry entries."""
    from reeln.models.plugin import RegistryEntry
    from reeln.plugins.loader import _fetch_registry_input_contributions

    entries = [
        RegistryEntry(
            name="google",
            input_contributions={"game_init": [{"id": "thumb", "type": "file"}]},
        ),
        RegistryEntry(name="plain"),  # no contributions
    ]
    with patch("reeln.core.plugin_registry.fetch_registry", return_value=entries):
        result = _fetch_registry_input_contributions("https://example.com/registry.json")
    assert "google" in result
    assert "plain" not in result


def test_detect_capabilities_inputs_via_method() -> None:
    """Plugins with get_input_schema() method are detected as having inputs capability."""

    class PluginWithMethod:
        name = "test"

        def get_input_schema(self) -> object:
            return None  # pragma: no cover

    caps = _detect_capabilities(PluginWithMethod())
    assert "inputs" in caps


# ---------------------------------------------------------------------------
# activate_plugins registers plugin inputs
# ---------------------------------------------------------------------------


def test_activate_plugins_registers_input_schema() -> None:
    """activate_plugins() populates the InputCollector with plugin input_schema."""
    from reeln.models.plugin_input import InputField, PluginInputSchema
    from reeln.plugins.inputs import get_input_collector

    class PluginWithInputs:
        input_schema = PluginInputSchema(
            fields=(InputField(id="thumb", label="Thumbnail", field_type="file", command="game_init"),)
        )

    ep = _make_entry_point("google", type(PluginWithInputs()))
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        patch("reeln.plugins.loader._fetch_registry_input_contributions", return_value={}),
    ):
        activate_plugins(PluginsConfig(enabled=["google"]))

    collector = get_input_collector()
    fields = collector.fields_for_command("game_init")
    assert len(fields) == 1
    assert fields[0].id == "thumb"
    assert fields[0].plugin_name == "google"
    reset_registry()


def test_activate_plugins_clears_input_collector_on_reactivation() -> None:
    """Double activation doesn't accumulate inputs."""
    from reeln.models.plugin_input import InputField, PluginInputSchema
    from reeln.plugins.inputs import get_input_collector

    class PluginWithInputs:
        input_schema = PluginInputSchema(
            fields=(InputField(id="thumb", label="Thumbnail", field_type="file", command="game_init"),)
        )

    ep = _make_entry_point("google", type(PluginWithInputs()))
    with (
        patch("reeln.plugins.loader.importlib.metadata.entry_points", return_value=[ep]),
        patch("reeln.plugins.loader._fetch_registry_input_contributions", return_value={}),
    ):
        activate_plugins(PluginsConfig(enabled=["google"]))
        activate_plugins(PluginsConfig(enabled=["google"]))

    collector = get_input_collector()
    fields = collector.fields_for_command("game_init")
    assert len(fields) == 1  # Not 2
    reset_registry()
