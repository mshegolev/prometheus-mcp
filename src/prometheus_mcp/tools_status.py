"""MCP tools for Prometheus status, health, and cardinality.

4 read-only tools for operational investigation:

- ``prometheus_health_check``      — liveness/readiness probe
- ``prometheus_get_cardinality``   — TSDB stats and top cardinality metrics
- ``prometheus_get_runtime_info``  — goroutines, retention, series count
- ``prometheus_get_build_info``    — Prometheus version, Go version
"""

from __future__ import annotations

from typing import Any

from prometheus_mcp import output
from prometheus_mcp._mcp import get_client, mcp
from prometheus_mcp.models import (
    BuildInfoOutput,
    CardinalityOutput,
    CardinalityTopItem,
    HealthCheckOutput,
    RuntimeInfoOutput,
)

_CARDINALITY_TOP_LIMIT = 20


# ── Health Check ──────────────────────────────────────────────────────────────


@mcp.tool(
    name="prometheus_health_check",
    annotations={
        "title": "Health Check",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_health_check(
    *,
    instance: str | None = None,
) -> HealthCheckOutput:
    """Check Prometheus liveness and readiness.

    Calls ``GET /-/healthy`` and ``GET /-/ready`` — management endpoints
    outside the ``/api/v1`` namespace. Returns whether each probe returned
    a 200 status code.

    Use this to verify Prometheus is actually running before investigating
    blank query results. A failed health check means Prometheus is down;
    a failed readiness check means it's starting up or shutting down.

    Examples:
        - Use when: "Why are all my queries returning empty results?"
          → check if Prometheus is healthy first.
        - Use when: Setting up a new MCP connection — verify the target
          is reachable and healthy.
        - Don't use when: You want metric values (call ``prometheus_query``).

    Returns:
        dict with ``healthy`` (bool), ``healthy_status_code``,
        ``ready`` (bool), ``ready_status_code``.
    """
    try:
        client = get_client(instance)

        # /-/healthy
        try:
            resp_healthy = client.get_raw("/-/healthy")
            healthy = resp_healthy.status_code == 200
            healthy_code = resp_healthy.status_code
        except Exception:
            healthy = False
            healthy_code = 0

        # /-/ready
        try:
            resp_ready = client.get_raw("/-/ready")
            ready = resp_ready.status_code == 200
            ready_code = resp_ready.status_code
        except Exception:
            ready = False
            ready_code = 0

        result: HealthCheckOutput = {
            "healthy": healthy,
            "healthy_status_code": healthy_code,
            "ready": ready,
            "ready_status_code": ready_code,
        }

        status_str = "healthy" if healthy else "**UNHEALTHY**"
        ready_str = "ready" if ready else "**NOT READY**"
        md = "## Prometheus Health Check\n\n"
        md += f"- **Healthy:** {status_str} (HTTP {healthy_code})\n"
        md += f"- **Ready:** {ready_str} (HTTP {ready_code})\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "checking Prometheus health")


# ── Cardinality ───────────────────────────────────────────────────────────────


@mcp.tool(
    name="prometheus_get_cardinality",
    annotations={
        "title": "Get Cardinality",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_get_cardinality(
    *,
    instance: str | None = None,
) -> CardinalityOutput:
    """Get TSDB statistics and cardinality data from Prometheus.

    Wraps ``GET /api/v1/status/tsdb``. Returns head stats (total series,
    chunks, time range) and top-N lists: metrics by series count, labels
    by value count, and labels by memory usage.

    Use this to investigate cardinality explosions — the #1 operational
    Prometheus problem. High series counts slow queries and increase memory.

    Examples:
        - Use when: "Why is Prometheus using so much memory?"
          → check ``num_series`` and ``top_metrics_by_series``.
        - Use when: "Which labels have the most values?"
          → check ``top_labels_by_value_count``.
        - Don't use when: You want current metric values
          (call ``prometheus_query``).

    Returns:
        dict with ``num_series`` / ``chunk_count`` / ``min_time`` / ``max_time`` /
        ``top_metrics_by_series`` / ``top_labels_by_value_count`` /
        ``top_labels_by_memory_bytes``.
    """
    try:
        client = get_client(instance)
        raw = client.get("/status/tsdb") or {}
        data: dict[str, Any] = raw.get("data") or {}
        head: dict[str, Any] = data.get("headStats") or {}

        def _top_items(key: str) -> list[CardinalityTopItem]:
            items: list[dict[str, Any]] = data.get(key) or []
            return [
                {"name": str(i.get("name", "")), "value": int(i.get("value", 0))}
                for i in items[:_CARDINALITY_TOP_LIMIT]
            ]

        result: CardinalityOutput = {
            "num_series": int(head.get("numSeries", 0)),
            "num_label_pairs": int(head.get("numLabelPairs", 0)),
            "chunk_count": int(head.get("chunkCount", 0)),
            "min_time": int(head.get("minTime", 0)),
            "max_time": int(head.get("maxTime", 0)),
            "top_metrics_by_series": _top_items("seriesCountByMetricName"),
            "top_labels_by_value_count": _top_items("labelValueCountByLabelName"),
            "top_labels_by_memory_bytes": _top_items("memoryInBytesByLabelName"),
        }

        md = "## TSDB Cardinality Statistics\n\n"
        md += f"- **Total series:** {result['num_series']:,}\n"
        md += f"- **Chunks:** {result['chunk_count']:,}\n"
        md += f"- **Label pairs:** {result['num_label_pairs']:,}\n\n"

        if result["top_metrics_by_series"]:
            md += "### Top Metrics by Series Count\n\n"
            md += "| Metric | Series |\n|--------|--------|\n"
            for item in result["top_metrics_by_series"][:10]:
                md += f"| `{item['name']}` | {item['value']:,} |\n"
            md += "\n"

        if result["top_labels_by_value_count"]:
            md += "### Top Labels by Value Count\n\n"
            md += "| Label | Values |\n|-------|--------|\n"
            for item in result["top_labels_by_value_count"][:10]:
                md += f"| `{item['name']}` | {item['value']:,} |\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "fetching TSDB cardinality statistics")


# ── Runtime Info ──────────────────────────────────────────────────────────────


@mcp.tool(
    name="prometheus_get_runtime_info",
    annotations={
        "title": "Runtime Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_get_runtime_info(
    *,
    instance: str | None = None,
) -> RuntimeInfoOutput:
    """Get Prometheus runtime information.

    Wraps ``GET /api/v1/status/runtimeinfo``. Returns operational data:
    goroutine count, time series count, storage retention policy,
    start time, corruption count, and config reload status.

    Examples:
        - Use when: "Why is Prometheus slow?" → check goroutine count
          and time series count.
        - Use when: "What's the retention policy?" → check ``storage_retention``.
        - Don't use when: You want the Prometheus version
          (call ``prometheus_get_build_info``).

    Returns:
        dict with ``start_time`` / ``goroutine_count`` / ``time_series_count`` /
        ``storage_retention`` / ``corruptionCount`` / ``reloadConfigSuccess`` /
        ``lastConfigTime``.
    """
    try:
        client = get_client(instance)
        raw = client.get("/status/runtimeinfo") or {}
        data: dict[str, Any] = raw.get("data") or {}

        result: RuntimeInfoOutput = {
            "start_time": str(data.get("startTime", "")),
            "goroutine_count": int(data.get("goroutineCount", 0)),
            "time_series_count": int(data.get("timeSeriesCount", 0)),
            "storage_retention": str(data.get("storageRetention", "")),
            "corruptionCount": int(data.get("corruptionCount", 0)),
            "reloadConfigSuccess": bool(data.get("reloadConfigSuccess", False)),
            "lastConfigTime": str(data.get("lastConfigTime", "")),
        }

        md = "## Prometheus Runtime Info\n\n"
        md += f"- **Start time:** {result['start_time']}\n"
        md += f"- **Goroutines:** {result['goroutine_count']:,}\n"
        md += f"- **Time series:** {result['time_series_count']:,}\n"
        md += f"- **Storage retention:** {result['storage_retention']}\n"
        md += f"- **Corruption count:** {result['corruptionCount']}\n"
        md += f"- **Config reload:** {'success' if result['reloadConfigSuccess'] else 'failed'}\n"
        md += f"- **Last config time:** {result['lastConfigTime']}\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "fetching Prometheus runtime info")


# ── Build Info ────────────────────────────────────────────────────────────────


@mcp.tool(
    name="prometheus_get_build_info",
    annotations={
        "title": "Build Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_get_build_info(
    *,
    instance: str | None = None,
) -> BuildInfoOutput:
    """Get Prometheus build information.

    Wraps ``GET /api/v1/status/buildinfo``. Returns version, Go version,
    Git revision, branch, build user, and build date.

    Examples:
        - Use when: "What version of Prometheus is running?" → check ``version``.
        - Use when: Debugging version-specific behavior.
        - Don't use when: You want runtime stats
          (call ``prometheus_get_runtime_info``).

    Returns:
        dict with ``version`` / ``revision`` / ``branch`` / ``buildUser`` /
        ``buildDate`` / ``goVersion``.
    """
    try:
        client = get_client(instance)
        raw = client.get("/status/buildinfo") or {}
        data: dict[str, Any] = raw.get("data") or {}

        result: BuildInfoOutput = {
            "version": str(data.get("version", "")),
            "revision": str(data.get("revision", "")),
            "branch": str(data.get("branch", "")),
            "buildUser": str(data.get("buildUser", "")),
            "buildDate": str(data.get("buildDate", "")),
            "goVersion": str(data.get("goVersion", "")),
        }

        md = "## Prometheus Build Info\n\n"
        md += f"- **Version:** {result['version']}\n"
        md += f"- **Go version:** {result['goVersion']}\n"
        md += f"- **Revision:** {result['revision']}\n"
        md += f"- **Branch:** {result['branch']}\n"
        md += f"- **Build date:** {result['buildDate']}\n"
        md += f"- **Build user:** {result['buildUser']}\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "fetching Prometheus build info")
