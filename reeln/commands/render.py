"""Render command group: short, preview, apply, reel."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from reeln.core.config import load_config
from reeln.core.errors import ReelnError
from reeln.core.shorts import plan_preview, plan_short
from reeln.models.short import (
    ANCHOR_POSITIONS,
    FORMAT_SIZES,
    CropAnchor,
    CropMode,
    OutputFormat,
    ShortConfig,
)
from reeln.models.template import TemplateContext
from reeln.plugins.loader import activate_plugins

app = typer.Typer(no_args_is_help=True, help="Render commands.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_size(fmt: str | None, size: str | None) -> tuple[int, int]:
    """Resolve output dimensions from format preset or explicit WxH."""
    if size is not None:
        parts = size.lower().split("x")
        if len(parts) != 2:
            raise typer.BadParameter(f"Invalid size format: {size!r}. Use WxH (e.g., 1080x1920).")
        try:
            return int(parts[0]), int(parts[1])
        except ValueError as exc:
            raise typer.BadParameter(f"Invalid size values: {size!r}. Width and height must be integers.") from exc
    if fmt is not None:
        try:
            return FORMAT_SIZES[OutputFormat(fmt)]
        except ValueError as exc:
            raise typer.BadParameter(f"Unknown format: {fmt!r}. Use vertical or square.") from exc
    return FORMAT_SIZES[OutputFormat.VERTICAL]


def _resolve_anchor(anchor: str) -> tuple[float, float]:
    """Resolve anchor to (x, y) floats.

    Accepts named positions (center, top, etc.) or ``x,y`` format.
    """
    try:
        return ANCHOR_POSITIONS[CropAnchor(anchor)]
    except ValueError:
        pass
    parts = anchor.split(",")
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    raise typer.BadParameter(f"Invalid anchor: {anchor!r}. Use center/top/bottom/left/right or 'x,y' (0.0-1.0).")


def _find_latest_video(directory: Path, source_glob: str) -> Path:
    """Find the most recently modified file matching *source_glob* in *directory*.

    Raises ``typer.Exit`` if no matching files are found.
    """
    import fnmatch

    candidates: list[Path] = [f for f in directory.iterdir() if f.is_file() and fnmatch.fnmatch(f.name, source_glob)]
    if not candidates:
        typer.echo(
            f"Error: No files matching '{source_glob}' in {directory}",
            err=True,
        )
        raise typer.Exit(code=1)
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _find_game_dir(output_dir: Path | None) -> Path | None:
    """Try to find the latest game directory for render tracking.

    Returns ``None`` if no game directory can be found (no error).
    """
    if output_dir is None:
        return None
    if (output_dir / "game.json").is_file():
        return output_dir
    if not output_dir.is_dir():
        return None
    candidates = [f for f in output_dir.iterdir() if f.is_dir() and (f / "game.json").is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p / "game.json").stat().st_mtime)


def _default_output(input_path: Path, suffix: str) -> Path:
    """Generate default output path from input path and suffix."""
    return input_path.parent / f"{input_path.stem}{suffix}.mp4"


def _record_render(
    game_dir: Path,
    input_path: Path,
    output_path: Path,
    segment_number: int,
    width: int,
    height: int,
    crop_mode: CropMode,
    event_id: str | None = None,
) -> None:
    """Append a render entry to game state.

    If *event_id* is provided, use it directly.  Otherwise, auto-link by
    matching the input clip path against registered events.
    """
    from reeln.core.highlights import load_game_state, save_game_state
    from reeln.models.game import RenderEntry

    state = load_game_state(game_dir)
    rel_input = str(input_path.relative_to(game_dir)) if input_path.is_relative_to(game_dir) else str(input_path)
    rel_output = str(output_path.relative_to(game_dir)) if output_path.is_relative_to(game_dir) else str(output_path)

    resolved_event_id = event_id or ""
    if not resolved_event_id:
        # Auto-link: match input clip against event clips
        for ev in state.events:
            if ev.clip == rel_input:
                resolved_event_id = ev.id
                break

    entry = RenderEntry(
        input=rel_input,
        output=rel_output,
        segment_number=segment_number,
        format=f"{width}x{height}",
        crop_mode=crop_mode.value,
        rendered_at=datetime.now(tz=UTC).isoformat(),
        event_id=resolved_event_id,
    )
    state.renders.append(entry)
    save_game_state(state, game_dir)


def _do_short(
    clip: Path | None,
    output: Path | None,
    fmt: str | None,
    size: str | None,
    crop: str,
    anchor: str,
    pad_color: str,
    speed: float,
    lut: Path | None,
    subtitle: Path | None,
    game_dir: Path | None,
    profile: str | None,
    config_path: Path | None,
    dry_run: bool,
    *,
    is_preview: bool,
    event_id: str | None = None,
    render_profile_name: str | None = None,
    iterate: bool = False,
    debug: bool = False,
    player: str | None = None,
    assists: str | None = None,
) -> None:
    """Shared implementation for short and preview commands."""
    from reeln.core.ffmpeg import discover_ffmpeg
    from reeln.core.profiles import apply_profile_to_short, resolve_profile
    from reeln.core.renderer import FFmpegRenderer

    try:
        config = load_config(path=config_path, profile=profile)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    activate_plugins(config.plugins)

    if clip is None:
        source_dir = config.paths.source_dir
        if source_dir is None:
            typer.echo(
                "Error: No clip provided and paths.source_dir not configured.\n"
                "Either pass a clip argument or set paths.source_dir in config "
                "(or REELN_PATHS_SOURCE_DIR env var).",
                err=True,
            )
            raise typer.Exit(code=1)
        clip = _find_latest_video(source_dir, config.paths.source_glob)

    width, height = _resolve_size(fmt, size)
    anchor_x, anchor_y = _resolve_anchor(anchor)

    suffix = "_preview" if is_preview else "_short"
    out = output or _default_output(clip, suffix)

    try:
        crop_mode = CropMode(crop)
    except ValueError:
        typer.echo(f"Error: Unknown crop mode: {crop!r}. Use pad or crop.", err=True)
        raise typer.Exit(code=1) from None

    short_config = ShortConfig(
        input=clip,
        output=out,
        width=width,
        height=height,
        crop_mode=crop_mode,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        pad_color=pad_color,
        speed=speed,
        lut=lut,
        subtitle=subtitle,
        codec=config.video.codec,
        preset=config.video.preset,
        crf=config.video.crf,
        audio_codec=config.video.audio_codec,
        audio_bitrate=config.video.audio_bitrate,
    )

    # Apply render profile overlay if specified
    rendered_subtitle: Path | None = None
    if render_profile_name is not None:
        from reeln.core.profiles import resolve_subtitle_for_profile
        from reeln.core.templates import build_base_context

        try:
            rp = resolve_profile(config, render_profile_name)
        except ReelnError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        # Resolve subtitle template if the profile has one
        if rp.subtitle_template is not None:
            game_event = None
            game_info = None
            resolved_game_dir = game_dir or _find_game_dir(config.paths.output_dir)
            if resolved_game_dir is not None:
                try:
                    from reeln.core.highlights import load_game_state

                    state = load_game_state(resolved_game_dir)
                    game_info = state.game_info
                    if event_id is not None:
                        game_event = next(
                            (e for e in state.events if e.id == event_id), None
                        )
                except ReelnError:
                    pass

            ctx = build_base_context(game_info, game_event) if game_info else TemplateContext()
            if player is not None:
                ctx = TemplateContext(variables={**ctx.variables, "player": player})

            event_meta = dict(game_event.metadata) if game_event else None
            if assists is not None:
                event_meta = event_meta or {}
                event_meta["assists"] = assists

            if event_meta is not None:
                from reeln.core.ffmpeg import discover_ffmpeg as _disc
                from reeln.core.ffmpeg import probe_duration as _probe_dur
                from reeln.core.overlay import build_overlay_context

                dur = _probe_dur(_disc(), clip) or 10.0
                ctx = build_overlay_context(ctx, duration=dur, event_metadata=event_meta)

            rendered_subtitle = resolve_subtitle_for_profile(
                rp, ctx, (output or _default_output(clip, "_short")).parent
            )

        short_config = apply_profile_to_short(
            short_config, rp, rendered_subtitle=rendered_subtitle
        )

    # Multi-iteration mode
    if iterate:
        from reeln.core.iterations import render_iterations
        from reeln.core.profiles import profiles_for_event
        from reeln.core.templates import build_base_context

        game_event = None
        game_info = None
        resolved_game_dir = game_dir or _find_game_dir(config.paths.output_dir)
        if resolved_game_dir is not None:
            try:
                from reeln.core.highlights import load_game_state

                state = load_game_state(resolved_game_dir)
                game_info = state.game_info
                if event_id is not None:
                    game_event = next((e for e in state.events if e.id == event_id), None)
            except ReelnError:
                pass

        profile_list = profiles_for_event(config, game_event)
        if profile_list:
            iter_ctx: TemplateContext | None = build_base_context(game_info, game_event) if game_info else None
            if player is not None and iter_ctx is not None:
                iter_ctx = TemplateContext(variables={**iter_ctx.variables, "player": player})
            event_meta = dict(game_event.metadata) if game_event else None
            if assists is not None:
                event_meta = event_meta or {}
                event_meta["assists"] = assists
            try:
                ffmpeg_path = discover_ffmpeg()
                _, messages = render_iterations(
                    clip,
                    profile_list,
                    config,
                    ffmpeg_path,
                    out,
                    context=iter_ctx,
                    event_metadata=event_meta,
                    is_short=True,
                    short_config=short_config,
                    dry_run=dry_run,
                )
            except ReelnError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1) from exc
            for msg in messages:
                typer.echo(msg)
            return
        typer.echo("Warning: No iteration profiles configured, using single render", err=True)

    try:
        try:
            plan = plan_preview(short_config) if is_preview else plan_short(short_config)
        except ReelnError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(f"Input: {clip}")
        typer.echo(f"Output: {out}")
        typer.echo(f"Size: {plan.width}x{plan.height}")
        typer.echo(f"Crop mode: {short_config.crop_mode.value}")
        if short_config.speed != 1.0:
            typer.echo(f"Speed: {short_config.speed}x")
        if short_config.lut:
            typer.echo(f"LUT: {short_config.lut}")
        if short_config.subtitle:
            typer.echo(f"Subtitle: {short_config.subtitle}")
        if render_profile_name is not None:
            typer.echo(f"Profile: {render_profile_name}")

        if dry_run:
            typer.echo("Dry run — no files written")
            return

        try:
            ffmpeg_path = discover_ffmpeg()
            renderer = FFmpegRenderer(ffmpeg_path)
            result = renderer.render(plan)
        except ReelnError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        if result.duration_seconds is not None:
            typer.echo(f"Duration: {result.duration_seconds:.1f}s")
        if result.file_size_bytes is not None:
            size_mb = result.file_size_bytes / (1024 * 1024)
            typer.echo(f"File size: {size_mb:.1f} MB")
        typer.echo("Render complete")

        resolved_game_dir = game_dir or _find_game_dir(config.paths.output_dir)
        if resolved_game_dir is not None:
            try:
                _record_render(
                    resolved_game_dir,
                    clip,
                    out,
                    0,
                    short_config.width,
                    short_config.height,
                    short_config.crop_mode,
                    event_id=event_id,
                )
            except ReelnError as exc:
                typer.echo(f"Warning: Failed to record render: {exc}", err=True)

            if debug and result.ffmpeg_command:
                from reeln.core.debug import build_debug_artifact, write_debug_artifact, write_debug_index

                artifact = build_debug_artifact(
                    "render_preview" if is_preview else "render_short",
                    result.ffmpeg_command,
                    [clip],
                    out,
                    resolved_game_dir,
                    ffmpeg_path,
                    extra={"crop_mode": crop, "size": f"{short_config.width}x{short_config.height}", "speed": speed},
                )
                write_debug_artifact(resolved_game_dir, artifact)
                write_debug_index(resolved_game_dir)
                typer.echo(f"Debug: {resolved_game_dir / 'debug'}")
    finally:
        if rendered_subtitle is not None:
            rendered_subtitle.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def short(
    clip: Path | None = typer.Argument(None, help="Input video file. Default: latest in cwd."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str | None = typer.Option(None, "--format", "-f", help="Output format: vertical, square."),
    size: str | None = typer.Option(None, "--size", help="Custom WxH (e.g., 1080x1920)."),
    crop: str = typer.Option("pad", "--crop", "-c", help="Crop mode: pad, crop."),
    anchor: str = typer.Option("center", "--anchor", "-a", help="Crop anchor: center/top/bottom/left/right or x,y."),
    pad_color: str = typer.Option("black", "--pad-color", help="Pad bar color."),
    speed: float = typer.Option(1.0, "--speed", help="Playback speed (0.5-2.0)."),
    lut: Path | None = typer.Option(None, "--lut", help="LUT file (.cube/.3dl)."),
    subtitle: Path | None = typer.Option(None, "--subtitle", help="ASS subtitle file."),
    game_dir: Path | None = typer.Option(None, "--game-dir", help="Game directory for render tracking."),
    event: str | None = typer.Option(None, "--event", help="Link to event ID (auto-detected if omitted)."),
    render_profile: str | None = typer.Option(None, "--render-profile", "-r", help="Named render profile from config."),
    player_name: str | None = typer.Option(None, "--player", help="Player name for overlay."),
    assists_str: str | None = typer.Option(None, "--assists", help="Assists, comma-separated."),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
    iterate: bool = typer.Option(False, "--iterate", help="Multi-iteration mode using event type config."),
    debug_flag: bool = typer.Option(False, "--debug", help="Write debug artifacts to game debug directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
) -> None:
    """Render a 9:16 short from a clip."""
    _do_short(
        clip,
        output,
        fmt,
        size,
        crop,
        anchor,
        pad_color,
        speed,
        lut,
        subtitle,
        game_dir,
        profile,
        config_path,
        dry_run,
        is_preview=False,
        event_id=event,
        render_profile_name=render_profile,
        iterate=iterate,
        debug=debug_flag,
        player=player_name,
        assists=assists_str,
    )


@app.command()
def preview(
    clip: Path | None = typer.Argument(None, help="Input video file. Default: latest in cwd."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str | None = typer.Option(None, "--format", "-f", help="Output format: vertical, square."),
    size: str | None = typer.Option(None, "--size", help="Custom WxH (e.g., 1080x1920)."),
    crop: str = typer.Option("pad", "--crop", "-c", help="Crop mode: pad, crop."),
    anchor: str = typer.Option("center", "--anchor", "-a", help="Crop anchor: center/top/bottom/left/right or x,y."),
    pad_color: str = typer.Option("black", "--pad-color", help="Pad bar color."),
    speed: float = typer.Option(1.0, "--speed", help="Playback speed (0.5-2.0)."),
    lut: Path | None = typer.Option(None, "--lut", help="LUT file (.cube/.3dl)."),
    subtitle: Path | None = typer.Option(None, "--subtitle", help="ASS subtitle file."),
    game_dir: Path | None = typer.Option(None, "--game-dir", help="Game directory for render tracking."),
    render_profile: str | None = typer.Option(None, "--render-profile", "-r", help="Named render profile from config."),
    player_name: str | None = typer.Option(None, "--player", help="Player name for overlay."),
    assists_str: str | None = typer.Option(None, "--assists", help="Assists, comma-separated."),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
    iterate: bool = typer.Option(False, "--iterate", help="Multi-iteration mode using event type config."),
    debug_flag: bool = typer.Option(False, "--debug", help="Write debug artifacts to game debug directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
) -> None:
    """Fast low-res preview render."""
    _do_short(
        clip,
        output,
        fmt,
        size,
        crop,
        anchor,
        pad_color,
        speed,
        lut,
        subtitle,
        game_dir,
        profile,
        config_path,
        dry_run,
        is_preview=True,
        render_profile_name=render_profile,
        iterate=iterate,
        debug=debug_flag,
        player=player_name,
        assists=assists_str,
    )


@app.command()
def reel(
    game_dir: Path = typer.Option(..., "--game-dir", help="Game directory."),
    segment_number: int | None = typer.Option(None, "--segment", "-s", help="Filter by segment number."),
    event_type: str | None = typer.Option(None, "--event-type", help="Filter by linked event type."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
) -> None:
    """Assemble rendered shorts into a concatenated reel."""
    from reeln.core.ffmpeg import (
        build_concat_command,
        discover_ffmpeg,
        run_ffmpeg,
        write_concat_file,
    )
    from reeln.core.highlights import load_game_state
    from reeln.core.segment import segment_dir_name

    try:
        config = load_config(path=config_path, profile=profile)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    activate_plugins(config.plugins)

    try:
        state = load_game_state(game_dir)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    renders = state.renders
    if segment_number is not None:
        renders = [r for r in renders if r.segment_number == segment_number]
    if event_type is not None:
        event_ids_by_type = {e.id for e in state.events if e.event_type == event_type}
        renders = [r for r in renders if r.event_id in event_ids_by_type]

    if not renders:
        typer.echo("Error: No rendered shorts found.", err=True)
        raise typer.Exit(code=1)

    files: list[Path] = []
    for r in renders:
        p = game_dir / r.output if not Path(r.output).is_absolute() else Path(r.output)
        if not p.is_file():
            typer.echo(f"Error: Rendered file not found: {p}", err=True)
            raise typer.Exit(code=1)
        files.append(p)

    info = state.game_info
    if output is not None:
        out = output
    elif segment_number is not None:
        seg_alias = segment_dir_name(info.sport, segment_number)
        out = game_dir / f"{info.home_team}_vs_{info.away_team}_{info.date}_{seg_alias}_reel.mp4"
    else:
        out = game_dir / f"{info.home_team}_vs_{info.away_team}_{info.date}_reel.mp4"

    extensions = {f.suffix.lower() for f in files}
    copy = len(extensions) <= 1

    typer.echo(f"Renders: {len(files)}")
    for f in files:
        typer.echo(f"  {f.name}")
    typer.echo(f"Mode: {'stream copy' if copy else 're-encode (mixed formats)'}")
    typer.echo(f"Output: {out}")

    if dry_run:
        typer.echo("Dry run — no files written")
        return

    try:
        ffmpeg_path = discover_ffmpeg()
        concat_file = write_concat_file(files, game_dir)
        try:
            cmd = build_concat_command(
                ffmpeg_path,
                concat_file,
                out,
                copy=copy,
                video_codec=config.video.codec,
                crf=config.video.crf,
                audio_codec=config.video.audio_codec,
            )
            run_ffmpeg(cmd)
        finally:
            concat_file.unlink(missing_ok=True)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Reel assembly complete")


@app.command(name="apply")
def apply_profile(
    clip: Path = typer.Argument(..., help="Input video file."),
    render_profile: str = typer.Option(..., "--render-profile", "-r", help="Named render profile from config."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
    game_dir: Path | None = typer.Option(None, "--game-dir", help="Game directory for template context."),
    event: str | None = typer.Option(None, "--event", help="Event ID for template context."),
    player_name: str | None = typer.Option(None, "--player", help="Player name for overlay."),
    assists_str: str | None = typer.Option(None, "--assists", help="Assists, comma-separated."),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
    iterate: bool = typer.Option(False, "--iterate", help="Multi-iteration mode using event type config."),
    debug_flag: bool = typer.Option(False, "--debug", help="Write debug artifacts to game debug directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
) -> None:
    """Apply a named render profile to a clip (full-frame, no crop/scale)."""
    from reeln.core.profiles import (
        plan_full_frame,
        resolve_profile,
        resolve_subtitle_for_profile,
    )
    from reeln.core.templates import build_base_context

    try:
        config = load_config(path=config_path, profile=profile)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    activate_plugins(config.plugins)

    out = output or _default_output(clip, f"_{render_profile}")

    # Build template context for subtitle rendering
    game_event = None
    game_info = None
    if game_dir is not None:
        try:
            from reeln.core.highlights import load_game_state

            state = load_game_state(game_dir)
            game_info = state.game_info
            if event is not None:
                game_event = next((e for e in state.events if e.id == event), None)
        except ReelnError:
            pass  # non-fatal: just skip context

    # Multi-iteration mode
    if iterate:
        from reeln.core.iterations import render_iterations
        from reeln.core.profiles import profiles_for_event

        profile_list = profiles_for_event(config, game_event)
        if profile_list:
            ctx = build_base_context(game_info, game_event) if game_info else None
            if player_name is not None and ctx is not None:
                ctx = TemplateContext(variables={**ctx.variables, "player": player_name})
            event_meta = dict(game_event.metadata) if game_event else None
            if assists_str is not None:
                event_meta = event_meta or {}
                event_meta["assists"] = assists_str
            try:
                from reeln.core.ffmpeg import discover_ffmpeg

                ffmpeg_path = discover_ffmpeg()
                _, messages = render_iterations(
                    clip,
                    profile_list,
                    config,
                    ffmpeg_path,
                    out,
                    context=ctx,
                    event_metadata=event_meta,
                    dry_run=dry_run,
                )
            except ReelnError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1) from exc
            for msg in messages:
                typer.echo(msg)
            return
        typer.echo("Warning: No iteration profiles configured, using single render", err=True)

    try:
        rp = resolve_profile(config, render_profile)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    rendered_subtitle: Path | None = None
    try:
        if rp.subtitle_template is not None:
            ctx = build_base_context(game_info, game_event) if game_info else TemplateContext()
            if player_name is not None:
                ctx = TemplateContext(variables={**ctx.variables, "player": player_name})

            event_meta = dict(game_event.metadata) if game_event else None
            if assists_str is not None:
                event_meta = event_meta or {}
                event_meta["assists"] = assists_str

            if event_meta is not None:
                from reeln.core.ffmpeg import discover_ffmpeg as _disc
                from reeln.core.ffmpeg import probe_duration as _probe_dur
                from reeln.core.overlay import build_overlay_context

                dur = _probe_dur(_disc(), clip) or 10.0
                ctx = build_overlay_context(ctx, duration=dur, event_metadata=event_meta)
            rendered_subtitle = resolve_subtitle_for_profile(rp, ctx, out.parent)

        try:
            plan = plan_full_frame(clip, out, rp, config, rendered_subtitle=rendered_subtitle)
        except ReelnError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(f"Input: {clip}")
        typer.echo(f"Output: {out}")
        typer.echo(f"Profile: {render_profile}")
        if rp.speed is not None and rp.speed != 1.0:
            typer.echo(f"Speed: {rp.speed}x")
        if rp.lut is not None:
            typer.echo(f"LUT: {rp.lut}")
        if rendered_subtitle is not None:
            typer.echo(f"Subtitle: {rp.subtitle_template}")

        if dry_run:
            typer.echo("Dry run — no files written")
            return

        from reeln.core.ffmpeg import discover_ffmpeg
        from reeln.core.renderer import FFmpegRenderer

        try:
            ffmpeg_path = discover_ffmpeg()
            renderer = FFmpegRenderer(ffmpeg_path)
            result = renderer.render(plan)
        except ReelnError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        if result.duration_seconds is not None:
            typer.echo(f"Duration: {result.duration_seconds:.1f}s")
        if result.file_size_bytes is not None:
            size_mb = result.file_size_bytes / (1024 * 1024)
            typer.echo(f"File size: {size_mb:.1f} MB")
        typer.echo("Render complete")

        if debug_flag and game_dir is not None and result.ffmpeg_command:
            from reeln.core.debug import build_debug_artifact, write_debug_artifact, write_debug_index

            artifact = build_debug_artifact(
                "render_apply",
                result.ffmpeg_command,
                [clip],
                out,
                game_dir,
                ffmpeg_path,
                extra={"profile": render_profile},
            )
            write_debug_artifact(game_dir, artifact)
            write_debug_index(game_dir)
            typer.echo(f"Debug: {game_dir / 'debug'}")
    finally:
        if rendered_subtitle is not None:
            rendered_subtitle.unlink(missing_ok=True)
