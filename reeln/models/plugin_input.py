"""Plugin input contribution models.

Plugins declare additional inputs they need during specific CLI commands
via a ``PluginInputSchema`` class attribute.  These inputs are collected
interactively (questionary prompts), non-interactively (``--plugin-input
KEY=VALUE``), or via reeln-dock UI fields, then passed to plugins through
``HookContext.data["plugin_inputs"]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Command scope constants
# ---------------------------------------------------------------------------


class InputCommand:
    """Valid command scopes for plugin input contributions."""

    GAME_INIT: str = "game_init"
    GAME_FINISH: str = "game_finish"
    GAME_SEGMENT: str = "game_segment"
    RENDER_SHORT: str = "render_short"
    RENDER_PREVIEW: str = "render_preview"

    _ALL: frozenset[str] = frozenset(
        {
            "game_init",
            "game_finish",
            "game_segment",
            "render_short",
            "render_preview",
        }
    )

    @classmethod
    def is_valid(cls, command: str) -> bool:
        """Return ``True`` if *command* is a recognised scope."""
        return command in cls._ALL


# ---------------------------------------------------------------------------
# Valid field types
# ---------------------------------------------------------------------------

VALID_INPUT_TYPES: frozenset[str] = frozenset({"str", "int", "float", "bool", "file", "select"})

_TYPE_COERCERS: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "file": str,
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputOption:
    """A selectable option for ``select``-type input fields."""

    value: str
    label: str


@dataclass(frozen=True)
class InputField:
    """A single plugin input field declaration.

    Each field is scoped to a specific CLI command (``command``) and owned
    by the declaring plugin (``plugin_name``).
    """

    id: str
    label: str
    field_type: str
    command: str
    plugin_name: str = ""
    default: Any = None
    required: bool = False
    description: str = ""
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    options: tuple[InputOption, ...] = ()
    maps_to: str = ""

    @property
    def effective_maps_to(self) -> str:
        """Return the mapping key, falling back to *id*."""
        return self.maps_to or self.id


@dataclass(frozen=True)
class PluginInputSchema:
    """Collection of input field declarations for a plugin."""

    fields: tuple[InputField, ...] = ()

    def fields_for_command(self, command: str) -> list[InputField]:
        """Return fields scoped to *command*."""
        return [f for f in self.fields if f.command == command]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def input_option_to_dict(option: InputOption) -> dict[str, str]:
    """Serialize an ``InputOption`` to a JSON-compatible dict."""
    return {"value": option.value, "label": option.label}


def dict_to_input_option(data: dict[str, Any]) -> InputOption:
    """Deserialize a dict into an ``InputOption``."""
    return InputOption(value=str(data.get("value", "")), label=str(data.get("label", "")))


def input_field_to_dict(f: InputField) -> dict[str, Any]:
    """Serialize an ``InputField`` to a JSON-compatible dict."""
    d: dict[str, Any] = {
        "id": f.id,
        "label": f.label,
        "type": f.field_type,
        "command": f.command,
    }
    if f.plugin_name:
        d["plugin_name"] = f.plugin_name
    if f.default is not None:
        d["default"] = f.default
    if f.required:
        d["required"] = f.required
    if f.description:
        d["description"] = f.description
    if f.min_value is not None:
        d["min"] = f.min_value
    if f.max_value is not None:
        d["max"] = f.max_value
    if f.step is not None:
        d["step"] = f.step
    if f.options:
        d["options"] = [input_option_to_dict(o) for o in f.options]
    if f.maps_to:
        d["maps_to"] = f.maps_to
    return d


def dict_to_input_field(
    data: dict[str, Any],
    *,
    command: str = "",
    plugin_name: str = "",
) -> InputField:
    """Deserialize a dict into an ``InputField``.

    *command* and *plugin_name* can be provided as overrides when parsing
    from the registry JSON where they are not embedded in each field dict.
    """
    raw_options = data.get("options", ())
    options: tuple[InputOption, ...] = ()
    if raw_options:
        options = tuple(dict_to_input_option(o) for o in raw_options)

    return InputField(
        id=str(data.get("id", "")),
        label=str(data.get("label", "")),
        field_type=str(data.get("type", data.get("field_type", "str"))),
        command=str(data.get("command", command)),
        plugin_name=str(data.get("plugin_name", plugin_name)),
        default=data.get("default"),
        required=bool(data.get("required", False)),
        description=str(data.get("description", "")),
        min_value=data.get("min", data.get("min_value")),
        max_value=data.get("max", data.get("max_value")),
        step=data.get("step"),
        options=options,
        maps_to=str(data.get("maps_to", "")),
    )


def input_schema_to_dict(schema: PluginInputSchema) -> dict[str, Any]:
    """Serialize a ``PluginInputSchema`` to a JSON-compatible dict."""
    return {"fields": [input_field_to_dict(f) for f in schema.fields]}


def dict_to_input_schema(
    data: dict[str, Any],
    *,
    plugin_name: str = "",
) -> PluginInputSchema:
    """Deserialize a dict into a ``PluginInputSchema``."""
    raw_fields = data.get("fields", ())
    fields = tuple(dict_to_input_field(f, plugin_name=plugin_name) for f in raw_fields)
    return PluginInputSchema(fields=fields)


# ---------------------------------------------------------------------------
# Type coercion / validation
# ---------------------------------------------------------------------------


def coerce_value(raw: str, f: InputField) -> Any:
    """Coerce a raw string value to the declared field type.

    Raises ``ValueError`` on type mismatch or constraint violation.
    """
    ft = f.field_type

    if ft == "bool":
        lowered = raw.lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        msg = f"Cannot coerce {raw!r} to bool for input {f.id!r}"
        raise ValueError(msg)

    if ft == "select":
        valid = {o.value for o in f.options}
        if valid and raw not in valid:
            msg = f"Invalid selection {raw!r} for input {f.id!r}; valid: {sorted(valid)}"
            raise ValueError(msg)
        return raw

    coercer = _TYPE_COERCERS.get(ft)
    if coercer is None:
        return raw

    try:
        value = coercer(raw)
    except (ValueError, TypeError) as exc:
        msg = f"Cannot coerce {raw!r} to {ft} for input {f.id!r}"
        raise ValueError(msg) from exc

    # Range validation for numeric types
    if ft in ("int", "float"):
        if f.min_value is not None and value < f.min_value:
            msg = f"Value {value} below minimum {f.min_value} for input {f.id!r}"
            raise ValueError(msg)
        if f.max_value is not None and value > f.max_value:
            msg = f"Value {value} above maximum {f.max_value} for input {f.id!r}"
            raise ValueError(msg)

    return value
