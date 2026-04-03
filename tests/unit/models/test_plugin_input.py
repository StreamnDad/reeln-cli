"""Tests for plugin input contribution models."""

from __future__ import annotations

import pytest

from reeln.models.plugin_input import (
    InputCommand,
    InputField,
    InputOption,
    PluginInputSchema,
    coerce_value,
    dict_to_input_field,
    dict_to_input_option,
    dict_to_input_schema,
    input_field_to_dict,
    input_option_to_dict,
    input_schema_to_dict,
)

# ---------------------------------------------------------------------------
# InputCommand
# ---------------------------------------------------------------------------


class TestInputCommand:
    def test_constants(self) -> None:
        assert InputCommand.GAME_INIT == "game_init"
        assert InputCommand.GAME_FINISH == "game_finish"
        assert InputCommand.GAME_SEGMENT == "game_segment"
        assert InputCommand.RENDER_SHORT == "render_short"
        assert InputCommand.RENDER_PREVIEW == "render_preview"

    def test_is_valid_known(self) -> None:
        assert InputCommand.is_valid("game_init") is True
        assert InputCommand.is_valid("render_short") is True
        assert InputCommand.is_valid("game_finish") is True
        assert InputCommand.is_valid("game_segment") is True
        assert InputCommand.is_valid("render_preview") is True

    def test_is_valid_unknown(self) -> None:
        assert InputCommand.is_valid("unknown") is False
        assert InputCommand.is_valid("") is False


# ---------------------------------------------------------------------------
# InputOption
# ---------------------------------------------------------------------------


class TestInputOption:
    def test_creation(self) -> None:
        o = InputOption(value="hd", label="HD 1080p")
        assert o.value == "hd"
        assert o.label == "HD 1080p"

    def test_frozen(self) -> None:
        o = InputOption(value="a", label="b")
        with pytest.raises(AttributeError):
            o.value = "c"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InputField
# ---------------------------------------------------------------------------


class TestInputField:
    def test_defaults(self) -> None:
        f = InputField(id="thumb", label="Thumbnail", field_type="file", command="game_init")
        assert f.id == "thumb"
        assert f.label == "Thumbnail"
        assert f.field_type == "file"
        assert f.command == "game_init"
        assert f.plugin_name == ""
        assert f.default is None
        assert f.required is False
        assert f.description == ""
        assert f.min_value is None
        assert f.max_value is None
        assert f.step is None
        assert f.options == ()
        assert f.maps_to == ""

    def test_full_construction(self) -> None:
        opts = (InputOption(value="a", label="A"), InputOption(value="b", label="B"))
        f = InputField(
            id="quality",
            label="Quality",
            field_type="select",
            command="render_short",
            plugin_name="myplugin",
            default="a",
            required=True,
            description="Output quality",
            min_value=1.0,
            max_value=10.0,
            step=0.5,
            options=opts,
            maps_to="output_quality",
        )
        assert f.plugin_name == "myplugin"
        assert f.required is True
        assert f.options == opts
        assert f.maps_to == "output_quality"

    def test_frozen(self) -> None:
        f = InputField(id="x", label="X", field_type="str", command="game_init")
        with pytest.raises(AttributeError):
            f.id = "y"  # type: ignore[misc]

    def test_effective_maps_to_with_maps_to(self) -> None:
        f = InputField(id="thumb", label="T", field_type="str", command="game_init", maps_to="thumbnail_image")
        assert f.effective_maps_to == "thumbnail_image"

    def test_effective_maps_to_fallback(self) -> None:
        f = InputField(id="thumb", label="T", field_type="str", command="game_init")
        assert f.effective_maps_to == "thumb"


# ---------------------------------------------------------------------------
# PluginInputSchema
# ---------------------------------------------------------------------------


class TestPluginInputSchema:
    def test_empty(self) -> None:
        s = PluginInputSchema()
        assert s.fields == ()
        assert s.fields_for_command("game_init") == []

    def test_fields_for_command(self) -> None:
        f1 = InputField(id="a", label="A", field_type="str", command="game_init")
        f2 = InputField(id="b", label="B", field_type="int", command="render_short")
        f3 = InputField(id="c", label="C", field_type="bool", command="game_init")
        s = PluginInputSchema(fields=(f1, f2, f3))

        game_fields = s.fields_for_command("game_init")
        assert len(game_fields) == 2
        assert {f.id for f in game_fields} == {"a", "c"}

        render_fields = s.fields_for_command("render_short")
        assert len(render_fields) == 1
        assert render_fields[0].id == "b"

        assert s.fields_for_command("unknown") == []

    def test_frozen(self) -> None:
        s = PluginInputSchema()
        with pytest.raises(AttributeError):
            s.fields = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Serialization: InputOption
# ---------------------------------------------------------------------------


class TestInputOptionSerialization:
    def test_round_trip(self) -> None:
        o = InputOption(value="hd", label="HD 1080p")
        d = input_option_to_dict(o)
        assert d == {"value": "hd", "label": "HD 1080p"}

        restored = dict_to_input_option(d)
        assert restored == o

    def test_dict_to_input_option_missing_keys(self) -> None:
        o = dict_to_input_option({})
        assert o.value == ""
        assert o.label == ""


# ---------------------------------------------------------------------------
# Serialization: InputField
# ---------------------------------------------------------------------------


class TestInputFieldSerialization:
    def test_to_dict_full(self) -> None:
        f = InputField(
            id="quality",
            label="Quality",
            field_type="select",
            command="render_short",
            plugin_name="myplugin",
            default="a",
            required=True,
            description="Output quality",
            min_value=1.0,
            max_value=10.0,
            step=0.5,
            options=(InputOption(value="a", label="A"),),
            maps_to="output_quality",
        )
        d = input_field_to_dict(f)
        assert d["id"] == "quality"
        assert d["label"] == "Quality"
        assert d["type"] == "select"
        assert d["command"] == "render_short"
        assert d["plugin_name"] == "myplugin"
        assert d["default"] == "a"
        assert d["required"] is True
        assert d["description"] == "Output quality"
        assert d["min"] == 1.0
        assert d["max"] == 10.0
        assert d["step"] == 0.5
        assert d["options"] == [{"value": "a", "label": "A"}]
        assert d["maps_to"] == "output_quality"

    def test_to_dict_minimal(self) -> None:
        f = InputField(id="x", label="X", field_type="str", command="game_init")
        d = input_field_to_dict(f)
        assert d == {"id": "x", "label": "X", "type": "str", "command": "game_init"}
        assert "plugin_name" not in d
        assert "default" not in d
        assert "required" not in d
        assert "description" not in d
        assert "min" not in d
        assert "max" not in d
        assert "step" not in d
        assert "options" not in d
        assert "maps_to" not in d

    def test_dict_to_input_field_basic(self) -> None:
        d = {"id": "thumb", "label": "Thumbnail", "type": "file"}
        f = dict_to_input_field(d, command="game_init", plugin_name="google")
        assert f.id == "thumb"
        assert f.label == "Thumbnail"
        assert f.field_type == "file"
        assert f.command == "game_init"
        assert f.plugin_name == "google"

    def test_dict_to_input_field_inline_command(self) -> None:
        d = {"id": "x", "label": "X", "type": "str", "command": "render_short", "plugin_name": "p"}
        f = dict_to_input_field(d)
        assert f.command == "render_short"
        assert f.plugin_name == "p"

    def test_dict_to_input_field_field_type_key(self) -> None:
        """Accept ``field_type`` as alternate key for ``type``."""
        d = {"id": "x", "label": "X", "field_type": "int"}
        f = dict_to_input_field(d, command="game_init")
        assert f.field_type == "int"

    def test_dict_to_input_field_with_options(self) -> None:
        d = {
            "id": "q",
            "label": "Q",
            "type": "select",
            "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
        }
        f = dict_to_input_field(d, command="game_init")
        assert len(f.options) == 2
        assert f.options[0].value == "a"
        assert f.options[1].label == "B"

    def test_dict_to_input_field_with_constraints(self) -> None:
        d = {
            "id": "z",
            "label": "Zoom",
            "type": "int",
            "min": 1,
            "max": 30,
            "step": 1,
            "required": True,
            "description": "Zoom frames",
            "default": 5,
            "maps_to": "zoom_frames",
        }
        f = dict_to_input_field(d, command="render_short")
        assert f.min_value == 1
        assert f.max_value == 30
        assert f.step == 1
        assert f.required is True
        assert f.default == 5
        assert f.maps_to == "zoom_frames"

    def test_dict_to_input_field_min_value_key(self) -> None:
        """Accept ``min_value`` as alternate key for ``min``."""
        d = {"id": "x", "label": "X", "type": "int", "min_value": 0, "max_value": 100}
        f = dict_to_input_field(d, command="game_init")
        assert f.min_value == 0
        assert f.max_value == 100

    def test_dict_to_input_field_empty(self) -> None:
        f = dict_to_input_field({})
        assert f.id == ""
        assert f.field_type == "str"

    def test_round_trip(self) -> None:
        original = InputField(
            id="thumb",
            label="Thumbnail",
            field_type="file",
            command="game_init",
            plugin_name="google",
            default="/path/to/img.png",
            required=True,
            description="Thumbnail for livestream",
            maps_to="thumbnail_image",
        )
        d = input_field_to_dict(original)
        restored = dict_to_input_field(d)
        assert restored.id == original.id
        assert restored.field_type == original.field_type
        assert restored.command == original.command
        assert restored.plugin_name == original.plugin_name
        assert restored.default == original.default
        assert restored.maps_to == original.maps_to


# ---------------------------------------------------------------------------
# Serialization: PluginInputSchema
# ---------------------------------------------------------------------------


class TestInputSchemaSerialization:
    def test_schema_to_dict(self) -> None:
        s = PluginInputSchema(
            fields=(
                InputField(id="a", label="A", field_type="str", command="game_init"),
                InputField(id="b", label="B", field_type="int", command="game_init"),
            )
        )
        d = input_schema_to_dict(s)
        assert len(d["fields"]) == 2
        assert d["fields"][0]["id"] == "a"
        assert d["fields"][1]["type"] == "int"

    def test_schema_to_dict_empty(self) -> None:
        d = input_schema_to_dict(PluginInputSchema())
        assert d == {"fields": []}

    def test_dict_to_input_schema(self) -> None:
        d = {
            "fields": [
                {"id": "a", "label": "A", "type": "str", "command": "game_init"},
                {"id": "b", "label": "B", "type": "int", "command": "render_short"},
            ]
        }
        s = dict_to_input_schema(d, plugin_name="test")
        assert len(s.fields) == 2
        assert s.fields[0].plugin_name == "test"
        assert s.fields[1].field_type == "int"

    def test_dict_to_input_schema_empty(self) -> None:
        s = dict_to_input_schema({})
        assert s.fields == ()


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


class TestCoerceValue:
    def test_str(self) -> None:
        f = InputField(id="x", label="X", field_type="str", command="game_init")
        assert coerce_value("hello", f) == "hello"

    def test_int_valid(self) -> None:
        f = InputField(id="x", label="X", field_type="int", command="game_init")
        assert coerce_value("42", f) == 42

    def test_int_invalid(self) -> None:
        f = InputField(id="x", label="X", field_type="int", command="game_init")
        with pytest.raises(ValueError, match="Cannot coerce"):
            coerce_value("abc", f)

    def test_float_valid(self) -> None:
        f = InputField(id="x", label="X", field_type="float", command="game_init")
        assert coerce_value("3.14", f) == pytest.approx(3.14)

    def test_float_invalid(self) -> None:
        f = InputField(id="x", label="X", field_type="float", command="game_init")
        with pytest.raises(ValueError, match="Cannot coerce"):
            coerce_value("abc", f)

    def test_bool_true_variants(self) -> None:
        f = InputField(id="x", label="X", field_type="bool", command="game_init")
        for val in ("true", "True", "TRUE", "1", "yes", "on"):
            assert coerce_value(val, f) is True

    def test_bool_false_variants(self) -> None:
        f = InputField(id="x", label="X", field_type="bool", command="game_init")
        for val in ("false", "False", "FALSE", "0", "no", "off"):
            assert coerce_value(val, f) is False

    def test_bool_invalid(self) -> None:
        f = InputField(id="x", label="X", field_type="bool", command="game_init")
        with pytest.raises(ValueError, match="Cannot coerce"):
            coerce_value("maybe", f)

    def test_file(self) -> None:
        f = InputField(id="x", label="X", field_type="file", command="game_init")
        assert coerce_value("/path/to/file.png", f) == "/path/to/file.png"

    def test_select_valid(self) -> None:
        opts = (InputOption(value="a", label="A"), InputOption(value="b", label="B"))
        f = InputField(id="x", label="X", field_type="select", command="game_init", options=opts)
        assert coerce_value("a", f) == "a"

    def test_select_invalid(self) -> None:
        opts = (InputOption(value="a", label="A"), InputOption(value="b", label="B"))
        f = InputField(id="x", label="X", field_type="select", command="game_init", options=opts)
        with pytest.raises(ValueError, match="Invalid selection"):
            coerce_value("c", f)

    def test_select_no_options(self) -> None:
        f = InputField(id="x", label="X", field_type="select", command="game_init")
        assert coerce_value("anything", f) == "anything"

    def test_int_min_violation(self) -> None:
        f = InputField(id="x", label="X", field_type="int", command="game_init", min_value=5)
        with pytest.raises(ValueError, match="below minimum"):
            coerce_value("3", f)

    def test_int_max_violation(self) -> None:
        f = InputField(id="x", label="X", field_type="int", command="game_init", max_value=10)
        with pytest.raises(ValueError, match="above maximum"):
            coerce_value("15", f)

    def test_float_range_valid(self) -> None:
        f = InputField(id="x", label="X", field_type="float", command="game_init", min_value=0.0, max_value=1.0)
        assert coerce_value("0.5", f) == pytest.approx(0.5)

    def test_unknown_type(self) -> None:
        f = InputField(id="x", label="X", field_type="custom", command="game_init")
        assert coerce_value("anything", f) == "anything"
