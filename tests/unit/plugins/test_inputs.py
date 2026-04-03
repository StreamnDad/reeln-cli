"""Tests for plugin input collection and conflict resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from reeln.models.plugin_input import InputField, InputOption, PluginInputSchema
from reeln.plugins.inputs import (
    InputCollector,
    _prompt_for_field,
    get_input_collector,
    reset_input_collector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_field(
    id: str = "thumb",
    label: str = "Thumbnail",
    field_type: str = "file",
    command: str = "game_init",
    plugin_name: str = "google",
    **kwargs: object,
) -> InputField:
    return InputField(
        id=id,
        label=label,
        field_type=field_type,
        command=command,
        plugin_name=plugin_name,
        **kwargs,  # type: ignore[arg-type]
    )


class _FakePlugin:
    """Fake plugin with an input_schema."""

    def __init__(self, schema: PluginInputSchema) -> None:
        self.input_schema = schema


class _NoSchemaPlugin:
    """Fake plugin without input_schema."""

    name = "bare"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegisterPluginInputs:
    def test_register_from_plugin(self) -> None:
        field = _make_field()
        plugin = _FakePlugin(PluginInputSchema(fields=(field,)))
        collector = InputCollector()
        collector.register_plugin_inputs(plugin, "google")

        fields = collector.fields_for_command("game_init")
        assert len(fields) == 1
        assert fields[0].id == "thumb"
        assert fields[0].plugin_name == "google"

    def test_stamps_plugin_name(self) -> None:
        """Plugin name is stamped if not already set on the field."""
        field = InputField(id="x", label="X", field_type="str", command="game_init")
        plugin = _FakePlugin(PluginInputSchema(fields=(field,)))
        collector = InputCollector()
        collector.register_plugin_inputs(plugin, "myplugin")

        result = collector.fields_for_command("game_init")
        assert result[0].plugin_name == "myplugin"

    def test_preserves_existing_plugin_name(self) -> None:
        field = _make_field(plugin_name="original")
        plugin = _FakePlugin(PluginInputSchema(fields=(field,)))
        collector = InputCollector()
        collector.register_plugin_inputs(plugin, "other")

        result = collector.fields_for_command("game_init")
        assert result[0].plugin_name == "original"

    def test_skip_no_schema(self) -> None:
        collector = InputCollector()
        collector.register_plugin_inputs(_NoSchemaPlugin(), "bare")
        assert collector.fields_for_command("game_init") == []

    def test_skip_non_schema_attribute(self) -> None:
        """Ignore input_schema if it's not a PluginInputSchema instance."""

        class Bad:
            input_schema = "not a schema"

        collector = InputCollector()
        collector.register_plugin_inputs(Bad(), "bad")
        assert collector.fields_for_command("game_init") == []

    def test_prefers_get_input_schema_method(self) -> None:
        """get_input_schema() is preferred over static input_schema attribute."""
        static_field = InputField(id="static", label="S", field_type="str", command="game_init")
        dynamic_field = InputField(id="dynamic", label="D", field_type="str", command="game_init")

        class MethodPlugin:
            input_schema = PluginInputSchema(fields=(static_field,))

            def get_input_schema(self) -> PluginInputSchema:
                return PluginInputSchema(fields=(dynamic_field,))

        collector = InputCollector()
        collector.register_plugin_inputs(MethodPlugin(), "test")
        fields = collector.fields_for_command("game_init")
        assert len(fields) == 1
        assert fields[0].id == "dynamic"

    def test_get_input_schema_empty_when_disabled(self) -> None:
        """Plugin returns empty schema when feature flag is off."""

        class ConditionalPlugin:
            def __init__(self, enabled: bool) -> None:
                self._enabled = enabled

            def get_input_schema(self) -> PluginInputSchema:
                if not self._enabled:
                    return PluginInputSchema()
                return PluginInputSchema(
                    fields=(InputField(id="thumb", label="T", field_type="file", command="game_init"),)
                )

        collector = InputCollector()
        collector.register_plugin_inputs(ConditionalPlugin(enabled=False), "google")
        assert collector.fields_for_command("game_init") == []

        collector.clear()
        collector.register_plugin_inputs(ConditionalPlugin(enabled=True), "google")
        assert len(collector.fields_for_command("game_init")) == 1

    def test_get_input_schema_failure_logged(self) -> None:
        """If get_input_schema() raises, the plugin is skipped."""

        class BrokenPlugin:
            def get_input_schema(self) -> PluginInputSchema:
                raise RuntimeError("boom")

        collector = InputCollector()
        collector.register_plugin_inputs(BrokenPlugin(), "broken")
        assert collector.fields_for_command("game_init") == []

    def test_get_input_schema_returns_non_schema(self) -> None:
        """If get_input_schema() returns non-PluginInputSchema, skip."""

        class WeirdPlugin:
            def get_input_schema(self) -> object:
                return "not a schema"

        collector = InputCollector()
        collector.register_plugin_inputs(WeirdPlugin(), "weird")  # type: ignore[arg-type]
        assert collector.fields_for_command("game_init") == []


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    def test_same_type_first_wins(self) -> None:
        f1 = _make_field(plugin_name="alpha", description="from alpha")
        f2 = _make_field(plugin_name="beta", description="from beta")
        collector = InputCollector()
        collector._register_field(f1)
        collector._register_field(f2)

        fields = collector.fields_for_command("game_init")
        assert len(fields) == 1
        assert fields[0].plugin_name == "alpha"
        assert len(collector.conflicts) == 1
        assert "already registered" in collector.conflicts[0]

    def test_different_type_namespaces(self) -> None:
        f1 = _make_field(plugin_name="alpha", field_type="str")
        f2 = _make_field(plugin_name="beta", field_type="int")
        collector = InputCollector()
        collector._register_field(f1)
        collector._register_field(f2)

        fields = collector.fields_for_command("game_init")
        assert len(fields) == 2
        ids = {f.id for f in fields}
        assert "thumb" in ids
        assert "beta.thumb" in ids
        assert len(collector.conflicts) == 1
        assert "Namespacing" in collector.conflicts[0]

    def test_different_commands_no_conflict(self) -> None:
        f1 = _make_field(command="game_init", plugin_name="alpha")
        f2 = _make_field(command="render_short", plugin_name="beta")
        collector = InputCollector()
        collector._register_field(f1)
        collector._register_field(f2)

        assert len(collector.fields_for_command("game_init")) == 1
        assert len(collector.fields_for_command("render_short")) == 1
        assert collector.conflicts == []


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


class TestQueries:
    def test_has_field(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field())
        assert collector.has_field("game_init", "thumb") is True
        assert collector.has_field("game_init", "missing") is False
        assert collector.has_field("render_short", "thumb") is False

    def test_fields_for_command_sorted(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="z", plugin_name="a"))
        collector._register_field(_make_field(id="a", plugin_name="b"))
        collector._register_field(_make_field(id="m", plugin_name="c"))

        fields = collector.fields_for_command("game_init")
        assert [f.id for f in fields] == ["a", "m", "z"]

    def test_fields_for_unknown_command(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field())
        assert collector.fields_for_command("unknown") == []


# ---------------------------------------------------------------------------
# Non-interactive collection
# ---------------------------------------------------------------------------


class TestCollectNoninteractive:
    def test_basic_parsing(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="name", field_type="str"))
        result = collector.collect_noninteractive("game_init", ["name=hello"])
        assert result == {"name": "hello"}

    def test_int_coercion(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="count", field_type="int"))
        result = collector.collect_noninteractive("game_init", ["count=42"])
        assert result == {"count": 42}

    def test_bool_coercion(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="flag", field_type="bool"))
        result = collector.collect_noninteractive("game_init", ["flag=true"])
        assert result == {"flag": True}

    def test_unknown_key_passthrough(self) -> None:
        collector = InputCollector()
        result = collector.collect_noninteractive("game_init", ["unknown=value"])
        assert result == {"unknown": "value"}

    def test_malformed_input_skipped(self) -> None:
        collector = InputCollector()
        result = collector.collect_noninteractive("game_init", ["noequals"])
        assert result == {}

    def test_invalid_value_falls_back_to_raw(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="count", field_type="int"))
        result = collector.collect_noninteractive("game_init", ["count=abc"])
        assert result == {"count": "abc"}

    def test_multiple_inputs(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="a", field_type="str"))
        collector._register_field(_make_field(id="b", field_type="int"))
        result = collector.collect_noninteractive("game_init", ["a=hello", "b=5"])
        assert result == {"a": "hello", "b": 5}

    def test_value_with_equals(self) -> None:
        """Values containing '=' should be preserved."""
        collector = InputCollector()
        collector._register_field(_make_field(id="url", field_type="str"))
        result = collector.collect_noninteractive("game_init", ["url=https://example.com?a=1&b=2"])
        assert result == {"url": "https://example.com?a=1&b=2"}

    def test_whitespace_trimmed(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="name", field_type="str"))
        result = collector.collect_noninteractive("game_init", [" name = hello "])
        assert result == {"name": "hello"}

    def test_empty_inputs(self) -> None:
        collector = InputCollector()
        result = collector.collect_noninteractive("game_init", [])
        assert result == {}


# ---------------------------------------------------------------------------
# Interactive collection
# ---------------------------------------------------------------------------


class TestCollectInteractive:
    def test_presets_bypass_prompting(self) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="name", field_type="str"))
        result = collector.collect_interactive("game_init", presets={"name": "preset_value"})
        assert result == {"name": "preset_value"}

    @patch("reeln.plugins.inputs._prompt_for_field", return_value="prompted_value")
    def test_prompts_for_missing(self, mock_prompt: MagicMock) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="name", field_type="str"))
        result = collector.collect_interactive("game_init")
        assert result == {"name": "prompted_value"}
        mock_prompt.assert_called_once()

    @patch("reeln.plugins.inputs._prompt_for_field", return_value="val")
    def test_mixed_presets_and_prompts(self, mock_prompt: MagicMock) -> None:
        collector = InputCollector()
        collector._register_field(_make_field(id="a", field_type="str", plugin_name="p1"))
        collector._register_field(_make_field(id="b", field_type="str", plugin_name="p2"))
        result = collector.collect_interactive("game_init", presets={"a": "preset"})
        assert result == {"a": "preset", "b": "val"}
        assert mock_prompt.call_count == 1

    def test_no_fields_returns_empty(self) -> None:
        collector = InputCollector()
        result = collector.collect_interactive("game_init")
        assert result == {}


# ---------------------------------------------------------------------------
# _prompt_for_field
# ---------------------------------------------------------------------------


class TestPromptForField:
    def test_non_tty_returns_default(self) -> None:
        f = _make_field(default="/default.png")
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = _prompt_for_field(f)
        assert result == "/default.png"

    def test_no_questionary_returns_default(self) -> None:
        f = _make_field(default="/default.png")
        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "questionary":
                raise ImportError("no questionary")
            return real_import(name, *args, **kwargs)

        with (
            patch("sys.stdin") as mock_stdin,
            patch("builtins.__import__", side_effect=_fake_import),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == "/default.png"

    def test_bool_field(self) -> None:
        f = _make_field(field_type="bool", default=False)
        mock_q = MagicMock()
        mock_q.confirm.return_value.ask.return_value = True
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result is True

    def test_bool_field_cancelled(self) -> None:
        f = _make_field(field_type="bool", default=False)
        mock_q = MagicMock()
        mock_q.confirm.return_value.ask.return_value = None
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result is False  # default

    def test_select_field(self) -> None:
        opts = (InputOption(value="a", label="A"), InputOption(value="b", label="B"))
        f = _make_field(field_type="select", options=opts)
        mock_q = MagicMock()
        mock_q.select.return_value.ask.return_value = "b"
        mock_q.Choice = MagicMock(side_effect=lambda title, value: MagicMock(title=title, value=value))
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == "b"

    def test_select_field_cancelled(self) -> None:
        opts = (InputOption(value="a", label="A"),)
        f = _make_field(field_type="select", options=opts, default="a")
        mock_q = MagicMock()
        mock_q.select.return_value.ask.return_value = None
        mock_q.Choice = MagicMock(side_effect=lambda title, value: MagicMock(title=title, value=value))
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == "a"  # default

    def test_text_field(self) -> None:
        f = _make_field(field_type="str")
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = "hello"
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == "hello"

    def test_text_field_cancelled(self) -> None:
        f = _make_field(field_type="str", default="fallback")
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = None
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == "fallback"

    def test_text_field_empty_non_required(self) -> None:
        f = _make_field(field_type="str", default="fallback", required=False)
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = ""
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == "fallback"

    def test_int_field_valid(self) -> None:
        f = _make_field(field_type="int")
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = "42"
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == 42

    def test_int_field_invalid_falls_back(self) -> None:
        f = _make_field(field_type="int", default=10)
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = "abc"
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == 10  # default

    def test_file_field(self) -> None:
        f = _make_field(field_type="file")
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = "/path/to/file.png"
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            result = _prompt_for_field(f)
        assert result == "/path/to/file.png"

    def test_description_in_label(self) -> None:
        f = _make_field(field_type="str", description="some help text")
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = "val"
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            _prompt_for_field(f)
        # Verify the label includes description
        call_args = mock_q.text.call_args
        assert "some help text" in call_args[0][0]

    def test_plugin_name_in_label(self) -> None:
        f = _make_field(field_type="str", plugin_name="google")
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = "val"
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            _prompt_for_field(f)
        call_args = mock_q.text.call_args
        assert "[google]" in call_args[0][0]

    def test_no_plugin_name_no_tag(self) -> None:
        f = _make_field(field_type="str", plugin_name="")
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = "val"
        with (
            patch("sys.stdin") as mock_stdin,
            patch.dict("sys.modules", {"questionary": mock_q}),
        ):
            mock_stdin.isatty.return_value = True
            _prompt_for_field(f)
        call_args = mock_q.text.call_args
        assert "[" not in call_args[0][0]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Registry fallback
# ---------------------------------------------------------------------------


class TestRegisterRegistryInputs:
    def test_registers_from_registry(self) -> None:
        collector = InputCollector()
        contributions: dict[str, list[dict[str, object]]] = {
            "game_init": [
                {"id": "thumb", "label": "Thumbnail", "type": "file", "description": "For livestream"}
            ]
        }
        collector.register_registry_inputs("google", contributions)
        fields = collector.fields_for_command("game_init")
        assert len(fields) == 1
        assert fields[0].id == "thumb"
        assert fields[0].plugin_name == "google"

    def test_skips_when_class_already_registered(self) -> None:
        """Registry fallback does not override class-level declarations."""
        collector = InputCollector()
        # Class-level registration
        collector._register_field(_make_field(id="thumb", plugin_name="google", description="from class"))
        # Registry fallback — same id, should be skipped
        contributions: dict[str, list[dict[str, object]]] = {
            "game_init": [{"id": "thumb", "label": "T", "type": "file", "description": "from registry"}]
        }
        collector.register_registry_inputs("google", contributions)
        fields = collector.fields_for_command("game_init")
        assert len(fields) == 1
        assert fields[0].description == "from class"

    def test_adds_new_fields_from_registry(self) -> None:
        """Registry can add fields not declared by the class."""
        collector = InputCollector()
        collector._register_field(_make_field(id="thumb", plugin_name="google"))
        contributions: dict[str, list[dict[str, object]]] = {
            "game_init": [
                {"id": "thumb", "label": "T", "type": "file"},  # already registered
                {"id": "title", "label": "Title", "type": "str"},  # new
            ]
        }
        collector.register_registry_inputs("google", contributions)
        fields = collector.fields_for_command("game_init")
        assert len(fields) == 2
        ids = {f.id for f in fields}
        assert "thumb" in ids
        assert "title" in ids

    def test_multiple_commands(self) -> None:
        collector = InputCollector()
        contributions: dict[str, list[dict[str, object]]] = {
            "game_init": [{"id": "thumb", "label": "T", "type": "file"}],
            "render_short": [{"id": "quality", "label": "Q", "type": "str"}],
        }
        collector.register_registry_inputs("google", contributions)
        assert len(collector.fields_for_command("game_init")) == 1
        assert len(collector.fields_for_command("render_short")) == 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_lazy_init(self) -> None:
        """get_input_collector() creates one when the global is None."""
        import reeln.plugins.inputs as mod

        mod._collector = None
        c = get_input_collector()
        assert c is not None
        assert c is get_input_collector()

    def test_get_returns_same_instance(self) -> None:
        reset_input_collector()
        a = get_input_collector()
        b = get_input_collector()
        assert a is b

    def test_reset_returns_fresh(self) -> None:
        a = get_input_collector()
        b = reset_input_collector()
        assert a is not b
        assert b is get_input_collector()

    def test_clear(self) -> None:
        collector = reset_input_collector()
        collector._register_field(_make_field())
        assert len(collector.fields_for_command("game_init")) == 1
        collector.clear()
        assert len(collector.fields_for_command("game_init")) == 0
        assert collector.conflicts == []
