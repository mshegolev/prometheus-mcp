"""MCP tools for alert correlation and analysis.

Provides tools for:
- Cross-instance alert correlation
- Service-based alert grouping
- Cascading alert detection
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from prometheus_mcp import output
from prometheus_mcp._mcp import _registry, mcp
from prometheus_mcp.correlation import CorrelationEngine
from prometheus_mcp.models import (
    AlertGroupResult,
    AMAlertItem,
    CascadeDetectionResult,
    CorrelationResult,
)

# RCA imports for enhanced correlation
try:
    from prometheus_mcp.rca import RCAEngine
    from prometheus_mcp.models import (
        AnomalyDetectionResult,
        DependencyTraversalResult,
        ChangePointDetectionResult,
        RootCauseRankingResult,
    )

    RCA_AVAILABLE = True
except ImportError:
    RCA_AVAILABLE = False


# ── Correlate Alerts Across Instances ────────────────────────────────────────


@mcp.tool(
    name="correlate_alerts_across_instances",
    annotations={
        "title": "Correlate Alerts Across Instances",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def correlate_alerts_across_instances(
    *,
    temporal_window: Annotated[
        int, Field(description="Time window in seconds for correlation (default: 300)", ge=1, le=3600, default=300)
    ] = 300,
    similarity_threshold: Annotated[
        float, Field(description="Minimum similarity score for correlation (default: 0.7)", ge=0.0, le=1.0, default=0.7)
    ] = 0.7,
    enable_rca: Annotated[
        bool, Field(description="Enable root cause analysis enhancement (default: False)", default=False)
    ] = False,
    instance: str | None = None,
    instances: list[str] | None = None,
) -> CorrelationResult:
    """Correlate alerts across multiple Prometheus instances.

    Identifies related alerts that fire simultaneously or in sequence across
    different Prometheus instances using temporal windows and label similarity.

    Use this to:
    - Understand cross-instance incident scope
    - Identify related alerts in different clusters/regions
    - Detect systemic issues affecting multiple instances

    Examples:
        - "Are there related alerts firing across our US and EU clusters?"
        - "Show me alerts that might be related to this HighCPU alert"

    Returns:
        CorrelationResult with correlated alerts, groups, and cascades.
    """
    try:
        # Get registry
        registry = _registry
        if registry is None:
            return output.fail(Exception("Registry not available"), "correlating alerts")

        # Initialize correlation engine
        engine = CorrelationEngine(registry)

        # Perform correlation
        result = engine.correlate_alerts_across_instances(
            temporal_window=temporal_window, similarity_threshold=similarity_threshold
        )

        # Optionally enhance with RCA analysis
        rca_enhancement = None
        if enable_rca and RCA_AVAILABLE:
            try:
                # Import RCA engine here to avoid import issues
                from prometheus_mcp.rca import RCAEngine

                # Initialize RCA engine
                rca_engine = RCAEngine(registry)

                # Convert correlation groups to alert groups for RCA
                alert_groups = {}
                for group in result.get("groups", []):
                    service_id = group["service_identifier"]
                    alerts = [corr_alert["alert"] for corr_alert in group["alerts"]]
                    if service_id not in alert_groups:
                        alert_groups[service_id] = []
                    alert_groups[service_id].extend(alerts)

                # Perform RCA analysis
                rca_result = rca_engine.perform_full_analysis(alert_groups)
                rca_enhancement = rca_result
            except Exception as rca_error:
                # Log RCA error but don't fail the entire operation
                import logging

                logging.warning(f"RCA enhancement failed: {rca_error}")

        # Generate markdown summary
        markdown = _format_correlation_result(result, rca_enhancement)

        # Add RCA data to structured output if available
        if rca_enhancement:
            result["rca_enhancement"] = rca_enhancement

        return output.ok(result, markdown)

    except Exception as e:
        return output.fail(e, "correlating alerts across instances")


def _format_correlation_result(result: CorrelationResult, rca_enhancement: dict | None = None) -> str:
    """Format correlation result as markdown."""
    md = [
        "# Cross-Instance Alert Correlation",
        "",
        f"**Total Correlations:** {result['total_correlations']}",
        f"**Detected Groups:** {len(result['groups'])}",
        f"**Identified Cascades:** {len(result['cascades'])}",
        "",
    ]

    # Instance attribution
    md.append("## Instance Attribution")
    for instance, count in result["instance_attribution"].items():
        md.append(f"- {instance}: {count} alerts")
    md.append("")

    # Correlated alerts summary
    if result["correlated_alerts"]:
        md.append("## Correlated Alerts")
        # Group by instance for clearer presentation
        alerts_by_instance = {}
        for corr_alert in result["correlated_alerts"]:
            instance = corr_alert["instance"]
            if instance not in alerts_by_instance:
                alerts_by_instance[instance] = []
            alerts_by_instance[instance].append(corr_alert)

        for instance, corr_alerts in alerts_by_instance.items():
            md.append(f"### {instance}")
            for corr_alert in corr_alerts[:5]:  # Limit to 5 per instance
                alert = corr_alert["alert"]
                score = corr_alert["correlation_score"]
                alertname = alert["labels"].get("alertname", "Unknown Alert")
                md.append(f"- **{alertname}** (score: {score:.2f})")
            if len(corr_alerts) > 5:
                md.append(f"  _... and {len(corr_alerts) - 5} more_")
            md.append("")

    # Groups summary
    if result["groups"]:
        md.append("## Alert Groups")
        for group in result["groups"][:10]:  # Limit to 10 groups
            service_id = group["service_identifier"]
            strength = group["correlation_strength"]
            alert_count = len(group["alerts"])
            md.append(f"- **{service_id}**: {alert_count} alerts (strength: {strength:.2f})")
        if len(result["groups"]) > 10:
            md.append(f"_... and {len(result['groups']) - 10} more groups_")
        md.append("")

    # Cascades summary
    if result["cascades"]:
        md.append("## Detected Cascades")
        for cascade in result["cascades"][:5]:  # Limit to 5 cascades
            parent_alert = cascade["parent"]["alert"]
            child_alert = cascade["child"]["alert"]
            strength = cascade["dependency_strength"]
            delay = cascade["temporal_delay"]

            parent_name = parent_alert["labels"].get("alertname", "Unknown Alert")
            child_name = child_alert["labels"].get("alertname", "Unknown Alert")

            md.append(f"- **{parent_name}** → **{child_name}** (strength: {strength:.2f}, delay: {delay:.1f}s)")
        if len(result["cascades"]) > 5:
            md.append(f"_... and {len(result['cascades']) - 5} more cascades_")
        md.append("")

    # RCA Enhancement section
    if rca_enhancement:
        md.append("## Root Cause Analysis Insights")
        md.append("")

        # Anomalies detected
        anomalies = rca_enhancement.get("anomalies", {})
        if anomalies.get("total_anomalies", 0) > 0:
            md.append("### Detected Metric Anomalies")
            md.append(f"**Total Anomalies:** {anomalies['total_anomalies']}")
            for anomaly in anomalies.get("metric_anomalies", [])[:3]:
                metric_labels = anomaly.get("metric", {})
                job = metric_labels.get("job", "unknown")
                z_score = anomaly.get("z_score", 0)
                md.append(f"- **{job}**: Anomaly (z-score: {z_score:.2f})")
            if len(anomalies.get("metric_anomalies", [])) > 3:
                md.append(f"  _... and {len(anomalies['metric_anomalies']) - 3} more_")
            md.append("")

        # Dependency paths
        dependencies = rca_enhancement.get("dependencies", {})
        if dependencies.get("total_paths", 0) > 0:
            md.append("### Dependency Paths")
            md.append(f"**Total Paths Analyzed:** {dependencies['total_paths']}")
            for path in dependencies.get("paths", [])[:3]:
                nodes = path.get("nodes", [])
                if nodes:
                    path_str = " → ".join(nodes[:3])  # Limit path display
                    weight = path.get("evidence_weight", 0)
                    md.append(f"- **{path_str}** (evidence: {weight:.2f})")
            if len(dependencies.get("paths", [])) > 3:
                md.append(f"  _... and {len(dependencies['paths']) - 3} more_")
            md.append("")

        # Change points
        changes = rca_enhancement.get("changes", {})
        if changes.get("total_events", 0) > 0:
            md.append("### Recent Changes")
            md.append(f"**Total Change Events:** {changes['total_events']}")
            for event in changes.get("events", [])[:3]:
                event_type = event.get("event_type", "unknown")
                description = event.get("description", "")
                strength = event.get("correlation_strength", 0)
                md.append(f"- **{event_type}**: {description} (strength: {strength:.2f})")
            if len(changes.get("events", [])) > 3:
                md.append(f"  _... and {len(changes['events']) - 3} more_")
            md.append("")

        # Ranked candidates
        ranking = rca_enhancement.get("ranking", {})
        if ranking.get("total_candidates", 0) > 0:
            md.append("### Root Cause Candidates")
            md.append(f"**Total Candidates:** {ranking['total_candidates']}")
            for candidate in ranking.get("candidates", [])[:5]:
                identifier = candidate.get("identifier", "unknown")
                score = candidate.get("evidence_score", 0)
                explanation = candidate.get("ranking_explanation", "")
                md.append(f"- **{identifier}**: {score:.2f} - {explanation}")
            if len(ranking.get("candidates", [])) > 5:
                md.append(f"  _... and {len(ranking['candidates']) - 5} more_")
            md.append("")

    return "\n".join(md)


# ── Group Alerts by Service ──────────────────────────────────────────────────


@mcp.tool(
    name="group_alerts_by_service",
    annotations={
        "title": "Group Alerts by Service",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def group_alerts_by_service(
    *,
    instance: str | None = None,
    instances: list[str] | None = None,
) -> AlertGroupResult:
    """Group alerts by service identifiers across all instances.

    Clusters related alerts into service-level incident analysis bundles.

    Use this to:
    - Understand which services are affected by current incidents
    - Focus incident response efforts on specific service teams
    - Identify services with multiple simultaneous alerts

    Examples:
        - "Which services are currently experiencing alerts?"
        - "Group all alerts by service for my incident report"

    Returns:
        AlertGroupResult with alerts grouped by service identifier.
    """
    try:
        # Get registry
        registry = _registry
        if registry is None:
            return output.fail(Exception("Registry not available"), "grouping alerts by service")

        # Get all Alertmanager clients
        clients = registry.all_alertmanager_clients()
        instance_names = registry.list_instances()

        # Filter to only Alertmanager instances
        am_instance_names = []
        for name in instance_names:
            try:
                registry.get_alertmanager_client(name)
                am_instance_names.append(name)
            except:
                pass

        # Collect alerts from all instances
        all_alerts = []

        for i, client in enumerate(clients):
            if i < len(am_instance_names):
                instance_name = am_instance_names[i]
                try:
                    # Get alerts from this instance
                    raw_alerts = client.get("/alerts") or []
                    alerts = []
                    for a in raw_alerts:
                        alert_item: AMAlertItem = {
                            "labels": {k: str(v) for k, v in (a.get("labels") or {}).items()},
                            "annotations": {k: str(v) for k, v in (a.get("annotations") or {}).items()},
                            "status": {
                                "state": str(a.get("status", {}).get("state", "")),
                                "silencedBy": [str(s) for s in (a.get("status", {}).get("silencedBy") or [])],
                                "inhibitedBy": [str(s) for s in (a.get("status", {}).get("inhibitedBy") or [])],
                            },
                            "startsAt": str(a.get("startsAt", "")),
                            "endsAt": str(a.get("endsAt", "")),
                            "generatorURL": str(a.get("generatorURL", "")),
                            "fingerprint": str(a.get("fingerprint", "")),
                        }
                        # Add instance attribution to labels
                        alert_item["labels"]["__prometheus_instance__"] = instance_name
                        alerts.append(alert_item)
                    all_alerts.extend(alerts)

                except Exception as e:
                    continue

        # Initialize correlation engine
        engine = CorrelationEngine(registry)

        # Perform grouping
        result = engine.group_alerts_by_service(all_alerts)

        # Generate markdown summary
        markdown = _format_group_result(result)

        return output.ok(result, markdown)

    except Exception as e:
        return output.fail(e, "grouping alerts by service")


def _format_group_result(result: AlertGroupResult) -> str:
    """Format group result as markdown."""
    md = [
        "# Alert Grouping by Service",
        "",
        f"**Total Groups:** {result['total_groups']}",
        f"**Ungrouped Alerts:** {result['ungrouped_count']}",
        "",
    ]

    # Groups
    if result["groups"]:
        md.append("## Service Groups")
        for service_id, alerts in result["groups"].items():
            md.append(f"### {service_id}")
            md.append(f"**Alert Count:** {len(alerts)}")
            md.append("**Alerts:**")
            for alert in alerts[:10]:  # Limit to 10 alerts per group
                alertname = alert["labels"].get("alertname", "Unknown Alert")
                instance = alert["labels"].get("__prometheus_instance__", "Unknown Instance")
                state = alert.get("status", {}).get("state", "unknown")
                md.append(f"- {alertname} ({instance}, {state})")
            if len(alerts) > 10:
                md.append(f"  _... and {len(alerts) - 10} more_")
            md.append("")

    return "\n".join(md)


# ── Detect Cascading Alerts ──────────────────────────────────────────────────


@mcp.tool(
    name="detect_cascading_alerts",
    annotations={
        "title": "Detect Cascading Alerts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def detect_cascading_alerts(
    *,
    temporal_window: Annotated[
        int,
        Field(description="Time window in seconds for cascade detection (default: 300)", ge=1, le=3600, default=300),
    ] = 300,
    instance: str | None = None,
    instances: list[str] | None = None,
) -> CascadeDetectionResult:
    """Detect cascading alert patterns with directional dependency inference.

    Identifies alert propagation patterns that indicate dependency failures.

    Use this to:
    - Trace failure propagation paths through your system
    - Identify root cause candidates for complex incidents
    - Understand service dependency relationships

    Examples:
        - "What alerts typically fire after DatabaseConnectionFailed?"
        - "Show me the failure propagation chain in this incident"

    Returns:
        CascadeDetectionResult with detected cascades and root causes.
    """
    try:
        # Get registry
        registry = _registry
        if registry is None:
            return output.fail(Exception("Registry not available"), "detecting cascading alerts")

        # Get all Alertmanager clients
        clients = registry.all_alertmanager_clients()
        instance_names = registry.list_instances()

        # Filter to only Alertmanager instances
        am_instance_names = []
        for name in instance_names:
            try:
                registry.get_alertmanager_client(name)
                am_instance_names.append(name)
            except:
                pass

        # Collect alerts from all instances
        all_alerts = []

        for i, client in enumerate(clients):
            if i < len(am_instance_names):
                instance_name = am_instance_names[i]
                try:
                    # Get alerts from this instance
                    raw_alerts = client.get("/alerts") or []
                    alerts = []
                    for a in raw_alerts:
                        alert_item: AMAlertItem = {
                            "labels": {k: str(v) for k, v in (a.get("labels") or {}).items()},
                            "annotations": {k: str(v) for k, v in (a.get("annotations") or {}).items()},
                            "status": {
                                "state": str(a.get("status", {}).get("state", "")),
                                "silencedBy": [str(s) for s in (a.get("status", {}).get("silencedBy") or [])],
                                "inhibitedBy": [str(s) for s in (a.get("status", {}).get("inhibitedBy") or [])],
                            },
                            "startsAt": str(a.get("startsAt", "")),
                            "endsAt": str(a.get("endsAt", "")),
                            "generatorURL": str(a.get("generatorURL", "")),
                            "fingerprint": str(a.get("fingerprint", "")),
                        }
                        # Add instance attribution to labels
                        alert_item["labels"]["__prometheus_instance__"] = instance_name
                        alerts.append(alert_item)
                    all_alerts.extend(alerts)

                except Exception as e:
                    continue

        # Initialize correlation engine
        engine = CorrelationEngine(registry)

        # Perform cascade detection
        result = engine.detect_cascading_alerts(all_alerts, temporal_window=temporal_window)

        # Generate markdown summary
        markdown = _format_cascade_result(result)

        return output.ok(result, markdown)

    except Exception as e:
        return output.fail(e, "detecting cascading alerts")


def _format_cascade_result(result: CascadeDetectionResult) -> str:
    """Format cascade result as markdown."""
    md = [
        "# Cascading Alert Detection",
        "",
        f"**Total Cascades Detected:** {result['total_cascades']}",
        f"**Potential Root Causes:** {len(result['root_causes'])}",
        "",
    ]

    # Root causes
    if result["root_causes"]:
        md.append("## Potential Root Causes")
        for root_cause in result["root_causes"][:10]:  # Limit to 10 root causes
            alert = root_cause["alert"]
            instance = root_cause["instance"]
            score = root_cause["correlation_score"]
            alertname = alert["labels"].get("alertname", "Unknown Alert")
            md.append(f"- **{alertname}** ({instance}, score: {score:.2f})")
        if len(result["root_causes"]) > 10:
            md.append(f"  _... and {len(result['root_causes']) - 10} more_")
        md.append("")

    # Cascades
    if result["cascades"]:
        md.append("## Cascade Relationships")
        for cascade in result["cascades"][:10]:  # Limit to 10 cascades
            parent = cascade["parent"]
            child = cascade["child"]
            strength = cascade["dependency_strength"]
            delay = cascade["temporal_delay"]

            parent_alert = parent["alert"]
            child_alert = child["alert"]
            parent_instance = parent["instance"]
            child_instance = child["instance"]

            parent_name = parent_alert["labels"].get("alertname", "Unknown Alert")
            child_name = child_alert["labels"].get("alertname", "Unknown Alert")

            md.append(f"- **{parent_name}** ({parent_instance})")
            md.append(f"  → **{child_name}** ({child_instance})")
            md.append(f"  - Strength: {strength:.2f}")
            md.append(f"  - Delay: {delay:.1f} seconds")
            md.append("")
        if len(result["cascades"]) > 10:
            md.append(f"_... and {len(result['cascades']) - 10} more cascades_")
        md.append("")

    return "\n".join(md)
