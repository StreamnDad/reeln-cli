"""Template context model for variable substitution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TemplateContext:
    """Aggregated context for template variable substitution.

    Built from GameInfo, GameEvent metadata, and plugin-provided data.
    All values are strings ready for ``{{key}}`` substitution.
    """

    variables: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        """Return the value for *key*, or *default* if not present."""
        return self.variables.get(key, default)

    def merge(self, other: TemplateContext) -> TemplateContext:
        """Return a new context with *other*'s variables merged in.

        Values from *other* take precedence on conflict.
        """
        merged = dict(self.variables)
        merged.update(other.variables)
        return TemplateContext(variables=merged)
