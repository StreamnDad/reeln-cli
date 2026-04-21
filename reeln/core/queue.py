"""Queue business logic — load, save, add, update, remove, publish."""

from __future__ import annotations

import contextlib
import json
import logging
import tempfile
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reeln.core.errors import QueueError
from reeln.core.log import get_logger
from reeln.core.metadata import (
    build_publish_metadata,
    generate_description,
    generate_title,
)
from reeln.models.game import GameEvent, GameInfo
from reeln.models.queue import (
    PublishStatus,
    PublishTargetResult,
    QueueItem,
    QueueStatus,
    RenderQueue,
    dict_to_render_queue,
    render_queue_to_dict,
)
from reeln.models.render_plan import RenderResult

log: logging.Logger = get_logger(__name__)

_QUEUE_FILE = "render_queue.json"
_INDEX_FILE = "queue_index.json"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------


def load_queue(game_dir: Path) -> RenderQueue:
    """Load the render queue from *game_dir*, returning empty if absent."""
    queue_file = game_dir / _QUEUE_FILE
    if not queue_file.is_file():
        return RenderQueue()
    try:
        raw = json.loads(queue_file.read_text(encoding="utf-8"))
        return dict_to_render_queue(raw)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise QueueError(f"Invalid queue file {queue_file}: {exc}") from exc


def save_queue(queue: RenderQueue, game_dir: Path) -> Path:
    """Atomically write the render queue to *game_dir*."""
    queue_file = game_dir / _QUEUE_FILE
    queue_file.parent.mkdir(parents=True, exist_ok=True)

    content = json.dumps(render_queue_to_dict(queue), indent=2) + "\n"

    tmp_fd, tmp_name = tempfile.mkstemp(
        suffix=".tmp", dir=queue_file.parent, text=True
    )
    try:
        with open(tmp_fd, "w") as tmp:
            tmp.write(content)
            tmp.flush()
        Path(tmp_name).replace(queue_file)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

    log.debug("Queue saved to %s", queue_file)
    return queue_file


# ---------------------------------------------------------------------------
# Queue index (advisory cross-game listing)
# ---------------------------------------------------------------------------


def update_queue_index(game_dir: Path) -> None:
    """Add *game_dir* to the central queue index."""
    from reeln.core.config import data_dir

    index_dir = data_dir()
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / _INDEX_FILE

    index: dict[str, list[str]] = {"queues": []}
    if index_file.is_file():
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            index = json.loads(index_file.read_text(encoding="utf-8"))

    game_str = str(game_dir)
    if game_str not in index.get("queues", []):
        index.setdefault("queues", []).append(game_str)
        tmp_fd, tmp_name = tempfile.mkstemp(
            suffix=".tmp", dir=index_dir, text=True
        )
        try:
            with open(tmp_fd, "w") as tmp:
                tmp.write(json.dumps(index, indent=2) + "\n")
                tmp.flush()
            Path(tmp_name).replace(index_file)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


def load_queue_index() -> list[str]:
    """Load the central queue index, returning game directory paths."""
    from reeln.core.config import data_dir

    index_file = data_dir() / _INDEX_FILE
    if not index_file.is_file():
        return []
    try:
        raw = json.loads(index_file.read_text(encoding="utf-8"))
        return list(raw.get("queues", []))
    except (json.JSONDecodeError, ValueError):
        return []


# ---------------------------------------------------------------------------
# Add / Update / Remove
# ---------------------------------------------------------------------------


def _generate_id() -> str:
    """Generate a short unique ID for a queue item."""
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(tz=UTC).isoformat()


def add_to_queue(
    game_dir: Path,
    result: RenderResult,
    *,
    game_info: GameInfo | None = None,
    game_event: GameEvent | None = None,
    player: str = "",
    assists: str = "",
    plugin_inputs: dict[str, Any] | None = None,
    render_profile: str = "",
    format_str: str = "",
    crop_mode: str = "",
    event_id: str = "",
    available_targets: list[str] | None = None,
    config_profile: str = "",
) -> QueueItem:
    """Create a queue item from a render result and save to disk.

    Soft-deletes any prior unpublished queue items that point at the same
    output file path. Rationale: when the user re-renders the same clip
    (to tweak the render profile, player overlay, or just regenerate the
    openai-generated title), the new render overwrites the previous
    ``.mp4`` on disk — so any prior queue item pointing at that file is
    stale. Leaving stale items in the queue causes ``reeln queue
    publish-all`` to upload the same file multiple times, producing
    duplicate IG Reels / YouTube videos / TikTok posts.

    Already-published items are never soft-deleted; they remain as a
    historical record of what was uploaded (their ``publish_targets``
    carry real URLs). ``publish_all`` already filters on status
    ``RENDERED`` so published items won't be re-processed.
    """
    title = generate_title(game_info, game_event, player, assists)
    description = generate_description(game_info, game_event, player, assists)

    targets = tuple(
        PublishTargetResult(target=t) for t in (available_targets or [])
    )

    item = QueueItem(
        id=_generate_id(),
        output=str(result.output),
        game_dir=str(game_dir),
        status=QueueStatus.RENDERED,
        queued_at=_now_iso(),
        duration_seconds=result.duration_seconds,
        file_size_bytes=result.file_size_bytes,
        format=format_str,
        crop_mode=crop_mode,
        render_profile=render_profile,
        event_id=event_id,
        home_team=game_info.home_team if game_info else "",
        away_team=game_info.away_team if game_info else "",
        date=game_info.date if game_info else "",
        sport=game_info.sport if game_info else "",
        level=game_info.level if game_info else "",
        tournament=game_info.tournament if game_info else "",
        event_type=game_event.event_type if game_event else "",
        player=player or (game_event.player if game_event else ""),
        assists=assists,
        title=title,
        description=description,
        publish_targets=targets,
        config_profile=config_profile,
        plugin_inputs=dict(plugin_inputs) if plugin_inputs else {},
    )

    queue = load_queue(game_dir)

    # Soft-delete stale prior items pointing at the same output file.
    # See the docstring for the rationale. We normalize both paths through
    # Path() so "/foo/bar.mp4" and "/foo/./bar.mp4" compare equal.
    new_output = Path(item.output)
    merged_items: list[QueueItem] = []
    superseded: list[str] = []
    for existing in queue.items:
        if existing.status not in (
            QueueStatus.REMOVED,
            QueueStatus.PUBLISHED,
        ) and Path(existing.output) == new_output:
            existing = replace(existing, status=QueueStatus.REMOVED)
            superseded.append(existing.id)
        merged_items.append(existing)
    merged_items.append(item)

    if superseded:
        log.info(
            "Superseded %d stale queue item(s) for %s: %s",
            len(superseded),
            new_output.name,
            ", ".join(superseded),
        )

    queue = RenderQueue(version=queue.version, items=tuple(merged_items))
    save_queue(queue, game_dir)
    update_queue_index(game_dir)

    log.info("Added queue item %s: %s", item.id, title)
    return item


def _find_item(queue: RenderQueue, item_id: str) -> tuple[int, QueueItem]:
    """Find an item by exact ID or prefix match. Raises QueueError if not found."""
    # Exact match first
    for idx, item in enumerate(queue.items):
        if item.id == item_id:
            return idx, item
    # Prefix match
    matches: list[tuple[int, QueueItem]] = []
    for idx, item in enumerate(queue.items):
        if item.id.startswith(item_id):
            matches.append((idx, item))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        ids = ", ".join(m[1].id for m in matches)
        raise QueueError(f"Ambiguous ID prefix '{item_id}' matches: {ids}")
    raise QueueError(f"Queue item '{item_id}' not found")


def get_queue_item(game_dir: Path, item_id: str) -> QueueItem | None:
    """Look up a queue item by ID or prefix. Returns None if not found."""
    queue = load_queue(game_dir)
    try:
        _, item = _find_item(queue, item_id)
        return item
    except QueueError:
        return None


def update_queue_item(
    game_dir: Path,
    item_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
) -> QueueItem:
    """Update editable fields on a queue item. Returns the updated item."""
    queue = load_queue(game_dir)
    idx, item = _find_item(queue, item_id)

    updates: dict[str, Any] = {}
    if title is not None:
        updates["title"] = title
    if description is not None:
        updates["description"] = description

    if not updates:
        return item

    updated = replace(item, **updates)
    items = list(queue.items)
    items[idx] = updated
    save_queue(RenderQueue(version=queue.version, items=tuple(items)), game_dir)
    return updated


def remove_from_queue(game_dir: Path, item_id: str) -> QueueItem:
    """Soft-delete a queue item by marking it as REMOVED."""
    queue = load_queue(game_dir)
    idx, item = _find_item(queue, item_id)
    removed = replace(item, status=QueueStatus.REMOVED)
    items = list(queue.items)
    items[idx] = removed
    save_queue(RenderQueue(version=queue.version, items=tuple(items)), game_dir)
    log.info("Removed queue item %s", item.id)
    return removed


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


def discover_targets(plugins: dict[str, object]) -> list[str]:
    """Return names of plugins that handle uploads.

    Checks for both the ``Uploader`` protocol (``upload()`` method) and
    plugins registered for ``POST_RENDER`` (``on_post_render()`` method),
    since existing plugins handle uploads inside their POST_RENDER handlers.
    """
    targets: list[str] = []
    for name, plugin in plugins.items():
        if callable(getattr(plugin, "upload", None)) or callable(getattr(plugin, "on_post_render", None)):
            targets.append(name)
    return sorted(targets)


def _is_publish_target(plugin: object) -> bool:
    """Check if a plugin can handle publishing (upload protocol or POST_RENDER hook)."""
    return callable(getattr(plugin, "upload", None)) or callable(
        getattr(plugin, "on_post_render", None)
    )


def publish_queue_item(
    game_dir: Path,
    item_id: str,
    plugins: dict[str, object],
    *,
    target: str | None = None,
) -> QueueItem:
    """Publish a queue item to one or all targets.

    When *target* is ``None``, publishes to all pending targets.
    When *target* is a string, publishes to that single target.

    Manual publish goes through the :class:`~reeln.plugins.capabilities.Uploader`
    protocol only — plugins must implement an ``upload()`` method that returns
    the public URL on success, raises
    :class:`~reeln.plugins.capabilities.UploaderSkipped` for an intentional
    skip, or raises any other ``Exception`` for a failure. Plugins that only
    implement ``on_post_render`` still run during the render fast-track
    (``reeln render`` without ``--queue``); for manual publish they are
    marked ``PublishStatus.SKIPPED`` with an explanatory message so the user
    can tell the difference between "uploaded", "failed", and "not wired".
    """
    from reeln.core.throttle import upload_lock
    from reeln.plugins.capabilities import UploaderSkipped
    from reeln.plugins.hooks import Hook, HookContext
    from reeln.plugins.registry import get_registry

    queue = load_queue(game_dir)
    idx, item = _find_item(queue, item_id)

    if item.status is QueueStatus.REMOVED:
        raise QueueError(f"Cannot publish removed item '{item.id}'")

    output_path = Path(item.output)
    if not output_path.is_file():
        raise QueueError(f"Output file not found: {item.output}")

    # Build metadata for uploaders. In addition to the game-context fields
    # from build_publish_metadata, include render-specific fields from the
    # QueueItem so uploaders that need to distinguish Shorts from Videos
    # (google, tiktok) can detect portrait vs landscape without access to
    # the original render plan.
    game_info = _reconstruct_game_info(item)
    game_event = _reconstruct_game_event(item)
    metadata = build_publish_metadata(
        title=item.title,
        description=item.description,
        game_info=game_info,
        game_event=game_event,
        player=item.player,
        assists=item.assists,
        plugin_inputs=item.plugin_inputs or None,
    )
    if item.format:
        metadata["format"] = item.format
    if item.render_profile:
        metadata["render_profile"] = item.render_profile
    if item.duration_seconds is not None:
        metadata["duration_seconds"] = item.duration_seconds

    # Seed metadata["video_url"] from any previously-published target that
    # already carries a hosted-file URL. This makes per-target retry
    # idempotent: when the user clicks "Retry" on meta alone, cloudflare
    # isn't re-invoked in this publish call — but its URL is still in
    # item.publish_targets from the previous call, so meta's upload()
    # can consume it via PULL_FROM_URL semantics.
    #
    # Only http(s) URLs are accepted. Non-HTTP sentinels like
    # ``tiktok:v_inbox_url~...`` are publication identifiers, not raw
    # media URLs, and would cause downstream plugins (meta, tiktok pull)
    # to fail if used as a source.
    for ptr in sorted(item.publish_targets, key=lambda t: t.target):
        if (
            ptr.status is PublishStatus.PUBLISHED
            and ptr.url
            and (ptr.url.startswith("http://") or ptr.url.startswith("https://"))
            and "video_url" not in metadata
        ):
            metadata["video_url"] = ptr.url
            break

    # Determine which targets to publish to
    targets_to_publish: list[str] = []
    if target is not None:
        if target not in plugins or not _is_publish_target(plugins[target]):
            raise QueueError(f"Unknown or non-uploader target: '{target}'")
        targets_to_publish = [target]
    else:
        # Check stored publish_targets first
        for ptr in item.publish_targets:
            if (
                ptr.status is PublishStatus.PENDING
                and ptr.target in plugins
                and _is_publish_target(plugins[ptr.target])
            ):
                targets_to_publish.append(ptr.target)
        # Fall back to discovering from loaded plugins if no stored targets
        if not targets_to_publish and not item.publish_targets:
            targets_to_publish = discover_targets(plugins)

    if not targets_to_publish:
        raise QueueError("No pending publish targets")

    # Mark as publishing
    item = replace(item, status=QueueStatus.PUBLISHING)
    items = list(queue.items)
    items[idx] = item
    save_queue(RenderQueue(version=queue.version, items=tuple(items)), game_dir)

    # Separate targets by publish mechanism
    uploader_targets = [t for t in targets_to_publish if callable(getattr(plugins[t], "upload", None))]
    hook_targets = [t for t in targets_to_publish if t not in uploader_targets]

    updated_targets = list(item.publish_targets)

    # Publish via Uploader protocol (direct call per target).
    # UploaderSkipped is caught BEFORE the generic Exception clause so it
    # maps to PublishStatus.SKIPPED (intentional skip) instead of FAILED.
    #
    # Alphabetical ordering in targets_to_publish means cloudflare (which
    # hosts raw media files on R2) runs before meta (which publishes Reels
    # from a hosted URL) and tiktok (which can use PULL_FROM_URL). The
    # first uploader's returned URL is threaded into metadata["video_url"]
    # so downstream plugins can consume it; subsequent plugins do NOT
    # overwrite it, preserving the raw-hosted-file URL.
    for target_name in uploader_targets:
        plugin = plugins[target_name]
        target_idx = _find_target_idx(updated_targets, target_name)

        try:
            with upload_lock():
                url: str = plugin.upload(output_path, metadata=metadata)  # type: ignore[attr-defined]
            result_ptr = PublishTargetResult(
                target=target_name,
                status=PublishStatus.PUBLISHED,
                url=url,
                published_at=_now_iso(),
            )
            log.info("Published %s to %s: %s", item.id, target_name, url)
            # First uploader to return a URL establishes video_url for
            # downstream plugins. Don't overwrite — later plugins produce
            # publication URLs (YouTube, Reels) that aren't ingestible as
            # raw media sources.
            if url and "video_url" not in metadata:
                metadata = {**metadata, "video_url": url}
        except UploaderSkipped as exc:
            result_ptr = PublishTargetResult(
                target=target_name,
                status=PublishStatus.SKIPPED,
                error=str(exc),
            )
            log.info("Skipped %s for %s: %s", target_name, item.id, exc)
        except Exception as exc:
            result_ptr = PublishTargetResult(
                target=target_name,
                status=PublishStatus.FAILED,
                error=str(exc),
            )
            log.warning(
                "Failed to publish %s to %s: %s", item.id, target_name, exc
            )

        if target_idx is not None:
            updated_targets[target_idx] = result_ptr
        else:
            updated_targets.append(result_ptr)

    # Plugins without upload() are marked SKIPPED for manual publish.
    # They still run via POST_RENDER during `reeln render` (fast-track path);
    # manual publish requires opt-in via the Uploader protocol. Previously
    # this branch emitted POST_RENDER and unconditionally marked every hook
    # target as PUBLISHED, which lied to the user when plugins silently
    # early-returned in their on_post_render guards.
    if hook_targets:
        skip_reason = (
            "Plugin does not support manual publish (no upload() method). "
            "It runs via POST_RENDER during `reeln render`."
        )
        for target_name in hook_targets:
            target_idx = _find_target_idx(updated_targets, target_name)
            result_ptr = PublishTargetResult(
                target=target_name,
                status=PublishStatus.SKIPPED,
                error=skip_reason,
            )
            if target_idx is not None:
                updated_targets[target_idx] = result_ptr
            else:
                updated_targets.append(result_ptr)
        log.info(
            "Skipped manual publish for hook-only targets %s on %s",
            hook_targets,
            item.id,
        )

    # Emit ON_PUBLISH for tracking
    for target_name in targets_to_publish:
        published_ptr: PublishTargetResult | None = next(
            (t for t in updated_targets if t.target == target_name), None
        )
        if published_ptr is not None:  # pragma: no branch
            get_registry().emit(
                Hook.ON_PUBLISH,
                HookContext(
                    hook=Hook.ON_PUBLISH,
                    data={
                        "queue_item_id": item.id,
                        "target": target_name,
                        "status": published_ptr.status.value,
                        "url": published_ptr.url,
                        "error": published_ptr.error,
                        "metadata": metadata,
                    },
                ),
            )

    # Determine overall status. SKIPPED targets are excluded from the
    # decision — they represent plugins that were intentionally not
    # published (disabled in config, or not wired for manual publish yet),
    # not failures. When every target is skipped, the item stays in
    # RENDERED so the user can re-publish later once more plugins are
    # wired. When at least one non-skipped target published successfully,
    # SKIPPED targets don't drag the overall to PARTIAL.
    all_statuses = {t.status for t in updated_targets}
    non_skipped = {s for s in all_statuses if s is not PublishStatus.SKIPPED}
    if not non_skipped:
        overall = QueueStatus.RENDERED
    elif non_skipped == {PublishStatus.PUBLISHED}:
        overall = QueueStatus.PUBLISHED
    elif non_skipped == {PublishStatus.FAILED}:
        overall = QueueStatus.FAILED
    elif PublishStatus.PUBLISHED in non_skipped:
        overall = QueueStatus.PARTIAL
    else:
        overall = QueueStatus.PARTIAL

    item = replace(
        item,
        status=overall,
        publish_targets=tuple(updated_targets),
    )
    queue = load_queue(game_dir)
    items_list = list(queue.items)
    for i, it in enumerate(items_list):  # pragma: no branch
        if it.id == item.id:
            items_list[i] = item
            break
    save_queue(RenderQueue(version=queue.version, items=tuple(items_list)), game_dir)

    return item


def publish_all(
    game_dir: Path,
    plugins: dict[str, object],
) -> list[QueueItem]:
    """Publish all rendered (unpublished) items in the queue."""
    queue = load_queue(game_dir)
    results: list[QueueItem] = []
    for item in queue.items:
        if item.status is QueueStatus.RENDERED:
            published = publish_queue_item(game_dir, item.id, plugins)
            results.append(published)
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_target_idx(
    targets: list[PublishTargetResult], target_name: str
) -> int | None:
    """Find the index of a target in the list, or None."""
    for i, t in enumerate(targets):  # pragma: no branch
        if t.target == target_name:
            return i
    return None


def _reconstruct_game_info(item: QueueItem) -> GameInfo | None:
    """Reconstruct a GameInfo from snapshotted queue item fields."""
    if not item.home_team and not item.away_team:
        return None
    return GameInfo(
        date=item.date,
        home_team=item.home_team,
        away_team=item.away_team,
        sport=item.sport,
        level=item.level,
        tournament=item.tournament,
    )


def _reconstruct_game_event(item: QueueItem) -> GameEvent | None:
    """Reconstruct a GameEvent from snapshotted queue item fields."""
    if not item.event_id:
        return None
    return GameEvent(
        id=item.event_id,
        clip="",
        segment_number=0,
        event_type=item.event_type,
        player=item.player,
    )
