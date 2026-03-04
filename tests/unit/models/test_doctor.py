"""Tests for doctor data models."""

from __future__ import annotations

import pytest

from reeln.models.doctor import CheckResult, CheckStatus, DoctorCheck

# ---------------------------------------------------------------------------
# CheckStatus
# ---------------------------------------------------------------------------


def test_check_status_values() -> None:
    assert CheckStatus.PASS.value == "pass"
    assert CheckStatus.WARN.value == "warn"
    assert CheckStatus.FAIL.value == "fail"


def test_check_status_members() -> None:
    assert set(CheckStatus) == {CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL}


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------


def test_check_result_fields() -> None:
    result = CheckResult(
        name="ffmpeg",
        status=CheckStatus.PASS,
        message="ffmpeg 7.1 found at /usr/bin/ffmpeg",
    )
    assert result.name == "ffmpeg"
    assert result.status == CheckStatus.PASS
    assert result.message == "ffmpeg 7.1 found at /usr/bin/ffmpeg"
    assert result.hint == ""


def test_check_result_with_hint() -> None:
    result = CheckResult(
        name="ffmpeg",
        status=CheckStatus.FAIL,
        message="ffmpeg not found",
        hint="Install via: brew install ffmpeg",
    )
    assert result.hint == "Install via: brew install ffmpeg"


def test_check_result_is_frozen() -> None:
    result = CheckResult(name="test", status=CheckStatus.PASS, message="ok")
    with pytest.raises(AttributeError):
        result.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DoctorCheck protocol
# ---------------------------------------------------------------------------


def test_doctor_check_protocol() -> None:
    """A class with name + run() satisfies the DoctorCheck protocol."""

    class MyCheck:
        name: str = "my_check"

        def run(self) -> list[CheckResult]:
            return [CheckResult(name=self.name, status=CheckStatus.PASS, message="ok")]

    check: DoctorCheck = MyCheck()
    results = check.run()
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
