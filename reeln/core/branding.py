"""Branding overlay resolution and context building."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import reeln
from reeln.core.errors import RenderError
from reeln.core.log import get_logger
from reeln.core.templates import format_ass_time, render_template_file
from reeln.models.branding import BrandingConfig
from reeln.models.template import TemplateContext

log: logging.Logger = get_logger(__name__)


def build_branding_context(duration: float) -> TemplateContext:
    """Build template context for the branding overlay.

    Provides ``version`` (from ``reeln.__version__``) and
    ``branding_end`` (ASS-formatted end timestamp).
    """
    return TemplateContext(
        variables={
            "version": f"v{reeln.__version__}",
            "branding_end": format_ass_time(duration),
        }
    )


def resolve_branding(config: BrandingConfig, output_dir: Path) -> Path | None:
    """Resolve and render the branding template to a temp ``.ass`` file.

    Returns ``None`` when branding is disabled.  The caller is
    responsible for cleaning up the returned temp file.
    """
    if not config.enabled:
        return None

    ctx = build_branding_context(config.duration)

    if config.template.startswith("builtin:"):
        from reeln.core.overlay import resolve_builtin_template

        template_name = config.template.removeprefix("builtin:")
        template_path = resolve_builtin_template(template_name)
    else:
        template_path = Path(config.template).expanduser()

    rendered = render_template_file(template_path, ctx)
    fd, tmp_path = tempfile.mkstemp(suffix=".ass", dir=str(output_dir))
    os.close(fd)
    tmp = Path(tmp_path)
    try:
        tmp.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise RenderError(f"Failed to write rendered branding: {exc}") from exc
    return tmp
