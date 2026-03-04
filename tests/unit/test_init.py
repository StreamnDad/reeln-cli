"""Tests for reeln package init."""

from __future__ import annotations

import re


def test_version_is_semver() -> None:
    from reeln import __version__

    assert re.match(r"^\d+\.\d+\.\d+$", __version__)


def test_version_value() -> None:
    from reeln import __version__

    assert __version__ == "0.0.24"
