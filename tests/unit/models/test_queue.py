"""Tests for queue data models."""

from __future__ import annotations

import pytest

from reeln.models.queue import (
    PublishStatus,
    PublishTargetResult,
    QueueItem,
    QueueStatus,
    RenderQueue,
    dict_to_publish_target_result,
    dict_to_queue_item,
    dict_to_render_queue,
    publish_target_result_to_dict,
    queue_item_to_dict,
    render_queue_to_dict,
)

# ---------------------------------------------------------------------------
# QueueStatus enum
# ---------------------------------------------------------------------------


def test_queue_status_values() -> None:
    assert QueueStatus.RENDERED.value == "rendered"
    assert QueueStatus.PUBLISHING.value == "publishing"
    assert QueueStatus.PUBLISHED.value == "published"
    assert QueueStatus.PARTIAL.value == "partial"
    assert QueueStatus.FAILED.value == "failed"
    assert QueueStatus.REMOVED.value == "removed"


def test_queue_status_from_string() -> None:
    assert QueueStatus("rendered") is QueueStatus.RENDERED
    assert QueueStatus("published") is QueueStatus.PUBLISHED


def test_queue_status_invalid() -> None:
    with pytest.raises(ValueError, match="not_a_status"):
        QueueStatus("not_a_status")


# ---------------------------------------------------------------------------
# PublishStatus enum
# ---------------------------------------------------------------------------


def test_publish_status_values() -> None:
    assert PublishStatus.PENDING.value == "pending"
    assert PublishStatus.PUBLISHED.value == "published"
    assert PublishStatus.FAILED.value == "failed"
    assert PublishStatus.SKIPPED.value == "skipped"


def test_publish_status_from_string() -> None:
    assert PublishStatus("pending") is PublishStatus.PENDING
    assert PublishStatus("failed") is PublishStatus.FAILED


def test_publish_status_invalid() -> None:
    with pytest.raises(ValueError, match="bad"):
        PublishStatus("bad")


# ---------------------------------------------------------------------------
# PublishTargetResult
# ---------------------------------------------------------------------------


def test_publish_target_result_required() -> None:
    ptr = PublishTargetResult(target="google")
    assert ptr.target == "google"
    assert ptr.status is PublishStatus.PENDING
    assert ptr.url == ""
    assert ptr.error == ""
    assert ptr.published_at == ""


def test_publish_target_result_full() -> None:
    ptr = PublishTargetResult(
        target="meta",
        status=PublishStatus.PUBLISHED,
        url="https://instagram.com/reel/abc",
        published_at="2026-04-06T12:00:00Z",
    )
    assert ptr.target == "meta"
    assert ptr.status is PublishStatus.PUBLISHED
    assert ptr.url == "https://instagram.com/reel/abc"
    assert ptr.published_at == "2026-04-06T12:00:00Z"


def test_publish_target_result_frozen() -> None:
    ptr = PublishTargetResult(target="google")
    with pytest.raises(AttributeError):
        ptr.target = "meta"  # type: ignore[misc]


def test_publish_target_result_roundtrip() -> None:
    ptr = PublishTargetResult(
        target="google",
        status=PublishStatus.FAILED,
        error="API quota exceeded",
    )
    d = publish_target_result_to_dict(ptr)
    restored = dict_to_publish_target_result(d)
    assert restored == ptr


def test_publish_target_result_from_dict_defaults() -> None:
    ptr = dict_to_publish_target_result({"target": "tiktok"})
    assert ptr.target == "tiktok"
    assert ptr.status is PublishStatus.PENDING
    assert ptr.url == ""
    assert ptr.error == ""
    assert ptr.published_at == ""


# ---------------------------------------------------------------------------
# QueueItem
# ---------------------------------------------------------------------------


def _make_item(**overrides: object) -> QueueItem:
    defaults: dict[str, object] = {
        "id": "abc123def456",
        "output": "/tmp/short.mp4",
        "game_dir": "/tmp/game",
        "status": QueueStatus.RENDERED,
        "queued_at": "2026-04-06T12:00:00Z",
    }
    defaults.update(overrides)
    return QueueItem(**defaults)  # type: ignore[arg-type]


def test_queue_item_required_fields() -> None:
    item = _make_item()
    assert item.id == "abc123def456"
    assert item.output == "/tmp/short.mp4"
    assert item.game_dir == "/tmp/game"
    assert item.status is QueueStatus.RENDERED
    assert item.queued_at == "2026-04-06T12:00:00Z"


def test_queue_item_defaults() -> None:
    item = _make_item()
    assert item.duration_seconds is None
    assert item.file_size_bytes is None
    assert item.format == ""
    assert item.crop_mode == ""
    assert item.render_profile == ""
    assert item.event_id == ""
    assert item.home_team == ""
    assert item.away_team == ""
    assert item.date == ""
    assert item.sport == ""
    assert item.level == ""
    assert item.tournament == ""
    assert item.event_type == ""
    assert item.player == ""
    assert item.assists == ""
    assert item.title == ""
    assert item.description == ""
    assert item.publish_targets == ()
    assert item.config_profile == ""
    assert item.plugin_inputs == {}


def test_queue_item_full() -> None:
    targets = (
        PublishTargetResult(target="google", status=PublishStatus.PUBLISHED, url="https://youtu.be/x"),
        PublishTargetResult(target="meta", status=PublishStatus.PENDING),
    )
    item = _make_item(
        duration_seconds=15.5,
        file_size_bytes=1024000,
        format="1080x1920",
        crop_mode="crop",
        render_profile="default",
        event_id="evt_001",
        home_team="North",
        away_team="South",
        date="2026-04-06",
        sport="hockey",
        level="2016",
        tournament="Spring Cup",
        event_type="goal",
        player="John Smith",
        assists="Jane Doe, Bob Jones",
        title="John Smith Goal - North vs South",
        description="Spring Cup 2016",
        publish_targets=targets,
        plugin_inputs={"thumbnail_image": "/tmp/thumb.png"},
    )
    assert item.duration_seconds == 15.5
    assert item.file_size_bytes == 1024000
    assert item.home_team == "North"
    assert len(item.publish_targets) == 2
    assert item.publish_targets[0].url == "https://youtu.be/x"
    assert item.plugin_inputs["thumbnail_image"] == "/tmp/thumb.png"


def test_queue_item_frozen() -> None:
    item = _make_item()
    with pytest.raises(AttributeError):
        item.title = "new"  # type: ignore[misc]


def test_queue_item_roundtrip() -> None:
    targets = (
        PublishTargetResult(target="google", status=PublishStatus.PUBLISHED, url="https://youtu.be/x"),
        PublishTargetResult(target="meta", status=PublishStatus.PENDING),
    )
    item = _make_item(
        duration_seconds=15.5,
        file_size_bytes=1024000,
        format="1080x1920",
        crop_mode="crop",
        home_team="North",
        away_team="South",
        player="John",
        title="Title",
        description="Desc",
        publish_targets=targets,
        plugin_inputs={"key": "val"},
    )
    d = queue_item_to_dict(item)
    restored = dict_to_queue_item(d)
    assert restored.id == item.id
    assert restored.output == item.output
    assert restored.game_dir == item.game_dir
    assert restored.status == item.status
    assert restored.queued_at == item.queued_at
    assert restored.duration_seconds == item.duration_seconds
    assert restored.file_size_bytes == item.file_size_bytes
    assert restored.format == item.format
    assert restored.crop_mode == item.crop_mode
    assert restored.home_team == item.home_team
    assert restored.away_team == item.away_team
    assert restored.player == item.player
    assert restored.title == item.title
    assert restored.description == item.description
    assert len(restored.publish_targets) == 2
    assert restored.publish_targets[0] == targets[0]
    assert restored.publish_targets[1] == targets[1]
    assert restored.plugin_inputs == item.plugin_inputs


def test_queue_item_from_dict_defaults() -> None:
    item = dict_to_queue_item({
        "id": "x",
        "output": "/tmp/out.mp4",
        "game_dir": "/tmp/g",
    })
    assert item.id == "x"
    assert item.status is QueueStatus.RENDERED
    assert item.queued_at == ""
    assert item.duration_seconds is None
    assert item.publish_targets == ()
    assert item.plugin_inputs == {}


def test_queue_item_to_dict_structure() -> None:
    item = _make_item(title="My Title")
    d = queue_item_to_dict(item)
    assert d["id"] == "abc123def456"
    assert d["status"] == "rendered"
    assert d["title"] == "My Title"
    assert isinstance(d["publish_targets"], list)
    assert isinstance(d["plugin_inputs"], dict)


# ---------------------------------------------------------------------------
# RenderQueue
# ---------------------------------------------------------------------------


def test_render_queue_defaults() -> None:
    q = RenderQueue()
    assert q.version == 1
    assert q.items == ()


def test_render_queue_with_items() -> None:
    item = _make_item()
    q = RenderQueue(items=(item,))
    assert len(q.items) == 1
    assert q.items[0].id == "abc123def456"


def test_render_queue_frozen() -> None:
    q = RenderQueue()
    with pytest.raises(AttributeError):
        q.version = 2  # type: ignore[misc]


def test_render_queue_roundtrip() -> None:
    items = (_make_item(id="a"), _make_item(id="b"))
    q = RenderQueue(version=1, items=items)
    d = render_queue_to_dict(q)
    restored = dict_to_render_queue(d)
    assert restored.version == q.version
    assert len(restored.items) == 2
    assert restored.items[0].id == "a"
    assert restored.items[1].id == "b"


def test_render_queue_from_dict_defaults() -> None:
    q = dict_to_render_queue({})
    assert q.version == 1
    assert q.items == ()


def test_render_queue_to_dict_structure() -> None:
    q = RenderQueue(items=(_make_item(),))
    d = render_queue_to_dict(q)
    assert d["version"] == 1
    assert len(d["items"]) == 1
    assert d["items"][0]["id"] == "abc123def456"
