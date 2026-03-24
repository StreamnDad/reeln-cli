"""Plugin discovery, capability detection, and loading."""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Any

from reeln.core.errors import PluginError
from reeln.core.log import get_logger
from reeln.models.config import PluginsConfig
from reeln.models.doctor import DoctorCheck
from reeln.models.plugin import PluginInfo
from reeln.plugins.hooks import Hook
from reeln.plugins.registry import FilteredRegistry, HookRegistry, get_registry

log: logging.Logger = get_logger(__name__)

_ENTRY_POINT_GROUP: str = "reeln.plugins"

# CLI-level override: when True, disables hook enforcement regardless of config.
_cli_no_enforce_hooks: bool = False


def set_enforce_hooks_override(*, disable: bool) -> None:
    """Set a CLI-level override to disable hook enforcement.

    Called by the top-level ``--no-enforce-hooks`` flag so that all
    ``activate_plugins`` calls in the process skip enforcement.
    """
    global _cli_no_enforce_hooks
    _cli_no_enforce_hooks = disable


_CAPABILITY_CHECKS: list[tuple[str, str]] = [
    ("generator", "generate"),
    ("enricher", "enrich"),
    ("uploader", "upload"),
    ("notifier", "notify"),
    ("doctor", "doctor_checks"),
]


def _detect_capabilities(plugin: object) -> list[str]:
    """Duck-type check a plugin instance for known capability methods."""
    caps: list[str] = []
    for cap_name, method_name in _CAPABILITY_CHECKS:
        if callable(getattr(plugin, method_name, None)):
            caps.append(cap_name)
    return caps


def discover_plugins() -> list[PluginInfo]:
    """Scan installed entry points for plugins in the ``reeln.plugins`` group."""
    try:
        eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
    except Exception:
        log.debug("Failed to read entry points", exc_info=True)
        return []

    results: list[PluginInfo] = []
    for ep in eps:
        # Resolve the distribution package name for version lookups
        pkg = ""
        if ep.dist is not None:
            pkg = ep.dist.name
        results.append(
            PluginInfo(
                name=ep.name,
                entry_point=str(ep.value),
                package=pkg,
                capabilities=[],
                enabled=False,
            )
        )
    return results


def load_plugin(name: str, *, config: dict[str, Any] | None = None) -> object:
    """Load a single plugin by entry point name.

    Raises ``PluginError`` if the entry point is not found or loading fails.
    """
    try:
        eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
    except Exception as exc:
        raise PluginError(f"Failed to read entry points: {exc}") from exc

    matches = [ep for ep in eps if ep.name == name]
    if not matches:
        raise PluginError(f"Plugin not found: {name!r}")

    ep = matches[0]
    try:
        plugin_cls = ep.load()
    except Exception as exc:
        raise PluginError(f"Failed to load plugin {name!r}: {exc}") from exc

    try:
        if config is not None:
            return plugin_cls(config)
        return plugin_cls()
    except TypeError:
        # Plugin doesn't accept config — instantiate without args
        if config is not None:
            return plugin_cls()
        raise  # pragma: no cover — already handled above
    except Exception as exc:
        raise PluginError(f"Failed to instantiate plugin {name!r}: {exc}") from exc


def load_enabled_plugins(
    enabled: list[str],
    disabled: list[str],
    settings: dict[str, dict[str, Any]] | None = None,
) -> dict[str, object]:
    """Load all enabled plugins, skipping disabled and handling errors gracefully.

    When *enabled* is empty, all discovered plugins are loaded unless
    explicitly in *disabled*. When *enabled* is non-empty, only those
    named plugins are loaded (minus any in *disabled*).
    """
    discovered = discover_plugins()
    plugin_settings = settings or {}

    # Determine which plugins to load
    if enabled:
        names_to_load = [n for n in enabled if n not in disabled]
    else:
        names_to_load = [p.name for p in discovered if p.name not in disabled]

    loaded: dict[str, object] = {}
    for name in names_to_load:
        try:
            cfg = plugin_settings.get(name)
            plugin = load_plugin(name, config=cfg)
            loaded[name] = plugin
            log.info("Loaded plugin: %s", name)
        except PluginError as exc:
            if "not found" in str(exc).lower():
                log.debug(
                    "Plugin %s is not installed, skipping: %s",
                    name,
                    exc,
                )
            else:
                log.warning(
                    "Failed to load plugin %s, skipping",
                    name,
                    exc_info=True,
                )

    return loaded


def _parse_allowed_hooks(capabilities: list[str]) -> set[Hook] | None:
    """Extract the set of allowed hooks from a registry capabilities list.

    Returns ``None`` when no hook capabilities are declared — which means the
    plugin is not in the registry, and registration is unrestricted.
    """
    hook_values = {h.value for h in Hook}
    allowed: set[Hook] = set()
    for cap in capabilities:
        if cap.startswith("hook:"):
            hook_name = cap.removeprefix("hook:").lower()
            if hook_name in hook_values:
                allowed.add(Hook(hook_name))
    return allowed if allowed else None


def _register_plugin_hooks(
    name: str,
    plugin: object,
    registry: HookRegistry,
    allowed_hooks: set[Hook] | None = None,
) -> None:
    """Register a plugin's hook handlers with the registry.

    When *allowed_hooks* is set, only those hooks may be registered.
    Attempts to register undeclared hooks are logged and skipped.

    If *plugin* has a callable ``register`` attribute, call it with the
    registry (explicit registration).  Otherwise, auto-discover ``on_<hook>``
    methods and register them.  ``register()`` takes precedence — if present,
    auto-discovery is skipped.

    Failures during ``register()`` are logged, never raised.
    """
    # Wrap the registry when there's an allowlist
    effective_registry: HookRegistry = registry
    if allowed_hooks is not None:
        effective_registry = FilteredRegistry(registry, allowed_hooks, name)

    register_fn = getattr(plugin, "register", None)
    if callable(register_fn):
        try:
            register_fn(effective_registry)
        except Exception:
            log.warning(
                "Plugin %s register() failed, skipping",
                name,
                exc_info=True,
            )
        return

    # Auto-discover on_<hook_name> methods
    for hook in Hook:
        handler = getattr(plugin, hook.value, None)
        if handler is None:
            handler = getattr(plugin, f"on_{hook.value}", None)
        if callable(handler):
            effective_registry.register(hook, handler)


def _fetch_registry_capabilities(registry_url: str) -> dict[str, list[str]]:
    """Fetch the plugin registry and return a name → capabilities mapping.

    Uses the cached registry when available. Returns an empty dict on
    any error so that plugin activation is never blocked by a registry
    fetch failure.
    """
    try:
        from reeln.core.plugin_registry import fetch_registry

        entries = fetch_registry(registry_url)
        return {e.name: list(e.capabilities) for e in entries}
    except Exception:
        log.debug("Could not fetch registry for capability enforcement", exc_info=True)
        return {}


def activate_plugins(plugins_config: PluginsConfig) -> dict[str, object]:
    """Load enabled plugins and wire their hook handlers into the registry.

    Fetches the plugin registry (from cache when available) to enforce
    capability restrictions — plugins may only register hooks declared
    in their registry entry.  Undeclared hooks are blocked with a warning.

    Clears the registry first for idempotency (prevents double-registration
    when called multiple times in the same process).

    Returns the dict of loaded plugin instances.
    """
    registry = get_registry()
    registry.clear()

    loaded = load_enabled_plugins(
        plugins_config.enabled,
        plugins_config.disabled,
        settings=plugins_config.settings,
    )

    enforce = plugins_config.enforce_hooks and not _cli_no_enforce_hooks
    if enforce:
        caps = _fetch_registry_capabilities(plugins_config.registry_url)
    else:
        caps = {}
        log.debug("Hook enforcement disabled — plugins may register any hook")

    for name, plugin in loaded.items():
        allowed = _parse_allowed_hooks(caps.get(name, []))
        _register_plugin_hooks(name, plugin, registry, allowed_hooks=allowed)

    return loaded


def collect_doctor_checks(loaded_plugins: dict[str, object]) -> list[DoctorCheck]:
    """Collect ``DoctorCheck`` instances from loaded plugins.

    Calls ``doctor_checks()`` on each plugin that exposes it.  Each call
    should return a list of ``DoctorCheck`` objects.  Failures are logged
    and skipped.
    """
    checks: list[DoctorCheck] = []
    for name, plugin in loaded_plugins.items():
        fn = getattr(plugin, "doctor_checks", None)
        if not callable(fn):
            continue
        try:
            plugin_checks = fn()
            checks.extend(plugin_checks)
        except Exception:
            log.warning(
                "Plugin %s doctor_checks() failed, skipping",
                name,
                exc_info=True,
            )
    return checks
