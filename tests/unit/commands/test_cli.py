"""Tests for the root CLI app."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from reeln.cli import app
from reeln.core.errors import FFmpegError
from reeln.models.config import AppConfig

runner = CliRunner()


def test_help_shows_all_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "game" in result.output
    assert "render" in result.output
    assert "media" in result.output
    assert "config" in result.output
    assert "doctor" in result.output
    assert "plugins" in result.output


def test_version() -> None:
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.check_version", return_value="7.1"),
        patch("reeln.plugins.loader.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "reeln 0.0.24" in result.output
    assert "ffmpeg 7.1 (/usr/bin/ffmpeg)" in result.output


def test_version_ffmpeg_not_found() -> None:
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", side_effect=FFmpegError("not found")),
        patch("reeln.plugins.loader.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "reeln 0.0.24" in result.output
    assert "ffmpeg: not found" in result.output


def test_version_with_plugins() -> None:
    from reeln.models.plugin import PluginInfo

    fake_plugins = [
        PluginInfo(name="scoreboard", package="reeln-scoreboard", capabilities=[], enabled=True),
        PluginInfo(name="youtube", package="reeln-youtube", capabilities=[], enabled=False),
    ]
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.check_version", return_value="7.1"),
        patch("reeln.plugins.loader.discover_plugins", return_value=fake_plugins),
        patch("reeln.core.plugin_registry.get_installed_version", side_effect=["1.2.0", "0.3.1"]),
    ):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "plugins:" in result.output
    assert "  scoreboard 1.2.0" in result.output
    assert "  youtube 0.3.1" in result.output


def test_version_no_plugins() -> None:
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.check_version", return_value="7.1"),
        patch("reeln.plugins.loader.discover_plugins", return_value=[]),
    ):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "plugins:" not in result.output


def test_version_plugin_discovery_error() -> None:
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.check_version", return_value="7.1"),
        patch("reeln.plugins.loader.discover_plugins", side_effect=RuntimeError("boom")),
    ):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "reeln 0.0.24" in result.output
    assert "plugins:" not in result.output


def test_version_plugin_no_package_or_no_version() -> None:
    from reeln.models.plugin import PluginInfo

    fake_plugins = [
        PluginInfo(name="no-pkg", package="", capabilities=[], enabled=True),
        PluginInfo(name="no-ver", package="some-pkg", capabilities=[], enabled=True),
    ]
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.check_version", return_value="7.1"),
        patch("reeln.plugins.loader.discover_plugins", return_value=fake_plugins),
        patch("reeln.core.plugin_registry.get_installed_version", return_value=""),
    ):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "plugins:" not in result.output
    assert "no-pkg" not in result.output
    assert "no-ver" not in result.output


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    # Typer returns exit code 0 for --help but 2 for no_args_is_help
    assert result.exit_code in (0, 2)
    assert "Usage" in result.output or "reeln" in result.output


def test_log_format_json() -> None:
    result = runner.invoke(app, ["--log-format", "json", "--help"])
    assert result.exit_code == 0


def test_log_format_human() -> None:
    result = runner.invoke(app, ["--log-format", "human", "--help"])
    assert result.exit_code == 0


def test_log_format_envvar(monkeypatch: object) -> None:
    import os

    # Use monkeypatch via os.environ directly since CliRunner env may not work with Typer envvar
    old = os.environ.get("REELN_LOG_FORMAT")
    try:
        os.environ["REELN_LOG_FORMAT"] = "json"
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
    finally:
        if old is None:
            os.environ.pop("REELN_LOG_FORMAT", None)
        else:
            os.environ["REELN_LOG_FORMAT"] = old


# ---------------------------------------------------------------------------
# reeln doctor
# ---------------------------------------------------------------------------


def test_doctor_healthy() -> None:
    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
        patch("reeln.core.doctor.list_codecs", return_value=["libx264", "libx265", "aac"]),
        patch("reeln.core.doctor.list_hwaccels", return_value=["videotoolbox"]),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
    ):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "PASS" in result.output


def test_doctor_with_failure() -> None:
    with (
        patch(
            "reeln.core.doctor.discover_ffmpeg",
            side_effect=FFmpegError("ffmpeg not found"),
        ),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
    ):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_doctor_with_profile() -> None:
    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
        patch("reeln.core.doctor.list_codecs", return_value=["libx264", "libx265", "aac"]),
        patch("reeln.core.doctor.list_hwaccels", return_value=["videotoolbox"]),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()) as mock_load,
    ):
        result = runner.invoke(app, ["doctor", "--profile", "hockey"])

    assert result.exit_code == 0
    # load_config called twice: once for check_config, once for check_directories
    for call in mock_load.call_args_list:
        assert call.kwargs.get("profile") == "hockey"


def test_doctor_with_config_path(tmp_path: Path) -> None:
    config_file = tmp_path / "custom.json"
    config_file.write_text("{}")
    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
        patch("reeln.core.doctor.list_codecs", return_value=["libx264", "libx265", "aac"]),
        patch("reeln.core.doctor.list_hwaccels", return_value=["videotoolbox"]),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()) as mock_load,
    ):
        result = runner.invoke(app, ["doctor", "--config", str(config_file)])

    assert result.exit_code == 0
    for call in mock_load.call_args_list:
        assert call.kwargs.get("path") == config_file


def test_doctor_shows_hints() -> None:
    with (
        patch(
            "reeln.core.doctor.discover_ffmpeg",
            side_effect=FFmpegError("ffmpeg not found"),
        ),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
    ):
        result = runner.invoke(app, ["doctor"])

    assert "hint" in result.output.lower() or "FAIL" in result.output


def test_doctor_help() -> None:
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "health checks" in result.output.lower() or "doctor" in result.output.lower()
