"""Branding overlay configuration for rendered shorts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrandingConfig:
    """Configuration for the branding overlay shown at the start of renders.

    Attributes:
        enabled: Whether branding is shown (default ``True``).
        template: Template path — ``"builtin:branding"`` or user path to ``.ass``.
        duration: How long the branding is visible in seconds.
    """

    enabled: bool = True
    template: str = "builtin:branding"
    duration: float = 5.0
