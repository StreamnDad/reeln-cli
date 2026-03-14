"""Health check diagnostics — built-in checks and runner."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from reeln.core.config import (
    config_to_dict,
    load_config,
    validate_config,
)
from reeln.core.errors import ConfigError, FFmpegError
from reeln.core.ffmpeg import (
    check_version,
    discover_ffmpeg,
    list_codecs,
    list_hwaccels,
)
from reeln.core.log import get_logger
from reeln.models.doctor import CheckResult, CheckStatus, DoctorCheck

log: logging.Logger = get_logger(__name__)

_REQUIRED_CODECS: list[str] = ["libx264", "libx265", "aac"]


# ---------------------------------------------------------------------------
# Built-in checks
# ---------------------------------------------------------------------------


def check_ffmpeg() -> list[CheckResult]:
    """Check ffmpeg discovery and version."""
    try:
        ffmpeg_path = discover_ffmpeg()
    except FFmpegError as exc:
        return [
            CheckResult(
                name="ffmpeg",
                status=CheckStatus.FAIL,
                message="ffmpeg not found",
                hint=str(exc),
            )
        ]

    try:
        version = check_version(ffmpeg_path)
    except FFmpegError as exc:
        return [
            CheckResult(
                name="ffmpeg",
                status=CheckStatus.FAIL,
                message=str(exc),
                hint="Upgrade your ffmpeg installation.",
            )
        ]

    return [
        CheckResult(
            name="ffmpeg",
            status=CheckStatus.PASS,
            message=f"ffmpeg {version} at {ffmpeg_path}",
        )
    ]


def check_ffmpeg_codecs(ffmpeg_path: Path) -> list[CheckResult]:
    """Check availability of key encoding codecs."""
    available = set(list_codecs(ffmpeg_path))
    results: list[CheckResult] = []

    for codec in _REQUIRED_CODECS:
        if codec in available:
            results.append(
                CheckResult(
                    name=f"codec:{codec}",
                    status=CheckStatus.PASS,
                    message=f"{codec} available",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"codec:{codec}",
                    status=CheckStatus.WARN,
                    message=f"{codec} not found",
                    hint=f"Rebuild ffmpeg with {codec} support.",
                )
            )

    return results


def check_ffmpeg_hwaccels(ffmpeg_path: Path) -> list[CheckResult]:
    """Check hardware acceleration availability."""
    hwaccels = list_hwaccels(ffmpeg_path)

    if hwaccels:
        return [
            CheckResult(
                name="hwaccel",
                status=CheckStatus.PASS,
                message=f"Hardware acceleration: {', '.join(hwaccels)}",
            )
        ]

    return [
        CheckResult(
            name="hwaccel",
            status=CheckStatus.WARN,
            message="No hardware acceleration available",
            hint="Software encoding will be used (slower but works fine).",
        )
    ]


def check_config(
    config_path: Path | None = None,
    profile: str | None = None,
) -> list[CheckResult]:
    """Check config validity."""
    try:
        config = load_config(path=config_path, profile=profile)
    except ConfigError as exc:
        return [
            CheckResult(
                name="config",
                status=CheckStatus.WARN,
                message=str(exc),
            )
        ]
    data = config_to_dict(config)
    issues = validate_config(data)

    if not issues:
        return [
            CheckResult(
                name="config",
                status=CheckStatus.PASS,
                message="Configuration is valid",
            )
        ]

    return [
        CheckResult(
            name="config",
            status=CheckStatus.WARN,
            message=issue,
        )
        for issue in issues
    ]


def check_directories(
    config_path: Path | None = None,
    profile: str | None = None,
) -> list[CheckResult]:
    """Check configured directory paths."""
    try:
        config = load_config(path=config_path, profile=profile)
    except ConfigError as exc:
        return [
            CheckResult(
                name="directories",
                status=CheckStatus.WARN,
                message=str(exc),
            )
        ]
    results: list[CheckResult] = []

    dirs_to_check: list[tuple[str, Path | None]] = [
        ("paths.output_dir", config.paths.output_dir),
        ("paths.source_dir", config.paths.source_dir),
    ]

    for label, dir_path in dirs_to_check:
        if dir_path is None:
            continue

        if not dir_path.exists():
            results.append(
                CheckResult(
                    name=f"dir:{label}",
                    status=CheckStatus.WARN,
                    message=f"{label}: {dir_path} does not exist",
                    hint="Directory will be created on first use.",
                )
            )
        elif not os.access(dir_path, os.W_OK):
            results.append(
                CheckResult(
                    name=f"dir:{label}",
                    status=CheckStatus.FAIL,
                    message=f"{label}: {dir_path} is not writable",
                    hint="Check directory permissions.",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"dir:{label}",
                    status=CheckStatus.PASS,
                    message=f"{label}: {dir_path} exists and is writable",
                )
            )

    return results


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_doctor(
    config_path: Path | None = None,
    profile: str | None = None,
    extra_checks: list[DoctorCheck] | None = None,
) -> list[CheckResult]:
    """Run all health checks and return aggregated results.

    Built-in checks run first, then any *extra_checks* (plugin extension
    point).  Exceptions in individual checks are caught and reported as
    FAIL results.
    """
    results: list[CheckResult] = []

    # FFmpeg checks
    ffmpeg_results = check_ffmpeg()
    results.extend(ffmpeg_results)

    # Only run codec/hwaccel checks if ffmpeg was found
    ffmpeg_ok = any(r.name == "ffmpeg" and r.status == CheckStatus.PASS for r in ffmpeg_results)
    if ffmpeg_ok:
        ffmpeg_path = discover_ffmpeg()
        results.extend(check_ffmpeg_codecs(ffmpeg_path))
        results.extend(check_ffmpeg_hwaccels(ffmpeg_path))

    # Config checks
    try:
        results.extend(check_config(config_path, profile))
    except Exception as exc:
        results.append(
            CheckResult(
                name="config",
                status=CheckStatus.FAIL,
                message=f"Config check failed: {exc}",
            )
        )

    # Directory checks
    try:
        results.extend(check_directories(config_path, profile))
    except Exception as exc:
        results.append(
            CheckResult(
                name="directories",
                status=CheckStatus.FAIL,
                message=f"Directory check failed: {exc}",
            )
        )

    # Plugin-contributed checks
    for check in extra_checks or []:
        try:
            results.extend(check.run())
        except Exception as exc:
            results.append(
                CheckResult(
                    name=check.name,
                    status=CheckStatus.FAIL,
                    message=f"Check failed: {exc}",
                )
            )

    return results


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_results(results: list[CheckResult]) -> list[str]:
    """Format check results as human-readable lines."""
    lines: list[str] = []
    for r in results:
        status_label = r.status.value.upper()
        line = f"  {status_label}: {r.message}"
        lines.append(line)
        if r.hint and r.status != CheckStatus.PASS:
            lines.append(f"    hint: {r.hint}")
    return lines


def doctor_exit_code(results: list[CheckResult]) -> int:
    """Return 0 if no FAIL results, 1 otherwise."""
    if any(r.status == CheckStatus.FAIL for r in results):
        return 1
    return 0
