"""Unit tests for real service-dependency mapping (v5.0 Phase 14, DEP-R01/R02).

Every test drives the mapper/tool against a mocked ``PrometheusClient`` whose
``get('/query_range', ...)`` returns Prometheus matrix JSON — no live server,
no simulated data paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from prometheus_mcp.dependency_map import (
    DependencyMapError,
    ServiceDependencyMapper,
    _build_selector,
    _mean_and_count,
    _parse_window_seconds,
)


def _matrix(*series: dict) -> dict:
    """Wrap raw series dicts in a Prometheus query_range matrix envelope."""
    return {"status": "success", "data": {"resultType": "matrix", "result": list(series)}}


def _series(labels: dict, values: list) -> dict:
    return {"metric": labels, "values": values}


# ── helper-level tests ───────────────────────────────────────────────────────


def test_mean_and_count_ignores_bad_and_nonfinite_points() -> None:
    mean, count = _mean_and_count([["1", "2"], ["2", "4"], ["3", "notafloat"], ["4", "NaN"], ["5", "Inf"]])
    assert count == 2
    assert mean == pytest.approx(3.0)


def test_mean_and_count_empty() -> None:
    assert _mean_and_count([]) == (0.0, 0)


def test_build_selector_escapes_injection() -> None:
    sel = _build_selector({"ns": 'prod"} or up{'})
    # The double-quote must be escaped so it cannot terminate the literal.
    assert '\\"' in sel
    assert sel.startswith("{ns=")


def test_build_selector_rejects_bad_label_name() -> None:
    with pytest.raises(DependencyMapError):
        _build_selector({"bad-label": "x"})


def test_build_selector_appends_extra() -> None:
    sel = _build_selector({"ns": "prod"}, extra='code=~"5.."')
    assert sel == '{ns="prod",code=~"5.."}'


def test_parse_window_seconds() -> None:
    assert _parse_window_seconds("5m") == 300.0
    assert _parse_window_seconds("2h") == 7200.0
    assert _parse_window_seconds("garbage") == 300.0  # safe fallback


# ── mapper: graph construction ────────────────────────────────────────────────


def test_map_dependencies_builds_graph_from_real_series() -> None:
    client = MagicMock()
    client.get.return_value = _matrix(
        _series({"source_workload": "frontend", "destination_workload": "api"}, [["1", "10"], ["2", "20"]]),
        _series({"source_workload": "api", "destination_workload": "db"}, [["1", "5"], ["2", "5"]]),
    )
    mapper = ServiceDependencyMapper(client)
    result = mapper.map_dependencies(
        metric="istio_requests_total",
        source_label="source_workload",
        destination_label="destination_workload",
        time_window="5m",
        step="1m",
    )

    assert result["node_count"] == 3
    assert result["edge_count"] == 2
    # Sorted by throughput desc: frontend→api (mean 15) before api→db (mean 5).
    assert (result["edges"][0]["source"], result["edges"][0]["target"]) == ("frontend", "api")
    assert result["edges"][0]["throughput"] == pytest.approx(15.0)
    assert result["edges"][0]["sample_count"] == 2
    assert result["edges"][0]["error_rate"] is None

    node_ids = {n["service_id"] for n in result["nodes"]}
    assert node_ids == {"frontend", "api", "db"}
    api = next(n for n in result["nodes"] if n["service_id"] == "api")
    assert api["in_degree"] == 1 and api["out_degree"] == 1


def test_map_dependencies_uses_query_range_with_aggregation() -> None:
    client = MagicMock()
    client.get.return_value = _matrix()
    mapper = ServiceDependencyMapper(client)
    mapper.map_dependencies(
        metric="istio_requests_total",
        source_label="source_workload",
        destination_label="destination_workload",
        time_window="10m",
        step="30s",
    )
    endpoint, kwargs = client.get.call_args[0][0], client.get.call_args.kwargs
    assert endpoint == "/query_range"
    q = kwargs["params"]["query"]
    assert q == "sum by (source_workload, destination_workload) (rate(istio_requests_total[10m]))"
    assert kwargs["params"]["step"] == "30s"


def test_map_dependencies_skips_series_missing_endpoints() -> None:
    client = MagicMock()
    client.get.return_value = _matrix(
        _series({"source_workload": "a", "destination_workload": "b"}, [["1", "3"]]),
        _series({"source_workload": "a"}, [["1", "9"]]),  # no destination → skipped
        _series({"destination_workload": "z"}, [["1", "9"]]),  # no source → skipped
    )
    mapper = ServiceDependencyMapper(client)
    result = mapper.map_dependencies(
        metric="reqs_total",
        source_label="source_workload",
        destination_label="destination_workload",
        time_window="5m",
        step="1m",
    )
    assert result["edge_count"] == 1
    assert (result["edges"][0]["source"], result["edges"][0]["target"]) == ("a", "b")


def test_map_dependencies_computes_error_rate_with_second_query() -> None:
    client = MagicMock()
    total = _matrix(_series({"source_workload": "a", "destination_workload": "b"}, [["1", "100"]]))
    errors = _matrix(_series({"source_workload": "a", "destination_workload": "b"}, [["1", "10"]]))
    client.get.side_effect = [total, errors]

    mapper = ServiceDependencyMapper(client)
    result = mapper.map_dependencies(
        metric="reqs_total",
        source_label="source_workload",
        destination_label="destination_workload",
        time_window="5m",
        step="1m",
        error_matcher='code=~"5.."',
    )
    assert client.get.call_count == 2
    # Second query folds the error selector into the metric selector.
    second_query = client.get.call_args_list[1][1]["params"]["query"]
    assert 'code=~"5.."' in second_query
    assert result["edges"][0]["error_rate"] == pytest.approx(0.10)


def test_map_dependencies_error_rate_capped_at_one() -> None:
    client = MagicMock()
    total = _matrix(_series({"source_workload": "a", "destination_workload": "b"}, [["1", "5"]]))
    errors = _matrix(_series({"source_workload": "a", "destination_workload": "b"}, [["1", "50"]]))
    client.get.side_effect = [total, errors]
    mapper = ServiceDependencyMapper(client)
    result = mapper.map_dependencies(
        metric="reqs_total",
        source_label="source_workload",
        destination_label="destination_workload",
        time_window="5m",
        step="1m",
        error_matcher='code="500"',
    )
    assert result["edges"][0]["error_rate"] == 1.0


def test_map_dependencies_applies_matchers() -> None:
    client = MagicMock()
    client.get.return_value = _matrix()
    mapper = ServiceDependencyMapper(client)
    mapper.map_dependencies(
        metric="reqs_total",
        source_label="source",
        destination_label="destination",
        time_window="5m",
        step="1m",
        matchers={"namespace": "prod"},
    )
    query = client.get.call_args.kwargs["params"]["query"]
    assert query == 'sum by (source, destination) (rate(reqs_total{namespace="prod"}[5m]))'


def test_map_dependencies_empty_result() -> None:
    client = MagicMock()
    client.get.return_value = _matrix()
    mapper = ServiceDependencyMapper(client)
    result = mapper.map_dependencies(
        metric="reqs_total",
        source_label="source",
        destination_label="destination",
        time_window="5m",
        step="1m",
    )
    assert result["node_count"] == 0
    assert result["edge_count"] == 0
    assert result["nodes"] == []
    assert result["edges"] == []


def test_map_dependencies_rejects_bad_metric_name() -> None:
    mapper = ServiceDependencyMapper(MagicMock())
    with pytest.raises(DependencyMapError):
        mapper.map_dependencies(
            metric="bad name!",
            source_label="source",
            destination_label="destination",
            time_window="5m",
            step="1m",
        )


# ── tool: dual-channel output + registry wiring ───────────────────────────────


class _RegistryPatch:
    """Install a mock registry on the live _mcp global for the tool path."""

    def __init__(self, client: MagicMock) -> None:
        self.client = client

    def __enter__(self):
        import prometheus_mcp._mcp as mcp_mod

        self._orig = mcp_mod._registry
        registry = MagicMock()
        registry.get_prometheus_client.return_value = self.client
        mcp_mod._registry = registry
        return self

    def __exit__(self, *exc):
        import prometheus_mcp._mcp as mcp_mod

        mcp_mod._registry = self._orig


def test_tool_returns_dual_channel_result() -> None:
    from prometheus_mcp.tools_dependency import prometheus_map_service_dependencies

    client = MagicMock()
    client.get.return_value = _matrix(
        _series({"source_workload": "frontend", "destination_workload": "api"}, [["1", "12"]]),
    )
    with _RegistryPatch(client):
        res = prometheus_map_service_dependencies(
            metric="istio_requests_total",
            time_window="5m",
            step="1m",
        )

    # Structured channel.
    assert res.structuredContent["edge_count"] == 1
    assert res.structuredContent["edges"][0]["source"] == "frontend"
    # Markdown channel.
    text = res.content[0].text
    assert "Service Dependency Map" in text
    assert "frontend" in text and "api" in text


def test_tool_wraps_bad_metric_as_toolerror() -> None:
    from prometheus_mcp.tools_dependency import prometheus_map_service_dependencies

    client = MagicMock()
    with _RegistryPatch(client), pytest.raises(ToolError):
        prometheus_map_service_dependencies(metric="oops space")
