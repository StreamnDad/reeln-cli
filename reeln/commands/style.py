"""Shared CLI styling helpers for consistent output formatting."""

from __future__ import annotations

import typer

GREEN = typer.colors.GREEN
RED = typer.colors.RED
YELLOW = typer.colors.YELLOW
DIM = typer.colors.BRIGHT_BLACK


def label(text: str) -> str:
    """Dim label text for secondary information."""
    return typer.style(text, fg=DIM)


def bold(text: str) -> str:
    """Bold text for names and headings."""
    return typer.style(text, bold=True)


def success(text: str) -> str:
    """Green text for positive status."""
    return typer.style(text, fg=GREEN)


def error(text: str) -> str:
    """Red text for negative status."""
    return typer.style(text, fg=RED)


def warn(text: str) -> str:
    """Yellow text for warnings and upgrades."""
    return typer.style(text, fg=YELLOW)




