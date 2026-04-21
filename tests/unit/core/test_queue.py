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
    PublishTargetResult,
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


def _render_result(
    tmp_path: Path, output_name: str = "short.mp4"
) -> RenderResult:
    out = tmp_path / output_name
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


def test_add_to_queue_multiple_different_files(tmp_path: Path) -> None:
    """Adding two items with DIFFERENT output files keeps both active."""
    result_a = _render_result(tmp_path, output_name="a.mp4")
    result_b = _render_result(tmp_path, output_name="b.mp4")
    with patch("reeln.core.queue.update_queue_index"):
        item_a = add_to_queue(tmp_path, result_a)
        item_b = add_to_queue(tmp_path, result_b)
    queue = load_queue(tmp_path)
    assert len(queue.items) == 2
    assert queue.items[0].id != queue.items[1].id
    assert all(i.status is QueueStatus.RENDERED for i in queue.items)
    assert {i.id for i in queue.items} == {item_a.id, item_b.id}


def test_add_to_queue_same_file_supersedes_prior_unpublished(
    tmp_path: Path,
) -> None:
    """Re-rendering the same clip soft-deletes the prior unpublished entry.

    REGRESSION: without this, the dock's game-level "Publish All" would
    iterate both items and upload the same file twice, producing
    duplicate IG Reels / YouTube videos / TikTok posts. See commit
    message for the production incident.
    """
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        first = add_to_queue(tmp_path, result)
        second = add_to_queue(tmp_path, result)
    queue = load_queue(tmp_path)

    # Two items total but only the second is active.
    assert len(queue.items) == 2
    by_id = {i.id: i for i in queue.items}
    assert by_id[first.id].status is QueueStatus.REMOVED
    assert by_id[second.id].status is QueueStatus.RENDERED

    # publish_all only iterates RENDERED items, so it would only publish
    # `second`. Verify this is observable.
    rendered_ids = [
        i.id for i in queue.items if i.status is QueueStatus.RENDERED
    ]
    assert rendered_ids == [second.id]


def test_add_to_queue_same_file_preserves_published_item(
    tmp_path: Path,
) -> None:
    """An already-published item with the same output file is NOT
    superseded. Published items are kept as historical records and
    their status already prevents re-publishing."""
    from dataclasses import replace as _replace

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        first = add_to_queue(tmp_path, result, available_targets=["google"])

    # Manually mark the first item as PUBLISHED (simulating a successful publish).
    queue = load_queue(tmp_path)
    published_first = _replace(
        queue.items[0],
        status=QueueStatus.PUBLISHED,
        publish_targets=(
            PublishTargetResult(
                target="google",
                status=PublishStatus.PUBLISHED,
                url="https://youtu.be/x",
            ),
        ),
    )
    from reeln.core.queue import save_queue
    from reeln.models.queue import RenderQueue

    save_queue(
        RenderQueue(version=queue.version, items=(published_first,)),
        tmp_path,
    )

    # Re-render the same clip.
    with patch("reeln.core.queue.update_queue_index"):
        second = add_to_queue(tmp_path, result, available_targets=["google"])

    queue = load_queue(tmp_path)
    # Published item preserved as-is, new item added alongside.
    assert len(queue.items) == 2
    by_id = {i.id: i for i in queue.items}
    assert by_id[first.id].status is QueueStatus.PUBLISHED
    assert by_id[first.id].publish_targets[0].url == "https://youtu.be/x"
    assert by_id[second.id].status is QueueStatus.RENDERED


def test_add_to_queue_same_file_skips_already_removed(
    tmp_path: Path,
) -> None:
    """Existing REMOVED items aren't touched (idempotent no-op)."""
    from dataclasses import replace as _replace

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        first = add_to_queue(tmp_path, result)

    queue = load_queue(tmp_path)
    removed_first = _replace(queue.items[0], status=QueueStatus.REMOVED)
    from reeln.core.queue import save_queue
    from reeln.models.queue import RenderQueue

    save_queue(
        RenderQueue(version=queue.version, items=(removed_first,)),
        tmp_path,
    )

    with patch("reeln.core.queue.update_queue_index"):
        second = add_to_queue(tmp_path, result)

    queue = load_queue(tmp_path)
    assert len(queue.items) == 2
    by_id = {i.id: i for i in queue.items}
    # First stays REMOVED (wasn't re-touched).
    assert by_id[first.id].status is QueueStatus.REMOVED
    assert by_id[second.id].status is QueueStatus.RENDERED


def test_add_to_queue_same_file_supersedes_multiple(
    tmp_path: Path,
) -> None:
    """Adding a third render with the same file supersedes BOTH prior
    unpublished items. Models the real user scenario where they rendered
    Ben Remitz's goal three times."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        first = add_to_queue(tmp_path, result)
        second = add_to_queue(tmp_path, result)
        third = add_to_queue(tmp_path, result)

    queue = load_queue(tmp_path)
    assert len(queue.items) == 3
    by_id = {i.id: i for i in queue.items}
    assert by_id[first.id].status is QueueStatus.REMOVED
    assert by_id[second.id].status is QueueStatus.REMOVED
    assert by_id[third.id].status is QueueStatus.RENDERED

    # Only the third is rendered, so publish_all only publishes once.
    rendered = [i for i in queue.items if i.status is QueueStatus.RENDERED]
    assert len(rendered) == 1
    assert rendered[0].id == third.id


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


def test_publish_hook_only_plugin_marked_skipped(tmp_path: Path) -> None:
    """Plugins with only on_post_render are SKIPPED by manual publish.

    Manual publish (``reeln queue publish``) requires the Uploader protocol
    (``upload()`` method). Hook-only plugins still fire during ``reeln render``
    via POST_RENDER, but they are not invoked from manual publish — they are
    marked SKIPPED with an explanatory reason instead of being lied about.
    """
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google"])

    # Plugin has on_post_render but no upload method
    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins)
    # All targets skipped → item stays RENDERED (re-publishable later).
    assert published.status is QueueStatus.RENDERED
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.SKIPPED
    assert "upload()" in google_target.error
    # on_post_render should NOT have been invoked — manual publish no longer
    # emits POST_RENDER.
    google.on_post_render.assert_not_called()


def test_publish_via_hook_target_flag(tmp_path: Path) -> None:
    """--target with a hook-only plugin marks it SKIPPED, not PUBLISHED."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google", "meta"])

    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins, target="google")
    # google is SKIPPED, meta is still PENDING → mixed state: PARTIAL.
    # (SKIPPED is excluded from the overall decision, leaving {PENDING} which
    # falls through to the PARTIAL fallback.)
    assert published.status is QueueStatus.PARTIAL
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.SKIPPED
    meta_target = next(t for t in published.publish_targets if t.target == "meta")
    assert meta_target.status is PublishStatus.PENDING


def test_publish_hook_only_ad_hoc_target_marked_skipped(tmp_path: Path) -> None:
    """Ad-hoc hook-only target gets appended with SKIPPED status."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result)  # no available_targets

    google = MagicMock(spec=["on_post_render", "name"])
    google.name = "google"
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins, target="google")
    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.SKIPPED
    assert "upload()" in google_target.error


# ---------------------------------------------------------------------------
# UploaderSkipped + SKIPPED-aware overall status
# ---------------------------------------------------------------------------


def test_publish_uploader_skipped_marked_skipped(tmp_path: Path) -> None:
    """An UploaderSkipped exception maps to PublishStatus.SKIPPED, not FAILED."""
    from reeln.plugins.capabilities import UploaderSkipped

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(tmp_path, result, available_targets=["google"])

    google = MagicMock()
    google.upload = MagicMock(
        side_effect=UploaderSkipped("upload_video disabled"),
    )
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins)

    google_target = next(t for t in published.publish_targets if t.target == "google")
    assert google_target.status is PublishStatus.SKIPPED
    assert "disabled" in google_target.error
    # All-skipped case → overall is RENDERED so the item remains re-publishable.
    assert published.status is QueueStatus.RENDERED


def test_publish_uploader_skipped_vs_failed_separation(tmp_path: Path) -> None:
    """UploaderSkipped and general Exception produce distinct statuses."""
    from reeln.plugins.capabilities import UploaderSkipped

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["google", "meta"]
        )

    google = MagicMock()
    google.upload = MagicMock(side_effect=UploaderSkipped("disabled"))
    meta = MagicMock()
    meta.upload = MagicMock(side_effect=RuntimeError("boom"))
    plugins: dict[str, object] = {"google": google, "meta": meta}

    published = publish_queue_item(tmp_path, added.id, plugins)

    google_target = next(t for t in published.publish_targets if t.target == "google")
    meta_target = next(t for t in published.publish_targets if t.target == "meta")
    assert google_target.status is PublishStatus.SKIPPED
    assert meta_target.status is PublishStatus.FAILED
    assert "boom" in meta_target.error
    # Non-skipped set is {FAILED} → overall is FAILED.
    assert published.status is QueueStatus.FAILED


def test_publish_overall_status_published_plus_skipped(tmp_path: Path) -> None:
    """Skipped targets don't drag a successful publish down to PARTIAL."""
    from reeln.plugins.capabilities import UploaderSkipped

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["google", "meta"]
        )

    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/good")
    meta = MagicMock()
    meta.upload = MagicMock(side_effect=UploaderSkipped("not configured"))
    plugins: dict[str, object] = {"google": google, "meta": meta}

    published = publish_queue_item(tmp_path, added.id, plugins)

    google_target = next(t for t in published.publish_targets if t.target == "google")
    meta_target = next(t for t in published.publish_targets if t.target == "meta")
    assert google_target.status is PublishStatus.PUBLISHED
    assert google_target.url == "https://youtu.be/good"
    assert meta_target.status is PublishStatus.SKIPPED
    # Non-skipped set is {PUBLISHED} → overall is PUBLISHED (not PARTIAL).
    assert published.status is QueueStatus.PUBLISHED


def test_publish_hook_only_plus_real_uploader_mixed(tmp_path: Path) -> None:
    """Mixing a real uploader with a hook-only plugin yields PUBLISHED overall."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["google", "meta"]
        )

    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/real")
    # Hook-only plugin — no upload() method
    meta = MagicMock(spec=["on_post_render", "name"])
    meta.name = "meta"
    plugins: dict[str, object] = {"google": google, "meta": meta}

    published = publish_queue_item(tmp_path, added.id, plugins)

    google_target = next(t for t in published.publish_targets if t.target == "google")
    meta_target = next(t for t in published.publish_targets if t.target == "meta")
    assert google_target.status is PublishStatus.PUBLISHED
    assert meta_target.status is PublishStatus.SKIPPED
    assert "upload()" in meta_target.error
    # Overall: PUBLISHED (non-skipped set is {PUBLISHED}).
    assert published.status is QueueStatus.PUBLISHED
    # The hook-only plugin should NOT have been invoked.
    meta.on_post_render.assert_not_called()


def test_publish_enriches_metadata_with_format_and_render_profile(
    tmp_path: Path,
) -> None:
    """QueueItem.format and render_profile flow into upload() metadata.

    Regression for the enrichment logic that lets google/tiktok detect
    portrait vs landscape without the original render plan.
    """
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path,
            result,
            format_str="1080x1920",
            render_profile="player-overlay",
            available_targets=["google"],
        )

    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/x")
    plugins: dict[str, object] = {"google": google}

    publish_queue_item(tmp_path, added.id, plugins)

    call_metadata = google.upload.call_args.kwargs["metadata"]
    assert call_metadata["format"] == "1080x1920"
    assert call_metadata["render_profile"] == "player-overlay"
    assert call_metadata["duration_seconds"] == 15.0


def test_publish_omits_duration_when_queue_item_has_none(
    tmp_path: Path,
) -> None:
    """When QueueItem.duration_seconds is None, metadata omits the key
    rather than including a ``None`` value. Covers the negative branch
    of the duration_seconds enrichment."""
    from reeln.models.render_plan import RenderResult

    out = tmp_path / "short.mp4"
    out.write_bytes(b"fake")
    result = RenderResult(
        output=out, duration_seconds=None, file_size_bytes=1024
    )

    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path,
            result,
            format_str="1080x1920",
            available_targets=["google"],
        )

    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/x")
    plugins: dict[str, object] = {"google": google}

    publish_queue_item(tmp_path, added.id, plugins)

    call_metadata = google.upload.call_args.kwargs["metadata"]
    assert "duration_seconds" not in call_metadata


def test_publish_seeds_video_url_from_already_published_target(
    tmp_path: Path,
) -> None:
    """Per-target retry on meta consumes cloudflare's already-stored URL.

    Scenario: user clicked Publish All earlier → cloudflare succeeded and
    stored https://cdn/foo.mp4; google/meta were skipped due to config.
    User flipped meta config on and clicked Retry (target="meta") — the
    CLI is only invoked for meta, so cloudflare isn't re-run in THIS
    publish call. Without seeding, meta's upload() would raise
    UploaderSkipped("Meta Reels require metadata['video_url']...").
    With seeding, meta picks up cloudflare's stored URL and publishes.
    """
    from reeln.models.queue import PublishTargetResult

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["cloudflare", "meta"]
        )

    # Mutate the stored queue so cloudflare is already PUBLISHED with a URL
    from reeln.core.queue import load_queue, save_queue
    from reeln.models.queue import RenderQueue

    q = load_queue(tmp_path)
    from dataclasses import replace as _replace
    updated_item = _replace(
        q.items[0],
        publish_targets=(
            PublishTargetResult(
                target="cloudflare",
                status=PublishStatus.PUBLISHED,
                url="https://cdn.example.com/clip.mp4",
                published_at="2026-04-10T12:00:00Z",
            ),
            PublishTargetResult(
                target="meta", status=PublishStatus.PENDING
            ),
        ),
    )
    save_queue(
        RenderQueue(version=q.version, items=(updated_item,)), tmp_path
    )

    meta = MagicMock()
    meta.upload = MagicMock(
        return_value="https://instagram.com/reel/abc"
    )
    plugins: dict[str, object] = {"meta": meta}

    published = publish_queue_item(
        tmp_path, added.id, plugins, target="meta"
    )

    # Meta was called with the cloudflare-seeded video_url in metadata
    meta.upload.assert_called_once()
    call_metadata = meta.upload.call_args.kwargs["metadata"]
    assert call_metadata["video_url"] == "https://cdn.example.com/clip.mp4"
    # Meta target is now PUBLISHED
    meta_target = next(
        t for t in published.publish_targets if t.target == "meta"
    )
    assert meta_target.status is PublishStatus.PUBLISHED
    assert meta_target.url == "https://instagram.com/reel/abc"


def test_publish_seeds_video_url_skips_non_http_sentinels(
    tmp_path: Path,
) -> None:
    """Non-HTTP sentinel URLs (e.g. tiktok:v_inbox_url~...) must not be
    threaded as video_url — they're publication identifiers, not
    hosted-file URLs, and would break meta's Reel API."""
    from reeln.models.queue import PublishTargetResult

    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["tiktok", "meta"]
        )

    from reeln.core.queue import load_queue, save_queue
    from reeln.models.queue import RenderQueue

    q = load_queue(tmp_path)
    from dataclasses import replace as _replace
    updated_item = _replace(
        q.items[0],
        publish_targets=(
            PublishTargetResult(
                target="tiktok",
                status=PublishStatus.PUBLISHED,
                url="tiktok:v_inbox_url~v2.76273563",
            ),
            PublishTargetResult(
                target="meta", status=PublishStatus.PENDING
            ),
        ),
    )
    save_queue(
        RenderQueue(version=q.version, items=(updated_item,)), tmp_path
    )

    meta = MagicMock()
    meta.upload = MagicMock(return_value="https://instagram.com/reel/abc")
    plugins: dict[str, object] = {"meta": meta}

    publish_queue_item(tmp_path, added.id, plugins, target="meta")

    call_metadata = meta.upload.call_args.kwargs["metadata"]
    # tiktok sentinel URL was NOT used as video_url
    assert "video_url" not in call_metadata


def test_publish_hook_only_and_failed_uploader_partial(tmp_path: Path) -> None:
    """When a real uploader fails and the other target is hook-only (skipped), overall is FAILED."""
    result = _render_result(tmp_path)
    with patch("reeln.core.queue.update_queue_index"):
        added = add_to_queue(
            tmp_path, result, available_targets=["google", "meta"]
        )

    google = MagicMock()
    google.upload = MagicMock(side_effect=RuntimeError("API down"))
    meta = MagicMock(spec=["on_post_render", "name"])
    meta.name = "meta"
    plugins: dict[str, object] = {"google": google, "meta": meta}

    published = publish_queue_item(tmp_path, added.id, plugins)

    google_target = next(t for t in published.publish_targets if t.target == "google")
    meta_target = next(t for t in published.publish_targets if t.target == "meta")
    assert google_target.status is PublishStatus.FAILED
    assert "API down" in google_target.error
    assert meta_target.status is PublishStatus.SKIPPED
    # Non-skipped set is {FAILED} → overall is FAILED.
    assert published.status is QueueStatus.FAILED


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
    # Use DIFFERENT output files so add_to_queue's dedup doesn't
    # supersede the first item. Each call simulates a distinct clip.
    result_a = _render_result(tmp_path, output_name="a.mp4")
    result_b = _render_result(tmp_path, output_name="b.mp4")
    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/1")
    plugins: dict[str, object] = {"google": google}

    with patch("reeln.core.queue.update_queue_index"):
        add_to_queue(tmp_path, result_a, available_targets=["google"])
        add_to_queue(tmp_path, result_b, available_targets=["google"])

    published = publish_all(tmp_path, plugins)
    assert len(published) == 2
    assert all(p.status is QueueStatus.PUBLISHED for p in published)


def test_publish_all_same_file_dedup_prevents_duplicate_uploads(
    tmp_path: Path,
) -> None:
    """REGRESSION: publish_all must not upload the same file twice when
    the user re-renders the same clip (which accumulates queue items
    pointing at the same output path). add_to_queue soft-deletes the
    prior unpublished item, so publish_all only sees one RENDERED item.

    This is the root cause of the "Ben Remitz goal uploaded to IG
    three times" production incident.
    """
    # Same file, called three times (simulating the user rendering the
    # same clip three times to tweak titles/overlays).
    result = _render_result(tmp_path)
    google = MagicMock()
    google.upload = MagicMock(return_value="https://youtu.be/unique")
    plugins: dict[str, object] = {"google": google}

    with patch("reeln.core.queue.update_queue_index"):
        add_to_queue(tmp_path, result, available_targets=["google"])
        add_to_queue(tmp_path, result, available_targets=["google"])
        add_to_queue(tmp_path, result, available_targets=["google"])

    published = publish_all(tmp_path, plugins)

    # Only ONE publish — not three.
    assert len(published) == 1
    assert google.upload.call_count == 1
    assert published[0].status is QueueStatus.PUBLISHED


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

    # Use an Uploader-protocol plugin so the full metadata round-trip is
    # exercised through the real publish path (manual publish only goes
    # through upload() now).
    google = MagicMock()
    google.name = "google"
    google.upload = MagicMock(return_value="https://youtu.be/context")
    plugins: dict[str, object] = {"google": google}

    published = publish_queue_item(tmp_path, added.id, plugins)
    assert published.status is QueueStatus.PUBLISHED
    # Confirm the metadata dict reached the plugin with the expected keys
    # from the reconstructed game context.
    google.upload.assert_called_once()
    call_metadata = google.upload.call_args.kwargs["metadata"]
    assert call_metadata["player"] == "John"
    assert call_metadata["assists"] == "Jane"
    assert call_metadata["event_id"] == "evt_001"
    assert call_metadata["plugin_inputs"] == {"thumb": "/tmp/t.png"}


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
