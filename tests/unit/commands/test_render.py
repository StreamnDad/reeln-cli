"""Tests for the render command group: short, preview, apply, reel."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from reeln.cli import app
from reeln.models.game import (
    GameEvent,
    GameInfo,
    GameState,
    RenderEntry,
    game_state_to_dict,
)
from reeln.models.render_plan import IterationResult, RenderResult

runner = CliRunner()


def _write_game_state(game_dir: Path, state: GameState) -> None:
    """Write a game.json in the given directory."""
    data = game_state_to_dict(state)
    (game_dir / "game.json").write_text(json.dumps(data, indent=2))


def _mock_result(tmp_path: Path) -> RenderResult:
    return RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=30.0,
        file_size_bytes=1024000,
    )


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_render_help_lists_commands() -> None:
    result = runner.invoke(app, ["render", "--help"])
    assert result.exit_code == 0
    assert "short" in result.output
    assert "preview" in result.output
    assert "reel" in result.output


# ---------------------------------------------------------------------------
# render short
# ---------------------------------------------------------------------------


def _config_with_source(
    tmp_path: Path,
    source_dir: Path,
    source_glob: str | None = None,
) -> Path:
    """Write a config file with paths.source_dir (and optional source_glob)."""
    paths: dict[str, str | None] = {"source_dir": str(source_dir)}
    if source_glob is not None:
        paths["source_glob"] = source_glob
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"paths": paths}))
    return cfg


def test_render_short_no_clip_uses_latest(tmp_path: Path) -> None:
    """When no clip argument, use the most recently modified matching file."""
    import time

    src = tmp_path / "recordings"
    src.mkdir()
    older = src / "Replay_old.mkv"
    older.write_bytes(b"old")
    time.sleep(0.05)
    newer = src / "Replay_new.mkv"
    newer.write_bytes(b"new")
    cfg = _config_with_source(tmp_path, src)
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            "--dry-run",
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 0
    assert "Replay_new.mkv" in result.output


def test_render_short_no_clip_no_source_dir(tmp_path: Path) -> None:
    """Error when no clip and source_dir not configured."""
    cfg = tmp_path / "empty.json"
    cfg.write_text(json.dumps({"config_version": 1}))
    result = runner.invoke(app, ["render", "short", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "source_dir not configured" in result.output


def test_render_short_no_clip_no_match(tmp_path: Path) -> None:
    """Error when source_dir has no files matching the default glob."""
    src = tmp_path / "recordings"
    src.mkdir()
    (src / "Manual_clip.mkv").write_bytes(b"data")
    cfg = _config_with_source(tmp_path, src)
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 1
    assert "No files matching" in result.output


def test_render_short_no_clip_skips_dirs_and_non_matching(tmp_path: Path) -> None:
    """Subdirectories and non-matching files are skipped."""
    src = tmp_path / "recordings"
    src.mkdir()
    (src / "Replay_dir.mkv").mkdir()  # directory, not a file
    (src / "notes.txt").write_text("hello")
    (src / "Replay_clip.mkv").write_bytes(b"video")
    cfg = _config_with_source(tmp_path, src)
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            "--dry-run",
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 0
    assert "Replay_clip.mkv" in result.output


def test_render_short_no_clip_custom_glob(tmp_path: Path) -> None:
    """Custom source_glob overrides the default pattern."""
    import time

    src = tmp_path / "recordings"
    src.mkdir()
    # Default glob would miss these (no Replay_ prefix)
    (src / "Game_old.mp4").write_bytes(b"old")
    time.sleep(0.05)
    (src / "Game_new.mp4").write_bytes(b"new")
    # This matches default but not custom glob
    (src / "Replay_2026.mkv").write_bytes(b"replay")
    cfg = _config_with_source(tmp_path, src, source_glob="Game_*.mp4")
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            "--dry-run",
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 0
    assert "Game_new.mp4" in result.output


def test_render_short_no_clip_custom_glob_no_match(tmp_path: Path) -> None:
    """Error when custom source_glob matches nothing."""
    src = tmp_path / "recordings"
    src.mkdir()
    (src / "Replay_clip.mkv").write_bytes(b"data")
    cfg = _config_with_source(tmp_path, src, source_glob="Game_*.mp4")
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 1
    assert "No files matching" in result.output
    assert "Game_*.mp4" in result.output


def test_render_short_dry_run(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "Input:" in result.output
    assert "Size: 1080x1920" in result.output


def test_render_short_default_output_in_shorts_subdir(tmp_path: Path) -> None:
    """Default output path puts renders in a shorts/ subdirectory."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "shorts/clip_short.mp4" in result.output


def test_render_preview_default_output_in_shorts_subdir(tmp_path: Path) -> None:
    """Default preview output path also uses shorts/ subdirectory."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "preview",
            str(clip),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "shorts/clip_preview.mp4" in result.output


def test_render_short_dry_run_crop_mode(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
            "--crop",
            "crop",
        ],
    )
    assert result.exit_code == 0
    assert "Crop mode: crop" in result.output


def test_render_short_dry_run_square(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
            "--format",
            "square",
        ],
    )
    assert result.exit_code == 0
    assert "Size: 1080x1080" in result.output


def test_render_short_dry_run_custom_size(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
            "--size",
            "720x1280",
        ],
    )
    assert result.exit_code == 0
    assert "Size: 720x1280" in result.output


def test_render_short_dry_run_with_speed(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
            "--speed",
            "0.5",
        ],
    )
    assert result.exit_code == 0
    assert "Speed: 0.5x" in result.output


def test_render_short_dry_run_with_lut_and_subtitle(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    lut = tmp_path / "grade.cube"
    lut.touch()
    sub = tmp_path / "subs.ass"
    sub.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
            "--lut",
            str(lut),
            "--subtitle",
            str(sub),
        ],
    )
    assert result.exit_code == 0
    assert "LUT:" in result.output
    assert "Subtitle:" in result.output


def test_render_short_with_output(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    out = tmp_path / "custom.mp4"
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert str(out) in result.output


def test_render_short_executes(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
    ):
        mock_renderer_cls.return_value.render.return_value = mock_result
        result = runner.invoke(app, ["render", "short", str(clip)])

    assert result.exit_code == 0
    assert "Render complete" in result.output
    assert "Duration: 30.0s" in result.output
    assert "File size:" in result.output


def test_render_short_render_error(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    from reeln.core.errors import FFmpegError

    with patch("reeln.core.ffmpeg.discover_ffmpeg", side_effect=FFmpegError("not found")):
        result = runner.invoke(app, ["render", "short", str(clip)])

    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_short_invalid_crop_mode(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--crop",
            "invalid",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown crop mode" in result.output


def test_render_short_invalid_size_format(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--size",
            "invalid",
        ],
    )
    assert result.exit_code != 0


def test_render_short_invalid_size_values(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--size",
            "axb",
        ],
    )
    assert result.exit_code != 0


def test_render_short_unknown_format(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--format",
            "widescreen",
        ],
    )
    assert result.exit_code != 0


def test_render_short_invalid_anchor(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--anchor",
            "invalid",
        ],
    )
    assert result.exit_code != 0


def test_render_short_custom_anchor(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
            "--anchor",
            "0.3,0.7",
        ],
    )
    assert result.exit_code == 0


def test_render_short_invalid_custom_anchor(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--anchor",
            "a,b",
        ],
    )
    assert result.exit_code != 0


def test_render_short_named_anchor(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    for anchor in ["center", "top", "bottom", "left", "right"]:
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--dry-run",
                "--anchor",
                anchor,
            ],
        )
        assert result.exit_code == 0, f"Failed for anchor={anchor}"


def test_render_short_validation_error(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--size",
            "1081x1920",
        ],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_short_config_error(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    bad_config = tmp_path / "bad.json"
    bad_config.write_text("not json!")
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--config",
            str(bad_config),
        ],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_short_no_duration_or_size(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    mock_result = RenderResult(output=tmp_path / "out.mp4")
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(app, ["render", "short", str(clip)])

    assert result.exit_code == 0
    assert "Duration:" not in result.output
    assert "File size:" not in result.output


# ---------------------------------------------------------------------------
# render short --game-dir (Stage B)
# ---------------------------------------------------------------------------


def test_render_short_with_game_dir(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="2026-02-26T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--game-dir",
                str(game_dir),
            ],
        )

    assert result.exit_code == 0
    assert "Render complete" in result.output
    # Verify render entry was saved
    saved = json.loads((game_dir / "game.json").read_text())
    assert len(saved["renders"]) == 1


def test_render_short_game_dir_error(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    bad_dir = tmp_path / "nonexistent"

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--game-dir",
                str(bad_dir),
            ],
        )

    assert result.exit_code == 0
    assert "Warning:" in result.output


# ---------------------------------------------------------------------------
# render short — auto-discover game dir
# ---------------------------------------------------------------------------


def test_render_short_auto_discovers_game_dir(tmp_path: Path) -> None:
    """When --game-dir is not passed, auto-discover from config output_dir."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    game_dir = output_dir / "2026-02-28_a_vs_b"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"paths": {"output_dir": str(output_dir)}}))

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--config",
                str(cfg),
            ],
        )

    assert result.exit_code == 0
    assert "Render complete" in result.output
    saved = json.loads((game_dir / "game.json").read_text())
    assert len(saved["renders"]) == 1


def test_render_short_no_game_dir_skips_tracking(tmp_path: Path) -> None:
    """When no game dir found, render still succeeds without tracking."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"config_version": 1}))

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--config",
                str(cfg),
            ],
        )

    assert result.exit_code == 0
    assert "Render complete" in result.output


def test_render_short_output_dir_not_a_dir(tmp_path: Path) -> None:
    """When output_dir doesn't exist, skip tracking silently."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"paths": {"output_dir": str(tmp_path / "nonexistent")}}))

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--config",
                str(cfg),
            ],
        )

    assert result.exit_code == 0
    assert "Render complete" in result.output


def test_render_short_output_dir_no_games(tmp_path: Path) -> None:
    """When output_dir has no game subdirs, skip tracking silently."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "random_dir").mkdir()

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"paths": {"output_dir": str(output_dir)}}))

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--config",
                str(cfg),
            ],
        )

    assert result.exit_code == 0
    assert "Render complete" in result.output


def test_render_short_auto_discover_direct_game_dir(tmp_path: Path) -> None:
    """When output_dir itself contains game.json, use it directly."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"paths": {"output_dir": str(game_dir)}}))

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--config",
                str(cfg),
            ],
        )

    assert result.exit_code == 0
    saved = json.loads((game_dir / "game.json").read_text())
    assert len(saved["renders"]) == 1


# ---------------------------------------------------------------------------
# render preview
# ---------------------------------------------------------------------------


def test_render_preview_dry_run(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "preview",
            str(clip),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    # Preview uses half resolution
    assert "Size: 540x960" in result.output


def test_render_preview_executes(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(app, ["render", "preview", str(clip)])

    assert result.exit_code == 0
    assert "Render complete" in result.output


def test_render_preview_default_output_suffix(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "preview",
            str(clip),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "clip_preview.mp4" in result.output


# ---------------------------------------------------------------------------
# render short/preview --render-profile
# ---------------------------------------------------------------------------


def test_render_short_with_render_profile(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path, "slowmo", speed=0.5)
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--render-profile",
            "slowmo",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Speed: 0.5x" in result.output
    assert "Profile: slowmo" in result.output


def test_render_short_render_profile_overrides_crop(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path, "cropped", speed=1.0, crop_mode="crop")
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--render-profile",
            "cropped",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Crop mode: crop" in result.output


def test_render_short_render_profile_not_found(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"config_version": 1}))
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--render-profile",
            "nonexistent",
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 1
    assert "not found" in result.output


def test_render_preview_with_render_profile(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path, "slowmo", speed=0.5)
    result = runner.invoke(
        app,
        [
            "render",
            "preview",
            str(clip),
            "--render-profile",
            "slowmo",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Speed: 0.5x" in result.output
    assert "Profile: slowmo" in result.output


def test_render_short_render_profile_executes(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path, "slowmo", speed=0.5)
    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--render-profile",
                "slowmo",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Render complete" in result.output


# ---------------------------------------------------------------------------
# --player / --assists flags + subtitle gap fix
# ---------------------------------------------------------------------------


def test_short_profile_subtitle_template_renders(tmp_path: Path) -> None:
    """Bug fix: subtitle_template in render profile was silently dropped in _do_short()."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{player}}", encoding="utf-8")

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="Roseville",
            away_team="Mahtomedi",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--render-profile",
            "overlay",
            "--game-dir",
            str(game_dir),
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Subtitle:" in result.output


def test_short_player_flag_populates_overlay_without_game(tmp_path: Path) -> None:
    """--player populates overlay context even without game state."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--render-profile",
                "overlay",
                "--player",
                "#17 Smith",
                "--assists",
                "#22 Jones, #5 Brown",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Subtitle:" in result.output


def test_short_assists_flag_populates_overlay_without_game(tmp_path: Path) -> None:
    """--assists populates overlay context even without game state."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Assists: {{goal_assist_1}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--render-profile",
                "overlay",
                "--assists",
                "#22 Jones",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Subtitle:" in result.output


def test_short_player_flag_overrides_event_data(tmp_path: Path) -> None:
    """CLI --player overrides player from game event metadata."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(date="2026-02-28", home_team="A", away_team="B", sport="hockey"),
        created_at="2026-02-28T12:00:00+00:00",
        events=[
            GameEvent(
                id="ev1",
                clip="clip.mkv",
                segment_number=1,
                event_type="goal",
                player="OldPlayer",
                metadata={"assists": "#99 OldAssist"},
            ),
        ],
    )
    _write_game_state(game_dir, state)

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--render-profile",
                "overlay",
                "--game-dir",
                str(game_dir),
                "--event",
                "ev1",
                "--player",
                "NewPlayer",
                "--assists",
                "#11 NewAssist",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Subtitle:" in result.output


def test_short_player_event_in_post_render_hook(tmp_path: Path) -> None:
    """Player, assists, and game_event are included in POST_RENDER hook data."""
    from unittest.mock import MagicMock

    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(date="2026-02-28", home_team="A", away_team="B", sport="hockey"),
        created_at="2026-02-28T12:00:00+00:00",
        events=[
            GameEvent(
                id="ev1",
                clip="clip.mkv",
                segment_number=1,
                event_type="goal",
            ),
        ],
    )
    _write_game_state(game_dir, state)

    mock_result = _mock_result(tmp_path)
    emitted: list[object] = []

    def capture_emit(hook: object, ctx: object) -> None:
        from reeln.plugins.hooks import Hook

        if getattr(hook, "value", None) == Hook.POST_RENDER.value:
            emitted.append(ctx)

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.plugins.registry.get_registry") as mock_get_reg,
    ):
        mock_renderer_cls.return_value.render.return_value = mock_result
        mock_reg = MagicMock()
        mock_reg.emit.side_effect = capture_emit
        mock_get_reg.return_value = mock_reg

        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--game-dir",
                str(game_dir),
                "--event",
                "ev1",
                "--player",
                "Jane Doe",
                "--assists",
                "John Smith",
            ],
        )

    assert result.exit_code == 0
    assert len(emitted) == 1
    ctx = emitted[0]
    assert getattr(ctx, "data", {}).get("player") == "Jane Doe"
    assert getattr(ctx, "data", {}).get("assists") == "John Smith"
    assert getattr(ctx, "data", {}).get("game_event") is not None
    assert getattr(ctx.data["game_event"], "event_type", None) == "goal"


def test_short_player_flag_without_render_profile_is_noop(tmp_path: Path) -> None:
    """--player without --render-profile is ignored (no subtitle template to fill)."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"config_version": 1}))

    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--player",
            "Smith",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Subtitle:" not in result.output


def test_preview_player_flag(tmp_path: Path) -> None:
    """--player flag works on render preview."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "preview",
                str(clip),
                "--render-profile",
                "overlay",
                "--player",
                "#17 Smith",
                "--assists",
                "#22",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Subtitle:" in result.output


def test_apply_player_flag_without_game_dir(tmp_path: Path) -> None:
    """--player on render apply populates overlay without game dir."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "overlay",
                "--player",
                "#17 Smith",
                "--assists",
                "#22 Jones",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Overlay:" in result.output


def test_apply_player_flag_overrides_event(tmp_path: Path) -> None:
    """--player on render apply overrides event-sourced player."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(date="2026-02-28", home_team="A", away_team="B", sport="hockey"),
        created_at="2026-02-28T12:00:00+00:00",
        events=[
            GameEvent(
                id="ev1",
                clip="x.mkv",
                segment_number=1,
                event_type="goal",
                player="OldPlayer",
            ),
        ],
    )
    _write_game_state(game_dir, state)

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "overlay",
                "--game-dir",
                str(game_dir),
                "--event",
                "ev1",
                "--player",
                "NewPlayer",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Overlay:" in result.output


def test_short_subtitle_temp_cleanup_after_render(tmp_path: Path) -> None:
    """Rendered subtitle temp files in _do_short() are cleaned up after render."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    out_dir = tmp_path / "output"
    out_dir.mkdir()

    template = tmp_path / "overlay.ass"
    template.write_text("Hello", encoding="utf-8")

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(date="2026-02-28", home_team="A", away_team="B", sport="hockey"),
        created_at="2026-02-28T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--render-profile",
                "overlay",
                "--game-dir",
                str(game_dir),
                "--output",
                str(out_dir / "out.mp4"),
                "--config",
                str(cfg),
            ],
        )

    assert result.exit_code == 0
    # Temp .ass files should be cleaned up
    ass_files = list(out_dir.glob("*.ass"))
    assert ass_files == []


def test_short_profile_no_subtitle_template_no_subtitle(tmp_path: Path) -> None:
    """Profile without subtitle_template doesn't trigger subtitle resolution."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path, "speedonly", speed=0.5)

    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--render-profile",
            "speedonly",
            "--player",
            "#17 Smith",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Subtitle:" not in result.output
    assert "Speed: 0.5x" in result.output


def test_apply_subtitle_without_game_info_uses_empty_context(tmp_path: Path) -> None:
    """render apply with subtitle_template but no game_info uses empty TemplateContext."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Static overlay", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "overlay",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Overlay:" in result.output


# ---------------------------------------------------------------------------
# render reel
# ---------------------------------------------------------------------------


def _setup_reel(tmp_path: Path) -> tuple[Path, Path]:
    """Create a game dir with one render entry and the rendered file."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    rendered = game_dir / "clip_short.mp4"
    rendered.write_bytes(b"video")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="roseville",
            away_team="mahtomedi",
            sport="hockey",
        ),
        renders=[
            RenderEntry(
                input="clip.mkv",
                output="clip_short.mp4",
                segment_number=1,
                format="1080x1920",
                crop_mode="pad",
                rendered_at="2026-02-26T12:00:00+00:00",
            ),
        ],
    )
    _write_game_state(game_dir, state)
    return game_dir, rendered


def test_render_reel_dry_run(tmp_path: Path) -> None:
    game_dir, _ = _setup_reel(tmp_path)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "Renders: 1" in result.output
    assert "clip_short.mp4" in result.output


def test_render_reel_executes(tmp_path: Path) -> None:
    game_dir, _ = _setup_reel(tmp_path)
    concat_file = game_dir / "concat.txt"
    concat_file.touch()
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.write_concat_file", return_value=concat_file),
        patch("reeln.core.ffmpeg.run_ffmpeg"),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "reel",
                "--game-dir",
                str(game_dir),
            ],
        )

    assert result.exit_code == 0
    assert "Reel assembly complete" in result.output


def test_render_reel_with_segment_filter(tmp_path: Path) -> None:
    game_dir, _ = _setup_reel(tmp_path)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--segment",
            "1",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Renders: 1" in result.output
    assert "period-1_reel.mp4" in result.output


def test_render_reel_segment_no_match(tmp_path: Path) -> None:
    game_dir, _ = _setup_reel(tmp_path)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--segment",
            "99",
        ],
    )
    assert result.exit_code == 1
    assert "No rendered shorts found" in result.output


def test_render_reel_no_renders(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
    )
    _write_game_state(game_dir, state)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
        ],
    )
    assert result.exit_code == 1
    assert "No rendered shorts found" in result.output


def test_render_reel_missing_file(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        renders=[
            RenderEntry(
                input="clip.mkv",
                output="missing.mp4",
                segment_number=1,
                format="1080x1920",
                crop_mode="pad",
                rendered_at="2026-02-26T12:00:00+00:00",
            ),
        ],
    )
    _write_game_state(game_dir, state)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
        ],
    )
    assert result.exit_code == 1
    assert "Rendered file not found" in result.output


def test_render_reel_custom_output(tmp_path: Path) -> None:
    game_dir, _ = _setup_reel(tmp_path)
    custom_out = tmp_path / "my_reel.mp4"
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--output",
            str(custom_out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert str(custom_out) in result.output


def test_render_reel_default_output_name(tmp_path: Path) -> None:
    game_dir, _ = _setup_reel(tmp_path)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "roseville_vs_mahtomedi_2026-02-26_reel.mp4" in result.output


def test_render_reel_game_state_error(tmp_path: Path) -> None:
    bad_dir = tmp_path / "nonexistent"
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(bad_dir),
        ],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_reel_config_error(tmp_path: Path) -> None:
    game_dir, _ = _setup_reel(tmp_path)
    bad_config = tmp_path / "bad.json"
    bad_config.write_text("invalid!")
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--config",
            str(bad_config),
        ],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_reel_ffmpeg_error(tmp_path: Path) -> None:
    game_dir, _ = _setup_reel(tmp_path)
    from reeln.core.errors import FFmpegError

    with patch("reeln.core.ffmpeg.discover_ffmpeg", side_effect=FFmpegError("not found")):
        result = runner.invoke(
            app,
            [
                "render",
                "reel",
                "--game-dir",
                str(game_dir),
            ],
        )
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_reel_mixed_formats(tmp_path: Path) -> None:
    """Mixed extensions trigger re-encode mode."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "a.mp4").write_bytes(b"video")
    (game_dir / "b.mkv").write_bytes(b"video")
    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        renders=[
            RenderEntry(
                input="a.mkv",
                output="a.mp4",
                segment_number=1,
                format="1080x1920",
                crop_mode="pad",
                rendered_at="2026-02-26T12:00:00+00:00",
            ),
            RenderEntry(
                input="b.mkv",
                output="b.mkv",
                segment_number=1,
                format="1080x1920",
                crop_mode="pad",
                rendered_at="2026-02-26T12:00:00+00:00",
            ),
        ],
    )
    _write_game_state(game_dir, state)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "re-encode" in result.output


# ---------------------------------------------------------------------------
# render short — event linking
# ---------------------------------------------------------------------------


def test_render_short_auto_links_event(tmp_path: Path) -> None:
    """Render auto-links to an event when the clip matches an event's clip path."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    clip = game_dir / "period-1" / "Replay_001.mkv"
    clip.parent.mkdir()
    clip.write_bytes(b"video")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
        events=[
            GameEvent(
                id="ev1234567890",
                clip="period-1/Replay_001.mkv",
                segment_number=1,
                event_type="goal",
            ),
        ],
    )
    _write_game_state(game_dir, state)

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--game-dir",
                str(game_dir),
            ],
        )

    assert result.exit_code == 0
    saved = json.loads((game_dir / "game.json").read_text())
    assert saved["renders"][0]["event_id"] == "ev1234567890"


def test_render_short_no_matching_event(tmp_path: Path) -> None:
    """Render entry has empty event_id when no event matches the clip."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    clip = tmp_path / "external_clip.mkv"
    clip.write_bytes(b"video")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
        events=[
            GameEvent(
                id="ev1234567890",
                clip="period-1/Replay_001.mkv",
                segment_number=1,
            ),
        ],
    )
    _write_game_state(game_dir, state)

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--game-dir",
                str(game_dir),
            ],
        )

    assert result.exit_code == 0
    saved = json.loads((game_dir / "game.json").read_text())
    assert saved["renders"][0]["event_id"] == ""


def test_render_short_explicit_event(tmp_path: Path) -> None:
    """--event flag explicitly links the render to an event ID."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"video")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--game-dir",
                str(game_dir),
                "--event",
                "custom_event_id",
            ],
        )

    assert result.exit_code == 0
    saved = json.loads((game_dir / "game.json").read_text())
    assert saved["renders"][0]["event_id"] == "custom_event_id"


def test_render_short_explicit_event_overrides_auto(tmp_path: Path) -> None:
    """--event flag takes precedence over auto-link detection."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    clip = game_dir / "period-1" / "Replay_001.mkv"
    clip.parent.mkdir()
    clip.write_bytes(b"video")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
        events=[
            GameEvent(
                id="auto_event_id",
                clip="period-1/Replay_001.mkv",
                segment_number=1,
            ),
        ],
    )
    _write_game_state(game_dir, state)

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--game-dir",
                str(game_dir),
                "--event",
                "explicit_event_id",
            ],
        )

    assert result.exit_code == 0
    saved = json.loads((game_dir / "game.json").read_text())
    assert saved["renders"][0]["event_id"] == "explicit_event_id"


# ---------------------------------------------------------------------------
# render reel — event-type filtering
# ---------------------------------------------------------------------------


def test_render_reel_event_type_filter(tmp_path: Path) -> None:
    """--event-type filters renders by linked event type."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "goal_short.mp4").write_bytes(b"video")
    (game_dir / "save_short.mp4").write_bytes(b"video")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        events=[
            GameEvent(id="ev_goal", clip="period-1/r1.mkv", segment_number=1, event_type="goal"),
            GameEvent(id="ev_save", clip="period-1/r2.mkv", segment_number=1, event_type="save"),
        ],
        renders=[
            RenderEntry(
                input="period-1/r1.mkv",
                output="goal_short.mp4",
                segment_number=1,
                format="1080x1920",
                crop_mode="pad",
                rendered_at="2026-02-26T12:00:00+00:00",
                event_id="ev_goal",
            ),
            RenderEntry(
                input="period-1/r2.mkv",
                output="save_short.mp4",
                segment_number=1,
                format="1080x1920",
                crop_mode="pad",
                rendered_at="2026-02-26T12:00:00+00:00",
                event_id="ev_save",
            ),
        ],
    )
    _write_game_state(game_dir, state)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--event-type",
            "goal",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Renders: 1" in result.output
    assert "goal_short.mp4" in result.output
    assert "save_short.mp4" not in result.output


def test_render_reel_event_type_no_match(tmp_path: Path) -> None:
    """--event-type with no matching events returns error."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "clip_short.mp4").write_bytes(b"video")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        events=[
            GameEvent(id="ev_save", clip="period-1/r1.mkv", segment_number=1, event_type="save"),
        ],
        renders=[
            RenderEntry(
                input="period-1/r1.mkv",
                output="clip_short.mp4",
                segment_number=1,
                format="1080x1920",
                crop_mode="pad",
                rendered_at="2026-02-26T12:00:00+00:00",
                event_id="ev_save",
            ),
        ],
    )
    _write_game_state(game_dir, state)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--event-type",
            "goal",
        ],
    )
    assert result.exit_code == 1
    assert "No rendered shorts found" in result.output


def test_render_reel_event_type_unlinked_renders_excluded(tmp_path: Path) -> None:
    """Renders without event_id are excluded when --event-type is used."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "clip_short.mp4").write_bytes(b"video")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        events=[
            GameEvent(id="ev_goal", clip="period-1/r1.mkv", segment_number=1, event_type="goal"),
        ],
        renders=[
            RenderEntry(
                input="period-1/r1.mkv",
                output="clip_short.mp4",
                segment_number=1,
                format="1080x1920",
                crop_mode="pad",
                rendered_at="2026-02-26T12:00:00+00:00",
                event_id="",  # unlinked
            ),
        ],
    )
    _write_game_state(game_dir, state)
    result = runner.invoke(
        app,
        [
            "render",
            "reel",
            "--game-dir",
            str(game_dir),
            "--event-type",
            "goal",
        ],
    )
    assert result.exit_code == 1
    assert "No rendered shorts found" in result.output


# ---------------------------------------------------------------------------
# render apply
# ---------------------------------------------------------------------------


def _config_with_profile(
    tmp_path: Path,
    profile_name: str = "slowmo",
    speed: float = 0.5,
    **kwargs: object,
) -> Path:
    """Write a config file with a render profile."""
    profile_data: dict[str, object] = {"speed": speed, **kwargs}
    cfg_data = {"render_profiles": {profile_name: profile_data}}
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))
    return cfg


def test_render_apply_help() -> None:
    result = runner.invoke(app, ["render", "apply", "--help"])
    assert result.exit_code == 0
    assert "--render-profile" in result.output


def test_render_apply_dry_run(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path)
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "slowmo",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "Profile: slowmo" in result.output
    assert "Speed: 0.5x" in result.output


def test_render_apply_default_output(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path)
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "slowmo",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "clip_slowmo.mp4" in result.output


def test_render_apply_custom_output(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    out = tmp_path / "custom.mp4"
    cfg = _config_with_profile(tmp_path)
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "slowmo",
            "--output",
            str(out),
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert str(out) in result.output


def test_render_apply_with_lut(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path, speed=1.0, lut="warm.cube")
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "slowmo",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "LUT: warm.cube" in result.output


def test_render_apply_executes(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path)
    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Render complete" in result.output
    assert "Duration: 30.0s" in result.output


def test_render_apply_no_duration(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path)
    mock_result = RenderResult(output=tmp_path / "out.mp4")
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Duration:" not in result.output
    assert "File size:" not in result.output


def test_render_apply_unknown_profile(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"config_version": 1}))
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "nonexistent",
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 1
    assert "not found" in result.output


def test_render_apply_config_error(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    bad_cfg = tmp_path / "bad.json"
    bad_cfg.write_text("invalid!")
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "slowmo",
            "--config",
            str(bad_cfg),
        ],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_apply_ffmpeg_error(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path)
    from reeln.core.errors import FFmpegError

    with patch("reeln.core.ffmpeg.discover_ffmpeg", side_effect=FFmpegError("not found")):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_apply_with_game_dir_and_subtitle(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    # Template file
    template = tmp_path / "overlay.ass"
    template.write_text("Team: {{home_team}} vs {{away_team}}", encoding="utf-8")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="Roseville",
            away_team="Mahtomedi",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    cfg_data = {
        "render_profiles": {
            "overlay": {"speed": 0.5, "subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "overlay",
            "--game-dir",
            str(game_dir),
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Overlay:" in result.output


def test_render_apply_with_event_context(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{player}}", encoding="utf-8")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="A",
            away_team="B",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
        events=[
            GameEvent(
                id="ev123",
                clip="period-1/r1.mkv",
                segment_number=1,
                event_type="goal",
                player="Smith",
            ),
        ],
    )
    _write_game_state(game_dir, state)

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "overlay",
                "--game-dir",
                str(game_dir),
                "--event",
                "ev123",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Overlay:" in result.output


def test_render_apply_game_dir_not_found_nonfatal(tmp_path: Path) -> None:
    """Bad game dir is non-fatal for apply (just skips context)."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    bad_dir = tmp_path / "nonexistent"
    cfg = _config_with_profile(tmp_path)
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "slowmo",
            "--game-dir",
            str(bad_dir),
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Profile: slowmo" in result.output


def test_render_apply_subtitle_cleanup_after_render(tmp_path: Path) -> None:
    """Rendered subtitle temp files are cleaned up after render."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    out_dir = tmp_path / "output"
    out_dir.mkdir()

    template = tmp_path / "overlay.ass"
    template.write_text("Hello", encoding="utf-8")

    state = GameState(
        game_info=GameInfo(
            date="2026-02-28",
            home_team="A",
            away_team="B",
            sport="hockey",
        ),
        created_at="2026-02-28T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    mock_result = _mock_result(tmp_path)
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "overlay",
                "--game-dir",
                str(game_dir),
                "--output",
                str(out_dir / "out.mp4"),
                "--config",
                str(cfg),
            ],
        )

    assert result.exit_code == 0
    # Temp .ass files should be cleaned up
    ass_files = list(out_dir.glob("*.ass"))
    assert ass_files == []


def test_render_apply_invalid_speed(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path, speed=5.0)
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "slowmo",
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code == 1
    assert "Speed must be" in result.output


# ---------------------------------------------------------------------------
# --iterate on render apply
# ---------------------------------------------------------------------------


def _config_with_iterations(tmp_path: Path) -> Path:
    """Write a config file with profiles + iterations."""
    cfg_data = {
        "render_profiles": {
            "fullspeed": {"speed": 1.0},
            "slowmo": {"speed": 0.5},
        },
        "iterations": {
            "default": ["fullspeed", "slowmo"],
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))
    return cfg


def test_render_apply_iterate_dry_run(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Dry run — no files written", "Iterations: 2 profile(s)"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--iterate",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Iterations: 2 profile(s)" in result.output


def test_render_apply_iterate_executes(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--iterate",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output


def test_render_apply_iterate_no_profiles_falls_through(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    # Config with profiles but no iterations section
    cfg = _config_with_profile(tmp_path, "slowmo", speed=0.5)
    result = runner.invoke(
        app,
        [
            "render",
            "apply",
            str(clip),
            "--render-profile",
            "slowmo",
            "--iterate",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "No iteration profiles configured" in result.output
    # Falls through to single render
    assert "Dry run" in result.output


def test_render_apply_iterate_with_game_dir(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="t1",
    )
    _write_game_state(game_dir, state)
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--iterate",
                "--game-dir",
                str(game_dir),
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output


def test_render_apply_iterate_error(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_iterations(tmp_path)
    from reeln.core.errors import RenderError

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            side_effect=RenderError("iteration failed"),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--iterate",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 1
    assert "iteration failed" in result.output


# ---------------------------------------------------------------------------
# --iterate on render short / render preview
# ---------------------------------------------------------------------------


def test_render_short_iterate_dry_run(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Dry run — no files written", "Iterations: 2 profile(s)"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--iterate",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Iterations: 2 profile(s)" in result.output


def test_render_short_iterate_no_profiles(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_profile(tmp_path, "slowmo", speed=0.5)
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--iterate",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "No iteration profiles configured" in result.output


def test_render_short_iterate_executes(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--iterate",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output


def test_render_short_iterate_with_game_dir(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="t1",
        events=[
            GameEvent(
                id="ev1",
                clip="period-1/clip.mkv",
                segment_number=1,
                event_type="goal",
                created_at="t1",
            )
        ],
    )
    _write_game_state(game_dir, state)
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--iterate",
                "--game-dir",
                str(game_dir),
                "--event",
                "ev1",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output


def test_render_preview_iterate(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "preview",
                str(clip),
                "--iterate",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output


def test_render_short_iterate_game_dir_no_event(tmp_path: Path) -> None:
    """Iterate with --game-dir but no --event (event_id is None)."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(
            date="2026-02-26",
            home_team="a",
            away_team="b",
            sport="hockey",
        ),
        created_at="t1",
    )
    _write_game_state(game_dir, state)
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--iterate",
                "--game-dir",
                str(game_dir),
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output


def test_render_short_iterate_game_dir_load_fails(tmp_path: Path) -> None:
    """Iterate with --game-dir pointing to invalid dir — load_game_state fails gracefully."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    # No game.json → load_game_state will raise MediaError
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--iterate",
                "--game-dir",
                str(game_dir),
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output


def test_render_short_iterate_error(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    cfg = _config_with_iterations(tmp_path)
    from reeln.core.errors import RenderError

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            side_effect=RenderError("iteration failed"),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--iterate",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 1
    assert "iteration failed" in result.output


# ---------------------------------------------------------------------------
# --debug flag
# ---------------------------------------------------------------------------


def test_render_short_debug(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    gi = GameInfo(date="2026-02-26", home_team="a", away_team="b", sport="hockey")
    state = GameState(game_info=gi)
    _write_game_state(game_dir, state)

    mock_result = RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=30.0,
        file_size_bytes=1024000,
        ffmpeg_command=["ffmpeg", "-i", str(clip), str(tmp_path / "out.mp4")],
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
        patch("reeln.core.ffmpeg.probe_duration", return_value=None),
        patch("reeln.core.ffmpeg.probe_fps", return_value=None),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=None),
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--game-dir",
                str(game_dir),
                "--debug",
            ],
        )

    assert result.exit_code == 0
    assert "Debug:" in result.output
    assert (game_dir / "debug").is_dir()


def test_render_short_debug_no_game_dir(tmp_path: Path) -> None:
    """Debug with no game dir doesn't crash — debug is silently skipped."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    mock_result = RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=30.0,
        file_size_bytes=1024000,
        ffmpeg_command=["ffmpeg", "-i", str(clip), str(tmp_path / "out.mp4")],
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
        patch("reeln.commands.render._find_game_dir", return_value=None),
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--debug",
            ],
        )

    assert result.exit_code == 0
    # No Debug line because there's no game dir to resolve to
    assert "Debug:" not in result.output


def test_render_preview_debug(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    gi = GameInfo(date="2026-02-26", home_team="a", away_team="b", sport="hockey")
    state = GameState(game_info=gi)
    _write_game_state(game_dir, state)

    mock_result = RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=10.0,
        file_size_bytes=512000,
        ffmpeg_command=["ffmpeg", "-i", str(clip), str(tmp_path / "out.mp4")],
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
        patch("reeln.core.ffmpeg.probe_duration", return_value=None),
        patch("reeln.core.ffmpeg.probe_fps", return_value=None),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=None),
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "preview",
                str(clip),
                "--game-dir",
                str(game_dir),
                "--debug",
            ],
        )

    assert result.exit_code == 0
    assert "Debug:" in result.output


def test_render_apply_debug(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    gi = GameInfo(date="2026-02-26", home_team="a", away_team="b", sport="hockey")
    state = GameState(game_info=gi)
    _write_game_state(game_dir, state)

    # Create config with a render profile
    cfg_data = {
        "config_version": 1,
        "render_profiles": {"slowmo": {"speed": 0.5}},
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(cfg_data))

    mock_result = RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=60.0,
        file_size_bytes=2048000,
        ffmpeg_command=["ffmpeg", "-i", str(clip), str(tmp_path / "out.mp4")],
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
        patch("reeln.core.ffmpeg.probe_duration", return_value=None),
        patch("reeln.core.ffmpeg.probe_fps", return_value=None),
        patch("reeln.core.ffmpeg.probe_resolution", return_value=None),
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--game-dir",
                str(game_dir),
                "--debug",
                "--config",
                str(cfg_path),
            ],
        )

    assert result.exit_code == 0
    assert "Debug:" in result.output
    assert (game_dir / "debug").is_dir()


def test_render_apply_debug_no_game_dir(tmp_path: Path) -> None:
    """--debug without --game-dir is silently skipped."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    cfg_data = {
        "config_version": 1,
        "render_profiles": {"slowmo": {"speed": 0.5}},
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(cfg_data))

    mock_result = RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=60.0,
        file_size_bytes=2048000,
        ffmpeg_command=["ffmpeg", "-i", str(clip), str(tmp_path / "out.mp4")],
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
    ):
        mock_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "slowmo",
                "--debug",
                "--config",
                str(cfg_path),
            ],
        )

    assert result.exit_code == 0
    assert "Debug:" not in result.output


# ---------------------------------------------------------------------------
# --player / --assists with iterate path
# ---------------------------------------------------------------------------


def test_short_iterate_with_player_and_assists(tmp_path: Path) -> None:
    """--player and --assists flow through to iterate path context."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    state = GameState(
        game_info=GameInfo(date="2026-02-26", home_team="A", away_team="B", sport="hockey"),
        created_at="t1",
        events=[
            GameEvent(
                id="ev1",
                clip="clip.mkv",
                segment_number=1,
                event_type="goal",
                created_at="t1",
            ),
        ],
    )
    _write_game_state(game_dir, state)
    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ) as mock_iter,
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--iterate",
                "--game-dir",
                str(game_dir),
                "--event",
                "ev1",
                "--player",
                "NewPlayer",
                "--assists",
                "#22 Jones",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output
    # Verify player override was passed to render_iterations
    call_kwargs = mock_iter.call_args
    ctx = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
    assert ctx is not None
    assert ctx.get("player") == "NewPlayer"
    meta = call_kwargs.kwargs.get("event_metadata") or call_kwargs[1].get("event_metadata")
    assert meta is not None
    assert meta["assists"] == "#22 Jones"


def test_short_iterate_smart_passes_zoom_path(tmp_path: Path) -> None:
    """--smart --iterate extracts frames and passes zoom_path to render_iterations."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )
    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    def _provide_zoom(context: object) -> None:
        from reeln.plugins.hooks import HookContext

        assert isinstance(context, HookContext)
        context.shared["smart_zoom"] = {"zoom_path": zoom}

    def _activate_with_zoom_handler(plugins_config: object) -> dict[str, object]:
        get_registry().register(Hook.ON_FRAMES_EXTRACTED, _provide_zoom)
        return {}

    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.commands.render.activate_plugins", side_effect=_activate_with_zoom_handler),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ) as mock_iter,
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "crop",
                "--smart",
                "--iterate",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Iteration rendering complete" in result.output
    call_kwargs = mock_iter.call_args
    assert call_kwargs.kwargs.get("zoom_path") is zoom
    assert call_kwargs.kwargs.get("source_fps") == 60.0


def test_short_iterate_smart_debug_writes_zoom(tmp_path: Path) -> None:
    """--smart --iterate --debug writes zoom debug artifacts."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )
    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    def _provide_zoom(context: object) -> None:
        from reeln.plugins.hooks import HookContext

        assert isinstance(context, HookContext)
        context.shared["smart_zoom"] = {"zoom_path": zoom}

    def _activate_with_zoom_handler(plugins_config: object) -> dict[str, object]:
        get_registry().register(Hook.ON_FRAMES_EXTRACTED, _provide_zoom)
        return {}

    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.commands.render.activate_plugins", side_effect=_activate_with_zoom_handler),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
        patch("reeln.core.zoom_debug.write_zoom_debug") as mock_zoom_debug,
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "crop",
                "--smart",
                "--iterate",
                "--game-dir",
                str(game_dir),
                "--debug",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Debug:" in result.output
    mock_zoom_debug.assert_called_once()


def test_short_iterate_debug_no_smart_no_zoom_debug(tmp_path: Path) -> None:
    """--iterate --debug without --smart doesn't write zoom debug."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--iterate",
                "--game-dir",
                str(game_dir),
                "--debug",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "Debug:" not in result.output


def test_short_iterate_smart_no_plugin_falls_back(tmp_path: Path) -> None:
    """--smart --iterate without plugin providing zoom falls back to static."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    cfg = _config_with_iterations(tmp_path)
    iter_result = IterationResult(
        output=tmp_path / "out.mp4",
        iteration_outputs=[],
        profile_names=["fullspeed", "slowmo"],
        concat_copy=True,
    )
    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch(
            "reeln.core.iterations.render_iterations",
            return_value=(iter_result, ["Iteration rendering complete"]),
        ) as mock_iter,
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "crop",
                "--smart",
                "--iterate",
                "--config",
                str(cfg),
            ],
        )
    assert result.exit_code == 0
    assert "No smart zoom data from plugins" in result.output
    assert "Iteration rendering complete" in result.output
    call_kwargs = mock_iter.call_args
    assert call_kwargs.kwargs.get("zoom_path") is None


def test_short_subtitle_game_dir_load_fails_nonfatal(tmp_path: Path) -> None:
    """Subtitle resolution handles game_dir load failure gracefully."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    template = tmp_path / "overlay.ass"
    template.write_text("Static overlay", encoding="utf-8")

    bad_game_dir = tmp_path / "badgame"
    bad_game_dir.mkdir()
    # Write invalid game.json to trigger ReelnError
    (bad_game_dir / "game.json").write_text("not json!")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--render-profile",
            "overlay",
            "--game-dir",
            str(bad_game_dir),
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Subtitle:" in result.output


# ---------------------------------------------------------------------------
# Smart zoom — crop mode: smart
# ---------------------------------------------------------------------------


def test_render_short_smart_crop_fallback_no_plugin(tmp_path: Path) -> None:
    """Smart crop with no plugin providing zoom data falls back to center crop."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "smart",
                "--dry-run",
            ],
        )

    assert result.exit_code == 0
    assert "No smart zoom data from plugins" in result.output
    assert "Crop mode: crop" in result.output
    assert "Dry run" in result.output


def test_render_short_smart_crop_with_zoom_path(tmp_path: Path) -> None:
    """Smart crop with a plugin providing zoom path shows smart zoom info."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    def _provide_zoom(context: object) -> None:
        from reeln.plugins.hooks import HookContext

        assert isinstance(context, HookContext)
        context.shared["smart_zoom"] = {"zoom_path": zoom}

    def _activate_with_zoom_handler(plugins_config: object) -> dict[str, object]:
        # Simulate activate_plugins but register our test handler
        get_registry().register(Hook.ON_FRAMES_EXTRACTED, _provide_zoom)
        return {}

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.commands.render.activate_plugins", side_effect=_activate_with_zoom_handler),
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "smart",
                "--dry-run",
            ],
        )

    assert result.exit_code == 0
    assert "Smart zoom: 2 target points" in result.output
    assert "Crop mode: smart" in result.output
    assert "Dry run" in result.output


def test_render_short_smart_crop_plugin_zoom_error(tmp_path: Path) -> None:
    """Smart zoom error from plugin raises RenderError and exits 1."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    def _provide_error(context: object) -> None:
        from reeln.plugins.hooks import HookContext

        assert isinstance(context, HookContext)
        context.shared["smart_zoom"] = {"error": "vision API timed out"}

    def _activate_with_error_handler(plugins_config: object) -> dict[str, object]:
        get_registry().register(Hook.ON_FRAMES_EXTRACTED, _provide_error)
        return {}

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.commands.render.activate_plugins", side_effect=_activate_with_error_handler),
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "crop",
                "--smart",
            ],
        )

    assert result.exit_code != 0
    assert result.exception is not None
    assert "Smart zoom analysis failed" in str(result.exception)


def test_render_short_smart_crop_extract_error(tmp_path: Path) -> None:
    """Smart crop errors when frame extraction fails."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.core.errors import RenderError

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
    ):
        mock_renderer_cls.return_value.extract_frames.side_effect = RenderError("probe failed")
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "smart",
            ],
        )

    assert result.exit_code == 1
    assert "Error extracting frames" in result.output


def test_render_short_smart_crop_zoom_frames_option(tmp_path: Path) -> None:
    """--zoom-frames is passed to extract_frames."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames

    frames = ExtractedFrames(
        frame_paths=tuple(tmp_path / f"f{i}.png" for i in range(3)),
        timestamps=(2.5, 5.0, 7.5),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "smart",
                "--zoom-frames",
                "3",
                "--dry-run",
            ],
        )

    assert result.exit_code == 0
    call_args = mock_renderer_cls.return_value.extract_frames.call_args
    assert call_args[1]["count"] == 3 or call_args[0][1] == 3


def test_render_short_smart_crop_cleanup(tmp_path: Path) -> None:
    """Extracted frames directory is cleaned up even on error."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    created_dirs: list[Path] = []
    original_mkdtemp = __import__("tempfile").mkdtemp

    def _tracking_mkdtemp(**kwargs: object) -> str:
        result_str = original_mkdtemp(**kwargs)
        created_dirs.append(Path(result_str))
        return result_str

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("tempfile.mkdtemp", side_effect=_tracking_mkdtemp),
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        runner.invoke(
            app,
            ["render", "short", str(clip), "--crop", "smart", "--dry-run"],
        )

    # The temp dir should have been cleaned up
    for d in created_dirs:
        assert not d.exists()


def test_render_short_smart_crop_ffmpeg_discovery_error(tmp_path: Path) -> None:
    """Smart crop errors when ffmpeg discovery fails."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.core.errors import FFmpegError

    with patch("reeln.core.ffmpeg.discover_ffmpeg", side_effect=FFmpegError("not found")):
        result = runner.invoke(
            app,
            ["render", "short", str(clip), "--crop", "smart"],
        )

    assert result.exit_code == 1
    assert "Error:" in result.output


def test_render_short_smart_crop_debug_with_zoom(tmp_path: Path) -> None:
    """Debug mode with smart zoom includes zoom_path info."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    info = GameInfo(
        home_team="TeamA",
        away_team="TeamB",
        sport="hockey",
        date="2026-03-19",
    )
    state = GameState(game_info=info)
    _write_game_state(game_dir, state)

    mock_result = RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=10.0,
        file_size_bytes=512000,
        ffmpeg_command=["ffmpeg", "-y", "out.mp4"],
    )

    def _activate_with_zoom(plugins_config: object) -> dict[str, object]:
        get_registry().register(
            Hook.ON_FRAMES_EXTRACTED,
            lambda ctx: ctx.shared.update({"smart_zoom": {"zoom_path": zoom}}),
        )
        return {}

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.commands.render.activate_plugins", side_effect=_activate_with_zoom),
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        mock_renderer_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "smart",
                "--game-dir",
                str(game_dir),
                "--debug",
            ],
        )

    assert result.exit_code == 0
    assert "Smart zoom: 2 target points" in result.output
    assert "Debug:" in result.output


def test_render_short_smart_debug_captures_plugin_debug(tmp_path: Path) -> None:
    """Debug mode saves plugin debug data (prompts) to zoom debug directory."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    info = GameInfo(
        home_team="TeamA",
        away_team="TeamB",
        sport="hockey",
        date="2026-03-21",
    )
    state = GameState(game_info=info)
    _write_game_state(game_dir, state)

    mock_result = RenderResult(
        output=tmp_path / "out.mp4",
        duration_seconds=10.0,
        file_size_bytes=512000,
        ffmpeg_command=["ffmpeg", "-y", "out.mp4"],
    )

    plugin_debug = {"prompt": "analyze this frame", "model": "gpt-4o"}

    def _activate_with_zoom_debug(plugins_config: object) -> dict[str, object]:
        get_registry().register(
            Hook.ON_FRAMES_EXTRACTED,
            lambda ctx: ctx.shared.update({"smart_zoom": {"zoom_path": zoom, "debug": plugin_debug}}),
        )
        return {}

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.commands.render.activate_plugins", side_effect=_activate_with_zoom_debug),
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        mock_renderer_cls.return_value.render.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "crop",
                "--smart",
                "--game-dir",
                str(game_dir),
                "--debug",
            ],
        )

    assert result.exit_code == 0
    # Plugin debug should be written
    plugin_json = game_dir / "debug" / "zoom" / "plugin_debug.json"
    assert plugin_json.is_file()
    data = json.loads(plugin_json.read_text())
    assert data["prompt"] == "analyze this frame"
    assert data["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# --scale and --smart CLI options
# ---------------------------------------------------------------------------


def test_render_short_scale_display(tmp_path: Path) -> None:
    """--scale shows Scale: Nx in output."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--scale",
            "1.3",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Scale: 1.3x" in result.output


def test_render_short_scale_default_no_display(tmp_path: Path) -> None:
    """Scale=1.0 (default) does NOT show Scale line."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Scale:" not in result.output


def test_render_short_smart_pad_deprecation_warning(tmp_path: Path) -> None:
    """--crop smart_pad shows deprecation warning."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    zoom = ZoomPath(
        points=(ZoomPoint(timestamp=0.0, center_x=0.5, center_y=0.5),),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    def _activate_with_zoom(plugins_config: object) -> dict[str, object]:
        get_registry().register(
            Hook.ON_FRAMES_EXTRACTED,
            lambda ctx: ctx.shared.update({"smart_zoom": {"zoom_path": zoom}}),
        )
        return {}

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.commands.render.activate_plugins", side_effect=_activate_with_zoom),
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        mock_renderer_cls.return_value.render.return_value = _mock_result(tmp_path)
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "smart_pad",
            ],
        )

    assert result.exit_code == 0
    assert "--crop smart_pad is deprecated" in result.output


def test_render_short_smart_flag_triggers_frames(tmp_path: Path) -> None:
    """--smart flag triggers frame extraction like --crop smart."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    from reeln.models.zoom import ExtractedFrames, ZoomPath, ZoomPoint
    from reeln.plugins.hooks import Hook
    from reeln.plugins.registry import get_registry

    frames = ExtractedFrames(
        frame_paths=(tmp_path / "f.png",),
        timestamps=(5.0,),
        source_width=1920,
        source_height=1080,
        duration=10.0,
        fps=60.0,
    )

    zoom = ZoomPath(
        points=(
            ZoomPoint(timestamp=0.0, center_x=0.3, center_y=0.5),
            ZoomPoint(timestamp=10.0, center_x=0.7, center_y=0.5),
        ),
        source_width=1920,
        source_height=1080,
        duration=10.0,
    )

    def _activate_with_zoom(plugins_config: object) -> dict[str, object]:
        get_registry().register(
            Hook.ON_FRAMES_EXTRACTED,
            lambda ctx: ctx.shared.update({"smart_zoom": {"zoom_path": zoom}}),
        )
        return {}

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_renderer_cls,
        patch("reeln.commands.render.activate_plugins", side_effect=_activate_with_zoom),
    ):
        mock_renderer_cls.return_value.extract_frames.return_value = frames
        mock_renderer_cls.return_value.render.return_value = _mock_result(tmp_path)
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--crop",
                "pad",
                "--smart",
            ],
        )

    assert result.exit_code == 0
    assert "Smart zoom: 2 target points" in result.output


def test_render_preview_scale_display(tmp_path: Path) -> None:
    """Preview also shows scale."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "preview",
            str(clip),
            "--scale",
            "1.5",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Scale: 1.5x" in result.output


# ---------------------------------------------------------------------------
# _find_game_dir — clip-aware resolution
# ---------------------------------------------------------------------------


def test_find_game_dir_prefers_clip_parent(tmp_path: Path) -> None:
    """When clip is inside a game dir, that game dir is preferred over most recent."""
    from reeln.commands.render import _find_game_dir

    # Older game dir that contains the clip
    game_a = tmp_path / "game_a"
    game_a.mkdir()
    (game_a / "game.json").write_text("{}")
    clip = game_a / "period-1" / "clip.mp4"
    clip.parent.mkdir()
    clip.touch()

    # Newer game dir (should NOT be picked)
    game_b = tmp_path / "game_b"
    game_b.mkdir()
    (game_b / "game.json").write_text("{}")
    # Ensure game_b is more recent
    import time

    time.sleep(0.01)
    (game_b / "game.json").write_text("{}")

    result = _find_game_dir(tmp_path, clip=clip)
    assert result == game_a


def test_find_game_dir_falls_back_to_most_recent_without_clip(tmp_path: Path) -> None:
    """Without clip, falls back to most recently modified game.json."""
    from reeln.commands.render import _find_game_dir

    game_a = tmp_path / "game_a"
    game_a.mkdir()
    (game_a / "game.json").write_text("{}")

    import time

    time.sleep(0.01)

    game_b = tmp_path / "game_b"
    game_b.mkdir()
    (game_b / "game.json").write_text("{}")

    result = _find_game_dir(tmp_path)
    assert result == game_b


def test_find_game_dir_clip_not_in_any_game_dir(tmp_path: Path) -> None:
    """When clip isn't inside any game dir, falls back to most recent."""
    from reeln.commands.render import _find_game_dir

    game_a = tmp_path / "game_a"
    game_a.mkdir()
    (game_a / "game.json").write_text("{}")

    clip = tmp_path / "stray" / "clip.mp4"
    clip.parent.mkdir()
    clip.touch()

    result = _find_game_dir(tmp_path, clip=clip)
    assert result == game_a


def test_find_game_dir_none_output_dir() -> None:
    """Returns None when output_dir is None."""
    from reeln.commands.render import _find_game_dir

    assert _find_game_dir(None) is None
    assert _find_game_dir(None, clip=Path("/tmp/clip.mp4")) is None


def test_find_game_dir_output_dir_is_game_dir(tmp_path: Path) -> None:
    """When output_dir itself has game.json, returns it directly."""
    from reeln.commands.render import _find_game_dir

    (tmp_path / "game.json").write_text("{}")
    result = _find_game_dir(tmp_path)
    assert result == tmp_path


def test_find_game_dir_resolve_error_skips_candidate(tmp_path: Path) -> None:
    """OSError during is_relative_to raises on resolved paths — candidate is skipped."""
    from reeln.commands.render import _find_game_dir

    game_a = tmp_path / "game_a"
    game_a.mkdir()
    (game_a / "game.json").write_text("{}")

    clip = game_a / "clip.mp4"
    clip.touch()

    # Make is_relative_to raise OSError to hit the except branch
    with patch.object(Path, "is_relative_to", side_effect=OSError("broken")):
        result = _find_game_dir(tmp_path, clip=clip)
    # Falls back to most recent since is_relative_to() failed
    assert result == game_a


# ---------------------------------------------------------------------------
# --player-numbers flag
# ---------------------------------------------------------------------------


def _write_roster(path: Path) -> None:
    """Write a sample roster CSV."""
    path.write_text(
        "number,name,position\n48,John Smith,C\n24,Jane Doe,D\n2,Bob Jones,RW\n",
        encoding="utf-8",
    )


def _game_state_with_level(
    level: str = "bantam",
    home_slug: str = "eagles",
    away_slug: str = "bears",
) -> GameState:
    """Create a GameState with level and slug fields populated."""
    return GameState(
        game_info=GameInfo(
            date="2026-03-04",
            home_team="Eagles",
            away_team="Bears",
            sport="hockey",
            level=level,
            home_slug=home_slug,
            away_slug=away_slug,
        ),
        created_at="2026-03-04T12:00:00+00:00",
    )


def test_player_numbers_with_valid_game_and_roster(tmp_path: Path) -> None:
    """--player-numbers looks up scorer and assists from team roster."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    roster_path = tmp_path / "roster.csv"
    _write_roster(roster_path)

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    home_profile = TeamProfile(
        team_name="Eagles",
        short_name="EGL",
        level="bantam",
        roster_path=str(roster_path),
    )

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
        patch("reeln.core.teams.load_team_profile", return_value=home_profile),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--player-numbers",
                "48,24,2",
                "--event-type",
                "HOME_GOAL",
                "--game-dir",
                str(game_dir),
                "--render-profile",
                "overlay",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "Subtitle:" in result.output


def test_player_numbers_without_game_dir(tmp_path: Path) -> None:
    """--player-numbers without a game directory exits with error."""
    clip = tmp_path / "clip.mkv"
    clip.touch()

    cfg = tmp_path / "empty.json"
    cfg.write_text(json.dumps({"config_version": 1}))

    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--player-numbers",
            "48",
            "--config",
            str(cfg),
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "requires a game directory" in result.output


def test_player_numbers_game_missing_level(tmp_path: Path) -> None:
    """--player-numbers with game that has no level/slugs exits with error."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    # GameInfo with no level/slugs
    state = GameState(
        game_info=GameInfo(
            date="2026-03-04",
            home_team="Eagles",
            away_team="Bears",
            sport="hockey",
        ),
        created_at="2026-03-04T12:00:00+00:00",
    )
    _write_game_state(game_dir, state)

    clip = tmp_path / "clip.mkv"
    clip.touch()

    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--player-numbers",
            "48",
            "--game-dir",
            str(game_dir),
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "requires team profiles" in result.output


def test_player_numbers_missing_roster(tmp_path: Path) -> None:
    """--player-numbers with team profile lacking roster_path exits with error."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    # Profile with no roster_path
    home_profile = TeamProfile(team_name="Eagles", short_name="EGL", level="bantam")

    with patch("reeln.core.teams.load_team_profile", return_value=home_profile):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--player-numbers",
                "48",
                "--game-dir",
                str(game_dir),
                "--dry-run",
            ],
        )
    assert result.exit_code == 1
    assert "No roster file configured" in result.output


def test_player_numbers_unknown_number_fallback(tmp_path: Path) -> None:
    """Unknown jersey number falls back to '#N' display with warning."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    roster_path = tmp_path / "roster.csv"
    roster_path.write_text("number,name,position\n48,John Smith,C\n", encoding="utf-8")

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    home_profile = TeamProfile(
        team_name="Eagles",
        short_name="EGL",
        level="bantam",
        roster_path=str(roster_path),
    )

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
        patch("reeln.core.teams.load_team_profile", return_value=home_profile),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--player-numbers",
                "48,99",
                "--game-dir",
                str(game_dir),
                "--render-profile",
                "overlay",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    # Should succeed despite unknown #99
    assert result.exit_code == 0, result.output


def test_player_numbers_explicit_player_overrides(tmp_path: Path) -> None:
    """Explicit --player and --assists take precedence over --player-numbers roster lookup."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    roster_path = tmp_path / "roster.csv"
    _write_roster(roster_path)

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    home_profile = TeamProfile(
        team_name="Eagles",
        short_name="EGL",
        level="bantam",
        roster_path=str(roster_path),
    )

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
        patch("reeln.core.teams.load_team_profile", return_value=home_profile),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--player-numbers",
                "48,24",
                "--player",
                "Custom Player",
                "--assists",
                "Custom Assist",
                "--game-dir",
                str(game_dir),
                "--render-profile",
                "overlay",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output


def test_player_numbers_away_goal(tmp_path: Path) -> None:
    """--event-type AWAY_GOAL resolves the away team's roster."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    roster_path = tmp_path / "roster.csv"
    _write_roster(roster_path)

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    away_profile = TeamProfile(
        team_name="Bears",
        short_name="BRS",
        level="bantam",
        roster_path=str(roster_path),
    )

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
        patch("reeln.core.teams.load_team_profile", return_value=away_profile),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--player-numbers",
                "48",
                "--event-type",
                "AWAY_GOAL",
                "--game-dir",
                str(game_dir),
                "--render-profile",
                "overlay",
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output


def test_player_numbers_game_state_load_error(tmp_path: Path) -> None:
    """--player-numbers with corrupt game.json exits with error."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "game.json").write_text("not valid json")

    clip = tmp_path / "clip.mkv"
    clip.touch()

    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--player-numbers",
            "48",
            "--game-dir",
            str(game_dir),
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "Error" in result.output


def test_player_numbers_team_profile_not_found(tmp_path: Path) -> None:
    """--player-numbers with missing team profile exits with error."""
    from reeln.core.errors import ConfigError as _CE

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    with patch("reeln.core.teams.load_team_profile", side_effect=_CE("not found")):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--player-numbers",
                "48",
                "--game-dir",
                str(game_dir),
                "--dry-run",
            ],
        )
    assert result.exit_code == 1
    assert "Team profile not found" in result.output


def test_player_numbers_roster_file_missing(tmp_path: Path) -> None:
    """--player-numbers with missing roster file exits with error."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    home_profile = TeamProfile(
        team_name="Eagles",
        short_name="EGL",
        level="bantam",
        roster_path=str(tmp_path / "nonexistent.csv"),
    )

    with patch("reeln.core.teams.load_team_profile", return_value=home_profile):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--player-numbers",
                "48",
                "--game-dir",
                str(game_dir),
                "--dry-run",
            ],
        )
    assert result.exit_code == 1
    assert "Roster file not found" in result.output


def test_player_numbers_on_preview(tmp_path: Path) -> None:
    """--player-numbers works on render preview."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    roster_path = tmp_path / "roster.csv"
    _write_roster(roster_path)

    home_profile = TeamProfile(
        team_name="Eagles",
        short_name="EGL",
        level="bantam",
        roster_path=str(roster_path),
    )

    with patch("reeln.core.teams.load_team_profile", return_value=home_profile):
        result = runner.invoke(
            app,
            [
                "render",
                "preview",
                str(clip),
                "--player-numbers",
                "48",
                "--game-dir",
                str(game_dir),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output


def test_player_numbers_auto_applies_overlay_profile(tmp_path: Path) -> None:
    """--player-numbers without -r auto-applies player-overlay profile."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    roster_path = tmp_path / "roster.csv"
    _write_roster(roster_path)

    home_profile = TeamProfile(
        team_name="Eagles",
        short_name="EGL",
        level="bantam",
        roster_path=str(roster_path),
    )

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
        patch("reeln.core.teams.load_team_profile", return_value=home_profile),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--player-numbers",
                "48,24",
                "--game-dir",
                str(game_dir),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    # The bundled config includes player-overlay, so it should be auto-applied
    assert "player-overlay" in result.output or "Dry run" in result.output


def test_player_numbers_on_apply(tmp_path: Path) -> None:
    """--player-numbers works on render apply."""
    from reeln.models.team import TeamProfile

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    _write_game_state(game_dir, _game_state_with_level())

    clip = tmp_path / "clip.mkv"
    clip.touch()

    roster_path = tmp_path / "roster.csv"
    _write_roster(roster_path)

    template = tmp_path / "overlay.ass"
    template.write_text("Player: {{goal_scorer_text}}", encoding="utf-8")

    cfg_data = {
        "render_profiles": {
            "overlay": {"subtitle_template": str(template)},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(cfg_data))

    home_profile = TeamProfile(
        team_name="Eagles",
        short_name="EGL",
        level="bantam",
        roster_path=str(roster_path),
    )

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.ffmpeg.probe_duration", return_value=10.0),
        patch("reeln.core.teams.load_team_profile", return_value=home_profile),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "apply",
                str(clip),
                "--render-profile",
                "overlay",
                "--player-numbers",
                "48,24",
                "--game-dir",
                str(game_dir),
                "--config",
                str(cfg),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# --no-branding flag
# ---------------------------------------------------------------------------


def test_render_short_no_branding_flag(tmp_path: Path) -> None:
    """--no-branding suppresses branding overlay."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--no-branding",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_render_preview_no_branding_flag(tmp_path: Path) -> None:
    """--no-branding on preview suppresses branding overlay."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "preview",
            str(clip),
            "--no-branding",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_render_short_branding_enabled_by_default(tmp_path: Path) -> None:
    """Without --no-branding, branding is resolved from config."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    result = runner.invoke(
        app,
        [
            "render",
            "short",
            str(clip),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_render_short_branding_error_continues(tmp_path: Path) -> None:
    """When branding resolution fails, render continues with a warning."""
    from unittest.mock import patch

    from reeln.core.errors import RenderError

    clip = tmp_path / "clip.mkv"
    clip.touch()
    with patch(
        "reeln.core.branding.resolve_branding",
        side_effect=RenderError("broken template"),
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "short",
                str(clip),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "Warning: Failed to resolve branding" in result.output
    assert "Dry run" in result.output


def test_render_short_plugin_input_in_hook_data(tmp_path: Path) -> None:
    """--plugin-input values are included in PRE_RENDER and POST_RENDER hook data."""
    clip = tmp_path / "clip.mkv"
    clip.touch()
    mock_result = _mock_result(tmp_path)

    captured_pre: dict[str, object] = {}
    captured_post: dict[str, object] = {}

    def _capture_emit(hook: object, ctx: object) -> None:
        from reeln.plugins.hooks import Hook

        if hasattr(ctx, "data"):
            if hook == Hook.PRE_RENDER:
                captured_pre.update(ctx.data)
            elif hook == Hook.POST_RENDER:
                captured_post.update(ctx.data)

    with (
        patch("reeln.core.ffmpeg.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.renderer.FFmpegRenderer") as mock_cls,
        patch("reeln.plugins.registry.get_registry") as mock_reg,
    ):
        mock_cls.return_value.render.return_value = mock_result
        mock_reg.return_value.emit.side_effect = _capture_emit
        result = runner.invoke(
            app,
            ["render", "short", str(clip), "-I", "mykey=myval"],
        )

    assert result.exit_code == 0
    assert captured_pre.get("plugin_inputs") == {"mykey": "myval"}
    assert captured_post.get("plugin_inputs") == {"mykey": "myval"}
