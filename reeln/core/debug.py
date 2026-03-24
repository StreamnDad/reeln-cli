"""Game-scoped pipeline debugging — artifact writing, probing, and HTML index."""

from __future__ import annotations

import contextlib
import html
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reeln.core.log import get_logger
from reeln.models.debug import (
    DebugArtifact,
    debug_artifact_to_dict,
    dict_to_debug_artifact,
)

log: logging.Logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def debug_dir(game_dir: Path) -> Path:
    """Return the debug directory for a game: ``{game_dir}/debug/``."""
    return game_dir / "debug"


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------


def _probe_file_metadata(ffmpeg_path: Path, path: Path) -> dict[str, object]:
    """Probe a video file for debug metadata.

    Returns a dict with ``duration``, ``fps``, ``resolution``, and ``codec``
    keys.  Values are ``None`` when probing fails.
    """
    from reeln.core.ffmpeg import probe_duration, probe_fps, probe_resolution

    result: dict[str, object] = {
        "file": str(path.name),
        "duration": None,
        "fps": None,
        "resolution": None,
    }

    if not path.is_file():
        return result

    with contextlib.suppress(Exception):
        result["duration"] = probe_duration(ffmpeg_path, path)

    with contextlib.suppress(Exception):
        result["fps"] = probe_fps(ffmpeg_path, path)

    try:
        res = probe_resolution(ffmpeg_path, path)
        if res is not None:
            result["resolution"] = f"{res[0]}x{res[1]}"
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Command inspection
# ---------------------------------------------------------------------------


def _extract_filter_complex(command: list[str]) -> str:
    """Extract ``-filter_complex`` value from an ffmpeg command list.

    Returns an empty string if the flag is not present.
    """
    for i, arg in enumerate(command):
        if arg == "-filter_complex" and i + 1 < len(command):
            return command[i + 1]
    return ""


# ---------------------------------------------------------------------------
# Artifact building and writing
# ---------------------------------------------------------------------------


def build_debug_artifact(
    operation: str,
    ffmpeg_command: list[str],
    input_files: list[Path],
    output_file: Path,
    game_dir: Path,
    ffmpeg_path: Path,
    *,
    extra: dict[str, object] | None = None,
) -> DebugArtifact:
    """Build a ``DebugArtifact`` by probing input/output files."""

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(game_dir))
        except ValueError:
            return str(p)

    input_meta: list[dict[str, object]] = []
    for f in input_files:
        input_meta.append(_probe_file_metadata(ffmpeg_path, f))

    output_meta = _probe_file_metadata(ffmpeg_path, output_file)

    return DebugArtifact(
        operation=operation,
        timestamp=datetime.now(tz=UTC).isoformat(),
        ffmpeg_command=list(ffmpeg_command),
        filter_complex=_extract_filter_complex(ffmpeg_command),
        input_files=[_rel(f) for f in input_files],
        output_file=_rel(output_file),
        input_metadata=input_meta,
        output_metadata=output_meta,
        extra=dict(extra) if extra else {},
    )


def write_debug_artifact(game_dir: Path, artifact: DebugArtifact) -> Path:
    """Write a debug artifact JSON to ``{game_dir}/debug/{operation}_{timestamp}.json``.

    Creates the debug directory if needed.  Returns the path to the written file.
    """
    d = debug_dir(game_dir)
    d.mkdir(parents=True, exist_ok=True)

    # Build a safe filename from timestamp (replace colons and plus signs)
    safe_ts = artifact.timestamp.replace(":", "-").replace("+", "p")
    filename = f"{artifact.operation}_{safe_ts}.json"
    target = d / filename

    data = debug_artifact_to_dict(artifact)
    content = json.dumps(data, indent=2) + "\n"

    # Atomic write
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".tmp", dir=d, text=True)
    try:
        with open(tmp_fd, "w") as tmp:
            tmp.write(content)
            tmp.flush()
        Path(tmp_name).replace(target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

    log.debug("Debug artifact written: %s", target)
    return target


# ---------------------------------------------------------------------------
# Artifact collection
# ---------------------------------------------------------------------------


def collect_debug_artifacts(game_dir: Path) -> list[DebugArtifact]:
    """Read all debug JSON files from the debug directory.

    Silently skips files that are not valid JSON or not valid artifacts.
    Returns artifacts sorted by timestamp.
    """
    d = debug_dir(game_dir)
    if not d.is_dir():
        return []

    artifacts: list[DebugArtifact] = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix != ".json":
            continue
        try:
            raw: Any = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                artifacts.append(dict_to_debug_artifact(raw))
        except (json.JSONDecodeError, OSError):
            log.debug("Skipping corrupt debug artifact: %s", f)
            continue

    return sorted(artifacts, key=lambda a: a.timestamp, reverse=True)


# ---------------------------------------------------------------------------
# HTML index generation
# ---------------------------------------------------------------------------


def write_debug_index(game_dir: Path) -> Path:
    """Generate ``{game_dir}/debug/index.html`` linking to all debug artifacts and videos.

    Returns the path to the written HTML file.
    """
    d = debug_dir(game_dir)
    d.mkdir(parents=True, exist_ok=True)

    artifacts = collect_debug_artifacts(game_dir)

    lines: list[str] = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<title>reeln Debug Index</title>",
        "<style>",
        "body { font-family: monospace; margin: 2em; background: #1a1a2e; color: #e0e0e0; }",
        "h1 { color: #e94560; }",
        "h2 { color: #0f3460; background: #e0e0e0; padding: 4px 8px; margin-top: 2em; }",
        "table { border-collapse: collapse; width: 100%; margin-bottom: 1em; }",
        "th, td { border: 1px solid #444; padding: 6px 10px; text-align: left; }",
        "th { background: #16213e; }",
        "pre { background: #16213e; padding: 1em; overflow-x: auto; white-space: pre-wrap; }",
        "a { color: #e94560; }",
        ".section { margin-bottom: 2em; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>"
        "<img src='https://raw.githubusercontent.com/StreamnDad/reeln-cli/main/assets/logo.jpg'"
        " alt='reeln' style='height:48px;vertical-align:middle;margin-right:12px;border-radius:6px;'>"
        "reeln Debug Index</h1>",
        f"<p>Game directory: <code>{html.escape(str(game_dir))}</code></p>",
        f"<p>Generated: {html.escape(datetime.now(tz=UTC).isoformat())}</p>",
    ]

    # Zoom debug section (if zoom/ subdirectory exists)
    zoom_dir = d / "zoom"
    if zoom_dir.is_dir():
        lines.append("<div class='section'>")
        lines.append("<h2>Smart Zoom Debug</h2>")

        # Plugin debug (prompts, model info)
        plugin_debug_json = zoom_dir / "plugin_debug.json"
        if plugin_debug_json.is_file():
            try:
                plugin_data = json.loads(plugin_debug_json.read_text(encoding="utf-8"))
                lines.append("<p><strong>Plugin debug data:</strong></p>")
                lines.append(f"<pre>{html.escape(json.dumps(plugin_data, indent=2))}</pre>")
            except (json.JSONDecodeError, OSError):
                pass

        # Zoom path JSON link
        zoom_json = zoom_dir / "zoom_path.json"
        if zoom_json.is_file():
            lines.append("<p><strong>Zoom path:</strong> <a href='zoom/zoom_path.json'>zoom_path.json</a></p>")

        # Collect frame images
        frames = sorted(zoom_dir.glob("frame_*.png"))
        annotated = sorted(zoom_dir.glob("annotated_*.png"))

        if annotated:
            lines.append(
                "<p><strong>Annotated frames</strong> (crosshair = detected center, green box = crop region):</p>"
            )
            lines.append("<div style='display:flex;flex-wrap:wrap;gap:8px;'>")
            for img in annotated:
                lines.append(
                    f"<a href='zoom/{html.escape(img.name)}'>"
                    f"<img src='zoom/{html.escape(img.name)}' "
                    f"style='max-width:320px;border:1px solid #444;' "
                    f"title='{html.escape(img.name)}'></a>"
                )
            lines.append("</div>")

        if frames:
            lines.append("<p><strong>Extracted frames:</strong></p>")
            lines.append("<div style='display:flex;flex-wrap:wrap;gap:8px;'>")
            for img in frames:
                lines.append(
                    f"<a href='zoom/{html.escape(img.name)}'>"
                    f"<img src='zoom/{html.escape(img.name)}' "
                    f"style='max-width:320px;border:1px solid #444;' "
                    f"title='{html.escape(img.name)}'></a>"
                )
            lines.append("</div>")

        lines.append("</div>")

    if not artifacts:
        lines.append("<p>No debug artifacts found.</p>")
    else:
        # Summary table
        lines.append("<h2>Summary</h2>")
        lines.append("<table>")
        lines.append("<tr><th>#</th><th>Operation</th><th>Timestamp</th><th>Output</th></tr>")
        for i, art in enumerate(artifacts, 1):
            out_link = html.escape(art.output_file)
            lines.append(
                f"<tr><td>{i}</td>"
                f"<td><a href='#{html.escape(art.operation)}_{i}'>{html.escape(art.operation)}</a></td>"
                f"<td>{html.escape(art.timestamp)}</td>"
                f"<td><a href='../{out_link}'>{out_link}</a></td></tr>"
            )
        lines.append("</table>")

        # Per-operation sections
        for i, art in enumerate(artifacts, 1):
            anchor = f"{html.escape(art.operation)}_{i}"
            lines.append(f"<div class='section' id='{anchor}'>")
            lines.append(f"<h2>{i}. {html.escape(art.operation)}</h2>")
            lines.append(f"<p><strong>Timestamp:</strong> {html.escape(art.timestamp)}</p>")

            # FFmpeg command
            cmd_str = " ".join(art.ffmpeg_command)
            lines.append("<p><strong>FFmpeg command:</strong></p>")
            lines.append(f"<pre>{html.escape(cmd_str)}</pre>")

            # Filter complex
            if art.filter_complex:
                lines.append("<p><strong>Filter complex:</strong></p>")
                lines.append(f"<pre>{html.escape(art.filter_complex)}</pre>")

            # Input files
            if art.input_files:
                lines.append("<p><strong>Input files:</strong></p>")
                lines.append("<ul>")
                for inp in art.input_files:
                    lines.append(f"<li><a href='../{html.escape(inp)}'>{html.escape(inp)}</a></li>")
                lines.append("</ul>")

            # Output file
            out_esc = html.escape(art.output_file)
            lines.append(f"<p><strong>Output:</strong> <a href='../{out_esc}'>{out_esc}</a></p>")

            # Input metadata
            if art.input_metadata:
                lines.append("<p><strong>Input metadata:</strong></p>")
                lines.append("<table>")
                lines.append("<tr><th>File</th><th>Duration</th><th>FPS</th><th>Resolution</th></tr>")
                for m in art.input_metadata:
                    lines.append(
                        f"<tr><td>{html.escape(str(m.get('file', '')))}</td>"
                        f"<td>{html.escape(str(m.get('duration', '')))}</td>"
                        f"<td>{html.escape(str(m.get('fps', '')))}</td>"
                        f"<td>{html.escape(str(m.get('resolution', '')))}</td></tr>"
                    )
                lines.append("</table>")

            # Output metadata
            if art.output_metadata:
                lines.append("<p><strong>Output metadata:</strong></p>")
                lines.append("<table>")
                lines.append("<tr><th>Key</th><th>Value</th></tr>")
                for k, v in art.output_metadata.items():
                    lines.append(f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>")
                lines.append("</table>")

            # Extra
            if art.extra:
                lines.append("<p><strong>Extra:</strong></p>")
                lines.append(f"<pre>{html.escape(json.dumps(art.extra, indent=2))}</pre>")

            lines.append("</div>")

    lines.extend(["</body>", "</html>", ""])

    target = d / "index.html"
    content = "\n".join(lines)

    # Atomic write
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".tmp", dir=d, text=True)
    try:
        with open(tmp_fd, "w") as tmp:
            tmp.write(content)
            tmp.flush()
        Path(tmp_name).replace(target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

    log.debug("Debug index written: %s", target)
    return target
