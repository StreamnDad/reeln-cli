"""Integration tests requiring a real ffmpeg binary.

Run with: pytest tests/integration/ -m integration
"""

from __future__ import annotations

import pytest

from reeln.core.ffmpeg import check_version, discover_ffmpeg, get_version


@pytest.mark.integration
def test_discover_finds_real_ffmpeg() -> None:
    path = discover_ffmpeg()
    assert path.exists()


@pytest.mark.integration
def test_get_version_real() -> None:
    path = discover_ffmpeg()
    version = get_version(path)
    assert version  # non-empty string


@pytest.mark.integration
def test_check_version_real() -> None:
    path = discover_ffmpeg()
    version = check_version(path)
    assert version
