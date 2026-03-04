"""Tests for health check diagnostics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from reeln.core.doctor import (
    _REQUIRED_CODECS,
    check_config,
    check_directories,
    check_ffmpeg,
    check_ffmpeg_codecs,
    check_ffmpeg_hwaccels,
    doctor_exit_code,
    format_results,
    run_doctor,
)
from reeln.core.errors import FFmpegError
from reeln.models.config import AppConfig, PathConfig
from reeln.models.doctor import CheckResult, CheckStatus

# ---------------------------------------------------------------------------
# check_ffmpeg
# ---------------------------------------------------------------------------


def test_check_ffmpeg_found() -> None:
    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
    ):
        results = check_ffmpeg()

    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert "7.1" in results[0].message
    assert "/usr/bin/ffmpeg" in results[0].message


def test_check_ffmpeg_not_found() -> None:
    with patch(
        "reeln.core.doctor.discover_ffmpeg",
        side_effect=FFmpegError("ffmpeg not found"),
    ):
        results = check_ffmpeg()

    assert len(results) == 1
    assert results[0].status == CheckStatus.FAIL
    assert "not found" in results[0].message
    assert results[0].hint != ""


def test_check_ffmpeg_too_old() -> None:
    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch(
            "reeln.core.doctor.check_version",
            side_effect=FFmpegError("ffmpeg 4.4 is too old"),
        ),
    ):
        results = check_ffmpeg()

    assert len(results) == 1
    assert results[0].status == CheckStatus.FAIL
    assert "too old" in results[0].message


# ---------------------------------------------------------------------------
# check_ffmpeg_codecs
# ---------------------------------------------------------------------------


def test_check_ffmpeg_codecs_all_present() -> None:
    with patch(
        "reeln.core.doctor.list_codecs",
        return_value=["libx264", "libx265", "aac", "opus"],
    ):
        results = check_ffmpeg_codecs(Path("/usr/bin/ffmpeg"))

    assert len(results) == len(_REQUIRED_CODECS)
    assert all(r.status == CheckStatus.PASS for r in results)


def test_check_ffmpeg_codecs_missing() -> None:
    with patch("reeln.core.doctor.list_codecs", return_value=["libx264"]):
        results = check_ffmpeg_codecs(Path("/usr/bin/ffmpeg"))

    assert len(results) == len(_REQUIRED_CODECS)
    pass_count = sum(1 for r in results if r.status == CheckStatus.PASS)
    warn_count = sum(1 for r in results if r.status == CheckStatus.WARN)
    assert pass_count == 1  # libx264
    assert warn_count == 2  # libx265, aac


def test_check_ffmpeg_codecs_none() -> None:
    with patch("reeln.core.doctor.list_codecs", return_value=[]):
        results = check_ffmpeg_codecs(Path("/usr/bin/ffmpeg"))

    assert all(r.status == CheckStatus.WARN for r in results)


# ---------------------------------------------------------------------------
# check_ffmpeg_hwaccels
# ---------------------------------------------------------------------------


def test_check_ffmpeg_hwaccels_available() -> None:
    with patch(
        "reeln.core.doctor.list_hwaccels",
        return_value=["videotoolbox", "cuda"],
    ):
        results = check_ffmpeg_hwaccels(Path("/usr/bin/ffmpeg"))

    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert "videotoolbox" in results[0].message


def test_check_ffmpeg_hwaccels_none() -> None:
    with patch("reeln.core.doctor.list_hwaccels", return_value=[]):
        results = check_ffmpeg_hwaccels(Path("/usr/bin/ffmpeg"))

    assert len(results) == 1
    assert results[0].status == CheckStatus.WARN
    assert "No hardware acceleration" in results[0].message


# ---------------------------------------------------------------------------
# check_config
# ---------------------------------------------------------------------------


def test_check_config_valid() -> None:
    with patch("reeln.core.doctor.load_config", return_value=AppConfig()):
        results = check_config()

    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert "valid" in results[0].message


def test_check_config_with_issues() -> None:
    with (
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
        patch(
            "reeln.core.doctor.validate_config",
            return_value=["Missing config_version", "Invalid video section"],
        ),
    ):
        results = check_config()

    assert len(results) == 2
    assert all(r.status == CheckStatus.WARN for r in results)


# ---------------------------------------------------------------------------
# check_directories
# ---------------------------------------------------------------------------


def test_check_directories_exists_writable(tmp_path: Path) -> None:
    cfg = AppConfig(paths=PathConfig(output_dir=tmp_path))
    with patch("reeln.core.doctor.load_config", return_value=cfg):
        results = check_directories()

    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert "writable" in results[0].message


def test_check_directories_not_exist(tmp_path: Path) -> None:
    cfg = AppConfig(paths=PathConfig(output_dir=tmp_path / "nonexistent"))
    with patch("reeln.core.doctor.load_config", return_value=cfg):
        results = check_directories()

    assert len(results) == 1
    assert results[0].status == CheckStatus.WARN
    assert "does not exist" in results[0].message


def test_check_directories_not_writable(tmp_path: Path) -> None:
    cfg = AppConfig(paths=PathConfig(output_dir=tmp_path))
    with (
        patch("reeln.core.doctor.load_config", return_value=cfg),
        patch("reeln.core.doctor.os.access", return_value=False),
    ):
        results = check_directories()

    assert len(results) == 1
    assert results[0].status == CheckStatus.FAIL
    assert "not writable" in results[0].message


def test_check_directories_no_paths_configured() -> None:
    cfg = AppConfig()
    with patch("reeln.core.doctor.load_config", return_value=cfg):
        results = check_directories()

    assert results == []


def test_check_directories_source_dir(tmp_path: Path) -> None:
    cfg = AppConfig(paths=PathConfig(source_dir=tmp_path))
    with patch("reeln.core.doctor.load_config", return_value=cfg):
        results = check_directories()

    assert len(results) == 1
    assert "source_dir" in results[0].name


# ---------------------------------------------------------------------------
# run_doctor
# ---------------------------------------------------------------------------


def test_run_doctor_healthy() -> None:
    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
        patch("reeln.core.doctor.list_codecs", return_value=["libx264", "libx265", "aac"]),
        patch("reeln.core.doctor.list_hwaccels", return_value=["videotoolbox"]),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
    ):
        results = run_doctor()

    # ffmpeg + 3 codecs + hwaccel + config = 6
    assert len(results) == 6
    assert all(r.status == CheckStatus.PASS for r in results)


def test_run_doctor_ffmpeg_missing() -> None:
    with (
        patch(
            "reeln.core.doctor.discover_ffmpeg",
            side_effect=FFmpegError("ffmpeg not found"),
        ),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
    ):
        results = run_doctor()

    # ffmpeg FAIL + config PASS = 2 (codec/hwaccel skipped)
    ffmpeg_results = [r for r in results if r.name == "ffmpeg"]
    assert len(ffmpeg_results) == 1
    assert ffmpeg_results[0].status == CheckStatus.FAIL


def test_run_doctor_config_error() -> None:
    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
        patch("reeln.core.doctor.list_codecs", return_value=["libx264", "libx265", "aac"]),
        patch("reeln.core.doctor.list_hwaccels", return_value=["videotoolbox"]),
        patch(
            "reeln.core.doctor.load_config",
            side_effect=Exception("config boom"),
        ),
    ):
        results = run_doctor()

    config_results = [r for r in results if r.name == "config"]
    assert len(config_results) == 1
    assert config_results[0].status == CheckStatus.FAIL
    assert "config boom" in config_results[0].message


def test_run_doctor_directory_error() -> None:
    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
        patch("reeln.core.doctor.list_codecs", return_value=["libx264", "libx265", "aac"]),
        patch("reeln.core.doctor.list_hwaccels", return_value=["videotoolbox"]),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
        patch(
            "reeln.core.doctor.check_directories",
            side_effect=Exception("dir boom"),
        ),
    ):
        results = run_doctor()

    dir_results = [r for r in results if r.name == "directories"]
    assert len(dir_results) == 1
    assert dir_results[0].status == CheckStatus.FAIL


def test_run_doctor_with_extra_checks() -> None:
    class GoodCheck:
        name = "my_plugin"

        def run(self) -> list[CheckResult]:
            return [CheckResult(name="my_plugin", status=CheckStatus.PASS, message="ok")]

    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
        patch("reeln.core.doctor.list_codecs", return_value=["libx264", "libx265", "aac"]),
        patch("reeln.core.doctor.list_hwaccels", return_value=["videotoolbox"]),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
    ):
        results = run_doctor(extra_checks=[GoodCheck()])

    plugin_results = [r for r in results if r.name == "my_plugin"]
    assert len(plugin_results) == 1
    assert plugin_results[0].status == CheckStatus.PASS


def test_run_doctor_extra_check_error() -> None:
    class BadCheck:
        name = "bad_plugin"

        def run(self) -> list[CheckResult]:
            raise RuntimeError("plugin crashed")

    with (
        patch("reeln.core.doctor.discover_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
        patch("reeln.core.doctor.check_version", return_value="7.1"),
        patch("reeln.core.doctor.list_codecs", return_value=["libx264", "libx265", "aac"]),
        patch("reeln.core.doctor.list_hwaccels", return_value=["videotoolbox"]),
        patch("reeln.core.doctor.load_config", return_value=AppConfig()),
    ):
        results = run_doctor(extra_checks=[BadCheck()])

    bad_results = [r for r in results if r.name == "bad_plugin"]
    assert len(bad_results) == 1
    assert bad_results[0].status == CheckStatus.FAIL
    assert "plugin crashed" in bad_results[0].message


# ---------------------------------------------------------------------------
# format_results
# ---------------------------------------------------------------------------


def test_format_results_pass() -> None:
    results = [CheckResult(name="test", status=CheckStatus.PASS, message="all good")]
    lines = format_results(results)
    assert lines == ["  PASS: all good"]


def test_format_results_warn_with_hint() -> None:
    results = [
        CheckResult(name="test", status=CheckStatus.WARN, message="issue found", hint="fix it"),
    ]
    lines = format_results(results)
    assert lines == ["  WARN: issue found", "    hint: fix it"]


def test_format_results_fail_with_hint() -> None:
    results = [
        CheckResult(name="test", status=CheckStatus.FAIL, message="broken", hint="reinstall"),
    ]
    lines = format_results(results)
    assert lines == ["  FAIL: broken", "    hint: reinstall"]


def test_format_results_mixed() -> None:
    results = [
        CheckResult(name="a", status=CheckStatus.PASS, message="ok"),
        CheckResult(name="b", status=CheckStatus.WARN, message="warn", hint="check"),
        CheckResult(name="c", status=CheckStatus.FAIL, message="fail", hint="fix"),
    ]
    lines = format_results(results)
    assert len(lines) == 5  # 1 PASS + 2 WARN lines + 2 FAIL lines


# ---------------------------------------------------------------------------
# doctor_exit_code
# ---------------------------------------------------------------------------


def test_doctor_exit_code_all_pass() -> None:
    results = [
        CheckResult(name="a", status=CheckStatus.PASS, message="ok"),
        CheckResult(name="b", status=CheckStatus.PASS, message="ok"),
    ]
    assert doctor_exit_code(results) == 0


def test_doctor_exit_code_with_warn() -> None:
    results = [
        CheckResult(name="a", status=CheckStatus.PASS, message="ok"),
        CheckResult(name="b", status=CheckStatus.WARN, message="warn"),
    ]
    assert doctor_exit_code(results) == 0


def test_doctor_exit_code_with_fail() -> None:
    results = [
        CheckResult(name="a", status=CheckStatus.PASS, message="ok"),
        CheckResult(name="b", status=CheckStatus.FAIL, message="fail"),
    ]
    assert doctor_exit_code(results) == 1


def test_doctor_exit_code_empty() -> None:
    assert doctor_exit_code([]) == 0
