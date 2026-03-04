"""Tests for reeln package init."""

from __future__ import annotations

import re


def test_version_is_semver() -> None:
    from reeln import __version__

    assert re.match(r"^\d+\.\d+\.\d+$", __version__)


def test_version_not_empty() -> None:
    from reeln import __version__

    assert len(__version__) > 0
