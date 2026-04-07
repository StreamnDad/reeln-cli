"""Tests for plugin authentication data models."""

from __future__ import annotations

import pytest

from reeln.models.auth import (
    AuthCheckResult,
    AuthStatus,
    PluginAuthReport,
    auth_check_result_to_dict,
    plugin_auth_report_to_dict,
)

# ---------------------------------------------------------------------------
# AuthStatus
# ---------------------------------------------------------------------------


def test_auth_status_values() -> None:
    assert AuthStatus.OK.value == "ok"
    assert AuthStatus.WARN.value == "warn"
    assert AuthStatus.FAIL.value == "fail"
    assert AuthStatus.EXPIRED.value == "expired"
    assert AuthStatus.NOT_CONFIGURED.value == "not_configured"


def test_auth_status_member_count() -> None:
    assert len(AuthStatus) == 5


# ---------------------------------------------------------------------------
# AuthCheckResult
# ---------------------------------------------------------------------------


def test_auth_check_result_required_fields() -> None:
    r = AuthCheckResult(service="YouTube", status=AuthStatus.OK, message="Connected")
    assert r.service == "YouTube"
    assert r.status == AuthStatus.OK
    assert r.message == "Connected"


def test_auth_check_result_defaults() -> None:
    r = AuthCheckResult(service="s", status=AuthStatus.OK, message="ok")
    assert r.identity == ""
    assert r.expires_at == ""
    assert r.scopes == []
    assert r.required_scopes == []
    assert r.hint == ""


def test_auth_check_result_all_fields() -> None:
    r = AuthCheckResult(
        service="YouTube",
        status=AuthStatus.OK,
        message="Authenticated",
        identity="StreamnDad Hockey",
        expires_at="2026-12-31T23:59:59",
        scopes=["youtube", "youtube.upload"],
        required_scopes=["youtube", "youtube.upload", "youtube.force-ssl"],
        hint="Grant youtube.force-ssl scope",
    )
    assert r.identity == "StreamnDad Hockey"
    assert r.expires_at == "2026-12-31T23:59:59"
    assert r.scopes == ["youtube", "youtube.upload"]
    assert r.required_scopes == ["youtube", "youtube.upload", "youtube.force-ssl"]
    assert r.hint == "Grant youtube.force-ssl scope"


def test_auth_check_result_frozen() -> None:
    r = AuthCheckResult(service="s", status=AuthStatus.OK, message="ok")
    with pytest.raises(AttributeError):
        r.service = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PluginAuthReport
# ---------------------------------------------------------------------------


def test_plugin_auth_report_defaults() -> None:
    report = PluginAuthReport(plugin_name="google")
    assert report.plugin_name == "google"
    assert report.results == []


def test_plugin_auth_report_with_results() -> None:
    r1 = AuthCheckResult(service="YouTube", status=AuthStatus.OK, message="ok")
    r2 = AuthCheckResult(service="Drive", status=AuthStatus.WARN, message="limited")
    report = PluginAuthReport(plugin_name="google", results=[r1, r2])
    assert len(report.results) == 2
    assert report.results[0].service == "YouTube"
    assert report.results[1].service == "Drive"


def test_plugin_auth_report_frozen() -> None:
    report = PluginAuthReport(plugin_name="test")
    with pytest.raises(AttributeError):
        report.plugin_name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def test_auth_check_result_to_dict_minimal() -> None:
    r = AuthCheckResult(service="OpenAI", status=AuthStatus.FAIL, message="Key invalid")
    d = auth_check_result_to_dict(r)
    assert d == {
        "service": "OpenAI",
        "status": "fail",
        "message": "Key invalid",
        "identity": "",
        "expires_at": "",
        "scopes": [],
        "required_scopes": [],
        "hint": "",
    }


def test_auth_check_result_to_dict_full() -> None:
    r = AuthCheckResult(
        service="YouTube",
        status=AuthStatus.OK,
        message="Connected",
        identity="StreamnDad",
        expires_at="2026-12-31",
        scopes=["youtube"],
        required_scopes=["youtube", "youtube.upload"],
        hint="Grant upload scope",
    )
    d = auth_check_result_to_dict(r)
    assert d["service"] == "YouTube"
    assert d["status"] == "ok"
    assert d["identity"] == "StreamnDad"
    assert d["expires_at"] == "2026-12-31"
    assert d["scopes"] == ["youtube"]
    assert d["required_scopes"] == ["youtube", "youtube.upload"]
    assert d["hint"] == "Grant upload scope"


def test_plugin_auth_report_to_dict_empty() -> None:
    report = PluginAuthReport(plugin_name="empty")
    d = plugin_auth_report_to_dict(report)
    assert d == {"name": "empty", "results": []}


def test_plugin_auth_report_to_dict_with_results() -> None:
    r = AuthCheckResult(service="R2", status=AuthStatus.OK, message="ok")
    report = PluginAuthReport(plugin_name="cloudflare", results=[r])
    d = plugin_auth_report_to_dict(report)
    assert d["name"] == "cloudflare"
    assert len(d["results"]) == 1  # type: ignore[arg-type]
    assert d["results"][0]["service"] == "R2"  # type: ignore[index]
    assert d["results"][0]["status"] == "ok"  # type: ignore[index]
