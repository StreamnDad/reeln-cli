"""Tests for template context model."""

from __future__ import annotations

import pytest

from reeln.models.template import TemplateContext


def test_template_context_defaults() -> None:
    ctx = TemplateContext()
    assert ctx.variables == {}


def test_template_context_with_variables() -> None:
    ctx = TemplateContext(variables={"home_team": "Roseville", "away_team": "Mahtomedi"})
    assert ctx.variables["home_team"] == "Roseville"
    assert ctx.variables["away_team"] == "Mahtomedi"


def test_template_context_get_present() -> None:
    ctx = TemplateContext(variables={"player": "Smith"})
    assert ctx.get("player") == "Smith"


def test_template_context_get_missing() -> None:
    ctx = TemplateContext()
    assert ctx.get("player") == ""


def test_template_context_get_missing_with_default() -> None:
    ctx = TemplateContext()
    assert ctx.get("player", "Unknown") == "Unknown"


def test_template_context_merge() -> None:
    a = TemplateContext(variables={"home_team": "A", "sport": "hockey"})
    b = TemplateContext(variables={"away_team": "B", "sport": "basketball"})
    merged = a.merge(b)
    assert merged.get("home_team") == "A"
    assert merged.get("away_team") == "B"
    assert merged.get("sport") == "basketball"  # b wins


def test_template_context_merge_does_not_mutate() -> None:
    a = TemplateContext(variables={"key": "a"})
    b = TemplateContext(variables={"key": "b"})
    merged = a.merge(b)
    assert a.get("key") == "a"  # original unchanged
    assert merged.get("key") == "b"


def test_template_context_merge_empty() -> None:
    a = TemplateContext(variables={"key": "value"})
    b = TemplateContext()
    merged = a.merge(b)
    assert merged.get("key") == "value"


def test_template_context_is_frozen() -> None:
    ctx = TemplateContext()
    with pytest.raises(AttributeError):
        ctx.variables = {}  # type: ignore[misc]
