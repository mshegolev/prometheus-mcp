"""MCP tools for advanced federation analysis in v4.0.

Provides integrated tools that combine correlation, root cause analysis,
dependency mapping, and trend analysis for comprehensive incident investigation.

.. warning::

    **EXPERIMENTAL — NOT WIRED INTO THE SERVER. DO NOT USE IN PRODUCTION.**

    This module is intentionally NOT imported by ``server.py``, so its
    ``federation_analyze_alerts`` tool is not registered or exposed. The
    implementation references engine/client APIs that do not exist as written
    (e.g. ``PrometheusClient.list_alerts``/``query``, ``output.warn``,
    ``RCAEngine(clients)`` vs the real ``(registry)`` constructor,
    ``registry.get_all_clients()``, ``CorrelationResult.dict()``) and will
    crash on first call. It must be rewritten against the real APIs — and its
    ``dependency`` backing (also experimental/simulated) made real — before it
    can be registered. Kept for reference only.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from prometheus_mcp import output
from prometheus_mcp._mcp import _registry, mcp
from prometheus_mcp.correlation import CorrelationEngine
from prometheus_mcp.dependency import DependencyEngine
from prometheus_mcp.models import (
    CorrelationResult,
    RangeSeries,
)
from prometheus_mcp.rca import RCAEngine
from prometheus_mcp.trend_analysis import analyze_trends, benchmark_resolution_times

# ── Federated Alert Analysis ─────────────────────────────────────────────────


@mcp.tool(
    name="federation_analyze_alerts",
    annotations={
        "title": "Analyze Alerts Across Federation with Full Context",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def federation_analyze_alerts(
    instance_filter: Annotated[
        list[str] | None,
        Field(
            description="Optional list of instance names to analyze. If omitted, all configured instances are analyzed."
        ),
    ] = None,
    alert_filter: Annotated[
        str | None,
        Field(description="Optional PromQL-style filter to select specific alerts by labels (e.g., 'job=~\"web.*\"')."),
    ] = None,
    analysis_depth: Annotated[
        int,
        Field(
            description="Depth of dependency traversal for root cause analysis (1-5, default 3).",
            ge=1,
            le=5,
        ),
    ] = 3,
    include_trends: Annotated[
        bool,
        Field(description="Include historical trend analysis in the results (default true)."),
    ] = True,
    include_benchmarks: Annotated[
        bool,
        Field(description="Include MTTR benchmarking against historical data (default true)."),
    ] = True,
) -> dict:
    """Comprehensive alert analysis across all federated instances.

    Combines cross-instance correlation, root cause analysis, dependency mapping,
    and trend analysis to provide complete incident context in a single tool call.

    This tool integrates all v4.0 features:
    - Cross-instance alert correlation to identify related alerts
    - Root cause analysis with anomaly detection and change point identification
    - Dependency traversal to trace service relationships
    - Historical trend analysis to identify patterns
    - MTTR benchmarking against historical performance

    Returns structured JSON with all analysis dimensions plus human-readable markdown.
    """
    try:
        # Get all configured clients
        clients = _registry.get_all_clients()
        if not clients:
            raise ValueError("No Prometheus instances configured")

        # Filter clients if requested
        if instance_filter:
            clients = [c for c in clients if c.instance_name in instance_filter]
            if not clients:
                raise ValueError(f"No instances found matching filter: {instance_filter}")

        # Initialize engines
        correlation_engine = CorrelationEngine(clients)
        rca_engine = RCAEngine(clients)
        dependency_engine = DependencyEngine(clients)

        # Collect alerts from all instances
        all_alerts = []
        all_metrics = []

        for client in clients:
            try:
                # Get alerts
                alerts_response = client.list_alerts()
                if alerts_response and hasattr(alerts_response, "data") and alerts_response.data:
                    for alert_group in alerts_response.data.get("groups", []):
                        for alert in alert_group.get("alerts", []):
                            # Add instance attribution
                            alert["instance"] = client.instance_name
                            all_alerts.append(alert)

                # Get metrics for trend analysis (if requested)
                if include_trends:
                    # Get some key metrics for trend analysis
                    try:
                        cpu_query = client.query("rate(process_cpu_seconds_total[5m])")
                        mem_query = client.query("process_resident_memory_bytes")
                        if cpu_query and hasattr(cpu_query, "data") and cpu_query.data:
                            all_metrics.extend(
                                _convert_query_result_to_rangeseries(cpu_query, client.instance_name, "cpu_usage")
                            )
                        if mem_query and hasattr(mem_query, "data") and mem_query.data:
                            all_metrics.extend(
                                _convert_query_result_to_rangeseries(mem_query, client.instance_name, "memory_usage")
                            )
                    except Exception:
                        # Continue even if metric collection fails
                        pass

            except Exception as e:
                # Log but continue with other instances
                output.warn(f"Failed to collect data from instance {client.instance_name}: {e}")
                continue

        if not all_alerts:
            return output.ok(
                content="# Federated Alert Analysis\n\nNo active alerts found across configured instances.",
                structured_content={
                    "analysis_type": "federated_alert_analysis",
                    "instances_analyzed": [c.instance_name for c in clients],
                    "alerts_found": 0,
                    "correlation_results": [],
                    "rca_results": [],
                    "dependency_results": [],
                    "trend_analysis": {} if include_trends else None,
                    "benchmark_results": {} if include_benchmarks else None,
                },
            )

        # Perform correlation analysis
        correlation_result = correlation_engine.correlate_alerts(all_alerts)

        # Perform root cause analysis on correlated alerts
        rca_results = []
        if correlation_result.groups:
            for group in correlation_result.groups:
                # Analyze anomalies in the group
                anomalies = rca_engine.detect_anomalies(group.alerts)

                # Traverse dependencies
                dependencies = rca_engine.traverse_dependencies(group.alerts, max_depth=analysis_depth)

                # Detect change points
                change_points = rca_engine.detect_change_points(group.alerts)

                # Rank root causes
                root_causes = rca_engine.rank_root_causes(group.alerts, anomalies, dependencies, change_points)

                rca_results.append(
                    {
                        "group_id": getattr(group, "id", None),
                        "anomalies": anomalies,
                        "dependencies": dependencies,
                        "change_points": change_points,
                        "root_causes": root_causes,
                    }
                )

        # Perform dependency analysis
        dependency_results = []
        if correlation_result.groups:
            for group in correlation_result.groups:
                # Create dependency graph for the alert group
                dep_graph = dependency_engine.build_dependency_graph(group.alerts)
                if dep_graph:
                    # Analyze health of dependencies
                    health_analysis = dependency_engine.analyze_dependency_health(dep_graph)
                    # Get cross-cluster information
                    cross_cluster_info = dependency_engine.get_cross_cluster_info(dep_graph)

                    dependency_results.append(
                        {
                            "group_id": getattr(group, "id", None),
                            "graph": dep_graph,
                            "health_analysis": health_analysis,
                            "cross_cluster_info": cross_cluster_info,
                        }
                    )

        # Perform trend analysis (if requested)
        trend_analysis = None
        if include_trends and all_metrics:
            trend_analysis = analyze_trends(all_alerts, all_metrics)

        # Perform benchmarking (if requested)
        benchmark_results = None
        if include_benchmarks:
            benchmark_results = benchmark_resolution_times(all_alerts)

        # Generate human-readable markdown output
        markdown_content = _generate_markdown_report(
            clients=[c.instance_name for c in clients],
            correlation_result=correlation_result,
            rca_results=rca_results,
            dependency_results=dependency_results,
            trend_analysis=trend_analysis,
            benchmark_results=benchmark_results,
            alert_filter=alert_filter,
        )

        # Return combined results
        return output.ok(
            content=markdown_content,
            structured_content={
                "analysis_type": "federated_alert_analysis",
                "instances_analyzed": [c.instance_name for c in clients],
                "alerts_found": len(all_alerts),
                "alert_filter": alert_filter,
                "analysis_depth": analysis_depth,
                "correlation_results": correlation_result.dict() if correlation_result else {},
                "rca_results": rca_results,
                "dependency_results": dependency_results,
                "trend_analysis": trend_analysis,
                "benchmark_results": benchmark_results,
            },
        )

    except Exception as exc:
        return output.fail(exc, "performing federated alert analysis")


def _convert_query_result_to_rangeseries(query_result, instance_name: str, metric_name: str) -> list[RangeSeries]:
    """Convert a query result to RangeSeries format for trend analysis."""
    rangeseries_list = []

    if not query_result or not hasattr(query_result, "data") or not query_result.data:
        return rangeseries_list

    # Handle vector results
    if query_result.data.get("resultType") == "vector":
        for sample in query_result.data.get("result", []):
            labels = sample.get("metric", {})
            labels["__name__"] = f"{metric_name}_{instance_name}"
            value = sample.get("value")
            if value and len(value) >= 2:
                rangeseries_list.append(
                    {"labels": labels, "point_count": 1, "values": [[float(value[0]), str(value[1])]]}
                )

    # Handle matrix results
    elif query_result.data.get("resultType") == "matrix":
        for series in query_result.data.get("result", []):
            labels = series.get("metric", {})
            labels["__name__"] = f"{metric_name}_{instance_name}"
            values = series.get("values", [])
            rangeseries_list.append(
                {"labels": labels, "point_count": len(values), "values": [[float(v[0]), str(v[1])] for v in values]}
            )

    return rangeseries_list


def _generate_markdown_report(
    clients: list[str],
    correlation_result: CorrelationResult,
    rca_results: list[dict],
    dependency_results: list[dict],
    trend_analysis: dict | None,
    benchmark_results: dict | None,
    alert_filter: str | None,
) -> str:
    """Generate human-readable markdown report from analysis results."""
    report_lines = ["# Federated Alert Analysis Report", ""]

    # Summary
    report_lines.extend(
        [
            "## Analysis Summary",
            f"- **Instances Analyzed**: {', '.join(clients)}",
            f"- **Total Alerts Found**: "
            f"{len(correlation_result.groups) if correlation_result and correlation_result.groups else 0}",
        ]
    )

    if alert_filter:
        report_lines.append(f"- **Alert Filter Applied**: `{alert_filter}`")

    report_lines.append("")

    # Correlation Results
    if correlation_result and correlation_result.groups:
        report_lines.extend(
            ["## Correlation Analysis", f"Found {len(correlation_result.groups)} correlated alert groups:", ""]
        )

        for i, group in enumerate(correlation_result.groups, 1):
            report_lines.extend(
                [
                    f"### Group {i}: {len(group.alerts)} related alerts",
                    f"- **Correlation Strength**: {getattr(group, 'strength', 'N/A')}",
                    f"- **Primary Alert**: "
                    f"{group.alerts[0].get('labels', {}).get('alertname', 'Unknown') if group.alerts else 'N/A'}",
                    "",
                ]
            )

    # Root Cause Analysis Results
    if rca_results:
        report_lines.extend(["## Root Cause Analysis", ""])

        for i, rca_result in enumerate(rca_results, 1):
            report_lines.append(f"### Group {i} Analysis")

            # Anomalies
            anomalies = rca_result.get("anomalies", {})
            if anomalies.get("anomalies"):
                report_lines.extend(
                    [
                        "- **Detected Anomalies**:",
                        *[
                            f"  - {a.get('metric', 'Unknown')} at {a.get('timestamp', 'Unknown')}"
                            for a in anomalies.get("anomalies", [])[:3]
                        ],  # Show top 3
                        "",
                    ]
                )

            # Top Root Causes
            root_causes = rca_result.get("root_causes", {})
            if root_causes.get("candidates"):
                report_lines.extend(
                    [
                        "- **Top Root Cause Candidates**:",
                        *[
                            f"  - {c.get('service', 'Unknown')} (confidence: {c.get('confidence', 0):.2f})"
                            for c in root_causes.get("candidates", [])[:3]
                        ],  # Show top 3
                        "",
                    ]
                )

    # Dependency Analysis Results
    if dependency_results:
        report_lines.extend(["## Dependency Analysis", ""])

        for i, dep_result in enumerate(dependency_results, 1):
            health_analysis = dep_result.get("health_analysis", {})
            if health_analysis.get("fragile_dependencies"):
                report_lines.extend(
                    [
                        f"### Group {i} Dependency Health",
                        "- **Fragile Dependencies Detected**:",
                        *[
                            f"  - {d.get('service', 'Unknown')} ({d.get('reason', 'Unknown issue')})"
                            for d in health_analysis.get("fragile_dependencies", [])[:3]
                        ],  # Show top 3
                        "",
                    ]
                )

    # Trend Analysis Results
    if trend_analysis:
        report_lines.extend(["## Trend Analysis", ""])

        # Recurring patterns
        recurring_schedules = trend_analysis.get("recurring_schedules", {})
        if recurring_schedules:
            report_lines.extend(
                [
                    "- **Recurring Alert Patterns**:",
                    *[
                        f"  - {alert_name}: Hours {schedule.get('hours', [])}"
                        for alert_name, schedule in list(recurring_schedules.items())[:3]
                    ],  # Show top 3
                    "",
                ]
            )

        # Seasonal behaviors
        seasonal_behaviors = trend_analysis.get("seasonal_behaviors", {})
        if seasonal_behaviors:
            report_lines.extend(
                [
                    "- **Seasonal Behaviors**:",
                    *[
                        f"  - {metric}: Peak at hour {behavior.get('peak_hour', 'N/A')}"
                        for metric, behavior in list(seasonal_behaviors.items())[:3]
                    ],  # Show top 3
                    "",
                ]
            )

    # Benchmark Results
    if benchmark_results:
        report_lines.extend(["## Performance Benchmarks", ""])

        # Show some benchmark results
        if benchmark_results:
            report_lines.extend(
                ["- **MTTR Comparisons Available**:", f"  - {len(benchmark_results)} alert types analyzed", ""]
            )

    return "\n".join(report_lines)
