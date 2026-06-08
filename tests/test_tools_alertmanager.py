"""Integration tests for the 4 Alertmanager tools."""

from __future__ import annotations

import pytest
import responses
from mcp.server.fastmcp.exceptions import ToolError

from prometheus_mcp.tools_alertmanager import (
    alertmanager_get_status,
    alertmanager_list_alert_groups,
    alertmanager_list_alerts,
    alertmanager_list_silences,
)

AM_BASE = "https://alertmanager.example.com"
AM_API = f"{AM_BASE}/api/v2"


@pytest.fixture(autouse=True)
def _auto_reset(reset_client_cache: None) -> None:
    """Use shared fixture to reset client cache between tests."""


@pytest.fixture(autouse=True)
def configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
    monkeypatch.setenv("ALERTMANAGER_URL", AM_BASE)
    monkeypatch.delenv("ALERTMANAGER_TOKEN", raising=False)


# ── List Silences ─────────────────────────────────────────────────────────────


@responses.activate
def test_silences_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{AM_API}/silences",
        json=[
            {
                "id": "silence-1",
                "status": {"state": "active"},
                "matchers": [{"name": "alertname", "value": "HighCPU", "isRegex": False, "isEqual": True}],
                "createdBy": "admin",
                "comment": "Maintenance window",
                "startsAt": "2024-01-15T10:00:00Z",
                "endsAt": "2024-01-15T12:00:00Z",
                "updatedAt": "2024-01-15T10:00:00Z",
            }
        ],
        status=200,
    )
    result = alertmanager_list_silences()
    data = result.structuredContent
    assert data["total_count"] == 1
    assert data["active_count"] == 1
    assert data["silences"][0]["createdBy"] == "admin"
    assert data["silences"][0]["matchers"][0]["name"] == "alertname"


@responses.activate
def test_silences_empty() -> None:
    responses.add(responses.GET, f"{AM_API}/silences", json=[], status=200)
    result = alertmanager_list_silences()
    data = result.structuredContent
    assert data["total_count"] == 0


@responses.activate
def test_silences_401() -> None:
    responses.add(responses.GET, f"{AM_API}/silences", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        alertmanager_list_silences()


# ── List Alerts ───────────────────────────────────────────────────────────────


@responses.activate
def test_alerts_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{AM_API}/alerts",
        json=[
            {
                "labels": {"alertname": "HighCPU", "severity": "critical"},
                "annotations": {"summary": "CPU is high"},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2024-01-15T10:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://prometheus:9090/...",
                "fingerprint": "abc123",
            },
            {
                "labels": {"alertname": "DiskFull", "severity": "warning"},
                "annotations": {},
                "status": {"state": "suppressed", "silencedBy": ["silence-1"], "inhibitedBy": []},
                "startsAt": "2024-01-15T09:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "",
                "fingerprint": "def456",
            },
        ],
        status=200,
    )
    result = alertmanager_list_alerts()
    data = result.structuredContent
    assert data["total_count"] == 2
    assert data["active_count"] == 1
    assert data["suppressed_count"] == 1
    assert data["alerts"][1]["status"]["silencedBy"] == ["silence-1"]


@responses.activate
def test_alerts_empty() -> None:
    responses.add(responses.GET, f"{AM_API}/alerts", json=[], status=200)
    result = alertmanager_list_alerts()
    assert result.structuredContent["total_count"] == 0


@responses.activate
def test_alerts_markdown() -> None:
    responses.add(
        responses.GET,
        f"{AM_API}/alerts",
        json=[
            {
                "labels": {"alertname": "TestAlert"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "",
            }
        ],
        status=200,
    )
    result = alertmanager_list_alerts()
    md = result.content[0].text
    assert "TestAlert" in md
    assert "active" in md


# ── Get Status ────────────────────────────────────────────────────────────────


@responses.activate
def test_status_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{AM_API}/status",
        json={
            "cluster": {"status": "ready"},
            "versionInfo": {
                "version": "0.27.0",
                "revision": "abc",
                "branch": "HEAD",
                "buildUser": "root",
                "buildDate": "2024-01-15",
                "goVersion": "go1.21",
            },
            "uptime": "72h30m0s",
            "config": {"original": "route:\n  receiver: default"},
        },
        status=200,
    )
    result = alertmanager_get_status()
    data = result.structuredContent
    assert data["cluster_status"] == "ready"
    assert data["version_info"]["version"] == "0.27.0"
    assert data["uptime"] == "72h30m0s"
    assert "route:" in data["config_yaml"]


@responses.activate
def test_status_401() -> None:
    responses.add(responses.GET, f"{AM_API}/status", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        alertmanager_get_status()


# ── List Alert Groups ─────────────────────────────────────────────────────────


@responses.activate
def test_alert_groups_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{AM_API}/alerts/groups",
        json=[
            {
                "labels": {"job": "node"},
                "receiver": {"name": "slack-critical"},
                "alerts": [
                    {"labels": {"alertname": "NodeDown"}, "status": {"state": "active"}},
                    {"labels": {"alertname": "NodeCPU"}, "status": {"state": "active"}},
                ],
            }
        ],
        status=200,
    )
    result = alertmanager_list_alert_groups()
    data = result.structuredContent
    assert data["total_groups"] == 1
    assert data["total_alerts"] == 2
    assert data["groups"][0]["receiver"] == "slack-critical"
    assert data["groups"][0]["alert_count"] == 2


@responses.activate
def test_alert_groups_empty() -> None:
    responses.add(responses.GET, f"{AM_API}/alerts/groups", json=[], status=200)
    result = alertmanager_list_alert_groups()
    data = result.structuredContent
    assert data["total_groups"] == 0
    assert data["total_alerts"] == 0


@responses.activate
def test_alert_groups_markdown() -> None:
    responses.add(
        responses.GET,
        f"{AM_API}/alerts/groups",
        json=[
            {
                "labels": {"team": "infra"},
                "receiver": {"name": "pagerduty"},
                "alerts": [{"labels": {"alertname": "X"}, "status": {"state": "active"}}],
            }
        ],
        status=200,
    )
    result = alertmanager_list_alert_groups()
    md = result.content[0].text
    assert "pagerduty" in md
    assert "Alert Groups" in md
