"""Tests for plugin config schema models."""

from __future__ import annotations

import pytest

from reeln.models.plugin_schema import (
    ConfigField,
    PluginConfigSchema,
    config_field_to_dict,
    schema_to_dict,
    validate_value_type,
)

# ---------------------------------------------------------------------------
# ConfigField
# ---------------------------------------------------------------------------


class TestConfigField:
    def test_defaults(self) -> None:
        f = ConfigField(name="api_key")
        assert f.name == "api_key"
        assert f.field_type == "str"
        assert f.default is None
        assert f.required is False
        assert f.description == ""
        assert f.secret is False

    def test_custom_values(self) -> None:
        f = ConfigField(
            name="port",
            field_type="int",
            default=8080,
            required=True,
            description="Listen port",
            secret=False,
        )
        assert f.name == "port"
        assert f.field_type == "int"
        assert f.default == 8080
        assert f.required is True
        assert f.description == "Listen port"

    def test_frozen(self) -> None:
        f = ConfigField(name="key")
        with pytest.raises(AttributeError):
            f.name = "other"  # type: ignore[misc]

    def test_str_type(self) -> None:
        f = ConfigField(name="host", field_type="str", default="localhost")
        assert f.field_type == "str"
        assert f.default == "localhost"

    def test_int_type(self) -> None:
        f = ConfigField(name="port", field_type="int", default=80)
        assert f.field_type == "int"

    def test_float_type(self) -> None:
        f = ConfigField(name="rate", field_type="float", default=1.5)
        assert f.field_type == "float"

    def test_bool_type(self) -> None:
        f = ConfigField(name="verbose", field_type="bool", default=False)
        assert f.field_type == "bool"
        assert f.default is False

    def test_list_type(self) -> None:
        f = ConfigField(name="tags", field_type="list", default=[])
        assert f.field_type == "list"

    def test_secret_flag(self) -> None:
        f = ConfigField(name="token", secret=True)
        assert f.secret is True


# ---------------------------------------------------------------------------
# PluginConfigSchema
# ---------------------------------------------------------------------------


class TestPluginConfigSchema:
    def test_defaults(self) -> None:
        s = PluginConfigSchema()
        assert s.fields == ()

    def test_defaults_dict_with_defaults(self) -> None:
        s = PluginConfigSchema(
            fields=(
                ConfigField(name="host", default="localhost"),
                ConfigField(name="port", field_type="int", default=8080),
                ConfigField(name="token"),  # No default
            )
        )
        assert s.defaults_dict() == {"host": "localhost", "port": 8080}

    def test_defaults_dict_without_defaults(self) -> None:
        s = PluginConfigSchema(fields=(ConfigField(name="token", required=True),))
        assert s.defaults_dict() == {}

    def test_required_fields(self) -> None:
        s = PluginConfigSchema(
            fields=(
                ConfigField(name="api_key", required=True),
                ConfigField(name="host", default="localhost"),
                ConfigField(name="secret", required=True),
            )
        )
        assert s.required_fields() == ["api_key", "secret"]

    def test_field_by_name_found(self) -> None:
        f = ConfigField(name="port", field_type="int")
        s = PluginConfigSchema(fields=(f,))
        assert s.field_by_name("port") is f

    def test_field_by_name_not_found(self) -> None:
        s = PluginConfigSchema(fields=(ConfigField(name="host"),))
        assert s.field_by_name("missing") is None

    def test_frozen(self) -> None:
        s = PluginConfigSchema()
        with pytest.raises(AttributeError):
            s.fields = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_config_field_to_dict_full(self) -> None:
        f = ConfigField(
            name="api_key",
            field_type="str",
            default="abc",
            required=True,
            description="The API key",
            secret=True,
        )
        d = config_field_to_dict(f)
        assert d == {
            "name": "api_key",
            "field_type": "str",
            "default": "abc",
            "required": True,
            "description": "The API key",
            "secret": True,
        }

    def test_config_field_to_dict_minimal(self) -> None:
        f = ConfigField(name="host")
        d = config_field_to_dict(f)
        assert d == {"name": "host", "field_type": "str"}
        assert "default" not in d
        assert "required" not in d
        assert "description" not in d
        assert "secret" not in d

    def test_schema_to_dict(self) -> None:
        s = PluginConfigSchema(
            fields=(
                ConfigField(name="host", default="localhost"),
                ConfigField(name="port", field_type="int", default=80),
            )
        )
        d = schema_to_dict(s)
        assert len(d["fields"]) == 2
        assert d["fields"][0]["name"] == "host"
        assert d["fields"][1]["field_type"] == "int"

    def test_schema_to_dict_empty(self) -> None:
        d = schema_to_dict(PluginConfigSchema())
        assert d == {"fields": []}


# ---------------------------------------------------------------------------
# Type validation
# ---------------------------------------------------------------------------


class TestValidateValueType:
    def test_str_valid(self) -> None:
        f = ConfigField(name="x", field_type="str")
        assert validate_value_type("hello", f) is True

    def test_str_invalid(self) -> None:
        f = ConfigField(name="x", field_type="str")
        assert validate_value_type(123, f) is False

    def test_int_valid(self) -> None:
        f = ConfigField(name="x", field_type="int")
        assert validate_value_type(42, f) is True

    def test_int_invalid(self) -> None:
        f = ConfigField(name="x", field_type="int")
        assert validate_value_type("42", f) is False

    def test_int_rejects_bool(self) -> None:
        f = ConfigField(name="x", field_type="int")
        assert validate_value_type(True, f) is False

    def test_float_valid(self) -> None:
        f = ConfigField(name="x", field_type="float")
        assert validate_value_type(3.14, f) is True

    def test_float_accepts_int(self) -> None:
        f = ConfigField(name="x", field_type="float")
        assert validate_value_type(42, f) is True

    def test_float_invalid(self) -> None:
        f = ConfigField(name="x", field_type="float")
        assert validate_value_type("3.14", f) is False

    def test_float_rejects_bool(self) -> None:
        f = ConfigField(name="x", field_type="float")
        assert validate_value_type(True, f) is False

    def test_bool_valid(self) -> None:
        f = ConfigField(name="x", field_type="bool")
        assert validate_value_type(False, f) is True

    def test_bool_invalid(self) -> None:
        f = ConfigField(name="x", field_type="bool")
        assert validate_value_type(1, f) is False

    def test_list_valid(self) -> None:
        f = ConfigField(name="x", field_type="list")
        assert validate_value_type([1, 2], f) is True

    def test_list_invalid(self) -> None:
        f = ConfigField(name="x", field_type="list")
        assert validate_value_type("not a list", f) is False

    def test_unknown_type_passes(self) -> None:
        f = ConfigField(name="x", field_type="custom_type")
        assert validate_value_type("anything", f) is True
