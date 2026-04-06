"""Render command group: short, preview, apply, reel."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from reeln.core.config import load_config
from reeln.core.errors import ReelnError, RenderError
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


def _find_game_dir(output_dir: Path | None, clip: Path | None = None) -> Path | None:
    """Try to find the game directory for render tracking.

    When *clip* is provided, prefer the game dir that contains the clip.
    Falls back to the most recently modified ``game.json`` otherwise.

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

    # Prefer the game dir that contains the clip
    if clip is not None:
        resolved_clip = clip.resolve()
        for candidate in candidates:
            try:
                if resolved_clip.is_relative_to(candidate.resolve()):
                    return candidate
            except (ValueError, OSError):
                continue

    return max(candidates, key=lambda p: (p / "game.json").stat().st_mtime)


def _default_output(input_path: Path, suffix: str) -> Path:
    """Generate default output path in a ``shorts/`` subdirectory.

    Renders go into ``<parent>/shorts/`` to keep the source directory clean
    and prevent segment merges from picking up rendered files.
    """
    return input_path.parent / "shorts" / f"{input_path.stem}{suffix}.mp4"


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


def _resolve_player_numbers(
    player_numbers: str,
    event_type: str | None,
    game_dir: Path | None,
    config_output_dir: Path | None,
    clip: Path | None,
) -> tuple[str, str | None, str | None, Path | None]:
    """Resolve --player-numbers to (scorer_display, assists_csv, scoring_team_name, logo_path).

    Loads game state, determines scoring team, loads roster, and looks up numbers.
    Returns the scorer display string, a comma-separated assists string (or None),
    the scoring team name (or None), and the team logo path (or None if not set
    or file does not exist).
    """
    from reeln.core.highlights import load_game_state
    from reeln.core.teams import load_roster, load_team_profile, lookup_players, resolve_scoring_team

    # 1. Find game directory
    resolved_game_dir = game_dir or _find_game_dir(config_output_dir, clip)
    if resolved_game_dir is None:
        typer.echo(
            "Error: --player-numbers requires a game directory (use --game-dir or run from a game workspace)",
            err=True,
        )
        raise typer.Exit(code=1)

    # 2. Load game state
    try:
        state = load_game_state(resolved_game_dir)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    game_info = state.game_info
    if not game_info.level or not game_info.home_slug:
        typer.echo(
            "Error: --player-numbers requires team profiles (game must be initialized with --level)",
            err=True,
        )
        raise typer.Exit(code=1)

    # 3. Determine scoring team
    team_name, team_slug, level = resolve_scoring_team(event_type or "", game_info)

    # 4. Load team profile → roster
    try:
        team_profile = load_team_profile(level, team_slug)
    except ReelnError:
        typer.echo(f"Error: Team profile not found: {level}/{team_slug}", err=True)
        raise typer.Exit(code=1) from None

    if not team_profile.roster_path:
        typer.echo(f"Error: No roster file configured for team '{team_name}'", err=True)
        raise typer.Exit(code=1)

    roster_path = Path(team_profile.roster_path)
    try:
        roster = load_roster(roster_path)
    except ReelnError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # 5. Look up numbers
    numbers = [n.strip() for n in player_numbers.split(",") if n.strip()]
    scorer, assist_list = lookup_players(roster, numbers, team_name)

    assists_csv = ", ".join(assist_list) if assist_list else None

    # 6. Resolve logo path
    logo: Path | None = None
    if team_profile.logo_path:
        candidate = Path(team_profile.logo_path)
        if candidate.is_file():
            logo = candidate

    return (scorer, assists_csv, team_name, logo)


def _do_short(
    clip: Path | None,
    output: Path | None,
    fmt: str | None,
    size: str | None,
    crop: str,
    anchor: str,
    pad_color: str,
    speed: float,
    scale: float,
    smart: bool,
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
    zoom_frames: int | None = None,
    player_numbers: str | None = None,
    event_type: str | None = None,
    no_branding: bool = False,
    plugin_input: list[str] | None = None,
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

    # Collect plugin-contributed inputs
    from reeln.plugins.inputs import get_input_collector as _get_input_collector

    _input_collector = _get_input_collector()
    _render_command = "render_preview" if is_preview else "render_short"
    _plugin_inputs = _input_collector.collect_noninteractive(_render_command, plugin_input or [])

    # Resolve --player-numbers before anything else
    _scoring_team_name: str | None = None
    _logo_path: Path | None = None
    if player_numbers is not None:
        scorer, assists_from_roster, _scoring_team_name, _logo_path = _resolve_player_numbers(
            player_numbers, event_type, game_dir, config.paths.output_dir, clip
        )
        # Explicit --player/--assists take precedence over roster lookup
        if player is None:
            player = scorer
        if assists is None:
            assists = assists_from_roster
        # Auto-apply player-overlay profile when no explicit -r is given
        if render_profile_name is None and not iterate and "player-overlay" in config.render_profiles:
            render_profile_name = "player-overlay"

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
        typer.echo(f"Error: Unknown crop mode: {crop!r}. Use pad, crop, smart, or smart_pad.", err=True)
        raise typer.Exit(code=1) from None

    # Deprecated --crop smart / --crop smart_pad aliases
    effective_smart = smart
    if crop_mode == CropMode.SMART:
        import warnings

        warnings.warn(
            "--crop smart is deprecated, use --crop crop --smart instead",
            DeprecationWarning,
            stacklevel=1,
        )
        typer.echo("Warning: --crop smart is deprecated. Use --crop crop --smart instead.", err=True)
        effective_smart = True
    elif crop_mode == CropMode.SMART_PAD:
        import warnings

        warnings.warn(
            "--crop smart_pad is deprecated, use --crop pad --smart instead",
            DeprecationWarning,
            stacklevel=1,
        )
        typer.echo("Warning: --crop smart_pad is deprecated. Use --crop pad --smart instead.", err=True)
        effective_smart = True

    resolved_zoom_frames = zoom_frames if zoom_frames is not None else 5

    short_config = ShortConfig(
        input=clip,
        output=out,
        width=width,
        height=height,
        crop_mode=crop_mode,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        scale=scale,
        smart=effective_smart,
        pad_color=pad_color,
        speed=speed,
        lut=lut,
        subtitle=subtitle,
        codec=config.video.codec,
        preset=config.video.preset,
        crf=config.video.crf,
        audio_codec=config.video.audio_codec,
        audio_bitrate=config.video.audio_bitrate,
        smart_zoom_frames=resolved_zoom_frames,
        logo=_logo_path,
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
            resolved_game_dir = game_dir or _find_game_dir(config.paths.output_dir, clip)
            if resolved_game_dir is not None:
                try:
                    from reeln.core.highlights import load_game_state

                    state = load_game_state(resolved_game_dir)
                    game_info = state.game_info
                    if event_id is not None:
                        game_event = next((e for e in state.events if e.id == event_id), None)
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
                from reeln.core.ffmpeg import probe_duration as _probe_dur
                from reeln.core.overlay import build_overlay_context

                dur = _probe_dur(clip) or 10.0
                ctx = build_overlay_context(
                    ctx,
                    duration=dur,
                    event_metadata=event_meta,
                    scoring_team=_scoring_team_name,
                    has_logo=_logo_path is not None,
                )

            subtitle_dir = (output or _default_output(clip, "_short")).parent
            subtitle_dir.mkdir(parents=True, exist_ok=True)
            rendered_subtitle = resolve_subtitle_for_profile(rp, ctx, subtitle_dir)

        short_config = apply_profile_to_short(short_config, rp, rendered_subtitle=rendered_subtitle)

    # Resolve branding overlay
    branding_subtitle: Path | None = None
    if not no_branding and config.branding.enabled:
        from reeln.core.branding import resolve_branding

        branding_dir = (output or _default_output(clip, "_short")).parent
        branding_dir.mkdir(parents=True, exist_ok=True)
        try:
            branding_subtitle = resolve_branding(config.branding, branding_dir)
        except ReelnError as exc:
            typer.echo(f"Warning: Failed to resolve branding, continuing without: {exc}", err=True)
    if branding_subtitle is not None:
        short_config = ShortConfig(
            input=short_config.input,
            output=short_config.output,
            width=short_config.width,
            height=short_config.height,
            crop_mode=short_config.crop_mode,
            anchor_x=short_config.anchor_x,
            anchor_y=short_config.anchor_y,
            scale=short_config.scale,
            smart=short_config.smart,
            pad_color=short_config.pad_color,
            speed=short_config.speed,
            lut=short_config.lut,
            subtitle=short_config.subtitle,
            codec=short_config.codec,
            preset=short_config.preset,
            crf=short_config.crf,
            audio_codec=short_config.audio_codec,
            audio_bitrate=short_config.audio_bitrate,
            speed_segments=short_config.speed_segments,
            smart_zoom_frames=short_config.smart_zoom_frames,
            branding=branding_subtitle,
            logo=short_config.logo,
        )

    # Smart zoom: extract frames before iterate or single render
    import tempfile

    extracted_dir: Path | None = None
    extracted_frames = None
    zoom_path = None
    plugin_debug_data: dict[str, object] | None = None
    try:
        if effective_smart:
            from reeln.models.zoom import ZoomPath
            from reeln.plugins.hooks import Hook, HookContext
            from reeln.plugins.registry import get_registry

            try:
                ffmpeg_path = discover_ffmpeg()
                renderer = FFmpegRenderer(ffmpeg_path)
            except ReelnError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1) from exc

            extracted_dir = Path(tempfile.mkdtemp(prefix="reeln_frames_"))
            try:
                extracted_frames = renderer.extract_frames(
                    clip, count=short_config.smart_zoom_frames, output_dir=extracted_dir
                )
                frames = extracted_frames
            except ReelnError as exc:
                typer.echo(f"Error extracting frames: {exc}", err=True)
                raise typer.Exit(code=1) from exc

            shared: dict[str, object] = {}
            hook_ctx = HookContext(
                hook=Hook.ON_FRAMES_EXTRACTED,
                data={
                    "frames": frames,
                    "input_path": clip,
                    "crop_mode": "smart",
                },
                shared=shared,
            )
            get_registry().emit(Hook.ON_FRAMES_EXTRACTED, hook_ctx)

            smart_zoom_data = shared.get("smart_zoom")
            if isinstance(smart_zoom_data, dict):
                zoom_error = smart_zoom_data.get("error")
                if zoom_error is not None:
                    raise RenderError(f"Smart zoom analysis failed after retries: {zoom_error}")
                zoom_path = smart_zoom_data.get("zoom_path")
                debug_from_plugin = smart_zoom_data.get("debug")
                if isinstance(debug_from_plugin, dict):
                    plugin_debug_data = debug_from_plugin

            if zoom_path is None or not isinstance(zoom_path, ZoomPath):
                from reeln.core.shorts import _resolve_smart

                fallback_mode, _ = _resolve_smart(crop_mode, False)
                typer.echo(
                    f"Warning: No smart zoom data from plugins, falling back to {fallback_mode.value}",
                    err=True,
                )
                zoom_path = None
                short_config = ShortConfig(
                    input=short_config.input,
                    output=short_config.output,
                    width=short_config.width,
                    height=short_config.height,
                    crop_mode=fallback_mode,
                    anchor_x=short_config.anchor_x,
                    anchor_y=short_config.anchor_y,
                    scale=short_config.scale,
                    smart=False,
                    pad_color=short_config.pad_color,
                    speed=short_config.speed,
                    lut=short_config.lut,
                    subtitle=short_config.subtitle,
                    codec=short_config.codec,
                    preset=short_config.preset,
                    crf=short_config.crf,
                    audio_codec=short_config.audio_codec,
                    audio_bitrate=short_config.audio_bitrate,
                    smart_zoom_frames=short_config.smart_zoom_frames,
                    logo=short_config.logo,
                )

        source_fps = extracted_frames.fps if extracted_frames is not None else 30.0

        # Load game state once — used by both iterate and single-render paths
        # so POST_RENDER hooks receive game_info for metadata generation.
        from reeln.models.game import GameEvent, GameInfo

        render_game_event: GameEvent | None = None
        render_game_info: GameInfo | None = None
        render_game_dir = game_dir or _find_game_dir(config.paths.output_dir, clip)
        if render_game_dir is not None:
            try:
                from reeln.core.highlights import load_game_state

                _state = load_game_state(render_game_dir)
                render_game_info = _state.game_info
                if event_id is not None:
                    render_game_event = next((e for e in _state.events if e.id == event_id), None)
            except ReelnError:
                pass

        # Multi-iteration mode
        if iterate:
            from reeln.core.iterations import render_iterations
            from reeln.core.profiles import profiles_for_event
            from reeln.core.templates import build_base_context

            profile_list = profiles_for_event(config, render_game_event)
            if profile_list:
                iter_ctx: TemplateContext | None = (
                    build_base_context(render_game_info, render_game_event) if render_game_info else None
                )
                if player is not None and iter_ctx is not None:
                    iter_ctx = TemplateContext(variables={**iter_ctx.variables, "player": player})
                event_meta = dict(render_game_event.metadata) if render_game_event else None
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
                        zoom_path=zoom_path,
                        source_fps=source_fps,
                        dry_run=dry_run,
                        game_info=render_game_info,
                        game_event=render_game_event,
                        player=player,
                        assists=assists,
                    )
                except ReelnError as exc:
                    typer.echo(f"Error: {exc}", err=True)
                    raise typer.Exit(code=1) from exc
                for msg in messages:
                    typer.echo(msg)

                # Debug output for iterate path
                if debug:
                    resolved_gd = game_dir or _find_game_dir(config.paths.output_dir, clip)
                    if resolved_gd is not None and extracted_frames is not None:
                        from reeln.core.zoom_debug import write_zoom_debug

                        write_zoom_debug(
                            resolved_gd,
                            extracted_frames,
                            zoom_path,
                            short_config.width,
                            short_config.height,
                            ffmpeg_path=ffmpeg_path,
                            plugin_debug=plugin_debug_data,
                        )
                        typer.echo(f"Debug: {resolved_gd / 'debug'}")

                return
            typer.echo("Warning: No iteration profiles configured, using single render", err=True)

        try:
            if is_preview:
                plan = plan_preview(short_config)
            else:
                plan = plan_short(short_config, zoom_path=zoom_path, source_fps=source_fps)
        except ReelnError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(f"Input: {clip}")
        typer.echo(f"Output: {out}")
        typer.echo(f"Size: {plan.width}x{plan.height}")
        typer.echo(f"Crop mode: {short_config.crop_mode.value}")
        if short_config.scale != 1.0:
            typer.echo(f"Scale: {short_config.scale}x")
        if short_config.speed != 1.0:
            typer.echo(f"Speed: {short_config.speed}x")
        if short_config.lut:
            typer.echo(f"LUT: {short_config.lut}")
        if short_config.subtitle:
            typer.echo(f"Subtitle: {short_config.subtitle}")
        if render_profile_name is not None:
            typer.echo(f"Profile: {render_profile_name}")
        if zoom_path is not None:
            typer.echo(f"Smart zoom: {len(zoom_path.points)} target points")
        if debug and plan.filter_complex is not None:
            typer.echo(f"Filter complex: {plan.filter_complex}")

        if dry_run:
            typer.echo("Dry run — no files written")
            return

        out.parent.mkdir(parents=True, exist_ok=True)

        # Emit hooks manually so POST_RENDER includes game_info for plugins
        from reeln.plugins.hooks import Hook as _RHook
        from reeln.plugins.hooks import HookContext as _RHookCtx
        from reeln.plugins.registry import get_registry as _get_reg

        _pre_data: dict[str, Any] = {"plan": plan}
        if _plugin_inputs:
            _pre_data["plugin_inputs"] = _plugin_inputs
        _get_reg().emit(
            _RHook.PRE_RENDER,
            _RHookCtx(hook=_RHook.PRE_RENDER, data=_pre_data),
        )
        try:
            ffmpeg_path = discover_ffmpeg()
            renderer = FFmpegRenderer(ffmpeg_path)
            result = renderer.render(plan, emit_hooks=False)
        except ReelnError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        _post_data: dict[str, Any] = {"plan": plan, "result": result}
        if render_game_info is not None:
            _post_data["game_info"] = render_game_info
        if render_game_event is not None:
            _post_data["game_event"] = render_game_event
        if player is not None:
            _post_data["player"] = player
        if assists is not None:
            _post_data["assists"] = assists
        if _plugin_inputs:
            _post_data["plugin_inputs"] = _plugin_inputs
        _get_reg().emit(
            _RHook.POST_RENDER,
            _RHookCtx(hook=_RHook.POST_RENDER, data=_post_data),
        )

        if result.duration_seconds is not None:
            typer.echo(f"Duration: {result.duration_seconds:.1f}s")
        if result.file_size_bytes is not None:
            size_mb = result.file_size_bytes / (1024 * 1024)
            typer.echo(f"File size: {size_mb:.1f} MB")
        typer.echo("Render complete")

        resolved_game_dir = game_dir or _find_game_dir(config.paths.output_dir, clip)
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

                extra: dict[str, object] = {
                    "crop_mode": crop,
                    "size": f"{short_config.width}x{short_config.height}",
                    "speed": speed,
                    "scale": short_config.scale,
                    "smart": short_config.smart,
                }
                if zoom_path is not None:
                    extra["smart_zoom_points"] = len(zoom_path.points)

                artifact = build_debug_artifact(
                    "render_preview" if is_preview else "render_short",
                    result.ffmpeg_command,
                    [clip],
                    out,
                    resolved_game_dir,
                    ffmpeg_path,
                    extra=extra,
                )
                write_debug_artifact(resolved_game_dir, artifact)
                write_debug_index(resolved_game_dir)

                if extracted_frames is not None:
                    from reeln.core.zoom_debug import write_zoom_debug

                    write_zoom_debug(
                        resolved_game_dir,
                        extracted_frames,
                        zoom_path,
                        short_config.width,
                        short_config.height,
                        ffmpeg_path=ffmpeg_path,
                        plugin_debug=plugin_debug_data,
                    )

                typer.echo(f"Debug: {resolved_game_dir / 'debug'}")
    finally:
        if rendered_subtitle is not None:
            rendered_subtitle.unlink(missing_ok=True)
        if branding_subtitle is not None:
            branding_subtitle.unlink(missing_ok=True)
        if extracted_dir is not None:
            import shutil

            shutil.rmtree(extracted_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def short(
    clip: Path | None = typer.Argument(None, help="Input video file. Default: latest in cwd."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str | None = typer.Option(None, "--format", "-f", help="Output format: vertical, square."),
    size: str | None = typer.Option(None, "--size", help="Custom WxH (e.g., 1080x1920)."),
    crop: str = typer.Option("pad", "--crop", "-c", help="Crop mode: pad, crop, smart, smart_pad."),
    anchor: str = typer.Option("center", "--anchor", "-a", help="Crop anchor: center/top/bottom/left/right or x,y."),
    pad_color: str = typer.Option("black", "--pad-color", help="Pad bar color."),
    speed: float = typer.Option(1.0, "--speed", help="Playback speed (0.5-2.0)."),
    scale: float = typer.Option(1.0, "--scale", help="Content scale (0.5-3.0). >1.0 zooms in."),
    smart: bool = typer.Option(False, "--smart", help="Smart tracking via vision plugin."),
    lut: Path | None = typer.Option(None, "--lut", help="LUT file (.cube/.3dl)."),
    subtitle: Path | None = typer.Option(None, "--subtitle", help="ASS subtitle file."),
    game_dir: Path | None = typer.Option(None, "--game-dir", help="Game directory for render tracking."),
    event: str | None = typer.Option(None, "--event", help="Link to event ID (auto-detected if omitted)."),
    render_profile: str | None = typer.Option(None, "--render-profile", "-r", help="Named render profile from config."),
    player_name: str | None = typer.Option(None, "--player", help="Player name for overlay."),
    assists_str: str | None = typer.Option(None, "--assists", help="Assists, comma-separated."),
    player_numbers_str: str | None = typer.Option(
        None,
        "--player-numbers",
        "-n",
        help="Jersey numbers: scorer[,assist1[,assist2]]. Looked up from team roster.",
    ),
    event_type: str | None = typer.Option(
        None,
        "--event-type",
        help="Event type for scoring team resolution (HOME_GOAL, AWAY_GOAL).",
    ),
    zoom_frames: int | None = typer.Option(
        None, "--zoom-frames", help="Number of frames to extract for smart zoom (1-20)."
    ),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
    iterate: bool = typer.Option(False, "--iterate", help="Multi-iteration mode using event type config."),
    debug_flag: bool = typer.Option(False, "--debug", help="Write debug artifacts to game debug directory."),
    no_branding: bool = typer.Option(False, "--no-branding", help="Disable branding overlay."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
    plugin_input: list[str] = typer.Option([], "--plugin-input", "-I", help="Plugin input as KEY=VALUE (repeatable)."),
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
        scale,
        smart,
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
        zoom_frames=zoom_frames,
        player_numbers=player_numbers_str,
        event_type=event_type,
        no_branding=no_branding,
        plugin_input=plugin_input,
    )


@app.command()
def preview(
    clip: Path | None = typer.Argument(None, help="Input video file. Default: latest in cwd."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str | None = typer.Option(None, "--format", "-f", help="Output format: vertical, square."),
    size: str | None = typer.Option(None, "--size", help="Custom WxH (e.g., 1080x1920)."),
    crop: str = typer.Option("pad", "--crop", "-c", help="Crop mode: pad, crop, smart, smart_pad."),
    anchor: str = typer.Option("center", "--anchor", "-a", help="Crop anchor: center/top/bottom/left/right or x,y."),
    pad_color: str = typer.Option("black", "--pad-color", help="Pad bar color."),
    speed: float = typer.Option(1.0, "--speed", help="Playback speed (0.5-2.0)."),
    scale: float = typer.Option(1.0, "--scale", help="Content scale (0.5-3.0). >1.0 zooms in."),
    smart: bool = typer.Option(False, "--smart", help="Smart tracking via vision plugin."),
    lut: Path | None = typer.Option(None, "--lut", help="LUT file (.cube/.3dl)."),
    subtitle: Path | None = typer.Option(None, "--subtitle", help="ASS subtitle file."),
    game_dir: Path | None = typer.Option(None, "--game-dir", help="Game directory for render tracking."),
    render_profile: str | None = typer.Option(None, "--render-profile", "-r", help="Named render profile from config."),
    player_name: str | None = typer.Option(None, "--player", help="Player name for overlay."),
    assists_str: str | None = typer.Option(None, "--assists", help="Assists, comma-separated."),
    player_numbers_str: str | None = typer.Option(
        None,
        "--player-numbers",
        "-n",
        help="Jersey numbers: scorer[,assist1[,assist2]]. Looked up from team roster.",
    ),
    event_type: str | None = typer.Option(
        None,
        "--event-type",
        help="Event type for scoring team resolution (HOME_GOAL, AWAY_GOAL).",
    ),
    zoom_frames: int | None = typer.Option(
        None, "--zoom-frames", help="Number of frames to extract for smart zoom (1-20)."
    ),
    profile: str | None = typer.Option(None, "--profile", help="Named config profile."),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
    iterate: bool = typer.Option(False, "--iterate", help="Multi-iteration mode using event type config."),
    debug_flag: bool = typer.Option(False, "--debug", help="Write debug artifacts to game debug directory."),
    no_branding: bool = typer.Option(False, "--no-branding", help="Disable branding overlay."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
    plugin_input: list[str] = typer.Option([], "--plugin-input", "-I", help="Plugin input as KEY=VALUE (repeatable)."),
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
        scale,
        smart,
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
        zoom_frames=zoom_frames,
        player_numbers=player_numbers_str,
        event_type=event_type,
        no_branding=no_branding,
        plugin_input=plugin_input,
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
    from reeln.core.ffmpeg import concat_files
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
        concat_files(
            files,
            out,
            copy=copy,
            video_codec=config.video.codec,
            crf=config.video.crf,
            audio_codec=config.video.audio_codec,
        )
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
    player_numbers_str: str | None = typer.Option(
        None,
        "--player-numbers",
        "-n",
        help="Jersey numbers: scorer[,assist1[,assist2]]. Looked up from team roster.",
    ),
    event_type: str | None = typer.Option(None, "--event-type", help="Event type for scoring team resolution."),
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

    # Resolve --player-numbers before anything else
    _scoring_team_name: str | None = None
    if player_numbers_str is not None:
        scorer, assists_from_roster, _scoring_team_name, _ = _resolve_player_numbers(
            player_numbers_str, event_type, game_dir, config.paths.output_dir, clip
        )
        if player_name is None:
            player_name = scorer
        if assists_str is None:
            assists_str = assists_from_roster

    out = output or _default_output(clip, f"_{render_profile}")

    # Build template context for subtitle rendering
    from reeln.models.game import GameEvent as _ApplyEvent
    from reeln.models.game import GameInfo as _ApplyInfo

    apply_game_event: _ApplyEvent | None = None
    apply_game_info: _ApplyInfo | None = None
    resolved_game_dir = game_dir or _find_game_dir(config.paths.output_dir, clip)
    if resolved_game_dir is not None:
        try:
            from reeln.core.highlights import load_game_state

            state = load_game_state(resolved_game_dir)
            apply_game_info = state.game_info
            if event is not None:
                apply_game_event = next((e for e in state.events if e.id == event), None)
        except ReelnError:
            pass  # non-fatal: just skip context

    # Multi-iteration mode
    if iterate:
        from reeln.core.iterations import render_iterations
        from reeln.core.profiles import profiles_for_event

        profile_list = profiles_for_event(config, apply_game_event)
        if profile_list:
            ctx = build_base_context(apply_game_info, apply_game_event) if apply_game_info else None
            if player_name is not None and ctx is not None:
                ctx = TemplateContext(variables={**ctx.variables, "player": player_name})
            event_meta = dict(apply_game_event.metadata) if apply_game_event else None
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
                    game_info=apply_game_info,
                    game_event=apply_game_event,
                    player=player_name,
                    assists=assists_str,
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
            ctx = build_base_context(apply_game_info, apply_game_event) if apply_game_info else TemplateContext()
            if player_name is not None:
                ctx = TemplateContext(variables={**ctx.variables, "player": player_name})

            event_meta = dict(apply_game_event.metadata) if apply_game_event else None
            if assists_str is not None:
                event_meta = event_meta or {}
                event_meta["assists"] = assists_str

            if event_meta is not None:
                from reeln.core.ffmpeg import probe_duration as _probe_dur
                from reeln.core.overlay import build_overlay_context

                dur = _probe_dur(clip) or 10.0
                ctx = build_overlay_context(
                    ctx,
                    duration=dur,
                    event_metadata=event_meta,
                    scoring_team=_scoring_team_name,
                )
            out.parent.mkdir(parents=True, exist_ok=True)
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
            typer.echo(f"Overlay: {rp.subtitle_template}")

        if dry_run:
            typer.echo("Dry run — no files written")
            return

        from reeln.core.ffmpeg import discover_ffmpeg
        from reeln.core.renderer import FFmpegRenderer
        from reeln.plugins.hooks import Hook as _ApplyHook
        from reeln.plugins.hooks import HookContext as _ApplyHookCtx
        from reeln.plugins.registry import get_registry as _apply_get_reg

        out.parent.mkdir(parents=True, exist_ok=True)
        _apply_get_reg().emit(
            _ApplyHook.PRE_RENDER,
            _ApplyHookCtx(hook=_ApplyHook.PRE_RENDER, data={"plan": plan}),
        )
        try:
            ffmpeg_path = discover_ffmpeg()
            renderer = FFmpegRenderer(ffmpeg_path)
            result = renderer.render(plan, emit_hooks=False)
        except ReelnError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        _apply_post: dict[str, Any] = {"plan": plan, "result": result}
        if apply_game_info is not None:
            _apply_post["game_info"] = apply_game_info
        if apply_game_event is not None:
            _apply_post["game_event"] = apply_game_event
        if player_name is not None:
            _apply_post["player"] = player_name
        if assists_str is not None:
            _apply_post["assists"] = assists_str
        _apply_get_reg().emit(
            _ApplyHook.POST_RENDER,
            _ApplyHookCtx(hook=_ApplyHook.POST_RENDER, data=_apply_post),
        )

        if result.duration_seconds is not None:
            typer.echo(f"Duration: {result.duration_seconds:.1f}s")
        if result.file_size_bytes is not None:
            size_mb = result.file_size_bytes / (1024 * 1024)
            typer.echo(f"File size: {size_mb:.1f} MB")
        typer.echo("Render complete")

        if debug_flag and resolved_game_dir is not None and result.ffmpeg_command:
            from reeln.core.debug import build_debug_artifact, write_debug_artifact, write_debug_index

            artifact = build_debug_artifact(
                "render_apply",
                result.ffmpeg_command,
                [clip],
                out,
                resolved_game_dir,
                ffmpeg_path,
                extra={"profile": render_profile},
            )
            write_debug_artifact(resolved_game_dir, artifact)
            write_debug_index(resolved_game_dir)
            typer.echo(f"Debug: {resolved_game_dir / 'debug'}")
    finally:
        if rendered_subtitle is not None:
            rendered_subtitle.unlink(missing_ok=True)
