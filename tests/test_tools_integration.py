"""Integration tests for the eight MCP tools.

We exercise each tool end-to-end via its public function, mocking the
Prometheus HTTP layer with :mod:`responses`. The goal is to cover the
happy path and key edge cases (empty results, auth errors, filter
forwarding, truncation hints, 422 bad_data).

These tests don't spin up a full MCP server — they call the decorated
tool functions directly, which is sufficient because our tools contain
the business logic; ``@mcp.tool`` only registers them with FastMCP.
"""

from __future__ import annotations

import pytest
import responses
from mcp.server.fastmcp.exceptions import ToolError

from prometheus_mcp import _mcp
from prometheus_mcp.tools import (
    prometheus_get_metric_metadata,
    prometheus_list_alerts,
    prometheus_list_label_values,
    prometheus_list_metrics,
    prometheus_list_rules,
    prometheus_list_targets,
    prometheus_query,
    prometheus_query_range,
)

BASE = "https://prometheus.example.com"
API = f"{BASE}/api/v1"


@pytest.fixture(autouse=True)
def configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set env vars + reset the module-global client cache per-test."""
    monkeypatch.setenv("PROMETHEUS_URL", BASE)
    monkeypatch.delenv("PROMETHEUS_TOKEN", raising=False)
    with _mcp._client_lock:
        if _mcp._client is not None:
            try:
                _mcp._client.close()
            except Exception:
                pass
        _mcp._client = None
    yield
    with _mcp._client_lock:
        if _mcp._client is not None:
            try:
                _mcp._client.close()
            except Exception:
                pass
        _mcp._client = None


# ── prometheus_list_metrics ────────────────────────────────────────────────


@responses.activate
def test_list_metrics_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/__name__/values",
        json={"status": "success", "data": ["http_requests_total", "node_cpu_seconds_total", "up"]},
        status=200,
    )
    result = prometheus_list_metrics()
    data = result.structuredContent
    assert data["returned_count"] == 3
    assert data["truncated"] is False
    assert data["pattern"] is None
    assert "up" in data["metrics"]
    assert data["metrics"] == sorted(data["metrics"])


@responses.activate
def test_list_metrics_with_pattern() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/__name__/values",
        json={"status": "success", "data": ["http_requests_total", "http_duration_seconds", "node_cpu", "up"]},
        status=200,
    )
    result = prometheus_list_metrics(pattern="http")
    data = result.structuredContent
    assert data["returned_count"] == 2
    assert data["pattern"] == "http"
    assert all("http" in m for m in data["metrics"])


@responses.activate
def test_list_metrics_pattern_case_insensitive() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/__name__/values",
        json={"status": "success", "data": ["HTTP_requests_total", "node_cpu"]},
        status=200,
    )
    result = prometheus_list_metrics(pattern="HTTP")
    data = result.structuredContent
    assert data["returned_count"] == 1
    assert "HTTP_requests_total" in data["metrics"]


@responses.activate
def test_list_metrics_empty() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/__name__/values",
        json={"status": "success", "data": []},
        status=200,
    )
    result = prometheus_list_metrics()
    data = result.structuredContent
    assert data["returned_count"] == 0
    assert data["metrics"] == []


@responses.activate
def test_list_metrics_truncated_at_500() -> None:
    big_list = [f"metric_{i}" for i in range(600)]
    responses.add(
        responses.GET,
        f"{API}/label/__name__/values",
        json={"status": "success", "data": big_list},
        status=200,
    )
    result = prometheus_list_metrics()
    data = result.structuredContent
    assert data["returned_count"] == 500
    assert data["truncated"] is True
    assert data["total_count"] == 600


@responses.activate
def test_list_metrics_markdown_truncation_hint() -> None:
    metrics = [f"metric_{i:02d}" for i in range(25)]
    responses.add(
        responses.GET,
        f"{API}/label/__name__/values",
        json={"status": "success", "data": metrics},
        status=200,
    )
    result = prometheus_list_metrics()
    md = result.content[0].text
    assert "Showing first 20 of 25" in md


@responses.activate
def test_list_metrics_401_raises_tool_error() -> None:
    responses.add(responses.GET, f"{API}/label/__name__/values", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_list_metrics()


# ── prometheus_query ───────────────────────────────────────────────────────


@responses.activate
def test_query_instant_vector() -> None:
    responses.add(
        responses.GET,
        f"{API}/query",
        json={
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"job": "prometheus", "instance": "localhost:9090"}, "value": [1705312800.0, "1"]},
                    {"metric": {"job": "node", "instance": "host1:9100"}, "value": [1705312800.0, "0"]},
                ],
            },
        },
        status=200,
    )
    result = prometheus_query(query="up")
    data = result.structuredContent
    assert data["query"] == "up"
    assert data["result_type"] == "vector"
    assert data["result_count"] == 2
    assert data["data"][0]["value"] == "1"
    assert data["data"][0]["labels"]["job"] == "prometheus"


@responses.activate
def test_query_with_time_param() -> None:
    responses.add(
        responses.GET,
        f"{API}/query",
        json={"status": "success", "data": {"resultType": "vector", "result": []}},
        status=200,
    )
    prometheus_query(query="up", time="2024-01-15T10:00:00Z")
    url = responses.calls[0].request.url
    assert "time=2024-01-15T10" in url or "time=" in url


@responses.activate
def test_query_scalar_result() -> None:
    responses.add(
        responses.GET,
        f"{API}/query",
        json={"status": "success", "data": {"resultType": "scalar", "result": [1705312800.0, "42"]}},
        status=200,
    )
    result = prometheus_query(query="scalar(up)")
    data = result.structuredContent
    assert data["result_type"] == "scalar"
    assert data["result_count"] == 1
    assert data["data"][0]["value"] == "42"
    assert data["data"][0]["labels"] == {}


@responses.activate
def test_query_empty_vector() -> None:
    responses.add(
        responses.GET,
        f"{API}/query",
        json={"status": "success", "data": {"resultType": "vector", "result": []}},
        status=200,
    )
    result = prometheus_query(query="nonexistent_metric")
    data = result.structuredContent
    assert data["result_count"] == 0
    assert data["data"] == []


@responses.activate
def test_query_400_raises_tool_error() -> None:
    responses.add(
        responses.GET,
        f"{API}/query",
        json={"status": "error", "errorType": "bad_data", "error": "invalid expression"},
        status=400,
    )
    with pytest.raises(ToolError, match="400"):
        prometheus_query(query="invalid{{{")


@responses.activate
def test_query_markdown_shows_labels_and_values() -> None:
    responses.add(
        responses.GET,
        f"{API}/query",
        json={
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"job": "prom"}, "value": [1.0, "1"]}],
            },
        },
        status=200,
    )
    result = prometheus_query(query="up")
    md = result.content[0].text
    assert "up" in md
    assert "1" in md


@responses.activate
def test_query_markdown_truncation_for_many_samples() -> None:
    items = [{"metric": {"instance": f"host{i}"}, "value": [1.0, str(i)]} for i in range(25)]
    responses.add(
        responses.GET,
        f"{API}/query",
        json={"status": "success", "data": {"resultType": "vector", "result": items}},
        status=200,
    )
    result = prometheus_query(query="up")
    md = result.content[0].text
    assert "Showing first 20 of 25" in md


# ── prometheus_query_range ─────────────────────────────────────────────────


@responses.activate
def test_query_range_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/query_range",
        json={
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"job": "node"},
                        "values": [
                            [1705312800.0, "0.5"],
                            [1705312860.0, "0.6"],
                        ],
                    }
                ],
            },
        },
        status=200,
    )
    result = prometheus_query_range(
        query="rate(node_cpu_seconds_total[5m])",
        start="2024-01-15T10:00:00Z",
        end="2024-01-15T11:00:00Z",
        step="1m",
    )
    data = result.structuredContent
    assert data["query"] == "rate(node_cpu_seconds_total[5m])"
    assert data["series_count"] == 1
    assert data["total_points"] == 2
    assert data["truncated"] is False
    assert data["data"][0]["labels"] == {"job": "node"}
    assert len(data["data"][0]["values"]) == 2


@responses.activate
def test_query_range_params_forwarded() -> None:
    responses.add(
        responses.GET,
        f"{API}/query_range",
        json={"status": "success", "data": {"resultType": "matrix", "result": []}},
        status=200,
    )
    prometheus_query_range(query="up", start="1705312800", end="1705316400", step="30")
    url = responses.calls[0].request.url
    assert "start=1705312800" in url
    assert "end=1705316400" in url
    assert "step=30" in url


@responses.activate
def test_query_range_total_points_cap() -> None:
    # Create a response with > 5000 total points across multiple series
    # 3 series * 2000 points each = 6000 total → truncated
    series = []
    for i in range(3):
        series.append(
            {
                "metric": {"instance": f"host{i}"},
                "values": [[float(t), str(t)] for t in range(2000)],
            }
        )
    responses.add(
        responses.GET,
        f"{API}/query_range",
        json={"status": "success", "data": {"resultType": "matrix", "result": series}},
        status=200,
    )
    result = prometheus_query_range(query="up", start="0", end="3600", step="1")
    data = result.structuredContent
    assert data["truncated"] is True
    assert data["total_points"] <= 5000


@responses.activate
def test_query_range_422_bad_data_raises_tool_error() -> None:
    responses.add(
        responses.GET,
        f"{API}/query_range",
        json={"status": "error", "errorType": "bad_data", "error": "exceeded maximum resolution"},
        status=422,
    )
    with pytest.raises(ToolError, match="422"):
        prometheus_query_range(query="up", start="0", end="1000000", step="0.001")


@responses.activate
def test_query_range_empty_result() -> None:
    responses.add(
        responses.GET,
        f"{API}/query_range",
        json={"status": "success", "data": {"resultType": "matrix", "result": []}},
        status=200,
    )
    result = prometheus_query_range(query="nonexistent", start="0", end="3600", step="60")
    data = result.structuredContent
    assert data["series_count"] == 0
    assert data["total_points"] == 0
    assert data["truncated"] is False


@responses.activate
def test_query_range_markdown_truncation_hint() -> None:
    series = [
        {"metric": {"instance": f"host{i}"}, "values": [[float(j), str(j)] for j in range(300)]} for i in range(20)
    ]
    responses.add(
        responses.GET,
        f"{API}/query_range",
        json={"status": "success", "data": {"resultType": "matrix", "result": series}},
        status=200,
    )
    result = prometheus_query_range(query="up", start="0", end="3600", step="1")
    md = result.content[0].text
    assert "capped at 5000" in md or "5000" in md


# ── prometheus_list_alerts ─────────────────────────────────────────────────


def _make_alert(name: str, state: str = "firing", severity: str = "critical") -> dict:
    return {
        "labels": {"alertname": name, "severity": severity, "job": "node"},
        "annotations": {"summary": f"{name} is {state}"},
        "state": state,
        "activeAt": "2024-01-15T10:00:00Z",
        "value": "1",
    }


@responses.activate
def test_list_alerts_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/alerts",
        json={
            "status": "success",
            "data": {
                "alerts": [
                    _make_alert("HighCPU", "firing"),
                    _make_alert("DiskFull", "pending"),
                ]
            },
        },
        status=200,
    )
    result = prometheus_list_alerts()
    data = result.structuredContent
    assert data["total_count"] == 2
    assert data["firing_count"] == 1
    assert data["pending_count"] == 1
    assert len(data["alerts"]) == 2
    assert data["alerts"][0]["labels"]["alertname"] == "HighCPU"
    assert data["alerts"][0]["state"] == "firing"


@responses.activate
def test_list_alerts_empty() -> None:
    responses.add(
        responses.GET,
        f"{API}/alerts",
        json={"status": "success", "data": {"alerts": []}},
        status=200,
    )
    result = prometheus_list_alerts()
    data = result.structuredContent
    assert data["total_count"] == 0
    assert data["firing_count"] == 0
    assert data["pending_count"] == 0
    md = result.content[0].text
    assert "No active alerts" in md


@responses.activate
def test_list_alerts_state_summary() -> None:
    alerts = [
        _make_alert("A1", "firing"),
        _make_alert("A2", "firing"),
        _make_alert("A3", "pending"),
    ]
    responses.add(
        responses.GET,
        f"{API}/alerts",
        json={"status": "success", "data": {"alerts": alerts}},
        status=200,
    )
    result = prometheus_list_alerts()
    data = result.structuredContent
    summary = {s["state"]: s["count"] for s in data["state_summary"]}
    assert summary["firing"] == 2
    assert summary["pending"] == 1


@responses.activate
def test_list_alerts_annotations_preserved() -> None:
    responses.add(
        responses.GET,
        f"{API}/alerts",
        json={
            "status": "success",
            "data": {"alerts": [_make_alert("Test", "firing")]},
        },
        status=200,
    )
    result = prometheus_list_alerts()
    data = result.structuredContent
    assert "summary" in data["alerts"][0]["annotations"]


@responses.activate
def test_list_alerts_401_raises_tool_error() -> None:
    responses.add(responses.GET, f"{API}/alerts", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_list_alerts()


@responses.activate
def test_list_alerts_markdown_shows_firing() -> None:
    responses.add(
        responses.GET,
        f"{API}/alerts",
        json={
            "status": "success",
            "data": {"alerts": [_make_alert("HighCPU", "firing", "critical")]},
        },
        status=200,
    )
    result = prometheus_list_alerts()
    md = result.content[0].text
    assert "HighCPU" in md
    assert "firing" in md


# ── prometheus_list_targets ────────────────────────────────────────────────


def _make_target(job: str, instance: str, health: str = "up", duration: float = 0.015, error: str = "") -> dict:
    return {
        "labels": {"job": job, "instance": instance},
        "health": health,
        "lastScrapeDuration": duration,
        "lastError": error,
        "scrapePool": job,
        "scrapeUrl": f"http://{instance}/metrics",
        "globalUrl": f"http://{instance}/metrics",
    }


@responses.activate
def test_list_targets_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/targets",
        json={
            "status": "success",
            "data": {
                "activeTargets": [
                    _make_target("prometheus", "localhost:9090", "up"),
                    _make_target("node", "host1:9100", "up"),
                    _make_target("node", "host2:9100", "down", error="connection refused"),
                ],
                "droppedTargets": [],
            },
        },
        status=200,
    )
    result = prometheus_list_targets()
    data = result.structuredContent
    assert data["total_count"] == 3
    assert data["up_count"] == 2
    assert data["down_count"] == 1
    assert data["state_filter"] == "active"


@responses.activate
def test_list_targets_job_summary() -> None:
    responses.add(
        responses.GET,
        f"{API}/targets",
        json={
            "status": "success",
            "data": {
                "activeTargets": [
                    _make_target("node", "host1:9100", "up"),
                    _make_target("node", "host2:9100", "down"),
                    _make_target("prometheus", "localhost:9090", "up"),
                ],
                "droppedTargets": [],
            },
        },
        status=200,
    )
    result = prometheus_list_targets()
    data = result.structuredContent
    job_map = {j["job"]: j for j in data["job_summary"]}
    assert job_map["node"]["total"] == 2
    assert job_map["node"]["up"] == 1
    assert job_map["node"]["down"] == 1
    assert job_map["prometheus"]["up"] == 1


@responses.activate
def test_list_targets_invalid_state_raises_tool_error() -> None:
    # state validation happens before HTTP call
    responses.add(responses.GET, f"{API}/targets", json={}, status=200)
    with pytest.raises(ToolError, match="state"):
        prometheus_list_targets(state="invalid")


@responses.activate
def test_list_targets_last_error_captured() -> None:
    responses.add(
        responses.GET,
        f"{API}/targets",
        json={
            "status": "success",
            "data": {
                "activeTargets": [_make_target("node", "host1:9100", "down", error="connection refused")],
                "droppedTargets": [],
            },
        },
        status=200,
    )
    result = prometheus_list_targets()
    data = result.structuredContent
    target = data["targets"][0]
    assert target["last_error"] == "connection refused"
    assert target["health"] == "down"


@responses.activate
def test_list_targets_scrape_duration_ms() -> None:
    responses.add(
        responses.GET,
        f"{API}/targets",
        json={
            "status": "success",
            "data": {
                "activeTargets": [_make_target("node", "host1:9100", "up", duration=0.025)],
                "droppedTargets": [],
            },
        },
        status=200,
    )
    result = prometheus_list_targets()
    target = result.structuredContent["targets"][0]
    assert abs(target["last_scrape_duration_ms"] - 25.0) < 0.01


@responses.activate
def test_list_targets_markdown_shows_down_targets() -> None:
    responses.add(
        responses.GET,
        f"{API}/targets",
        json={
            "status": "success",
            "data": {
                "activeTargets": [_make_target("node", "host1:9100", "down", error="timeout")],
                "droppedTargets": [],
            },
        },
        status=200,
    )
    result = prometheus_list_targets()
    md = result.content[0].text
    assert "Down Targets" in md
    assert "timeout" in md


@responses.activate
def test_list_targets_401_raises_tool_error() -> None:
    responses.add(responses.GET, f"{API}/targets", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_list_targets()


# ── prometheus_get_metric_metadata ─────────────────────────────────────────


@responses.activate
def test_metadata_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/metadata",
        json={
            "status": "success",
            "data": {
                "http_requests_total": [{"type": "counter", "help": "Total HTTP requests", "unit": ""}],
                "node_cpu_seconds_total": [{"type": "counter", "help": "CPU seconds", "unit": "seconds"}],
                "up": [{"type": "gauge", "help": "Target up/down", "unit": ""}],
            },
        },
        status=200,
    )
    result = prometheus_get_metric_metadata()
    data = result.structuredContent
    assert data["total_count"] == 3
    assert data["returned_count"] == 3
    assert data["truncated"] is False
    assert "http_requests_total" in data["metadata"]
    assert data["metadata"]["http_requests_total"][0]["type"] == "counter"
    assert data["metadata"]["http_requests_total"][0]["help"] == "Total HTTP requests"


@responses.activate
def test_metadata_with_metric_filter() -> None:
    responses.add(
        responses.GET,
        f"{API}/metadata",
        json={
            "status": "success",
            "data": {
                "http_requests_total": [{"type": "counter", "help": "Total HTTP requests", "unit": ""}],
            },
        },
        status=200,
    )
    result = prometheus_get_metric_metadata(metric="http_requests_total")
    data = result.structuredContent
    assert data["metric"] == "http_requests_total"
    assert data["returned_count"] == 1
    # Verify filter param forwarded
    assert "metric=http_requests_total" in responses.calls[0].request.url


@responses.activate
def test_metadata_empty_result() -> None:
    responses.add(
        responses.GET,
        f"{API}/metadata",
        json={"status": "success", "data": {}},
        status=200,
    )
    result = prometheus_get_metric_metadata()
    data = result.structuredContent
    assert data["total_count"] == 0
    assert data["returned_count"] == 0
    assert data["metadata"] == {}


@responses.activate
def test_metadata_401_raises_tool_error() -> None:
    responses.add(responses.GET, f"{API}/metadata", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_get_metric_metadata()


@responses.activate
def test_metadata_markdown_contains_table() -> None:
    responses.add(
        responses.GET,
        f"{API}/metadata",
        json={
            "status": "success",
            "data": {
                "up": [{"type": "gauge", "help": "Target health", "unit": ""}],
            },
        },
        status=200,
    )
    result = prometheus_get_metric_metadata()
    md = result.content[0].text
    assert "Metric Metadata" in md
    assert "`up`" in md
    assert "gauge" in md


# ── prometheus_list_label_values ───────────────────────────────────────────


@responses.activate
def test_label_values_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/job/values",
        json={"status": "success", "data": ["node-exporter", "prometheus", "grafana"]},
        status=200,
    )
    result = prometheus_list_label_values(label="job")
    data = result.structuredContent
    assert data["label"] == "job"
    assert data["total_count"] == 3
    assert data["returned_count"] == 3
    assert data["truncated"] is False
    assert data["values"] == ["grafana", "node-exporter", "prometheus"]  # sorted


@responses.activate
def test_label_values_with_match_filter() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/instance/values",
        json={"status": "success", "data": ["host1:9100", "host2:9100"]},
        status=200,
    )
    result = prometheus_list_label_values(label="instance", match='{job="node-exporter"}')
    data = result.structuredContent
    assert data["match"] == '{job="node-exporter"}'
    assert data["returned_count"] == 2
    # Verify match[] forwarded in URL
    assert "match%5B%5D" in responses.calls[0].request.url or "match[]" in responses.calls[0].request.url


@responses.activate
def test_label_values_empty_result() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/nonexistent/values",
        json={"status": "success", "data": []},
        status=200,
    )
    result = prometheus_list_label_values(label="nonexistent")
    data = result.structuredContent
    assert data["total_count"] == 0
    assert data["values"] == []


@responses.activate
def test_label_values_401_raises_tool_error() -> None:
    responses.add(responses.GET, f"{API}/label/job/values", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_list_label_values(label="job")


@responses.activate
def test_label_values_markdown_content() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/job/values",
        json={"status": "success", "data": ["node", "prom"]},
        status=200,
    )
    result = prometheus_list_label_values(label="job")
    md = result.content[0].text
    assert "Label Values" in md
    assert "`job`" in md
    assert "`node`" in md


# ── prometheus_list_rules ──────────────────────────────────────────────────


@responses.activate
def test_rules_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/rules",
        json={
            "status": "success",
            "data": {
                "groups": [
                    {
                        "name": "node_alerts",
                        "file": "/etc/prometheus/rules/node.yml",
                        "rules": [
                            {
                                "name": "NodeDown",
                                "query": "up{job='node'} == 0",
                                "type": "alerting",
                                "state": "firing",
                                "labels": {"severity": "critical"},
                                "health": "ok",
                            },
                            {
                                "name": "node:cpu:rate5m",
                                "query": "rate(node_cpu_seconds_total[5m])",
                                "type": "recording",
                                "labels": {},
                                "health": "ok",
                            },
                        ],
                    }
                ]
            },
        },
        status=200,
    )
    result = prometheus_list_rules()
    data = result.structuredContent
    assert data["total_groups"] == 1
    assert data["total_rules"] == 2
    assert data["recording_count"] == 1
    assert data["alerting_count"] == 1
    assert data["type_filter"] is None
    group = data["groups"][0]
    assert group["name"] == "node_alerts"
    assert group["rule_count"] == 2
    assert group["rules"][0]["name"] == "NodeDown"
    assert group["rules"][0]["state"] == "firing"
    assert group["rules"][1]["type"] == "recording"


@responses.activate
def test_rules_with_type_filter() -> None:
    responses.add(
        responses.GET,
        f"{API}/rules",
        json={
            "status": "success",
            "data": {
                "groups": [
                    {
                        "name": "alerts",
                        "file": "alerts.yml",
                        "rules": [
                            {
                                "name": "HighCPU",
                                "query": "cpu > 80",
                                "type": "alerting",
                                "state": "inactive",
                                "labels": {},
                                "health": "ok",
                            }
                        ],
                    }
                ]
            },
        },
        status=200,
    )
    result = prometheus_list_rules(type="alert")
    data = result.structuredContent
    assert data["type_filter"] == "alert"
    assert "type=alert" in responses.calls[0].request.url


@responses.activate
def test_rules_empty_result() -> None:
    responses.add(
        responses.GET,
        f"{API}/rules",
        json={"status": "success", "data": {"groups": []}},
        status=200,
    )
    result = prometheus_list_rules()
    data = result.structuredContent
    assert data["total_groups"] == 0
    assert data["total_rules"] == 0


@responses.activate
def test_rules_invalid_type_raises_tool_error() -> None:
    with pytest.raises(ToolError, match="type must be"):
        prometheus_list_rules(type="invalid")


@responses.activate
def test_rules_401_raises_tool_error() -> None:
    responses.add(responses.GET, f"{API}/rules", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_list_rules()


@responses.activate
def test_rules_markdown_content() -> None:
    responses.add(
        responses.GET,
        f"{API}/rules",
        json={
            "status": "success",
            "data": {
                "groups": [
                    {
                        "name": "test_group",
                        "file": "test.yml",
                        "rules": [
                            {
                                "name": "TestAlert",
                                "query": "up == 0",
                                "type": "alerting",
                                "state": "inactive",
                                "labels": {},
                                "health": "ok",
                            }
                        ],
                    }
                ]
            },
        },
        status=200,
    )
    result = prometheus_list_rules()
    md = result.content[0].text
    assert "Prometheus Rules" in md
    assert "test_group" in md
    assert "TestAlert" in md
