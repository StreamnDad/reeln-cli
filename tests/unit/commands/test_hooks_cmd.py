"""Tests for the hooks CLI commands."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from reeln.cli import app
from reeln.commands.hooks_cmd import (
    _dicts_to_namespaces,
    _LogCapture,
    _parse_json_arg,
    _resolve_hook,
)
from reeln.core.errors import ReelnError
from reeln.models.config import AppConfig
from reeln.plugins.hooks import Hook, HookContext

runner = CliRunner()


# ---------------------------------------------------------------------------
# _LogCapture
# ---------------------------------------------------------------------------


def test_log_capture_info_goes_to_records() -> None:
    capture = _LogCapture()
    capture.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )
    capture.emit(record)
    assert capture.records == ["hello"]
    assert capture.errors == []


def test_log_capture_warning_goes_to_records() -> None:
    capture = _LogCapture()
    capture.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="warn",
        args=(),
        exc_info=None,
    )
    capture.emit(record)
    assert capture.records == ["warn"]
    assert capture.errors == []


def test_log_capture_error_goes_to_errors() -> None:
    capture = _LogCapture()
    capture.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="bad",
        args=(),
        exc_info=None,
    )
    capture.emit(record)
    assert capture.records == []
    assert capture.errors == ["bad"]


def test_log_capture_critical_goes_to_errors() -> None:
    capture = _LogCapture()
    capture.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="test",
        level=logging.CRITICAL,
        pathname="",
        lineno=0,
        msg="fatal",
        args=(),
        exc_info=None,
    )
    capture.emit(record)
    assert capture.errors == ["fatal"]


# ---------------------------------------------------------------------------
# _dicts_to_namespaces
# ---------------------------------------------------------------------------


def test_dicts_to_namespaces_flat() -> None:
    data = {"key": "value", "num": 42}
    result = _dicts_to_namespaces(data)
    assert result["key"] == "value"
    assert result["num"] == 42


def test_dicts_to_namespaces_nested_dict() -> None:
    data = {"game_info": {"home_team": "East", "sport": "hockey"}}
    result = _dicts_to_namespaces(data)
    ns = result["game_info"]
    assert ns.home_team == "East"
    assert ns.sport == "hockey"


def test_dicts_to_namespaces_deeply_nested() -> None:
    data = {"a": {"b": {"c": "deep"}}}
    result = _dicts_to_namespaces(data)
    assert result["a"].b.c == "deep"


def test_dicts_to_namespaces_non_dict_values_preserved() -> None:
    data = {"items": [1, 2, 3], "flag": True, "name": "test"}
    result = _dicts_to_namespaces(data)
    assert result["items"] == [1, 2, 3]
    assert result["flag"] is True


def test_dicts_to_namespaces_empty() -> None:
    assert _dicts_to_namespaces({}) == {}


def test_dicts_to_namespaces_getattr_fallback() -> None:
    """Verify getattr works with defaults on converted namespace."""
    data = {"game_info": {"home_team": "East"}}
    result = _dicts_to_namespaces(data)
    ns = result["game_info"]
    assert getattr(ns, "home_team", "") == "East"
    assert getattr(ns, "away_team", "default") == "default"


# ---------------------------------------------------------------------------
# _resolve_hook
# ---------------------------------------------------------------------------


def test_resolve_hook_valid() -> None:
    assert _resolve_hook("on_game_init") == Hook.ON_GAME_INIT


def test_resolve_hook_case_insensitive() -> None:
    assert _resolve_hook("ON_GAME_INIT") == Hook.ON_GAME_INIT


def test_resolve_hook_strips_prefix() -> None:
    assert _resolve_hook("hook.on_game_init") == Hook.ON_GAME_INIT


def test_resolve_hook_strips_whitespace() -> None:
    assert _resolve_hook("  on_game_ready  ") == Hook.ON_GAME_READY


def test_resolve_hook_unknown() -> None:
    import typer

    try:
        _resolve_hook("not_a_hook")
        msg = "Expected BadParameter"
        raise AssertionError(msg)
    except typer.BadParameter as exc:
        assert "Unknown hook" in str(exc)
        assert "not_a_hook" in str(exc)


# ---------------------------------------------------------------------------
# _parse_json_arg
# ---------------------------------------------------------------------------


def test_parse_json_arg_none_returns_empty() -> None:
    assert _parse_json_arg(None, "test") == {}


def test_parse_json_arg_empty_string_returns_empty() -> None:
    assert _parse_json_arg("", "test") == {}


def test_parse_json_arg_valid_json() -> None:
    result = _parse_json_arg('{"key": "value"}', "test")
    assert result == {"key": "value"}


def test_parse_json_arg_invalid_json() -> None:
    import typer

    try:
        _parse_json_arg("not-json", "ctx")
        msg = "Expected BadParameter"
        raise AssertionError(msg)
    except typer.BadParameter as exc:
        assert "Invalid JSON for ctx" in str(exc)


def test_parse_json_arg_non_dict_json() -> None:
    import typer

    try:
        _parse_json_arg("[1, 2, 3]", "ctx")
        msg = "Expected BadParameter"
        raise AssertionError(msg)
    except typer.BadParameter as exc:
        assert "must be a JSON object" in str(exc)
        assert "list" in str(exc)


def test_parse_json_arg_file_reference(tmp_path: Path) -> None:
    f = tmp_path / "data.json"
    f.write_text('{"from_file": true}')
    result = _parse_json_arg(f"@{f}", "test")
    assert result == {"from_file": True}


def test_parse_json_arg_file_not_found() -> None:
    import typer

    try:
        _parse_json_arg("@/nonexistent/path.json", "ctx")
        msg = "Expected BadParameter"
        raise AssertionError(msg)
    except typer.BadParameter as exc:
        assert "file not found" in str(exc)


def test_parse_json_arg_file_invalid_json(tmp_path: Path) -> None:
    import typer

    f = tmp_path / "bad.json"
    f.write_text("not-json")
    try:
        _parse_json_arg(f"@{f}", "ctx")
        msg = "Expected BadParameter"
        raise AssertionError(msg)
    except typer.BadParameter as exc:
        assert "Invalid JSON for ctx" in str(exc)


def test_parse_json_arg_file_non_dict(tmp_path: Path) -> None:
    import typer

    f = tmp_path / "arr.json"
    f.write_text("[1, 2]")
    try:
        _parse_json_arg(f"@{f}", "ctx")
        msg = "Expected BadParameter"
        raise AssertionError(msg)
    except typer.BadParameter as exc:
        assert "must be a JSON object" in str(exc)


# ---------------------------------------------------------------------------
# hooks list
# ---------------------------------------------------------------------------


def test_list_hooks() -> None:
    result = runner.invoke(app, ["hooks", "list"])
    assert result.exit_code == 0
    for hook in Hook:
        assert hook.value in result.output


# ---------------------------------------------------------------------------
# hooks run — happy path
# ---------------------------------------------------------------------------


def test_run_happy_path_no_context() -> None:
    with patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()):
        result = runner.invoke(app, ["hooks", "run", "on_game_init"])

    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["success"] is True
    assert output["hook"] == "on_game_init"
    assert isinstance(output["shared"], dict)
    assert isinstance(output["logs"], list)
    assert isinstance(output["errors"], list)


def test_run_with_context_json() -> None:
    ctx = '{"game_dir": "/tmp/test", "game_info": {"sport": "hockey"}}'
    with patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()):
        result = runner.invoke(app, ["hooks", "run", "on_game_init", "--context-json", ctx])

    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["success"] is True


def test_run_with_shared_json() -> None:
    shared = '{"livestream_metadata": {"title": "Test"}}'
    with patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()):
        result = runner.invoke(app, ["hooks", "run", "on_game_ready", "--shared-json", shared])

    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["success"] is True
    assert output["hook"] == "on_game_ready"


def test_run_shared_dict_preserved_through_emission() -> None:
    """Shared data passed via --shared-json should be available after hook emission."""
    shared = '{"existing_key": "preserved"}'

    with patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()):
        result = runner.invoke(app, ["hooks", "run", "on_game_ready", "--shared-json", shared])

    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["shared"]["existing_key"] == "preserved"


def test_run_with_profile_option() -> None:
    mock_config = MagicMock(return_value=AppConfig())
    with patch("reeln.commands.hooks_cmd.load_config", mock_config):
        result = runner.invoke(app, ["hooks", "run", "on_game_init", "--profile", "test-profile"])

    assert result.exit_code == 0
    mock_config.assert_called_once_with(path=None, profile="test-profile")


def test_run_with_config_option(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}")
    mock_config = MagicMock(return_value=AppConfig())
    with patch("reeln.commands.hooks_cmd.load_config", mock_config):
        result = runner.invoke(app, ["hooks", "run", "on_game_init", "--config", str(cfg_file)])

    assert result.exit_code == 0
    mock_config.assert_called_once_with(path=cfg_file, profile=None)


def test_run_with_file_references(tmp_path: Path) -> None:
    ctx_file = tmp_path / "ctx.json"
    ctx_file.write_text('{"game_dir": "/tmp"}')
    shared_file = tmp_path / "shared.json"
    shared_file.write_text('{"key": "val"}')

    with patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()):
        result = runner.invoke(
            app,
            [
                "hooks",
                "run",
                "on_game_init",
                "--context-json",
                f"@{ctx_file}",
                "--shared-json",
                f"@{shared_file}",
            ],
        )

    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["success"] is True
    assert output["shared"]["key"] == "val"


# ---------------------------------------------------------------------------
# hooks run — plugin interaction
# ---------------------------------------------------------------------------


def test_run_plugin_writes_to_shared() -> None:
    """A plugin handler that writes to context.shared should appear in output."""

    def fake_handler(ctx: HookContext) -> None:
        ctx.shared["generated"] = {"title": "Test Title"}

    def fake_activate(plugins_config: object) -> dict[str, object]:
        from reeln.plugins.registry import get_registry

        registry = get_registry()
        registry.register(Hook.ON_GAME_INIT, fake_handler)
        return {}

    with (
        patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.hooks_cmd.activate_plugins", side_effect=fake_activate),
    ):
        result = runner.invoke(app, ["hooks", "run", "on_game_init"])

    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["success"] is True
    assert output["shared"]["generated"]["title"] == "Test Title"


def _parse_json_output(raw: str) -> dict[str, object]:
    """Extract the JSON line from CliRunner output (may include stderr lines)."""
    for line in reversed(raw.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)  # type: ignore[return-value]
    msg = f"No JSON found in output: {raw!r}"
    raise ValueError(msg)


def test_run_plugin_logs_captured() -> None:
    """Log messages from plugin handlers should appear in logs."""
    plugin_logger = logging.getLogger("test_plugin")

    def logging_handler(ctx: HookContext) -> None:
        plugin_logger.info("plugin did something")

    def fake_activate(plugins_config: object) -> dict[str, object]:
        from reeln.plugins.registry import get_registry

        registry = get_registry()
        registry.register(Hook.ON_GAME_INIT, logging_handler)
        return {}

    with (
        patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.hooks_cmd.activate_plugins", side_effect=fake_activate),
    ):
        result = runner.invoke(app, ["hooks", "run", "on_game_init"])

    assert result.exit_code == 0
    output = _parse_json_output(result.output)
    assert any("plugin did something" in log for log in output["logs"])


def test_run_plugin_error_logged_not_fatal() -> None:
    """A plugin that raises should not crash the hook; error appears in logs."""

    def bad_handler(ctx: HookContext) -> None:
        msg = "plugin exploded"
        raise RuntimeError(msg)

    def fake_activate(plugins_config: object) -> dict[str, object]:
        from reeln.plugins.registry import get_registry

        registry = get_registry()
        registry.register(Hook.ON_GAME_INIT, bad_handler)
        return {}

    with (
        patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()),
        patch("reeln.commands.hooks_cmd.activate_plugins", side_effect=fake_activate),
    ):
        result = runner.invoke(app, ["hooks", "run", "on_game_init"])

    assert result.exit_code == 0
    output = _parse_json_output(result.output)
    # Hook registry catches exceptions, so success is still True
    assert output["success"] is True


# ---------------------------------------------------------------------------
# hooks run — error paths
# ---------------------------------------------------------------------------


def test_run_unknown_hook() -> None:
    result = runner.invoke(app, ["hooks", "run", "invalid_hook"])
    assert result.exit_code == 2


def test_run_invalid_context_json() -> None:
    result = runner.invoke(app, ["hooks", "run", "on_game_init", "--context-json", "not-json"])
    assert result.exit_code == 2


def test_run_invalid_shared_json() -> None:
    result = runner.invoke(app, ["hooks", "run", "on_game_init", "--shared-json", "[1,2]"])
    assert result.exit_code == 2


def test_run_config_load_failure() -> None:
    with patch(
        "reeln.commands.hooks_cmd.load_config",
        side_effect=ReelnError("config broken"),
    ):
        result = runner.invoke(app, ["hooks", "run", "on_game_init"])

    assert result.exit_code == 1
    # _emit_error writes JSON to stdout before exit
    output = json.loads(result.output.strip())
    assert output["success"] is False
    assert any("config broken" in e for e in output["errors"])


def test_run_unexpected_exception_during_activation() -> None:
    """An unexpected exception (not ReelnError) during activation is caught."""
    with (
        patch("reeln.commands.hooks_cmd.load_config", return_value=AppConfig()),
        patch(
            "reeln.commands.hooks_cmd.activate_plugins",
            side_effect=RuntimeError("unexpected"),
        ),
    ):
        result = runner.invoke(app, ["hooks", "run", "on_game_init"])

    assert result.exit_code == 0  # Command completes, but success=false in JSON
    output = json.loads(result.output.strip())
    assert output["success"] is False
    assert any("unexpected" in e for e in output["errors"])


# ---------------------------------------------------------------------------
# _emit_error
# ---------------------------------------------------------------------------


def test_emit_error_writes_json(capsys: object) -> None:
    from reeln.commands.hooks_cmd import _emit_error

    exc = _emit_error("something went wrong")
    assert isinstance(exc, ReelnError)

    # _emit_error writes directly to sys.stdout, but in test context
    # it's verified through the config_load_failure test above
    assert str(exc) == "something went wrong"
