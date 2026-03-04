"""Shared fixtures for reeln tests."""

from __future__ import annotations

import logging

import pytest
from typer.testing import CliRunner


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Return a Typer CliRunner for invoking CLI commands."""
    return CliRunner()


@pytest.fixture(autouse=True)
def reset_logging() -> None:
    """Clear logging handlers between tests."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)


@pytest.fixture(autouse=True)
def _reset_hook_registry() -> None:
    """Reset the plugin hook registry between tests for isolation."""
    from reeln.plugins.registry import reset_registry

    reset_registry()
