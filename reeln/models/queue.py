"""Queue data models for staged render-then-publish workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QueueStatus(Enum):
    """Lifecycle status of a queue item."""

    RENDERED = "rendered"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PARTIAL = "partial"
    FAILED = "failed"
    REMOVED = "removed"


class PublishStatus(Enum):
    """Status of a single publish target."""

    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class PublishTargetResult:
    """Outcome of publishing to a single target."""

    target: str
    status: PublishStatus = PublishStatus.PENDING
    url: str = ""
    error: str = ""
    published_at: str = ""


@dataclass(frozen=True)
class QueueItem:
    """A rendered clip queued for review and selective publishing."""

    id: str
    output: str
    game_dir: str
    status: QueueStatus
    queued_at: str

    # Render metadata (snapshotted at queue time)
    duration_seconds: float | None = None
    file_size_bytes: int | None = None
    format: str = ""
    crop_mode: str = ""
    render_profile: str = ""
    event_id: str = ""

    # Game context (snapshotted from GameInfo/GameEvent)
    home_team: str = ""
    away_team: str = ""
    date: str = ""
    sport: str = ""
    level: str = ""
    tournament: str = ""
    event_type: str = ""
    player: str = ""
    assists: str = ""

    # Editable publish metadata
    title: str = ""
    description: str = ""

    # Per-target publish tracking
    publish_targets: tuple[PublishTargetResult, ...] = ()

    # Config profile used at queue time (loaded at publish time)
    config_profile: str = ""

    # Plugin inputs passed through
    plugin_inputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderQueue:
    """Container for queue items persisted to render_queue.json."""

    version: int = 1
    items: tuple[QueueItem, ...] = ()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def publish_target_result_to_dict(ptr: PublishTargetResult) -> dict[str, Any]:
    """Serialize a ``PublishTargetResult`` to a JSON-compatible dict."""
    return {
        "target": ptr.target,
        "status": ptr.status.value,
        "url": ptr.url,
        "error": ptr.error,
        "published_at": ptr.published_at,
    }


def dict_to_publish_target_result(data: dict[str, Any]) -> PublishTargetResult:
    """Deserialize a dict into a ``PublishTargetResult``."""
    return PublishTargetResult(
        target=str(data["target"]),
        status=PublishStatus(data.get("status", "pending")),
        url=str(data.get("url", "")),
        error=str(data.get("error", "")),
        published_at=str(data.get("published_at", "")),
    )


def queue_item_to_dict(item: QueueItem) -> dict[str, Any]:
    """Serialize a ``QueueItem`` to a JSON-compatible dict."""
    return {
        "id": item.id,
        "output": item.output,
        "game_dir": item.game_dir,
        "status": item.status.value,
        "queued_at": item.queued_at,
        "duration_seconds": item.duration_seconds,
        "file_size_bytes": item.file_size_bytes,
        "format": item.format,
        "crop_mode": item.crop_mode,
        "render_profile": item.render_profile,
        "event_id": item.event_id,
        "home_team": item.home_team,
        "away_team": item.away_team,
        "date": item.date,
        "sport": item.sport,
        "level": item.level,
        "tournament": item.tournament,
        "event_type": item.event_type,
        "player": item.player,
        "assists": item.assists,
        "title": item.title,
        "description": item.description,
        "publish_targets": [
            publish_target_result_to_dict(t) for t in item.publish_targets
        ],
        "config_profile": item.config_profile,
        "plugin_inputs": dict(item.plugin_inputs),
    }


def dict_to_queue_item(data: dict[str, Any]) -> QueueItem:
    """Deserialize a dict into a ``QueueItem``."""
    targets_raw = data.get("publish_targets", [])
    return QueueItem(
        id=str(data["id"]),
        output=str(data["output"]),
        game_dir=str(data["game_dir"]),
        status=QueueStatus(data.get("status", "rendered")),
        queued_at=str(data.get("queued_at", "")),
        duration_seconds=data.get("duration_seconds"),
        file_size_bytes=data.get("file_size_bytes"),
        format=str(data.get("format", "")),
        crop_mode=str(data.get("crop_mode", "")),
        render_profile=str(data.get("render_profile", "")),
        event_id=str(data.get("event_id", "")),
        home_team=str(data.get("home_team", "")),
        away_team=str(data.get("away_team", "")),
        date=str(data.get("date", "")),
        sport=str(data.get("sport", "")),
        level=str(data.get("level", "")),
        tournament=str(data.get("tournament", "")),
        event_type=str(data.get("event_type", "")),
        player=str(data.get("player", "")),
        assists=str(data.get("assists", "")),
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        publish_targets=tuple(
            dict_to_publish_target_result(t) for t in targets_raw
        ),
        config_profile=str(data.get("config_profile", "")),
        plugin_inputs=dict(data.get("plugin_inputs", {})),
    )


def render_queue_to_dict(queue: RenderQueue) -> dict[str, Any]:
    """Serialize a ``RenderQueue`` to a JSON-compatible dict."""
    return {
        "version": queue.version,
        "items": [queue_item_to_dict(item) for item in queue.items],
    }


def dict_to_render_queue(data: dict[str, Any]) -> RenderQueue:
    """Deserialize a dict into a ``RenderQueue``."""
    items_raw = data.get("items", [])
    return RenderQueue(
        version=int(data.get("version", 1)),
        items=tuple(dict_to_queue_item(item) for item in items_raw),
    )
