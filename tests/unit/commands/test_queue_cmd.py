"""Tests for the queue command group."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from reeln.cli import app
from reeln.core.errors import QueueError
from reeln.models.queue import (
    PublishStatus,
    PublishTargetResult,
    QueueItem,
    QueueStatus,
    RenderQueue,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_item(**overrides: Any) -> QueueItem:
    defaults: dict[str, Any] = {
        "id": "abc123def456",
        "output": "/tmp/short.mp4",
        "game_dir": "/tmp/game",
        "status": QueueStatus.RENDERED,
        "queued_at": "2026-04-06T12:00:00Z",
        "title": "John Goal - North vs South",
        "player": "John",
        "home_team": "North",
        "away_team": "South",
    }
    defaults.update(overrides)
    return QueueItem(**defaults)


def _make_queue(*items: QueueItem) -> RenderQueue:
    return RenderQueue(items=items)


# ---------------------------------------------------------------------------
# queue --help
# ---------------------------------------------------------------------------


def test_queue_help() -> None:
    result = runner.invoke(app, ["queue", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "show" in result.output
    assert "edit" in result.output
    assert "publish" in result.output
    assert "remove" in result.output
    assert "targets" in result.output


# ---------------------------------------------------------------------------
# queue list
# ---------------------------------------------------------------------------


def test_list_empty(tmp_path: Path) -> None:
    with patch("reeln.core.queue.load_queue", return_value=_make_queue()):
        result = runner.invoke(app, ["queue", "list", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "No queue items" in result.output


def test_list_with_items(tmp_path: Path) -> None:
    item = _make_item()
    with patch("reeln.core.queue.load_queue", return_value=_make_queue(item)):
        result = runner.invoke(app, ["queue", "list", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "abc123de" in result.output
    assert "John Goal" in result.output


def test_list_filter_by_status(tmp_path: Path) -> None:
    rendered = _make_item(id="aaa111")
    published = _make_item(id="bbb222", status=QueueStatus.PUBLISHED)
    with patch("reeln.core.queue.load_queue", return_value=_make_queue(rendered, published)):
        result = runner.invoke(app, ["queue", "list", "--game-dir", str(tmp_path), "--status", "published"])
    assert result.exit_code == 0
    assert "bbb222" in result.output
    assert "aaa111" not in result.output


def test_list_invalid_status(tmp_path: Path) -> None:
    result = runner.invoke(app, ["queue", "list", "--game-dir", str(tmp_path), "--status", "bad"])
    assert result.exit_code == 1
    assert "Unknown status" in result.output


def test_list_hides_removed(tmp_path: Path) -> None:
    removed = _make_item(status=QueueStatus.REMOVED)
    with patch("reeln.core.queue.load_queue", return_value=_make_queue(removed)):
        result = runner.invoke(app, ["queue", "list", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "No queue items" in result.output


def test_list_all_games(tmp_path: Path) -> None:
    item = _make_item()
    with (
        patch("reeln.core.queue.load_queue_index", return_value=[str(tmp_path)]),
        patch("reeln.core.queue.load_queue", return_value=_make_queue(item)),
    ):
        result = runner.invoke(app, ["queue", "list", "--all"])
    assert result.exit_code == 0
    assert "John Goal" in result.output


# ---------------------------------------------------------------------------
# queue show
# ---------------------------------------------------------------------------


def test_show_item(tmp_path: Path) -> None:
    targets = (
        PublishTargetResult(target="google", status=PublishStatus.PUBLISHED, url="https://youtu.be/x"),
        PublishTargetResult(target="meta", status=PublishStatus.PENDING),
    )
    item = _make_item(
        duration_seconds=15.5,
        file_size_bytes=2097152,
        render_profile="default",
        crop_mode="crop",
        assists="Jane",
        publish_targets=targets,
    )
    with patch("reeln.core.queue.get_queue_item", return_value=item):
        result = runner.invoke(app, ["queue", "show", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "abc123def456" in result.output
    assert "John Goal" in result.output
    assert "15.5s" in result.output
    assert "2.0 MB" in result.output
    assert "google" in result.output
    assert "https://youtu.be/x" in result.output
    assert "meta" in result.output


def test_show_not_found(tmp_path: Path) -> None:
    with patch("reeln.core.queue.get_queue_item", return_value=None):
        result = runner.invoke(app, ["queue", "show", "nope", "--game-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# queue edit
# ---------------------------------------------------------------------------


def test_edit_title(tmp_path: Path) -> None:
    updated = _make_item(title="New Title")
    with patch("reeln.core.queue.update_queue_item", return_value=updated):
        result = runner.invoke(app, ["queue", "edit", "abc123", "--title", "New Title", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "New Title" in result.output


def test_edit_no_args(tmp_path: Path) -> None:
    result = runner.invoke(app, ["queue", "edit", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "--title" in result.output


def test_edit_not_found(tmp_path: Path) -> None:
    with patch("reeln.core.queue.update_queue_item", side_effect=QueueError("not found")):
        result = runner.invoke(app, ["queue", "edit", "nope", "--title", "X", "--game-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# queue publish
# ---------------------------------------------------------------------------


def test_publish_success(tmp_path: Path) -> None:
    targets = (PublishTargetResult(target="google", status=PublishStatus.PUBLISHED, url="https://youtu.be/x"),)
    published = _make_item(status=QueueStatus.PUBLISHED, publish_targets=targets)
    mock_config = MagicMock()
    with (
        patch("reeln.core.config.load_config", return_value=mock_config),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.publish_queue_item", return_value=published),
    ):
        result = runner.invoke(app, ["queue", "publish", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Published to" in result.output
    assert "google" in result.output


def test_publish_failure(tmp_path: Path) -> None:
    targets = (PublishTargetResult(target="google", status=PublishStatus.FAILED, error="API error"),)
    failed = _make_item(status=QueueStatus.FAILED, publish_targets=targets)
    mock_config = MagicMock()
    with (
        patch("reeln.core.config.load_config", return_value=mock_config),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.publish_queue_item", return_value=failed),
    ):
        result = runner.invoke(app, ["queue", "publish", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Failed" in result.output
    assert "API error" in result.output


def test_publish_queue_error(tmp_path: Path) -> None:
    mock_config = MagicMock()
    with (
        patch("reeln.core.config.load_config", return_value=mock_config),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.publish_queue_item", side_effect=QueueError("not found")),
    ):
        result = runner.invoke(app, ["queue", "publish", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# queue publish-all
# ---------------------------------------------------------------------------


def test_publish_all_empty(tmp_path: Path) -> None:
    mock_config = MagicMock()
    with (
        patch("reeln.core.config.load_config", return_value=mock_config),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.publish_all", return_value=[]),
    ):
        result = runner.invoke(app, ["queue", "publish-all", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "No items to publish" in result.output


def test_publish_all_with_results(tmp_path: Path) -> None:
    published = _make_item(status=QueueStatus.PUBLISHED)
    mock_config = MagicMock()
    with (
        patch("reeln.core.config.load_config", return_value=mock_config),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.publish_all", return_value=[published]),
    ):
        result = runner.invoke(app, ["queue", "publish-all", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "abc123de" in result.output


# ---------------------------------------------------------------------------
# queue remove
# ---------------------------------------------------------------------------


def test_remove_success(tmp_path: Path) -> None:
    removed = _make_item(status=QueueStatus.REMOVED)
    with patch("reeln.core.queue.remove_from_queue", return_value=removed):
        result = runner.invoke(app, ["queue", "remove", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_remove_not_found(tmp_path: Path) -> None:
    with patch("reeln.core.queue.remove_from_queue", side_effect=QueueError("not found")):
        result = runner.invoke(app, ["queue", "remove", "nope", "--game-dir", str(tmp_path)])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# queue targets
# ---------------------------------------------------------------------------


def test_targets_empty(tmp_path: Path) -> None:
    mock_config = MagicMock()
    with (
        patch("reeln.core.config.load_config", return_value=mock_config),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.discover_targets", return_value=[]),
    ):
        result = runner.invoke(app, ["queue", "targets"])
    assert result.exit_code == 0
    assert "No publish targets" in result.output


def test_show_item_publishing_status(tmp_path: Path) -> None:
    """Cover the PUBLISHING status badge branch."""
    item = _make_item(status=QueueStatus.PUBLISHING)
    with patch("reeln.core.queue.get_queue_item", return_value=item):
        result = runner.invoke(app, ["queue", "show", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0


def test_show_item_partial_status(tmp_path: Path) -> None:
    """Cover the PARTIAL status badge branch."""
    item = _make_item(status=QueueStatus.PARTIAL)
    with patch("reeln.core.queue.get_queue_item", return_value=item):
        result = runner.invoke(app, ["queue", "show", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0


def test_show_item_failed_status(tmp_path: Path) -> None:
    """Cover the FAILED status badge branch."""
    item = _make_item(status=QueueStatus.FAILED)
    with patch("reeln.core.queue.get_queue_item", return_value=item):
        result = runner.invoke(app, ["queue", "show", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0


def test_show_item_removed_status(tmp_path: Path) -> None:
    """Cover the REMOVED status badge branch."""
    item = _make_item(status=QueueStatus.REMOVED)
    with patch("reeln.core.queue.get_queue_item", return_value=item):
        result = runner.invoke(app, ["queue", "show", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0


def test_show_item_with_skipped_target(tmp_path: Path) -> None:
    """Cover the SKIPPED publish badge branch."""
    targets = (PublishTargetResult(target="tiktok", status=PublishStatus.SKIPPED),)
    item = _make_item(publish_targets=targets)
    with patch("reeln.core.queue.get_queue_item", return_value=item):
        result = runner.invoke(app, ["queue", "show", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "tiktok" in result.output


def test_show_item_with_failed_target(tmp_path: Path) -> None:
    """Cover the FAILED publish badge branch."""
    targets = (PublishTargetResult(target="meta", status=PublishStatus.FAILED, error="API 500"),)
    item = _make_item(publish_targets=targets)
    with patch("reeln.core.queue.get_queue_item", return_value=item):
        result = runner.invoke(app, ["queue", "show", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "API 500" in result.output


def test_list_uses_cwd_by_default() -> None:
    """When no --game-dir and not --all, uses cwd."""
    with patch("reeln.core.queue.load_queue", return_value=_make_queue()):
        result = runner.invoke(app, ["queue", "list"])
    assert result.exit_code == 0


def test_publish_uses_stored_config_profile(tmp_path: Path) -> None:
    """publish command loads the config_profile stored in the queue item."""
    item = _make_item(config_profile="tournament-stream")
    targets = (PublishTargetResult(target="google", status=PublishStatus.PUBLISHED, url="https://youtu.be/x"),)
    published = _make_item(status=QueueStatus.PUBLISHED, publish_targets=targets)
    mock_config = MagicMock()
    with (
        patch("reeln.core.queue.get_queue_item", return_value=item),
        patch("reeln.core.config.load_config", return_value=mock_config) as mock_load,
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.publish_queue_item", return_value=published),
    ):
        result = runner.invoke(app, ["queue", "publish", "abc123", "--game-dir", str(tmp_path)])
    assert result.exit_code == 0
    # Verify load_config was called with the stored profile
    mock_load.assert_called_once_with(path=None, profile="tournament-stream")


def test_publish_cli_profile_overrides_stored(tmp_path: Path) -> None:
    """CLI --profile overrides the stored config_profile."""
    item = _make_item(config_profile="tournament-stream")
    targets = (PublishTargetResult(target="google", status=PublishStatus.PUBLISHED, url="https://youtu.be/x"),)
    published = _make_item(status=QueueStatus.PUBLISHED, publish_targets=targets)
    mock_config = MagicMock()
    with (
        patch("reeln.core.queue.get_queue_item", return_value=item),
        patch("reeln.core.config.load_config", return_value=mock_config) as mock_load,
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.publish_queue_item", return_value=published),
    ):
        result = runner.invoke(
            app, ["queue", "publish", "abc123", "--game-dir", str(tmp_path), "--profile", "override"],
        )
    assert result.exit_code == 0
    mock_load.assert_called_once_with(path=None, profile="override")


def test_targets_with_plugins(tmp_path: Path) -> None:
    mock_config = MagicMock()
    with (
        patch("reeln.core.config.load_config", return_value=mock_config),
        patch("reeln.plugins.loader.activate_plugins", return_value={}),
        patch("reeln.core.queue.discover_targets", return_value=["google", "meta"]),
    ):
        result = runner.invoke(app, ["queue", "targets"])
    assert result.exit_code == 0
    assert "google" in result.output
    assert "meta" in result.output
