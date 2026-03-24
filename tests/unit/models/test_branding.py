"""Tests for branding configuration model."""

from __future__ import annotations

import pytest

from reeln.models.branding import BrandingConfig


class TestBrandingConfigDefaults:
    def test_enabled_default(self) -> None:
        config = BrandingConfig()
        assert config.enabled is True

    def test_template_default(self) -> None:
        config = BrandingConfig()
        assert config.template == "builtin:branding"

    def test_duration_default(self) -> None:
        config = BrandingConfig()
        assert config.duration == 5.0


class TestBrandingConfigCustom:
    def test_disabled(self) -> None:
        config = BrandingConfig(enabled=False)
        assert config.enabled is False

    def test_custom_template(self) -> None:
        config = BrandingConfig(template="/path/to/custom.ass")
        assert config.template == "/path/to/custom.ass"

    def test_custom_duration(self) -> None:
        config = BrandingConfig(duration=5.0)
        assert config.duration == 5.0


class TestBrandingConfigFrozen:
    def test_cannot_mutate_enabled(self) -> None:
        config = BrandingConfig()
        with pytest.raises(AttributeError):
            config.enabled = False  # type: ignore[misc]

    def test_cannot_mutate_template(self) -> None:
        config = BrandingConfig()
        with pytest.raises(AttributeError):
            config.template = "other"  # type: ignore[misc]

    def test_cannot_mutate_duration(self) -> None:
        config = BrandingConfig()
        with pytest.raises(AttributeError):
            config.duration = 10.0  # type: ignore[misc]


class TestBrandingConfigEquality:
    def test_equal_defaults(self) -> None:
        assert BrandingConfig() == BrandingConfig()

    def test_not_equal_different_enabled(self) -> None:
        assert BrandingConfig(enabled=True) != BrandingConfig(enabled=False)

    def test_not_equal_different_duration(self) -> None:
        assert BrandingConfig(duration=5.0) != BrandingConfig(duration=3.0)
