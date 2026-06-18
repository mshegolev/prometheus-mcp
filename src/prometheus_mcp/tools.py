"""MCP tools for Prometheus metrics and observability.

5 read-only tools covering the Prometheus HTTP API v1 surface most useful to
an agent monitoring, debugging, or exploring a Prometheus instance:

- ``prometheus_list_metrics``   — discover metric names with optional filter
- ``prometheus_query``          — instant PromQL query
- ``prometheus_query_range``    — range PromQL query returning time-series
- ``prometheus_list_alerts``    — list active/pending alerts
- ``prometheus_list_targets``   — list scrape targets by health and job

**Threading model.** All tools are synchronous ``def``. FastMCP runs them
in a worker thread via ``anyio.to_thread.run_sync``, so blocking HTTP
calls don't block the asyncio event loop.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Any

from pydantic import Field

from prometheus_mcp import output
from prometheus_mcp._mcp import get_client, mcp
from prometheus_mcp.cache import get_metrics_cache
from prometheus_mcp.models import (
    AlertItem,
    AlertStateSummary,
    GetMetricMetadataOutput,
    InstantSample,
    ListAlertsOutput,
    ListLabelValuesOutput,
    ListMetricsOutput,
    ListRulesOutput,
    ListTargetsOutput,
    MetadataEntry,
    QueryOutput,
    QueryRangeOutput,
    RangeSeries,
    RuleGroupItem,
    RuleItem,
    TargetItem,
    TargetJobSummary,
)

_METRICS_CAP = 500
_RANGE_POINTS_CAP = 5000
_MD_ITEM_LIMIT = 20


# ── Helpers ────────────────────────────────────────────────────────────────


def _truncation_hint(total: int, shown: int, noun: str) -> str:
    """Return a markdown truncation hint when items are capped."""
    return f"\n\n_Showing first {shown} of {total} {noun} — see the structured content for the full list._"


def _format_value(val: Any) -> str:
    """Convert a Prometheus sample value to string."""
    if val is None:
        return ""
    return str(val)


def _shape_instant_sample(item: Any) -> InstantSample:
    """Convert a Prometheus instant vector/scalar result item into :class:`InstantSample`."""
    if isinstance(item, dict):
        metric = item.get("metric") or {}
        value = item.get("value") or [0, ""]
        ts = float(value[0]) if len(value) > 0 else 0.0
        v = _format_value(value[1]) if len(value) > 1 else ""
        return {
            "labels": {k: str(v2) for k, v2 in metric.items()},
            "timestamp": ts,
            "value": v,
        }
    # scalar: [timestamp, value]
    if isinstance(item, list) and len(item) == 2:
        return {
            "labels": {},
            "timestamp": float(item[0]),
            "value": _format_value(item[1]),
        }
    return {"labels": {}, "timestamp": 0.0, "value": _format_value(item)}


def _shape_range_series(item: dict[str, Any]) -> RangeSeries:
    """Convert a Prometheus range vector result item into :class:`RangeSeries`."""
    metric = item.get("metric") or {}
    values = item.get("values") or []
    # Each value: [timestamp (float), value (str)]
    shaped: list[list[float | str]] = []
    for v in values:
        if isinstance(v, list) and len(v) == 2:
            shaped.append([float(v[0]), str(v[1])])
        else:
            shaped.append([0.0, str(v)])
    return {
        "labels": {k: str(mv) for k, mv in metric.items()},
        "point_count": len(shaped),
        "values": shaped,
    }


# ── Tools ──────────────────────────────────────────────────────────────────


@mcp.tool(
    name="prometheus_list_metrics",
    annotations={
        "title": "List Metrics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_list_metrics(
    pattern: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
            description=(
                "Optional substring filter applied case-insensitively to metric names. "
                "Example: 'http' returns all metrics containing 'http' in their name. "
                "Leave empty to list all metrics (capped at 500)."
            ),
        ),
    ] = None,
    *,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description="Target instance name (omit for default instance)",
        ),
    ] = None,
) -> ListMetricsOutput:
    """List all metric names known to Prometheus, with optional substring filter.

    Wraps ``GET /api/v1/label/__name__/values``. Prometheus returns all metric
    names at once — no pagination. Output is capped at 500 metrics after filtering,
    with a truncation hint when more exist.

    Use this first to discover valid metric names before writing PromQL
    expressions for ``prometheus_query`` or ``prometheus_query_range``.

    Examples:
        - Use when: "What metrics does Prometheus have about HTTP requests?"
          → ``pattern='http'``; read the ``metrics`` list.
        - Use when: "List all node_exporter metrics"
          → ``pattern='node_'``.
        - Use when: Starting a monitoring investigation — list metrics first
          to discover what's instrumented, then query specific ones.
        - Don't use when: You already know the exact metric name and want to
          query its value (call ``prometheus_query`` directly — one fewer round trip).
        - Don't use when: You want to see current alert state
          (call ``prometheus_list_alerts``).

    Returns:
        dict with ``total_count`` / ``returned_count`` / ``truncated`` /
        ``pattern`` / ``metrics`` (sorted list).
    """
    try:
        cache = get_metrics_cache()
        cache_key = "__name__values"
        cached = cache.get(cache_key)
        if cached is not None:
            raw: list[str] = cached
        else:
            client = get_client(instance)
            data = client.get("/label/__name__/values") or {}
            raw = data.get("data") or []
            cache.set(cache_key, raw)

        # Apply pattern filter
        if pattern:
            pat_lower = pattern.lower()
            filtered = [m for m in raw if pat_lower in m.lower()]
        else:
            filtered = list(raw)

        total_count = len(filtered)
        truncated = total_count > _METRICS_CAP
        metrics = sorted(filtered[:_METRICS_CAP])

        result: ListMetricsOutput = {
            "total_count": total_count,
            "returned_count": len(metrics),
            "truncated": truncated,
            "pattern": pattern,
            "metrics": metrics,
        }

        suffix = " — truncated at 500" if truncated else ""
        header = f"## Prometheus Metrics ({len(metrics)} shown{suffix})"
        if pattern:
            header += f" matching `{pattern}`"
        md = header + "\n\n"
        md_metrics = metrics[:_MD_ITEM_LIMIT]
        md += "\n".join(f"- `{m}`" for m in md_metrics)
        if len(metrics) > _MD_ITEM_LIMIT:
            md += _truncation_hint(len(metrics), _MD_ITEM_LIMIT, "metrics")
        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "listing Prometheus metrics")


@mcp.tool(
    name="prometheus_query",
    annotations={
        "title": "Instant Query",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_query(
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=2000,
            description=(
                "PromQL expression to evaluate. "
                "Examples: 'up', 'rate(http_requests_total[5m])', "
                "'sum(rate(http_requests_total[5m])) by (job)'."
            ),
        ),
    ],
    time: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
            description=(
                "Evaluation timestamp (optional). RFC3339 (e.g. '2024-01-15T10:00:00Z') "
                "or Unix timestamp (e.g. '1705312800'). Defaults to now."
            ),
        ),
    ] = None,
    *,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description="Target instance name (omit for default instance)",
        ),
    ] = None,
) -> QueryOutput:
    """Execute an instant PromQL query against Prometheus.

    Wraps ``GET /api/v1/query``. Returns the result type (vector, scalar,
    matrix, string) and a list of samples each carrying labels, timestamp,
    and value. For ``vector`` results each element is one time series at the
    evaluation instant.

    Examples:
        - Use when: "Is the payment service up right now?"
          → ``query='up{job="payment-service"}'``.
        - Use when: "What is the current HTTP request rate?"
          → ``query='sum(rate(http_requests_total[5m])) by (job)'``.
        - Use when: "Show me all metrics for a specific instance"
          → ``query='{instance="localhost:9090"}'``.
        - Don't use when: You want to see how a metric changed over time
          (call ``prometheus_query_range`` with start/end/step).
        - Don't use when: You don't know the metric name yet
          (call ``prometheus_list_metrics`` first to discover names).

    Returns:
        dict with ``query`` / ``time`` / ``result_type`` / ``result_count`` /
        ``data`` (list of samples with ``labels``, ``timestamp``, ``value``).
    """
    try:
        client = get_client(instance)
        params: dict[str, Any] = {"query": query}
        if time is not None:
            params["time"] = time

        raw = client.get("/query", params=params) or {}
        result_data = raw.get("data") or {}
        result_type: str = result_data.get("resultType", "vector")
        raw_result: list[Any] = result_data.get("result") or []

        # Normalise all result types to list[InstantSample]
        if result_type == "scalar":
            # scalar: [timestamp, value]
            samples: list[InstantSample] = [_shape_instant_sample(raw_result)]
        elif result_type == "string":
            samples = [{"labels": {}, "timestamp": 0.0, "value": str(raw_result)}]
        else:
            # vector or matrix (treat matrix rows as individual items)
            samples = [_shape_instant_sample(item) for item in raw_result]

        result: QueryOutput = {
            "query": query,
            "time": time,
            "result_type": result_type,
            "result_count": len(samples),
            "data": samples,
        }

        md = f"## Query: `{query}`\n\n"
        md += f"**Result type:** {result_type} | **Samples:** {len(samples)}\n\n"
        md_samples = samples[:_MD_ITEM_LIMIT]
        for s in md_samples:
            label_str = ", ".join(f'{k}="{v}"' for k, v in s["labels"].items()) if s["labels"] else "(no labels)"
            md += f"- `{label_str}` → **{s['value']}**\n"
        if len(samples) > _MD_ITEM_LIMIT:
            md += _truncation_hint(len(samples), _MD_ITEM_LIMIT, "samples")
        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, f"executing instant query {query!r}")


@mcp.tool(
    name="prometheus_query_range",
    annotations={
        "title": "Range Query",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_query_range(
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=2000,
            description=(
                "PromQL expression to evaluate over a time range. "
                "Examples: 'rate(http_requests_total[5m])', "
                "'node_cpu_seconds_total{mode=\"idle\"}'."
            ),
        ),
    ],
    start: Annotated[
        str,
        Field(
            min_length=1,
            max_length=50,
            description=(
                "Start of range. RFC3339 (e.g. '2024-01-15T10:00:00Z') or Unix timestamp (e.g. '1705312800')."
            ),
        ),
    ],
    end: Annotated[
        str,
        Field(
            min_length=1,
            max_length=50,
            description=("End of range. RFC3339 (e.g. '2024-01-15T11:00:00Z') or Unix timestamp (e.g. '1705316400')."),
        ),
    ],
    step: Annotated[
        str,
        Field(
            min_length=1,
            max_length=20,
            description=(
                "Query resolution step. Duration string (e.g. '15s', '1m', '5m') "
                "or float seconds (e.g. '30'). "
                "Prometheus rejects steps that produce more than 11,000 data points per series."
            ),
        ),
    ],
    *,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description="Target instance name (omit for default instance)",
        ),
    ] = None,
) -> QueryRangeOutput:
    """Execute a PromQL range query returning time-series data points.

    Wraps ``GET /api/v1/query_range``. Returns one series per matching time
    series, each with labels and a list of ``[timestamp, value]`` pairs.
    Total points across all series are capped at 5000 with a truncation hint.

    Prometheus may reject the query with HTTP 422 (bad_data) if the step
    produces too many data points (> 11,000 per series). Increase the step
    or narrow the time range if this happens.

    Note: The Prometheus API does not support filtering by branch or commit
    in this endpoint — filters are expressed purely in PromQL label matchers.

    Examples:
        - Use when: "Show me CPU usage over the last hour with 1-minute resolution"
          → ``query='rate(node_cpu_seconds_total[5m])'``, ``step='1m'``.
        - Use when: "Graph HTTP error rate for the last 24 hours"
          → ``query='rate(http_requests_total{status=~"5.."}[5m])'``,
          ``start='2024-01-15T00:00:00Z'``, ``end='2024-01-16T00:00:00Z'``,
          ``step='5m'``.
        - Use when: Investigating a past incident — pick the time window of the
          incident and use a fine step.
        - Don't use when: You only want the current value
          (call ``prometheus_query`` — faster and simpler).
        - Don't use when: You want alert history (call ``prometheus_list_alerts``).

    Returns:
        dict with ``query`` / ``start`` / ``end`` / ``step`` / ``result_type`` /
        ``series_count`` / ``total_points`` / ``truncated`` /
        ``data`` (list of series with ``labels``, ``point_count``, ``values``).
    """
    try:
        client = get_client(instance)
        params: dict[str, Any] = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }

        raw = client.get("/query_range", params=params) or {}
        result_data = raw.get("data") or {}
        result_type: str = result_data.get("resultType", "matrix")
        raw_result: list[dict[str, Any]] = result_data.get("result") or []

        series: list[RangeSeries] = [_shape_range_series(item) for item in raw_result]

        # Count total points and enforce cap
        total_points = sum(s["point_count"] for s in series)
        truncated = total_points > _RANGE_POINTS_CAP

        if truncated:
            # Downsample: keep only the first _RANGE_POINTS_CAP points across series in order
            kept: list[RangeSeries] = []
            remaining = _RANGE_POINTS_CAP
            for s in series:
                if remaining <= 0:
                    break
                take = min(s["point_count"], remaining)
                kept.append(
                    {
                        "labels": s["labels"],
                        "point_count": take,
                        "values": s["values"][:take],
                    }
                )
                remaining -= take
            series = kept

        result: QueryRangeOutput = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
            "result_type": result_type,
            "series_count": len(series),
            "total_points": min(total_points, _RANGE_POINTS_CAP) if truncated else total_points,
            "truncated": truncated,
            "data": series,
        }

        md = f"## Range Query: `{query}`\n\n"
        md += f"**Period:** {start} → {end} (step: {step})\n"
        md += f"**Series:** {len(series)} | **Points:** {result['total_points']}"
        if truncated:
            md += f" (capped at {_RANGE_POINTS_CAP})"
        md += "\n\n"
        md_series = series[:_MD_ITEM_LIMIT]
        for s in md_series:
            label_str = ", ".join(f'{k}="{v}"' for k, v in s["labels"].items()) if s["labels"] else "(no labels)"
            first_val = s["values"][0][1] if s["values"] else "—"
            last_val = s["values"][-1][1] if s["values"] else "—"
            md += f"- `{label_str}` — {s['point_count']} points, first={first_val}, last={last_val}\n"
        if len(series) > _MD_ITEM_LIMIT:
            md += _truncation_hint(len(series), _MD_ITEM_LIMIT, "series")
        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, f"executing range query {query!r}")


@mcp.tool(
    name="prometheus_list_alerts",
    annotations={
        "title": "List Alerts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_list_alerts(
    *,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description="Target instance name (omit for default instance)",
        ),
    ] = None,
) -> ListAlertsOutput:
    """List all active and pending alerts from Prometheus.

    Wraps ``GET /api/v1/alerts``. Returns every alert that Prometheus currently
    tracks, with labels (including ``alertname``, ``severity``), state
    (``firing`` / ``pending``), the time it became active, and its current value.
    Also returns a summary grouped by state and a count by severity label.

    Examples:
        - Use when: "Are there any firing alerts right now?"
          → check ``firing_count`` and ``alerts`` where ``state='firing'``.
        - Use when: "Show me all critical alerts"
          → filter ``alerts`` by ``labels.severity == 'critical'``.
        - Use when: Checking system health during an incident — list alerts
          first to understand what's firing before querying metrics.
        - Don't use when: You want historical alert data (Prometheus stores only
          current state; use Alertmanager or a recording rule for history).
        - Don't use when: You want raw metric values
          (call ``prometheus_query`` or ``prometheus_query_range``).

    Returns:
        dict with ``total_count`` / ``firing_count`` / ``pending_count`` /
        ``state_summary`` / ``alerts`` (list with ``labels``, ``annotations``,
        ``state``, ``active_at``, ``value``).
    """
    try:
        client = get_client(instance)
        raw = client.get("/alerts") or {}
        alerts_data: list[dict[str, Any]] = (raw.get("data") or {}).get("alerts") or []

        alerts: list[AlertItem] = []
        for a in alerts_data:
            alerts.append(
                {
                    "labels": {k: str(v) for k, v in (a.get("labels") or {}).items()},
                    "annotations": {k: str(v) for k, v in (a.get("annotations") or {}).items()},
                    "state": str(a.get("state", "")),
                    "active_at": str(a.get("activeAt", "")),
                    "value": str(a.get("value", "")),
                }
            )

        firing_count = sum(1 for a in alerts if a["state"] == "firing")
        pending_count = sum(1 for a in alerts if a["state"] == "pending")

        # Group summary by state
        state_counts: dict[str, int] = defaultdict(int)
        for a in alerts:
            state_counts[a["state"]] += 1
        state_summary: list[AlertStateSummary] = [
            {"state": state, "count": count} for state, count in sorted(state_counts.items())
        ]

        result: ListAlertsOutput = {
            "total_count": len(alerts),
            "firing_count": firing_count,
            "pending_count": pending_count,
            "state_summary": state_summary,
            "alerts": alerts,
        }

        md = f"## Prometheus Alerts ({len(alerts)} total)\n\n"
        md += f"- **Firing:** {firing_count}\n- **Pending:** {pending_count}\n\n"

        if not alerts:
            md += "_No active alerts._\n"
        else:
            md += "### Alert List\n\n"
            md_alerts = alerts[:_MD_ITEM_LIMIT]
            for a in md_alerts:
                name = a["labels"].get("alertname", "(unknown)")
                severity = a["labels"].get("severity", "")
                sev_str = f" [{severity}]" if severity else ""
                md += f"- **{name}**{sev_str} — `{a['state']}` since {a['active_at']}\n"
            if len(alerts) > _MD_ITEM_LIMIT:
                md += _truncation_hint(len(alerts), _MD_ITEM_LIMIT, "alerts")

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "listing Prometheus alerts")


@mcp.tool(
    name="prometheus_list_targets",
    annotations={
        "title": "List Targets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_list_targets(
    state: Annotated[
        str,
        Field(
            default="active",
            description=(
                "Filter targets by state: 'active' (default, scrape targets Prometheus is scraping), "
                "'dropped' (targets that were dropped by relabelling), "
                "or 'any' (all targets regardless of state)."
            ),
        ),
    ] = "active",
    *,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description="Target instance name (omit for default instance)",
        ),
    ] = None,
) -> ListTargetsOutput:
    """List Prometheus scrape targets, summarised by job and health.

    Wraps ``GET /api/v1/targets``. Returns scrape targets with job name,
    instance address, health status (``up`` / ``down`` / ``unknown``),
    last scrape duration in milliseconds, and any last error. Also returns
    a summary grouped by job and health state.

    Examples:
        - Use when: "Which targets are currently down?"
          → filter ``targets`` where ``health='down'`` and check ``last_error``.
        - Use when: "How many instances of the 'node-exporter' job are up?"
          → check ``job_summary`` for the 'node-exporter' entry.
        - Use when: Investigating a scrape failure — list targets for the
          affected job to see which instances have errors.
        - Don't use when: You want metric values from a target
          (call ``prometheus_query`` with label matchers instead).
        - Don't use when: You want alert status
          (call ``prometheus_list_alerts`` instead).

    Returns:
        dict with ``state_filter`` / ``total_count`` / ``up_count`` /
        ``down_count`` / ``unknown_count`` / ``job_summary`` (per-job health counts) /
        ``targets`` (list with ``job``, ``instance``, ``health``,
        ``last_scrape_duration_ms``, ``last_error``, ``labels``).
    """
    try:
        if state not in ("active", "dropped", "any"):
            raise ValueError(
                f"state must be 'active', 'dropped', or 'any' (got: {state!r}). "
                "Use 'active' for targets currently being scraped, "
                "'dropped' for targets dropped by relabelling, or 'any' for all."
            )

        client = get_client(instance)
        params: dict[str, Any] = {"state": state}
        raw = client.get("/targets", params=params) or {}
        targets_data = raw.get("data") or {}

        active_raw: list[dict[str, Any]] = targets_data.get("activeTargets") or []
        dropped_raw: list[dict[str, Any]] = targets_data.get("droppedTargets") or []

        # Which set to iterate based on state filter
        if state == "dropped":
            items_raw = dropped_raw
        elif state == "active":
            items_raw = active_raw
        else:
            items_raw = active_raw + dropped_raw

        targets: list[TargetItem] = []
        for t in items_raw:
            labels = t.get("labels") or {}
            job = str(labels.get("job", t.get("job", "")))
            instance = str(labels.get("instance", t.get("instance", "")))
            health = str(t.get("health", "unknown"))
            scrape_dur = t.get("lastScrapeDuration", 0.0)
            try:
                scrape_ms = float(scrape_dur) * 1000.0
            except (TypeError, ValueError):
                scrape_ms = 0.0
            last_error = t.get("lastError") or None
            if last_error == "":
                last_error = None
            targets.append(
                {
                    "job": job,
                    "instance": instance,
                    "health": health,
                    "last_scrape_duration_ms": round(scrape_ms, 3),
                    "last_error": last_error,
                    "labels": {k: str(v) for k, v in labels.items()},
                }
            )

        up_count = sum(1 for t in targets if t["health"] == "up")
        down_count = sum(1 for t in targets if t["health"] == "down")
        unknown_count = sum(1 for t in targets if t["health"] == "unknown")

        # Per-job summary
        job_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "up": 0, "down": 0, "unknown": 0})
        for t in targets:
            j = t["job"] or "(unknown)"
            job_stats[j]["total"] += 1
            h = t["health"]
            if h in ("up", "down", "unknown"):
                job_stats[j][h] += 1
        job_summary: list[TargetJobSummary] = [
            {"job": job, "total": stats["total"], "up": stats["up"], "down": stats["down"], "unknown": stats["unknown"]}
            for job, stats in sorted(job_stats.items())
        ]

        result: ListTargetsOutput = {
            "state_filter": state,
            "total_count": len(targets),
            "up_count": up_count,
            "down_count": down_count,
            "unknown_count": unknown_count,
            "job_summary": job_summary,
            "targets": targets,
        }

        md = f"## Prometheus Targets (state={state}, {len(targets)} total)\n\n"
        md += f"- **Up:** {up_count} | **Down:** {down_count} | **Unknown:** {unknown_count}\n\n"

        if job_summary:
            md += "### By Job\n\n"
            for js in job_summary[:_MD_ITEM_LIMIT]:
                status_parts = []
                if js["up"]:
                    status_parts.append(f"{js['up']} up")
                if js["down"]:
                    status_parts.append(f"**{js['down']} down**")
                if js["unknown"]:
                    status_parts.append(f"{js['unknown']} unknown")
                md += f"- `{js['job']}` — {', '.join(status_parts) or 'no targets'}\n"
            if len(job_summary) > _MD_ITEM_LIMIT:
                md += _truncation_hint(len(job_summary), _MD_ITEM_LIMIT, "jobs")

        if down_count > 0:
            md += "\n### Down Targets\n\n"
            down_targets = [t for t in targets if t["health"] == "down"]
            for t in down_targets[:10]:
                err = f" — error: {t['last_error']}" if t["last_error"] else ""
                md += f"- `{t['job']}/{t['instance']}`{err}\n"
            if len(down_targets) > 10:
                md += f"\n_...and {len(down_targets) - 10} more down targets._\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, f"listing Prometheus targets (state={state!r})")


# ── Investigation Tools ───────────────────────────────────────────────────────


@mcp.tool(
    name="prometheus_get_metric_metadata",
    annotations={
        "title": "Get Metric Metadata",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_get_metric_metadata(
    metric: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
            description=(
                "Optional metric name to filter metadata. "
                "Example: 'http_requests_total' returns metadata only for that metric. "
                "Leave empty to list metadata for all metrics (capped at 500)."
            ),
        ),
    ] = None,
    *,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description="Target instance name (omit for default instance)",
        ),
    ] = None,
) -> GetMetricMetadataOutput:
    """Get metric metadata (HELP text, TYPE, UNIT) from Prometheus.

    Wraps ``GET /api/v1/metadata``. Returns the metadata that Prometheus
    scraped from ``HELP``, ``TYPE``, and ``UNIT`` lines in the exposition
    format. Each metric may have multiple metadata entries if different
    scrape targets expose different help strings.

    Use this to understand what a metric measures, its type (counter, gauge,
    histogram, summary), and unit — essential for writing correct PromQL.
    For example, knowing a metric is a counter means you should use ``rate()``
    or ``increase()``; a gauge can be used directly.

    Examples:
        - Use when: "What does http_requests_total measure?"
          → ``metric='http_requests_total'``; read ``help`` and ``type``.
        - Use when: "Show me all histogram metrics"
          → call with no filter; filter results where ``type='histogram'``.
        - Use when: Starting an investigation — check metric types before
          writing PromQL to avoid using rate() on a gauge.
        - Don't use when: You already know the metric type and want to
          query values (call ``prometheus_query`` directly).

    Returns:
        dict with ``metric`` / ``total_count`` / ``returned_count`` /
        ``truncated`` / ``metadata`` (dict of metric name → list of
        ``{type, help, unit}``).
    """
    try:
        client = get_client(instance)
        params: dict[str, Any] = {}
        if metric is not None:
            params["metric"] = metric

        raw = client.get("/metadata", params=params) or {}
        raw_data: dict[str, list[dict[str, Any]]] = raw.get("data") or {}

        total_count = len(raw_data)
        truncated = total_count > _METRICS_CAP

        # Sort and cap
        sorted_names = sorted(raw_data.keys())[:_METRICS_CAP]
        metadata: dict[str, list[MetadataEntry]] = {}
        for name in sorted_names:
            entries = raw_data.get(name) or []
            metadata[name] = [
                {
                    "type": str(e.get("type", "")),
                    "help": str(e.get("help", "")),
                    "unit": str(e.get("unit", "")),
                }
                for e in entries
            ]

        result: GetMetricMetadataOutput = {
            "metric": metric,
            "total_count": total_count,
            "returned_count": len(metadata),
            "truncated": truncated,
            "metadata": metadata,
        }

        suffix = " — truncated at 500" if truncated else ""
        header = f"## Metric Metadata ({len(metadata)} metrics{suffix})"
        if metric:
            header += f" for `{metric}`"
        md = header + "\n\n"

        md_names = sorted_names[:_MD_ITEM_LIMIT]
        md += "| Metric | Type | Help |\n|--------|------|------|\n"
        for name in md_names:
            entries = metadata.get(name) or [{"type": "", "help": "", "unit": ""}]
            entry = entries[0]
            help_text = entry["help"][:80] + "..." if len(entry["help"]) > 80 else entry["help"]
            md += f"| `{name}` | {entry['type']} | {help_text} |\n"
        if len(sorted_names) > _MD_ITEM_LIMIT:
            md += _truncation_hint(len(sorted_names), _MD_ITEM_LIMIT, "metrics")

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "fetching metric metadata")


@mcp.tool(
    name="prometheus_list_label_values",
    annotations={
        "title": "List Label Values",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_list_label_values(
    label: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description=(
                "Label name to retrieve values for. "
                "Examples: 'job' (list all job names), 'instance' (list all instances), "
                "'__name__' (list all metric names — same as prometheus_list_metrics)."
            ),
        ),
    ],
    match: Annotated[
        str | None,
        Field(
            default=None,
            max_length=2000,
            description=(
                "Optional series selector to restrict which series the label values come from. "
                "Example: 'up' returns label values only from the 'up' metric. "
                "Example: '{job=\"node\"}' returns label values only from the node job. "
                "Leave empty to get values across all series."
            ),
        ),
    ] = None,
    *,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description="Target instance name (omit for default instance)",
        ),
    ] = None,
) -> ListLabelValuesOutput:
    """List all values for a specific label from Prometheus.

    Wraps ``GET /api/v1/label/{label_name}/values``. Returns all distinct
    values for the named label across all time series, optionally filtered
    by a series selector.

    Use this to discover what entities exist for a given label dimension —
    for example, which jobs are running, which instances are scraped, or
    which namespaces have metrics. This is essential for building targeted
    PromQL queries during investigation.

    Examples:
        - Use when: "What jobs does Prometheus scrape?"
          → ``label='job'``; read the ``values`` list.
        - Use when: "What instances are in the 'node-exporter' job?"
          → ``label='instance'``, ``match='{job="node-exporter"}'``.
        - Use when: "What namespaces have metrics?"
          → ``label='namespace'``.
        - Don't use when: You want metric names
          (call ``prometheus_list_metrics`` — has substring filtering).
        - Don't use when: You want current metric values
          (call ``prometheus_query`` with a PromQL expression).

    Returns:
        dict with ``label`` / ``match`` / ``total_count`` /
        ``returned_count`` / ``truncated`` / ``values`` (sorted list).
    """
    try:
        client = get_client(instance)
        params: dict[str, Any] = {}
        if match is not None:
            params["match[]"] = match

        raw = client.get(f"/label/{label}/values", params=params) or {}
        raw_values: list[str] = raw.get("data") or []

        total_count = len(raw_values)
        truncated = total_count > _METRICS_CAP
        values = sorted(raw_values[:_METRICS_CAP])

        result: ListLabelValuesOutput = {
            "label": label,
            "match": match,
            "total_count": total_count,
            "returned_count": len(values),
            "truncated": truncated,
            "values": values,
        }

        suffix = " — truncated at 500" if truncated else ""
        header = f"## Label Values for `{label}` ({len(values)} values{suffix})"
        if match:
            header += f" matching `{match}`"
        md = header + "\n\n"
        md_values = values[:_MD_ITEM_LIMIT]
        md += "\n".join(f"- `{v}`" for v in md_values)
        if len(values) > _MD_ITEM_LIMIT:
            md += _truncation_hint(len(values), _MD_ITEM_LIMIT, "values")

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, f"listing label values for {label!r}")


@mcp.tool(
    name="prometheus_list_rules",
    annotations={
        "title": "List Rules",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_list_rules(
    type: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Optional filter by rule type: 'alert' for alerting rules only, "
                "'record' for recording rules only. Leave empty for both types."
            ),
        ),
    ] = None,
    *,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description="Target instance name (omit for default instance)",
        ),
    ] = None,
) -> ListRulesOutput:
    """List recording and alerting rules from Prometheus.

    Wraps ``GET /api/v1/rules``. Returns rule groups with their rules,
    including the PromQL expression, rule type (recording or alerting),
    and for alerting rules their current state (firing/pending/inactive).

    Use this to understand the alerting configuration, find recording
    rules that pre-compute useful aggregations, and investigate which
    rules are currently firing or have health issues.

    Examples:
        - Use when: "What alerting rules are configured?"
          → ``type='alert'``; inspect rule names and expressions.
        - Use when: "Are there any recording rules I can use instead of
          computing aggregations from scratch?"
          → ``type='record'``; look for rules matching your investigation.
        - Use when: "Why is this alert firing? What's its PromQL expression?"
          → call with no filter; find the alert by name; read its ``query``.
        - Don't use when: You want to see which alerts are currently
          firing (call ``prometheus_list_alerts`` — shows active alerts with
          state and value, without the PromQL definition).

    Returns:
        dict with ``type_filter`` / ``total_groups`` / ``total_rules`` /
        ``recording_count`` / ``alerting_count`` / ``groups`` (list of
        rule groups with ``name``, ``file``, ``rule_count``, ``rules``).
    """
    try:
        if type is not None and type not in ("alert", "record"):
            raise ValueError(
                f"type must be 'alert', 'record', or empty (got: {type!r}). "
                "Use 'alert' for alerting rules, 'record' for recording rules, "
                "or leave empty for both."
            )

        client = get_client(instance)
        params: dict[str, Any] = {}
        if type is not None:
            params["type"] = type

        raw = client.get("/rules", params=params) or {}
        raw_data = raw.get("data") or {}
        raw_groups: list[dict[str, Any]] = raw_data.get("groups") or []

        groups: list[RuleGroupItem] = []
        total_rules = 0
        recording_count = 0
        alerting_count = 0

        for g in raw_groups:
            raw_rules: list[dict[str, Any]] = g.get("rules") or []
            rules: list[RuleItem] = []
            for r in raw_rules:
                rule_type = str(r.get("type", ""))
                rule_state = r.get("state")
                if rule_state is not None:
                    rule_state = str(rule_state)
                rule_health = r.get("health")
                if rule_health is not None:
                    rule_health = str(rule_health)
                rules.append(
                    {
                        "name": str(r.get("name", "")),
                        "query": str(r.get("query", r.get("expr", ""))),
                        "type": rule_type,
                        "state": rule_state,
                        "labels": {k: str(v) for k, v in (r.get("labels") or {}).items()},
                        "health": rule_health,
                    }
                )
                if rule_type == "recording":
                    recording_count += 1
                elif rule_type == "alerting":
                    alerting_count += 1
                total_rules += 1

            groups.append(
                {
                    "name": str(g.get("name", "")),
                    "file": str(g.get("file", "")),
                    "rule_count": len(rules),
                    "rules": rules,
                }
            )

        result: ListRulesOutput = {
            "type_filter": type,
            "total_groups": len(groups),
            "total_rules": total_rules,
            "recording_count": recording_count,
            "alerting_count": alerting_count,
            "groups": groups,
        }

        type_str = f" ({type})" if type else ""
        md = f"## Prometheus Rules{type_str}\n\n"
        md += f"**Groups:** {len(groups)} | **Rules:** {total_rules}"
        md += f" ({recording_count} recording, {alerting_count} alerting)\n\n"

        if not groups:
            md += "_No rules found._\n"
        else:
            md_groups = groups[:_MD_ITEM_LIMIT]
            for g in md_groups:
                md += f"### {g['name']}\n"
                md += f"_File: {g['file']}_ | {g['rule_count']} rules\n\n"
                md_rules = g["rules"][:_MD_ITEM_LIMIT]
                for r in md_rules:
                    state_str = f" [{r['state']}]" if r["state"] else ""
                    md += f"- **{r['name']}** ({r['type']}){state_str} — `{r['query'][:60]}`\n"
                if len(g["rules"]) > _MD_ITEM_LIMIT:
                    md += _truncation_hint(len(g["rules"]), _MD_ITEM_LIMIT, "rules")
                md += "\n"
            if len(groups) > _MD_ITEM_LIMIT:
                md += _truncation_hint(len(groups), _MD_ITEM_LIMIT, "groups")

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, f"listing Prometheus rules (type={type!r})")
