"""Tests for branding overlay resolution and context building."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import reeln
from reeln.core.branding import build_branding_context, resolve_branding
from reeln.core.errors import RenderError
from reeln.core.templates import format_ass_time
from reeln.models.branding import BrandingConfig

# ---------------------------------------------------------------------------
# build_branding_context
# ---------------------------------------------------------------------------


class TestBuildBrandingContext:
    def test_version_included(self) -> None:
        ctx = build_branding_context(3.0)
        assert ctx.get("version") == f"v{reeln.__version__}"

    def test_branding_end_format(self) -> None:
        ctx = build_branding_context(3.0)
        assert ctx.get("branding_end") == format_ass_time(3.0)

    def test_custom_duration(self) -> None:
        ctx = build_branding_context(5.0)
        assert ctx.get("branding_end") == format_ass_time(5.0)

    def test_zero_duration(self) -> None:
        ctx = build_branding_context(0.0)
        assert ctx.get("branding_end") == format_ass_time(0.0)


# ---------------------------------------------------------------------------
# resolve_branding
# ---------------------------------------------------------------------------


class TestResolveBranding:
    def test_disabled_returns_none(self, tmp_path: Path) -> None:
        config = BrandingConfig(enabled=False)
        result = resolve_branding(config, tmp_path)
        assert result is None

    def test_builtin_template_renders(self, tmp_path: Path) -> None:
        config = BrandingConfig()
        result = resolve_branding(config, tmp_path)
        assert result is not None
        assert result.is_file()
        assert result.suffix == ".ass"
        content = result.read_text(encoding="utf-8")
        assert f"v{reeln.__version__}" in content
        result.unlink()

    def test_builtin_template_contains_fade(self, tmp_path: Path) -> None:
        config = BrandingConfig()
        result = resolve_branding(config, tmp_path)
        assert result is not None
        content = result.read_text(encoding="utf-8")
        assert "\\fad(300,800)" in content
        result.unlink()

    def test_builtin_template_contains_branding_end(self, tmp_path: Path) -> None:
        config = BrandingConfig(duration=5.0)
        result = resolve_branding(config, tmp_path)
        assert result is not None
        content = result.read_text(encoding="utf-8")
        assert format_ass_time(5.0) in content
        result.unlink()

    def test_custom_template(self, tmp_path: Path) -> None:
        template = tmp_path / "custom.ass"
        template.write_text(
            "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,{{branding_end}},Default,,0,0,0,,custom {{version}}\n",
            encoding="utf-8",
        )
        config = BrandingConfig(template=str(template))
        result = resolve_branding(config, tmp_path)
        assert result is not None
        content = result.read_text(encoding="utf-8")
        assert f"v{reeln.__version__}" in content
        assert format_ass_time(5.0) in content
        result.unlink()

    def test_missing_custom_template(self, tmp_path: Path) -> None:
        config = BrandingConfig(template="/nonexistent/branding.ass")
        with pytest.raises(RenderError, match="Template file not found"):
            resolve_branding(config, tmp_path)

    def test_missing_builtin_template(self, tmp_path: Path) -> None:
        config = BrandingConfig(template="builtin:nonexistent")
        with pytest.raises(RenderError, match="Builtin template not found"):
            resolve_branding(config, tmp_path)

    def test_write_failure(self, tmp_path: Path) -> None:
        config = BrandingConfig()
        with (
            patch("reeln.core.branding.Path.write_text", side_effect=OSError("disk full")),
            pytest.raises(RenderError, match="Failed to write rendered branding"),
        ):
            resolve_branding(config, tmp_path)
