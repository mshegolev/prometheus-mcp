"""Integration tests for the 4 Prometheus status tools.

Tests follow the same pattern as test_tools_integration.py — mock HTTP,
call tool functions directly, verify structured + markdown output.
"""

from __future__ import annotations

import pytest
import responses
from mcp.server.fastmcp.exceptions import ToolError

from prometheus_mcp.tools_status import (
    prometheus_get_build_info,
    prometheus_get_cardinality,
    prometheus_get_runtime_info,
    prometheus_health_check,
)

BASE = "https://prometheus.example.com"
API = f"{BASE}/api/v1"


@pytest.fixture(autouse=True)
def _auto_reset(reset_client_cache: None) -> None:
    """Use shared fixture to reset client cache between tests."""


@pytest.fixture(autouse=True)
def configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_URL", BASE)
    monkeypatch.delenv("PROMETHEUS_TOKEN", raising=False)


# ── Health Check ──────────────────────────────────────────────────────────────


@responses.activate
def test_health_check_both_healthy() -> None:
    responses.add(responses.GET, f"{BASE}/-/healthy", body="OK", status=200)
    responses.add(responses.GET, f"{BASE}/-/ready", body="OK", status=200)
    result = prometheus_health_check()
    data = result.structuredContent
    assert data["healthy"] is True
    assert data["healthy_status_code"] == 200
    assert data["ready"] is True
    assert data["ready_status_code"] == 200


@responses.activate
def test_health_check_not_ready() -> None:
    responses.add(responses.GET, f"{BASE}/-/healthy", body="OK", status=200)
    responses.add(responses.GET, f"{BASE}/-/ready", body="Service Unavailable", status=503)
    result = prometheus_health_check()
    data = result.structuredContent
    assert data["healthy"] is True
    assert data["ready"] is False


@responses.activate
def test_health_check_markdown() -> None:
    responses.add(responses.GET, f"{BASE}/-/healthy", body="OK", status=200)
    responses.add(responses.GET, f"{BASE}/-/ready", body="OK", status=200)
    result = prometheus_health_check()
    md = result.content[0].text
    assert "Health Check" in md
    assert "healthy" in md.lower()


# ── Cardinality ───────────────────────────────────────────────────────────────


@responses.activate
def test_cardinality_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/status/tsdb",
        json={
            "status": "success",
            "data": {
                "headStats": {
                    "numSeries": 150000,
                    "numLabelPairs": 500000,
                    "chunkCount": 300000,
                    "minTime": 1705000000000,
                    "maxTime": 1705100000000,
                },
                "seriesCountByMetricName": [
                    {"name": "http_requests_total", "value": 5000},
                    {"name": "node_cpu_seconds_total", "value": 3000},
                ],
                "labelValueCountByLabelName": [
                    {"name": "instance", "value": 200},
                    {"name": "job", "value": 50},
                ],
                "memoryInBytesByLabelName": [
                    {"name": "instance", "value": 1048576},
                ],
            },
        },
        status=200,
    )
    result = prometheus_get_cardinality()
    data = result.structuredContent
    assert data["num_series"] == 150000
    assert data["chunk_count"] == 300000
    assert len(data["top_metrics_by_series"]) == 2
    assert data["top_metrics_by_series"][0]["name"] == "http_requests_total"


@responses.activate
def test_cardinality_empty() -> None:
    responses.add(
        responses.GET,
        f"{API}/status/tsdb",
        json={"status": "success", "data": {}},
        status=200,
    )
    result = prometheus_get_cardinality()
    data = result.structuredContent
    assert data["num_series"] == 0
    assert data["top_metrics_by_series"] == []


@responses.activate
def test_cardinality_markdown() -> None:
    responses.add(
        responses.GET,
        f"{API}/status/tsdb",
        json={
            "status": "success",
            "data": {
                "headStats": {"numSeries": 100},
                "seriesCountByMetricName": [{"name": "up", "value": 10}],
                "labelValueCountByLabelName": [],
                "memoryInBytesByLabelName": [],
            },
        },
        status=200,
    )
    result = prometheus_get_cardinality()
    md = result.content[0].text
    assert "Cardinality" in md
    assert "`up`" in md


@responses.activate
def test_cardinality_401() -> None:
    responses.add(responses.GET, f"{API}/status/tsdb", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_get_cardinality()


# ── Runtime Info ──────────────────────────────────────────────────────────────


@responses.activate
def test_runtime_info_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/status/runtimeinfo",
        json={
            "status": "success",
            "data": {
                "startTime": "2024-01-15T10:00:00Z",
                "goroutineCount": 42,
                "timeSeriesCount": 150000,
                "storageRetention": "15d",
                "corruptionCount": 0,
                "reloadConfigSuccess": True,
                "lastConfigTime": "2024-01-15T10:00:00Z",
            },
        },
        status=200,
    )
    result = prometheus_get_runtime_info()
    data = result.structuredContent
    assert data["goroutine_count"] == 42
    assert data["time_series_count"] == 150000
    assert data["storage_retention"] == "15d"


@responses.activate
def test_runtime_info_markdown() -> None:
    responses.add(
        responses.GET,
        f"{API}/status/runtimeinfo",
        json={
            "status": "success",
            "data": {
                "goroutineCount": 42,
                "storageRetention": "15d",
            },
        },
        status=200,
    )
    result = prometheus_get_runtime_info()
    md = result.content[0].text
    assert "Runtime" in md
    assert "15d" in md


@responses.activate
def test_runtime_info_401() -> None:
    responses.add(responses.GET, f"{API}/status/runtimeinfo", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_get_runtime_info()


# ── Build Info ────────────────────────────────────────────────────────────────


@responses.activate
def test_build_info_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/status/buildinfo",
        json={
            "status": "success",
            "data": {
                "version": "2.48.0",
                "revision": "abc123",
                "branch": "HEAD",
                "buildUser": "root@host",
                "buildDate": "20240115-10:00:00",
                "goVersion": "go1.21.6",
            },
        },
        status=200,
    )
    result = prometheus_get_build_info()
    data = result.structuredContent
    assert data["version"] == "2.48.0"
    assert data["goVersion"] == "go1.21.6"
    assert data["revision"] == "abc123"


@responses.activate
def test_build_info_markdown() -> None:
    responses.add(
        responses.GET,
        f"{API}/status/buildinfo",
        json={
            "status": "success",
            "data": {"version": "2.48.0", "goVersion": "go1.21.6"},
        },
        status=200,
    )
    result = prometheus_get_build_info()
    md = result.content[0].text
    assert "Build Info" in md
    assert "2.48.0" in md
    assert "go1.21.6" in md


@responses.activate
def test_build_info_401() -> None:
    responses.add(responses.GET, f"{API}/status/buildinfo", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_get_build_info()
