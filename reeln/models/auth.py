"""Data structures for plugin authentication check results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AuthStatus(Enum):
    """Outcome status for a single auth check."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    EXPIRED = "expired"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class AuthCheckResult:
    """Result of a single authentication check.

    Each plugin may return multiple of these (e.g., Meta returns one
    per service: Facebook Page, Instagram, Threads).
    """

    service: str
    status: AuthStatus
    message: str
    identity: str = ""
    expires_at: str = ""
    scopes: list[str] = field(default_factory=list)
    required_scopes: list[str] = field(default_factory=list)
    hint: str = ""


@dataclass(frozen=True)
class PluginAuthReport:
    """Aggregated auth report from a single plugin."""

    plugin_name: str
    results: list[AuthCheckResult] = field(default_factory=list)


def auth_check_result_to_dict(result: AuthCheckResult) -> dict[str, object]:
    """Serialize an ``AuthCheckResult`` to a JSON-compatible dict."""
    return {
        "service": result.service,
        "status": result.status.value,
        "message": result.message,
        "identity": result.identity,
        "expires_at": result.expires_at,
        "scopes": list(result.scopes),
        "required_scopes": list(result.required_scopes),
        "hint": result.hint,
    }


def plugin_auth_report_to_dict(report: PluginAuthReport) -> dict[str, object]:
    """Serialize a ``PluginAuthReport`` to a JSON-compatible dict."""
    return {
        "name": report.plugin_name,
        "results": [auth_check_result_to_dict(r) for r in report.results],
    }
