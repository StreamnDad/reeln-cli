"""Tests for queue business logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from reeln.core.errors import QueueError
from reeln.core.queue import (
    _find_item,
    _generate_id,
    _now_iso,
    add_to_queue,
    discover_targets,
    get_queue_item,
    load_queue,
    load_queue_index,
    publish_all,
    publish_queue_item,
    remove_from_queue,
    save_queue,
    update_queue_index,
    update_queue_item,
)
from reeln.models.game import GameEvent, GameInfo
from reeln.models.queue import (
    PublishStatus,
    QueueItem,
    QueueStatus,
    RenderQueue,
)
from reeln.models.render_plan import RenderResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _game_info() -> GameInfo:
    return GameInfo(
        date="2026-04-06",
        home_team="North",
        away_team="South",
        sport="hockey",
        level="2016",
    )


def _game_event() -> GameEvent:
    return GameEvent(
        id="evt_001",
        clip="/tmp/clip.mp4",
        segment_number=1,
        event_type="goal",
        player="John Smith",
    )


def _render_result(tmp_path: Path) -> RenderResult:
    out = tmp_path / "short.mp4"
    out.write_bytes(b"fake video")
    return RenderResult(output=out, duration_seconds=15.0, file_size_bytes=1024)


def _make_item(**overrides: Any) -> QueueItem:
    defaults: dict[str, Any] = {
        "id": "abc123def456",
        "output": "/tmp/short.mp4",
        "game_dir": "/tmp/game",
        "status": QueueStatus.RENDERED,
        "queued_at": "2026-04-06T12:00:00Z",
    }
    defaults.update(overrides)
    return QueueItem(**defaults)


# ---------------------------------------------------------------------------
# load_queue / save_queue
# ---------------------------------------------------------------------------


def test_load_queue_empty(tmp_path: Path) -> None:
    q = load_queue(tmp_path)
    assert q.version == 1
    assert q.items == ()


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    item = _make_item(game_dir=str(tmp_path))
    queue = RenderQueue(items=(item,))
    save_queue(queue, tmp_path)

    loaded = load_queue(tmp_path)
    assert len(loaded.items) == 1
    assert loaded.items[0].id == "abc123def456"


def test_save_queue_creates_file(tmp_path: Path) -> None:
    queue = RenderQueue()
    path = save_queue(queue, tmp_path)
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert data["items"] == []


def test_load_queue_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "render_queue.json").write_text("not json")
    with pytest.raises(QueueError, match="Invalid queue file"):
        load_queue(tmp_path)


# ---------------------------------------------------------------------------
# _generate_id / _now_iso
# ---------------------------------------------------------------------------


def test_generate_id_length() -> None:
    assert len(_generate_id()) == 12


def test_generate_id_unique() -> None:
    ids = {_generate_id() for _ in range(100)}
    assert len(ids) == 100


def test_now_iso_format() -> None:
    ts = _now_iso()
    assert "T" in ts
    assert "+" in ts or "Z" in ts or ts.endswith("+00:00")


# ---------------------------------------------------------------------------
# add_to_queue
# ---------------------------------------------------------------------------


def test_add_to_queue(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        item = add_to_queue(
            tmp_path,
            result,
            game_info=_game_info(),
            game_event=_game_event(),
            player="John Smith",
            assists="Jane Doe",
            render_profile="default",
            format_str="1080x1920",
            crop_mode="crop",
            event_id="evt_001",
            available_targets=["google", "meta"],
        )

    assert len(item.id) == 12
    assert item.status is QueueStatus.RENDERED
    assert item.home_team == "North"
    assert item.player == "John Smith"
    assert item.title != ""
    assert item.description != ""
    assert len(item.publish_targets) == 2
    assert item.publish_targets[0].target == "google"
    assert item.publish_targets[0].status is PublishStatus.PENDING

    # Verify persisted
    queue = load_queue(tmp_path)
    assert len(queue.items) == 1
    assert queue.items[0].id == item.id


def test_add_to_queue_no_targets(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        item = add_to_queue(tmp_path, result)
    assert item.publish_targets == ()


def test_add_to_queue_multiple(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        add_to_queue(tmp_path, result)
        add_to_queue(tmp_path, result)
    queue = load_queue(tmp_path)
    assert len(queue.items) == 2
    assert queue.items[0].id != queue.items[1].id


# ---------------------------------------------------------------------------
# _find_item
# ---------------------------------------------------------------------------


def test_find_item_exact() -> None:
    queue = RenderQueue(items=(_make_item(id="abc123def456"),))
    idx, item = _find_item(queue, "abc123def456")
    assert idx == 0
    assert item.id == "abc123def456"


def test_find_item_prefix() -> None:
    queue = RenderQueue(items=(_make_item(id="abc123def456"),))
    idx, _item = _find_item(queue, "abc")
    assert idx == 0


def test_find_item_not_found() -> None:
    queue = RenderQueue(items=(_make_item(id="abc123def456"),))
    with pytest.raises(QueueError, match="not found"):
        _find_item(queue, "xyz")


def test_find_item_ambiguous() -> None:
    queue = RenderQueue(items=(_make_item(id="abc111"), _make_item(id="abc222")))
    with pytest.raises(QueueError, match="Ambiguous"):
        _find_item(queue, "abc")


# ---------------------------------------------------------------------------
# get_queue_item
# ---------------------------------------------------------------------------


def test_get_queue_item_found(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)
    item = get_queue_item(tmp_path, added.id)
    assert item is not None
    assert item.id == added.id


def test_get_queue_item_not_found(tmp_path: Path) -> None:
    assert get_queue_item(tmp_path, "nope") is None


# ---------------------------------------------------------------------------
# update_queue_item
# ---------------------------------------------------------------------------


def test_update_title(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)
    updated = update_queue_item(tmp_path, added.id, title="New Title")
    assert updated.title == "New Title"
    # Verify persisted
    loaded = get_queue_item(tmp_path, added.id)
    assert loaded is not None
    assert loaded.title == "New Title"


def test_update_description(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)
    updated = update_queue_item(tmp_path, added.id, description="New Desc")
    assert updated.description == "New Desc"


def test_update_no_changes(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)
    updated = update_queue_item(tmp_path, added.id)
    assert updated.id == added.id


def test_update_not_found(tmp_path: Path) -> None:
    with pytest.raises(QueueError, match="not found"):
        update_queue_item(tmp_path, "nope", title="x")


# ---------------------------------------------------------------------------
# remove_from_queue
# ---------------------------------------------------------------------------


def test_remove(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)
    removed = remove_from_queue(tmp_path, added.id)
    assert removed.status is QueueStatus.REMOVED
    # Verify persisted
    loaded = get_queue_item(tmp_path, added.id)
    assert loaded is not None
    assert loaded.status is QueueStatus.REMOVED


def test_remove_not_found(tmp_path: Path) -> None:
    with pytest.raises(QueueError, match="not found"):
        remove_from_queue(tmp_path, "nope")


# ---------------------------------------------------------------------------
# discover_targets
# ---------------------------------------------------------------------------


def test_discover_targets() -> None:
    google = MagicMock()
    google.upload = MagicMock()
    meta = MagicMock()
    meta.upload = MagicMock()
    notifier = MagicMock(spec=[])  # no upload method
    plugins: dict[str, object] = {"google": google, "meta": meta, "notifier": notifier}
    targets = discover_targets(plugins)
    assert targets == ["google", "meta"]


def test_discover_targets_empty() -> None:
    assert discover_targets({}) == []


# ---------------------------------------------------------------------------
# publish_queue_item
# ---------------------------------------------------------------------------


def test_publish_single_target(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["google", "meta"]
        )

    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/x")
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins, target="google")
    google.upload.assert_called_once()
    assert published.status is QueueStatus.PARTIAL  # meta still pending
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.PUBLISHED
    assert google_target.url == "https://youtu.be/x"


def test_publish_all_targets(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google"])

    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/x")
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins)
    assert published.status is QueueStatus.PUBLISHED


def test_publish_target_failure(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google"])

    google = MagicMock()
    google.upload = MagicMock(side_effect=RuntimeError("API error"))
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins)
    assert published.status is QueueStatus.FAILED
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.FAILED
    assert "API error" in google_target.error


def test_publish_removed_item_raises(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google"])
    remove_from_queue(tmp_path, added.id)

    with pytest.raises(QueueError, match="Cannot publish removed"):
        publish_queue_item(tmp_path, added.id, {})


def test_publish_missing_output_raises(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)
    # Delete the output file
    Path(added.output).unlink()

    with pytest.raises(QueueError, match="Output file not found"):
        publish_queue_item(tmp_path, added.id, {})


def test_publish_unknown_target_raises(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)

    with pytest.raises(QueueError, match="Unknown or non-uploader"):
        publish_queue_item(tmp_path, added.id, {}, target="nonexistent")


def test_publish_no_pending_targets_raises(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)  # no available_targets

    with pytest.raises(QueueError, match="No pending publish targets"):
        publish_queue_item(tmp_path, added.id, {})


# ---------------------------------------------------------------------------
# publish via POST_RENDER hook (existing plugin pattern)
# ---------------------------------------------------------------------------


def test_publish_via_post_render_hook(tmp_path: Path) -> None:
    """Plugins with on_post_render are published via POST_RENDER hook emission."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google"])

    # Plugin has on_post_render but no upload method
    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins)
    assert published.status is QueueStatus.PUBLISHED
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.PUBLISHED


def test_publish_via_hook_target_flag(tmp_path: Path) -> None:
    """--target works with hook-based plugins."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google", "meta"])

    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins, target="google")
    assert published.status is QueueStatus.PARTIAL  # meta still pending


def test_publish_via_hook_ad_hoc_target(tmp_path: Path) -> None:
    """Hook target not in original publish_targets gets appended."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)  # no available_targets

    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins, target="google")
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.PUBLISHED


def test_publish_via_hook_failure_ad_hoc_target(tmp_path: Path) -> None:
    """Hook failure with ad-hoc target appends failed result."""
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)  # no available_targets

    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    original_emit = get_registry().emit

    def failing_emit(hook: Hook, context: object = None) -> None:
        if hook is Hook.POST_RENDER:
            raise RuntimeError("boom")
        original_emit(hook, context)

    with patch.object(get_registry(), "emit", side_effect=failing_emit):
        published = publish_queue_item(tmp_path, added.id, plugins, target="google")
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.FAILED


def test_publish_via_hook_failure(tmp_path: Path) -> None:
    """POST_RENDER emission failure marks hook targets as failed."""
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google"])

    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    # Make the registry emit raise only for POST_RENDER
    original_emit = get_registry().emit

    def failing_emit(hook: Hook, context: object = None) -> None:
        if hook is Hook.POST_RENDER:
            raise RuntimeError("hook boom")
        original_emit(hook, context)

    with patch.object(get_registry(), "emit", side_effect=failing_emit):
        published = publish_queue_item(tmp_path, added.id, plugins)
    assert published.status is QueueStatus.FAILED
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.FAILED
    assert "hook boom" in google_target.error


# ---------------------------------------------------------------------------
# discover_targets — both patterns
# ---------------------------------------------------------------------------


def test_discover_targets_hook_based() -> None:
    """Plugins with on_post_render are discovered as targets."""
    google = MagicMock(spec=["on_post_render", "name"])
    meta = MagicMock(spec=["on_post_render", "name"])
    notifier = MagicMock(spec=["on_game_init", "name"])
    plugins: dict[str, object] = {"google": google, "meta": meta, "notifier": notifier}
    targets = discover_targets(plugins)
    assert targets == ["google", "meta"]


def test_discover_targets_mixed() -> None:
    """Both upload-protocol and hook-based plugins are discovered."""
    uploader = MagicMock()
    uploader.upload = MagicMock()
    hook_plugin = MagicMock(spec=["on_post_render", "name"])
    plugins: dict[str, object] = {"uploader": uploader, "hook": hook_plugin}
    targets = discover_targets(plugins)
    assert targets == ["hook", "uploader"]


# ---------------------------------------------------------------------------
# publish_all
# ---------------------------------------------------------------------------


def test_publish_all(tmp_path: Path) -> None:
    result = _render_result(tmp_path)
    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/1")
    plugins: dict[str, object] = {"google": google}

    with patch("reeln.core.queue.update_queue_index"):
        add_to_queue(tmp_path, result, available_targets=["google"])
        add_to_queue(tmp_path, result, available_targets=["google"])

    published = publish_all(tmp_path, plugins)
    assert len(published) == 2
    assert all(p.status is QueueStatus.PUBLISHED for p in published)


def test_publish_all_empty(tmp_path: Path) -> None:
    results = publish_all(tmp_path, {})
    assert results == []


# ---------------------------------------------------------------------------
# Queue index
# ---------------------------------------------------------------------------


def test_update_and_load_index(tmp_path: Path) -> None:
    with patch("reeln.core.config.data_dir", return_value=tmp_path):
        update_queue_index(Path("/fake/game1"))
        update_queue_index(Path("/fake/game2"))
        update_queue_index(Path("/fake/game1"))  # duplicate

        index = load_queue_index()
    assert index == ["/fake/game1", "/fake/game2"]


def test_load_index_empty(tmp_path: Path) -> None:
    with patch("reeln.core.config.data_dir", return_value=tmp_path):
        index = load_queue_index()
    assert index == []


def test_load_index_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "queue_index.json").write_text("bad")
    with patch("reeln.core.config.data_dir", return_value=tmp_path):
        index = load_queue_index()
    assert index == []


# ---------------------------------------------------------------------------
# save_queue failure cleanup
# ---------------------------------------------------------------------------


def test_save_queue_cleans_up_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Atomic write cleans up temp file on failure."""

    def failing_replace(self: Path, target: str | Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        save_queue(RenderQueue(), tmp_path)

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


# ---------------------------------------------------------------------------
# update_queue_index failure cleanup
# ---------------------------------------------------------------------------


def test_update_index_cleans_up_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Atomic index write cleans up temp file on failure."""

    def failing_replace(self: Path, target: str | Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"), patch("reeln.core.config.data_dir", return_value=tmp_path):
        update_queue_index(Path("/fake/game"))

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


# ---------------------------------------------------------------------------
# publish: ad-hoc target not in existing publish_targets
# ---------------------------------------------------------------------------


def test_publish_ad_hoc_target(tmp_path: Path) -> None:
    """Publishing to a target not in the item's publish_targets list appends it."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)  # no available_targets

    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/x")
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins, target="google")
    # The ad-hoc target should be appended
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.PUBLISHED


# ---------------------------------------------------------------------------
# publish: mixed statuses (PARTIAL overall via else branch)
# ---------------------------------------------------------------------------


def test_publish_mixed_pending_and_failed(tmp_path: Path) -> None:
    """When one target fails and another is still pending, overall is PARTIAL."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["google", "meta"]
        )

    google = MagicMock()
    google.upload = MagicMock(side_effect=RuntimeError("fail"))
    plugins: dict[str, object] = {"google": google}

    # Publish only google (which fails), meta stays pending
    published = publish_queue_item(tmp_path, added.id, plugins, target="google")
    assert published.status is QueueStatus.PARTIAL


# ---------------------------------------------------------------------------
# _reconstruct helpers
# ---------------------------------------------------------------------------


def test_publish_with_game_context(tmp_path: Path) -> None:
    """Publish with game info and event context reconstructs metadata."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path,
            result,
            game_info=_game_info(),
            game_event=_game_event(),
            player="John",
            assists="Jane",
            event_id="evt_001",
            available_targets=["google"],
            plugin_inputs={"thumb": "/tmp/t.png"},
        )

    # Use hook-based plugin to exercise the POST_RENDER path with full context
    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins)
    assert published.status is QueueStatus.PUBLISHED


def test_find_target_idx_empty_list() -> None:
    """Cover the _find_target_idx function with empty targets list."""
    from reeln.core.queue import _find_target_idx

    assert _find_target_idx([], "google") is None


def test_find_target_idx_no_match() -> None:
    """Cover the branch where target_name doesn't match any entry."""
    from reeln.core.queue import _find_target_idx
    from reeln.models.queue import PublishTargetResult

    targets = [PublishTargetResult(target="meta"), PublishTargetResult(target="tiktok")]
    assert _find_target_idx(targets, "google") is None


def test_find_target_idx_match() -> None:
    """Cover the branch where target_name matches."""
    from reeln.core.queue import _find_target_idx
    from reeln.models.queue import PublishTargetResult

    targets = [PublishTargetResult(target="meta"), PublishTargetResult(target="google")]
    assert _find_target_idx(targets, "google") == 1


# ---------------------------------------------------------------------------
# publish: target pending but plugin not available (skips the target)
# ---------------------------------------------------------------------------


def test_publish_all_targets_skips_unavailable(tmp_path: Path) -> None:
    """Pending targets whose plugins aren't loaded are skipped."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["google", "meta"]
        )

    # Only provide google plugin, not meta
    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/x")
    plugins: dict[str, object] = {"google": google}

    # Publish all pending → only google gets published, meta stays pending
    published = publish_queue_item(tmp_path, added.id, plugins)
    assert published.status is QueueStatus.PARTIAL


# ---------------------------------------------------------------------------
# publish_all: queue with non-rendered items (skipped)
# ---------------------------------------------------------------------------


def test_publish_all_skips_non_rendered(tmp_path: Path) -> None:
    """publish_all only publishes RENDERED items, skips others."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google"])
        # Mark it as removed
        remove_from_queue(tmp_path, added.id)

    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/x")
    plugins: dict[str, object] = {"google": google}

    results = publish_all(tmp_path, plugins)
    assert results == []  # nothing published since item is REMOVED
