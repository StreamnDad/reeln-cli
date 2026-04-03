"""Plugin input collection and conflict resolution.

The :class:`InputCollector` gathers :class:`InputField` declarations from
loaded plugins, resolves conflicts when two plugins declare the same input ID,
and collects values from the user (interactively or via CLI arguments).
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from reeln.core.log import get_logger
from reeln.models.plugin_input import (
    InputField,
    PluginInputSchema,
    coerce_value,
)

log: logging.Logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# InputCollector
# ---------------------------------------------------------------------------


class InputCollector:
    """Gather, validate, and collect plugin-contributed inputs."""

    def __init__(self) -> None:
        self._fields: dict[str, InputField] = {}  # key = "{command}:{id}"
        self._conflicts: list[str] = []

    # -- registration -------------------------------------------------------

    def register_plugin_inputs(self, plugin: object, plugin_name: str) -> None:
        """Extract input schema from *plugin* and register its fields.

        Prefers ``get_input_schema()`` (config-aware, called at runtime) over
        the static ``input_schema`` class attribute.  This lets plugins gate
        inputs on feature flags — e.g. only prompt for ``thumbnail_image``
        when ``create_livestream`` is enabled.

        Plugins that expose neither are silently skipped.
        """
        get_fn = getattr(plugin, "get_input_schema", None)
        if callable(get_fn):
            try:
                schema = get_fn()
            except Exception:
                log.warning(
                    "Plugin %s get_input_schema() failed, skipping",
                    plugin_name,
                    exc_info=True,
                )
                return
        else:
            schema = getattr(plugin, "input_schema", None)
        if not isinstance(schema, PluginInputSchema):
            return

        for field in schema.fields:
            # Stamp the plugin name if not already set
            stamped = field
            if not field.plugin_name:
                stamped = dataclasses.replace(field, plugin_name=plugin_name)
            self._register_field(stamped)

    def _register_field(self, field: InputField) -> None:
        """Register a single field, resolving conflicts."""
        key = f"{field.command}:{field.id}"

        if key not in self._fields:
            self._fields[key] = field
            return

        existing = self._fields[key]

        if existing.field_type == field.field_type:
            # Same type — first wins, log info
            msg = (
                f"Input '{field.id}' for command '{field.command}' already "
                f"registered by '{existing.plugin_name}', skipping duplicate "
                f"from '{field.plugin_name}'"
            )
            log.info(msg)
            self._conflicts.append(msg)
            return

        # Type conflict — namespace the second field
        namespaced_id = f"{field.plugin_name}.{field.id}"
        namespaced_key = f"{field.command}:{namespaced_id}"
        msg = (
            f"Input conflict: '{field.id}' declared by '{field.plugin_name}' "
            f"(type {field.field_type}) conflicts with '{existing.plugin_name}' "
            f"(type {existing.field_type}). Namespacing to '{namespaced_id}'"
        )
        log.warning(msg)
        self._conflicts.append(msg)
        self._fields[namespaced_key] = dataclasses.replace(field, id=namespaced_id)

    def register_registry_inputs(
        self,
        plugin_name: str,
        contributions: dict[str, list[dict[str, object]]],
    ) -> None:
        """Register input fields from the remote registry as a fallback.

        Only registers fields for *plugin_name* if that plugin did not
        already contribute fields via ``input_schema`` or
        ``get_input_schema()``.  This lets the registry serve as a
        fallback for plugins that haven't yet adopted the class-level
        declaration, while plugins that do declare their own schema
        always win.
        """
        from reeln.models.plugin_input import dict_to_input_field

        for command, field_dicts in contributions.items():
            for fd in field_dicts:
                field = dict_to_input_field(
                    fd,
                    command=command,
                    plugin_name=plugin_name,
                )
                key = f"{field.command}:{field.id}"
                if key not in self._fields:
                    self._register_field(field)

    # -- queries ------------------------------------------------------------

    def fields_for_command(self, command: str) -> list[InputField]:
        """Return all registered fields for *command*, sorted by id."""
        return sorted(
            (f for f in self._fields.values() if f.command == command),
            key=lambda f: f.id,
        )

    def has_field(self, command: str, field_id: str) -> bool:
        """Return ``True`` if a field with *field_id* is registered for *command*."""
        return f"{command}:{field_id}" in self._fields

    @property
    def conflicts(self) -> list[str]:
        """Return logged conflict messages (for testing/debugging)."""
        return list(self._conflicts)

    # -- collection ---------------------------------------------------------

    def collect_noninteractive(
        self,
        command: str,
        raw_inputs: list[str],
    ) -> dict[str, Any]:
        """Parse ``KEY=VALUE`` pairs and validate against registered fields.

        Unknown keys (no matching field) are passed through as strings.
        Returns ``{field_id: coerced_value}``.
        """
        fields = {f.id: f for f in self.fields_for_command(command)}
        result: dict[str, Any] = {}

        for item in raw_inputs:
            if "=" not in item:
                log.warning("Ignoring malformed plugin input (expected KEY=VALUE): %r", item)
                continue
            key, _, raw_value = item.partition("=")
            key = key.strip()
            raw_value = raw_value.strip()

            field = fields.get(key)
            if field is None:
                # Pass through unknown keys as strings
                result[key] = raw_value
                continue

            try:
                result[key] = coerce_value(raw_value, field)
            except ValueError as exc:
                log.warning("Plugin input validation: %s", exc)
                # Still store the raw value so the plugin gets something
                result[key] = raw_value

        return result

    def collect_interactive(
        self,
        command: str,
        presets: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prompt for plugin inputs, skipping those already in *presets*.

        Returns ``{field_id: value}``.  Fields with defaults that the user
        skips (empty input) get the default value.
        """
        presets = presets or {}
        fields = self.fields_for_command(command)
        result: dict[str, Any] = {}

        for field in fields:
            if field.id in presets:
                result[field.id] = presets[field.id]
                continue
            result[field.id] = _prompt_for_field(field)

        return result

    # -- lifecycle ----------------------------------------------------------

    def clear(self) -> None:
        """Reset all registered fields and conflicts."""
        self._fields.clear()
        self._conflicts.clear()


# ---------------------------------------------------------------------------
# Interactive prompt dispatch
# ---------------------------------------------------------------------------


def _prompt_for_field(field: InputField) -> Any:
    """Prompt the user for a single input field value via questionary.

    Returns the collected (and coerced) value, or the field's default
    when the user provides no input and a default exists.
    """
    import sys

    if not sys.stdin.isatty():
        return field.default

    try:
        import questionary
    except ImportError:
        log.debug("questionary not installed, using default for %s", field.id)
        return field.default

    ft = field.field_type
    plugin_tag = f"[{field.plugin_name}] " if field.plugin_name else ""
    label = f"{plugin_tag}{field.label}"
    if field.description:
        label = f"{label} ({field.description})"

    if ft == "bool":
        default_bool = bool(field.default) if field.default is not None else False
        answer = questionary.confirm(f"{label}:", default=default_bool).ask()
        if answer is None:
            return field.default
        return answer

    if ft == "select" and field.options:
        choices = [questionary.Choice(title=o.label, value=o.value) for o in field.options]
        answer = questionary.select(f"{label}:", choices=choices).ask()
        if answer is None:
            return field.default
        return answer

    # str, int, float, file — all use text prompt
    default_str = str(field.default) if field.default is not None else ""
    answer = questionary.text(
        f"{label}:",
        default=default_str,
    ).ask()

    if answer is None:
        return field.default
    if answer == "" and not field.required:
        return field.default

    # Coerce typed fields
    if ft in ("int", "float"):
        try:
            return coerce_value(answer, field)
        except ValueError:
            return field.default

    return answer


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_collector: InputCollector | None = None


def get_input_collector() -> InputCollector:
    """Return the module-level :class:`InputCollector` singleton."""
    global _collector
    if _collector is None:
        _collector = InputCollector()
    return _collector


def reset_input_collector() -> InputCollector:
    """Clear and return a fresh :class:`InputCollector` singleton.

    Used at the start of ``activate_plugins()`` for idempotency and
    by tests for isolation.
    """
    global _collector
    _collector = InputCollector()
    return _collector
