"""Artifact cleanup — per-game and global prune operations."""

from __future__ import annotations

import logging
from pathlib import Path

from reeln.core.errors import MediaError
from reeln.core.highlights import load_game_state
from reeln.core.log import get_logger
from reeln.models.render_plan import PruneResult

log: logging.Logger = get_logger(__name__)

_GAME_STATE_FILE: str = "game.json"

_VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mkv",
        ".mp4",
        ".mov",
        ".avi",
        ".webm",
        ".ts",
        ".m4v",
        ".flv",
    }
)

_TEMP_EXTENSIONS: frozenset[str] = frozenset({".tmp", ".txt"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def format_bytes(n: int) -> str:
    """Format a byte count as a human-readable string.

    Examples::

        >>> format_bytes(0)
        '0 B'
        >>> format_bytes(1024)
        '1.0 KB'
        >>> format_bytes(1_500_000)
        '1.4 MB'
    """
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n_f = n / 1024
        if n_f < 1024 or unit == "TB":
            return f"{n_f:.1f} {unit}"
        n = int(n_f)
    return f"{n} B"  # pragma: no cover - unreachable


def _file_size(path: Path) -> int:
    """Return file size in bytes, 0 on error."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _remove_file(path: Path, dry_run: bool, result: PruneResult) -> None:
    """Remove a file and accumulate stats in *result*."""
    size = _file_size(path)
    if dry_run:
        result.removed_paths.append(path)
        result.bytes_freed += size
        return

    try:
        path.unlink()
    except OSError as exc:
        result.errors.append(f"{path}: {exc}")
        return

    result.removed_paths.append(path)
    result.bytes_freed += size


def _remove_dir_if_empty(path: Path, dry_run: bool) -> None:
    """Remove *path* if it is an empty directory."""
    if dry_run:
        return
    try:
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Per-game prune
# ---------------------------------------------------------------------------


def prune_game(
    game_dir: Path,
    *,
    all_files: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[PruneResult, list[str]]:
    """Remove generated artifacts from a finished game directory.

    By default, removes generated files (segment merges, highlight reels,
    rendered shorts, compilations, temp files) while preserving tagged
    event clips and ``game.json``.  Untagged event clips (no ``event_type``)
    are warned about but not removed unless *force* is set.

    With *force*, also removes untagged event clips — clips that exist in
    the event list but have no ``event_type`` assigned.

    With *all_files*, removes everything except ``game.json``.

    Raises ``MediaError`` if the game is not finished.
    """
    state = load_game_state(game_dir)

    if not state.finished:
        raise MediaError("Game must be finished before pruning")

    tagged_clips: set[str] = {ev.clip for ev in state.events if ev.event_type}
    untagged_clips: set[str] = {ev.clip for ev in state.events if not ev.event_type}
    skipped_untagged: list[str] = []

    result = PruneResult()

    # Collect all files under game_dir (skip game.json itself)
    for path in sorted(game_dir.rglob("*")):
        if not path.is_file():
            continue

        rel = str(path.relative_to(game_dir))

        # Never remove game.json
        if rel == _GAME_STATE_FILE:
            continue

        suffix = path.suffix.lower()

        # Temp files are always removed
        if suffix in _TEMP_EXTENSIONS:
            _remove_file(path, dry_run, result)
            continue

        # Only consider video files for the rest
        if suffix not in _VIDEO_EXTENSIONS:
            continue

        is_tagged = rel in tagged_clips
        is_untagged = rel in untagged_clips

        if is_tagged and not all_files:
            # Always preserve tagged event clips unless --all
            continue

        if is_untagged and not all_files:
            if force:
                _remove_file(path, dry_run, result)
            else:
                skipped_untagged.append(rel)
            continue

        _remove_file(path, dry_run, result)

    # Remove debug directory contents (always, no --all needed)
    debug_path = game_dir / "debug"
    if debug_path.is_dir():
        for f in sorted(debug_path.rglob("*")):
            if f.is_file():
                _remove_file(f, dry_run, result)
        # Remove empty subdirectories inside debug/ (deepest first)
        for d in sorted(debug_path.rglob("*"), reverse=True):
            if d.is_dir():
                _remove_dir_if_empty(d, dry_run)
        _remove_dir_if_empty(debug_path, dry_run)

    # Clean up empty segment directories
    for child in sorted(game_dir.iterdir()):
        if child.is_dir():
            _remove_dir_if_empty(child, dry_run)

    messages = _build_prune_summary(result, dry_run)

    if skipped_untagged:
        messages.append(
            f"Warning: {len(skipped_untagged)} untagged clip(s) not removed "
            "(use --force to remove):"
        )
        for clip in skipped_untagged:
            messages.append(f"  {clip}")

    if not dry_run:
        log.info("Pruned %s: %d files, %s freed", game_dir, len(result.removed_paths), format_bytes(result.bytes_freed))

    return result, messages


# ---------------------------------------------------------------------------
# Global prune
# ---------------------------------------------------------------------------


def find_game_dirs(base: Path) -> list[Path]:
    """Discover game directories under *base*.

    If *base* itself contains ``game.json``, returns ``[base]``.
    Otherwise scans immediate children for directories with ``game.json``.
    """
    if (base / _GAME_STATE_FILE).is_file():
        return [base]

    dirs: list[Path] = []
    if base.is_dir():
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / _GAME_STATE_FILE).is_file():
                dirs.append(child)
    return dirs


def prune_all(
    base: Path,
    *,
    all_files: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[PruneResult, list[str]]:
    """Prune all finished game directories under *base*.

    Discovers game dirs, prunes each finished game, skips unfinished games
    with a message.  Aggregates results across all games.
    """
    game_dirs = find_game_dirs(base)
    if not game_dirs:
        return PruneResult(), ["No game directories found"]

    combined = PruneResult()
    messages: list[str] = []

    for game_dir in game_dirs:
        state = load_game_state(game_dir)
        if not state.finished:
            messages.append(f"Skipping {game_dir.name}: not finished")
            continue

        result, game_messages = prune_game(game_dir, all_files=all_files, force=force, dry_run=dry_run)
        combined.removed_paths.extend(result.removed_paths)
        combined.bytes_freed += result.bytes_freed
        combined.errors.extend(result.errors)
        messages.append(f"{game_dir.name}:")
        messages.extend(f"  {m}" for m in game_messages)

    if not combined.removed_paths and not any("Skipping" in m for m in messages):
        messages.append("Nothing to prune")

    return combined, messages


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _build_prune_summary(result: PruneResult, dry_run: bool) -> list[str]:
    """Build human-readable summary lines for a prune operation."""
    prefix = "Would remove" if dry_run else "Removed"
    messages: list[str] = []

    if not result.removed_paths:
        messages.append("Nothing to prune")
        return messages

    messages.append(f"{prefix} {len(result.removed_paths)} file(s), {format_bytes(result.bytes_freed)}")

    if result.errors:
        messages.append(f"Errors: {len(result.errors)}")
        for err in result.errors:
            messages.append(f"  {err}")

    return messages
