"""Tests for ``python -m reeln`` support."""

from __future__ import annotations

import contextlib
import runpy
from unittest.mock import patch


def test_main_invokes_app() -> None:
    with patch("reeln.cli.app") as mock_app:
        mock_app.side_effect = SystemExit(0)
        with contextlib.suppress(SystemExit):
            runpy.run_module("reeln", run_name="__main__")
    mock_app.assert_called_once()
