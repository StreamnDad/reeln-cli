"""Plugin config schema declaration models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_VALID_TYPES: frozenset[str] = frozenset({"str", "int", "float", "bool", "list"})

_TYPE_VALIDATORS: dict[str, type | tuple[type, ...]] = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "list": list,
}


@dataclass(frozen=True)
class ConfigField:
    """A single plugin configuration field declaration."""

    name: str
    field_type: str = "str"
    default: Any = None
    required: bool = False
    description: str = ""
    secret: bool = False


@dataclass(frozen=True)
class PluginConfigSchema:
    """Schema declaration for a plugin's configuration fields."""

    fields: tuple[ConfigField, ...] = ()

    def defaults_dict(self) -> dict[str, Any]:
        """Return ``{name: default}`` for fields with non-None defaults."""
        return {f.name: f.default for f in self.fields if f.default is not None}

    def required_fields(self) -> list[str]:
        """Return names of required fields."""
        return [f.name for f in self.fields if f.required]

    def field_by_name(self, name: str) -> ConfigField | None:
        """Look up a field by name, or return ``None``."""
        for f in self.fields:
            if f.name == name:
                return f
        return None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def config_field_to_dict(field: ConfigField) -> dict[str, Any]:
    """Serialize a ``ConfigField`` to a JSON-compatible dict."""
    d: dict[str, Any] = {"name": field.name, "field_type": field.field_type}
    if field.default is not None:
        d["default"] = field.default
    if field.required:
        d["required"] = field.required
    if field.description:
        d["description"] = field.description
    if field.secret:
        d["secret"] = field.secret
    return d


def schema_to_dict(schema: PluginConfigSchema) -> dict[str, Any]:
    """Serialize a ``PluginConfigSchema`` to a JSON-compatible dict."""
    return {"fields": [config_field_to_dict(f) for f in schema.fields]}


# ---------------------------------------------------------------------------
# Type validation
# ---------------------------------------------------------------------------


def validate_value_type(value: Any, field: ConfigField) -> bool:
    """Check whether *value* matches the declared *field* type.

    Unknown types pass validation. ``float`` accepts ``int`` values.
    """
    validator = _TYPE_VALIDATORS.get(field.field_type)
    if validator is None:
        return True
    # bool is a subclass of int in Python — reject bools for int/float
    if field.field_type in ("int", "float") and isinstance(value, bool):
        return False
    return isinstance(value, validator)
