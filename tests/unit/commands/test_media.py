"""Tests for the media command group."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from reeln.cli import app
from reeln.core.errors import ConfigError, MediaError
from reeln.models.config import AppConfig, PathConfig
from reeln.models.render_plan import PruneResult

runner = CliRunner()


def _mock_load_config(**kwargs: object) -> AppConfig:
    return AppConfig(**kwargs)  # type: ignore[arg-type]


def test_media_help_lists_commands() -> None:
    result = runner.invoke(app, ["media", "--help"])
    assert result.exit_code == 0
    assert "prune" in result.output


def test_media_prune_basic(tmp_path: Path) -> None:
    result_obj = PruneResult(removed_paths=[tmp_path / "a.mkv"], bytes_freed=1024)
    messages = ["game1:", "  Removed 1 file(s), 1.0 KB"]
    with (
        patch("reeln.commands.media.load_config", return_value=_mock_load_config()),
        patch(
            "reeln.core.prune.prune_all",
            return_value=(result_obj, messages),
        ),
    ):
        result = runner.invoke(app, ["media", "prune", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Removed 1 file(s)" in result.output


def test_media_prune_all_flag(tmp_path: Path) -> None:
    result_obj = PruneResult()
    messages = ["Nothing to prune"]
    with (
        patch("reeln.commands.media.load_config", return_value=_mock_load_config()),
        patch(
            "reeln.core.prune.prune_all",
            return_value=(result_obj, messages),
        ) as mock_pa,
    ):
        result = runner.invoke(app, ["media", "prune", "--all", "-o", str(tmp_path)])

    assert result.exit_code == 0
    call_kwargs = mock_pa.call_args.kwargs
    assert call_kwargs["all_files"] is True


def test_media_prune_dry_run(tmp_path: Path) -> None:
    result_obj = PruneResult(removed_paths=[tmp_path / "a.mkv"], bytes_freed=100)
    messages = ["Would remove 1 file(s), 100 B"]
    with (
        patch("reeln.commands.media.load_config", return_value=_mock_load_config()),
        patch(
            "reeln.core.prune.prune_all",
            return_value=(result_obj, messages),
        ) as mock_pa,
    ):
        result = runner.invoke(app, ["media", "prune", "--dry-run", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Would remove" in result.output
    call_kwargs = mock_pa.call_args.kwargs
    assert call_kwargs["dry_run"] is True


def test_media_prune_uses_config_output_dir(tmp_path: Path) -> None:
    """When -o is not passed, uses paths.output_dir from config."""
    result_obj = PruneResult()
    messages = ["Nothing to prune"]
    cfg = AppConfig(paths=PathConfig(output_dir=tmp_path))
    with (
        patch("reeln.commands.media.load_config", return_value=cfg),
        patch(
            "reeln.core.prune.prune_all",
            return_value=(result_obj, messages),
        ) as mock_pa,
    ):
        result = runner.invoke(app, ["media", "prune"])

    assert result.exit_code == 0
    call_args = mock_pa.call_args
    assert call_args[0][0] == tmp_path


def test_media_prune_uses_cwd_fallback() -> None:
    """When -o and config output_dir are both absent, uses cwd."""
    result_obj = PruneResult()
    messages = ["No game directories found"]
    with (
        patch("reeln.commands.media.load_config", return_value=_mock_load_config()),
        patch(
            "reeln.core.prune.prune_all",
            return_value=(result_obj, messages),
        ) as mock_pa,
    ):
        result = runner.invoke(app, ["media", "prune"])

    assert result.exit_code == 0
    call_args = mock_pa.call_args
    assert call_args[0][0] == Path.cwd()


def test_media_prune_config_error_exits() -> None:
    with patch(
        "reeln.commands.media.load_config",
        side_effect=ConfigError("bad config"),
    ):
        result = runner.invoke(app, ["media", "prune"])

    assert result.exit_code == 1
    assert "bad config" in result.output


def test_media_prune_error_exits(tmp_path: Path) -> None:
    with (
        patch("reeln.commands.media.load_config", return_value=_mock_load_config()),
        patch(
            "reeln.core.prune.prune_all",
            side_effect=MediaError("something went wrong"),
        ),
    ):
        result = runner.invoke(app, ["media", "prune", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "something went wrong" in result.output


def test_media_prune_help_shows_options() -> None:
    result = runner.invoke(app, ["media", "prune", "--help"])
    assert result.exit_code == 0
    assert "--output-dir" in result.output
    assert "--all" in result.output
    assert "--dry-run" in result.output
    assert "--profile" in result.output
    assert "--config" in result.output
