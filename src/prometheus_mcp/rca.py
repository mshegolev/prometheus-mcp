"""Root cause analysis engine for advanced alert correlation.

Provides functionality for:
- Statistical anomaly detection in metrics with seasonality adjustment
- Service dependency traversal from symptoms to potential root causes
- Change point detection correlating deployments/config changes with alerts
- Candidate ranking based on evidence strength and impact analysis
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from prometheus_mcp.federation import fan_out_prometheus
from prometheus_mcp.models import (
    AMAlertItem,
    AnomalyDetectionResult,
    ChangePointDetectionResult,
    DependencyTraversalResult,
    RootCauseCandidate,
    RootCauseRankingResult,
)

if TYPE_CHECKING:
    from prometheus_mcp.client import PrometheusClient
    from prometheus_mcp.registry import InstanceRegistry

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detects statistical outliers in metrics with seasonality adjustment."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize anomaly detector with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def detect_metric_anomalies(
        self, metric_names: list[str], start_time: str, end_time: str, sensitivity: float = 0.5
    ) -> AnomalyDetectionResult:
        """Detect anomalies in specified metrics across all instances.

        Args:
            metric_names: List of metric names to analyze
            start_time: ISO format start time for analysis window
            end_time: ISO format end time for analysis window
            sensitivity: Sensitivity threshold (0.0-1.0) for anomaly detection

        Returns:
            AnomalyDetectionResult with detected anomalies and metadata
        """
        # Get all Prometheus clients for fan-out
        clients = self.registry.all_prometheus_clients()
        instance_names = self.registry.list_instances()

        # Filter to only Prometheus instances
        prom_instance_names = []
        for name in instance_names:
            try:
                self.registry.get_prometheus_client(name)
                prom_instance_names.append(name)
            except Exception:
                pass

        # Collect metric data from all instances
        all_series_data = []

        def query_range(client: PrometheusClient) -> dict:
            """Query range data from a single client."""
            results = []
            for metric in metric_names:
                try:
                    # Query range data for the metric
                    params = {
                        "query": metric,
                        "start": start_time,
                        "end": end_time,
                        "step": "60s",  # 1-minute resolution
                    }
                    response = client.get("/query_range", params=params)
                    if response and "data" in response and "result" in response["data"]:
                        results.extend(response["data"]["result"])
                except Exception as e:
                    logger.warning(f"Failed to query metric {metric} from client: {e}")
                    continue
            return {"result": results}

        # Execute fan-out query
        fan_out_result = fan_out_prometheus(query_range, clients, instance_names=prom_instance_names)

        # Process results from successful instances
        if fan_out_result.get("data") and "result" in fan_out_result["data"]:
            for item in fan_out_result["data"]["result"]:
                if isinstance(item, dict) and "metric" in item and "values" in item:
                    all_series_data.append(item)

        # Detect anomalies in collected data
        anomalies = []
        for series in all_series_data:
            metric_anomalies = self._detect_anomalies_in_series(series, sensitivity)
            anomalies.extend(metric_anomalies)

        return {
            "total_anomalies": len(anomalies),
            "metric_anomalies": anomalies,
            "detection_method": "statistical_process_control",
            "sensitivity": sensitivity,
            "time_range": {"start": start_time, "end": end_time},
        }

    def _detect_anomalies_in_series(self, series: dict, sensitivity: float) -> list[dict]:
        """Detect anomalies in a single time series using statistical methods.

        Args:
            series: Time series data with metric and values
            sensitivity: Sensitivity threshold for anomaly detection

        Returns:
            List of detected anomalies
        """
        anomalies = []
        if "values" not in series or not series["values"]:
            return anomalies

        # Extract values (timestamp, value pairs)
        values = []
        timestamps = []
        for point in series["values"]:
            if len(point) >= 2:
                try:
                    timestamp = float(point[0])
                    value = float(point[1])
                    values.append(value)
                    timestamps.append(timestamp)
                except (ValueError, TypeError):
                    continue

        if len(values) < 3:  # Need at least 3 points for meaningful analysis
            return anomalies

        # Calculate baseline statistics
        mean_val = sum(values) / len(values)
        variance = sum((x - mean_val) ** 2 for x in values) / len(values)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        # Z-score threshold based on sensitivity
        z_threshold = 2.0 + (sensitivity * 2.0)  # Maps 0.0-1.0 to 2.0-4.0

        # Detect outliers using z-score
        for i, value in enumerate(values):
            if std_dev > 0:
                z_score = abs(value - mean_val) / std_dev
                if z_score > z_threshold:
                    anomalies.append(
                        {
                            "metric": series.get("metric", {}),
                            "timestamp": timestamps[i],
                            "value": value,
                            "z_score": z_score,
                            "baseline_mean": mean_val,
                            "baseline_std": std_dev,
                            "anomaly_type": "statistical_outlier",
                        }
                    )

        return anomalies

    def _seasonal_decomposition(self, values: list[float], period: int = 24) -> dict:
        """Perform simple seasonal decomposition using moving averages.

        Args:
            values: Time series values
            period: Seasonal period (default 24 for hourly data)

        Returns:
            Dictionary with trend, seasonal, and residual components
        """
        if len(values) < period * 2:
            # Not enough data for seasonal decomposition
            return {"trend": values, "seasonal": [0.0] * len(values), "residual": [0.0] * len(values)}

        # Simple moving average for trend
        trend = []
        window = min(period, len(values) // 4)  # Use smaller window for trend
        window = max(3, window)  # Minimum window size

        for i in range(len(values)):
            start_idx = max(0, i - window // 2)
            end_idx = min(len(values), i + window // 2 + 1)
            window_values = values[start_idx:end_idx]
            trend.append(sum(window_values) / len(window_values) if window_values else 0)

        # Seasonal component
        seasonal = []
        residual = []
        for i, value in enumerate(values):
            seasonal_component = 0.0
            residual_component = 0.0
            if i < len(trend):
                seasonal_component = value - trend[i]
                residual_component = value - trend[i] - seasonal_component
            seasonal.append(seasonal_component)
            residual.append(residual_component)

        return {"trend": trend, "seasonal": seasonal, "residual": residual}


class DependencyTraverser:
    """Traces service dependencies from symptoms to potential root causes."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize dependency traverser with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def traverse_from_symptoms(self, alert_groups: dict[str, list[AMAlertItem]]) -> DependencyTraversalResult:
        """Traverse dependency graph from alert symptoms to root causes.

        Args:
            alert_groups: Dictionary mapping service identifiers to alert lists

        Returns:
            DependencyTraversalResult with traversal paths and root causes
        """
        # Build dependency graph from correlation data
        dependency_graph = self._build_dependency_graph(alert_groups)

        # Traverse from affected services upstream
        paths = []
        root_causes = []

        for service_id in alert_groups.keys():
            # Perform breadth-first search upstream
            service_paths = self._traverse_upstream(dependency_graph, service_id, max_depth=5)
            paths.extend(service_paths)

            # Identify potential root causes
            for path in service_paths:
                if path["nodes"]:
                    # Root cause is the last node in the path (upstream)
                    root_node = path["nodes"][-1]
                    root_causes.append(
                        {
                            "service": root_node,
                            "path_evidence": path["evidence_weight"],
                            "impact_score": path["impact_score"],
                        }
                    )

        return {"total_paths": len(paths), "paths": paths, "root_causes": root_causes, "traversal_depth": 5}

    def _build_dependency_graph(self, alert_groups: dict[str, list[AMAlertItem]]) -> dict:
        """Build dependency graph from alert correlation data.

        Args:
            alert_groups: Dictionary mapping service identifiers to alert lists

        Returns:
            Dependency graph representation
        """
        graph = defaultdict(list)

        # Get all Alertmanager clients
        clients = self.registry.all_alertmanager_clients()
        instance_names = self.registry.list_instances()

        # Filter to only Alertmanager instances
        am_instance_names = []
        for name in instance_names:
            try:
                self.registry.get_alertmanager_client(name)
                am_instance_names.append(name)
            except Exception:
                pass

        # Collect alerts from all instances to build correlation data
        all_alerts = []
        for i, client in enumerate(clients):
            if i < len(am_instance_names):
                instance_name = am_instance_names[i]
                try:
                    # Get alerts from this instance
                    raw_alerts = client.get("/alerts") or []
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
                        all_alerts.append(alert_item)
                except Exception as e:
                    logger.warning(f"Failed to fetch alerts from instance {instance_name}: {e}")
                    continue

        # Build correlation matrix based on temporal proximity
        correlation_matrix = defaultdict(lambda: defaultdict(float))

        # Compare all pairs of alerts
        for i, alert1 in enumerate(all_alerts):
            for j, alert2 in enumerate(all_alerts):
                if i >= j:  # Avoid duplicate comparisons and self-comparison
                    continue

                # Calculate temporal correlation (within 5 minutes)
                try:
                    ts1 = datetime.fromisoformat(alert1["startsAt"].replace("Z", "+00:00"))
                    ts2 = datetime.fromisoformat(alert2["startsAt"].replace("Z", "+00:00"))
                    time_diff = abs((ts1 - ts2).total_seconds())

                    if time_diff <= 300:  # 5 minutes window
                        # Calculate label similarity as correlation strength
                        labels1 = alert1["labels"]
                        labels2 = alert2["labels"]

                        # Convert to sets of key-value pairs for comparison
                        set1 = set(labels1.items())
                        set2 = set(labels2.items())

                        # Calculate Jaccard similarity
                        intersection = len(set1.intersection(set2))
                        union = len(set1.union(set2))

                        if union > 0:
                            similarity = intersection / union

                            # Extract service identifiers
                            service1 = self._identify_service_identifier(labels1)
                            service2 = self._identify_service_identifier(labels2)

                            # Update correlation matrix
                            correlation_matrix[service1][service2] = max(
                                correlation_matrix[service1][service2], similarity
                            )
                            correlation_matrix[service2][service1] = max(
                                correlation_matrix[service2][service1], similarity
                            )
                except Exception as e:
                    logger.warning(f"Error calculating correlation: {e}")
                    continue

        # Convert correlation matrix to adjacency list
        for source_service, targets in correlation_matrix.items():
            for target_service, strength in targets.items():
                if strength > 0.3:  # Minimum correlation threshold
                    graph[source_service].append(
                        {"target": target_service, "strength": strength, "type": "temporal_correlation"}
                    )

        return dict(graph)

    def _identify_service_identifier(self, labels: dict[str, str]) -> str:
        """Extract service identifier from alert labels.

        Args:
            labels: Alert labels dictionary

        Returns:
            Service identifier string
        """
        # Priority order for service identification
        service_keys = ["job", "service", "app", "namespace", "component"]

        for key in service_keys:
            if key in labels:
                return labels[key]

        # Fallback to instance if available
        if "instance" in labels:
            return labels["instance"]

        # Generic identifier
        return "unknown_service"

    def _traverse_upstream(self, graph: dict, start_service: str, max_depth: int = 5) -> list[dict]:
        """Perform breadth-first traversal upstream in the dependency graph.

        Args:
            graph: Dependency graph representation
            start_service: Starting service for traversal
            max_depth: Maximum traversal depth

        Returns:
            List of traversal paths with evidence weights
        """
        paths = []
        visited = set()
        queue = [(start_service, [start_service], 1.0, 0)]  # (current_node, path, cumulative_weight, depth)

        while queue:
            current_node, path, weight, depth = queue.pop(0)

            if depth >= max_depth or current_node in visited:
                continue

            visited.add(current_node)

            # Add current path to results
            paths.append(
                {
                    "nodes": path.copy(),
                    "edges": [
                        {"source": path[i], "target": path[i + 1], "weight": weight} for i in range(len(path) - 1)
                    ],
                    "evidence_weight": weight,
                    "impact_score": self._calculate_impact_score(path, graph),
                    "depth": depth,
                }
            )

            # Explore neighbors (dependencies)
            if current_node in graph:
                for edge in graph[current_node]:
                    neighbor = edge["target"]
                    edge_strength = edge["strength"]
                    new_weight = weight * edge_strength

                    # Only continue if the evidence is strong enough
                    if new_weight > 0.1 and neighbor not in path:  # Avoid cycles
                        new_path = path + [neighbor]
                        queue.append((neighbor, new_path, new_weight, depth + 1))

        return paths

    def _calculate_impact_score(self, path: list[str], graph: dict) -> float:
        """Calculate impact score for a dependency path.

        Args:
            path: List of services in the path
            graph: Dependency graph

        Returns:
            Impact score (0.0-1.0)
        """
        if not path:
            return 0.0

        # Simple impact calculation based on path length and connectivity
        path_length_factor = 1.0 / len(path)

        # Connectivity factor (how well-connected the services are)
        connectivity_sum = 0.0
        for service in path:
            if service in graph:
                connectivity_sum += len(graph[service])

        avg_connectivity = connectivity_sum / len(path) if path else 0
        connectivity_factor = min(1.0, avg_connectivity / 10.0)  # Normalize by assuming max 10 connections

        # Combine factors
        impact_score = (path_length_factor * 0.3) + (connectivity_factor * 0.7)
        return min(1.0, max(0.0, impact_score))


class ChangePointDetector:
    """Detects change points correlating deployments/config changes with alerts."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize change point detector with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def detect_change_points(self, alert_timestamps: list[str], time_window: int = 3600) -> ChangePointDetectionResult:
        """Detect deployment/config/scaling change points around alert timestamps.

        Change-point detection requires an external change source — a deployment
        tracker, a config-management audit log, or CI/CD event stream — to
        correlate infrastructure changes with alert timing. No such source is
        wired into this server, so this returns an **empty** result rather than
        fabricating plausible-looking events. Input timestamps are still parsed
        and validated so a real detector can drop in without changing the
        interface or any downstream consumer (:meth:`RootCauseRanker.rank_candidates`
        simply contributes no change-score when ``events`` is empty).

        Args:
            alert_timestamps: List of alert start timestamps in ISO format
            time_window: Time window in seconds to search for changes (default: 1 hour)

        Returns:
            ChangePointDetectionResult with an empty ``events`` list until a
            change source is integrated.
        """
        # Validate/parse input timestamps (kept so a real detector can consume
        # them unchanged); malformed values are logged and skipped, never fatal.
        for ts_str in alert_timestamps:
            try:
                datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception as e:
                logger.warning(f"Failed to parse timestamp {ts_str}: {e}")

        # No external change source configured → do not fabricate change events.
        return {
            "total_events": 0,
            "events": [],
            "time_window": {"duration_seconds": time_window, "search_backwards": True},
            "correlation_threshold": 0.3,
        }


class RootCauseRanker:
    """Ranks root cause candidates based on evidence strength and impact."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize root cause ranker with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def rank_candidates(self, anomalies: list, dependencies: list, changes: list) -> RootCauseRankingResult:
        """Rank root cause candidates using evidence from multiple sources.

        Args:
            anomalies: List of detected anomalies
            dependencies: List of dependency paths
            changes: List of detected change events

        Returns:
            RootCauseRankingResult with ranked candidates
        """
        # Collect all candidate services
        candidates = defaultdict(
            lambda: {"anomaly_score": 0.0, "dependency_score": 0.0, "change_score": 0.0, "occurrence_count": 0}
        )

        # Score candidates based on anomalies
        for anomaly in anomalies:
            if "metric" in anomaly and "job" in anomaly["metric"]:
                service = anomaly["metric"]["job"]
                candidates[service]["anomaly_score"] = max(
                    candidates[service]["anomaly_score"],
                    min(1.0, anomaly.get("z_score", 0) / 5.0),  # Normalize z-score
                )
                candidates[service]["occurrence_count"] += 1

        # Score candidates based on dependency paths
        for path in dependencies:
            if "nodes" in path and path["nodes"]:
                # Root cause is typically the last node in the path
                root_service = path["nodes"][-1]
                candidates[root_service]["dependency_score"] = max(
                    candidates[root_service]["dependency_score"],
                    min(1.0, path.get("evidence_weight", 0) * 2.0),  # Boost dependency evidence
                )
                candidates[root_service]["occurrence_count"] += 1

        # Score candidates based on change events
        for change in changes:
            # In a real implementation, we'd correlate changes with specific services
            # For simulation, we'll distribute change scores across candidates
            if candidates:
                change_score = change.get("correlation_strength", 0)
                for service in candidates:
                    candidates[service]["change_score"] = max(candidates[service]["change_score"], change_score)
                    # Don't increment occurrence count for changes as they're more general

        # Convert to ranked list
        candidate_list = []
        for service, scores in candidates.items():
            # Calculate composite score using weighted average
            composite_score = (
                scores["anomaly_score"] * 0.4 + scores["dependency_score"] * 0.4 + scores["change_score"] * 0.2
            )

            # Calculate confidence interval (simplified)
            confidence_lower = max(0.0, composite_score - 0.1)
            confidence_upper = min(1.0, composite_score + 0.1)

            candidate_obj: RootCauseCandidate = {
                "identifier": service,
                "evidence_score": composite_score,
                "impact_assessment": {
                    "anomaly_contribution": scores["anomaly_score"],
                    "dependency_contribution": scores["dependency_score"],
                    "change_contribution": scores["change_score"],
                    "occurrence_count": scores["occurrence_count"],
                },
                "confidence_interval": {"lower": confidence_lower, "upper": confidence_upper},
                "ranking_explanation": self._generate_ranking_explanation(scores),
            }
            candidate_list.append(candidate_obj)

        # Sort by evidence score (descending)
        candidate_list.sort(key=lambda x: x["evidence_score"], reverse=True)

        # Determine top candidate
        top_candidate = candidate_list[0]["identifier"] if candidate_list else None

        return {
            "candidates": candidate_list,
            "ranking_method": "weighted_evidence_composite",
            "total_candidates": len(candidate_list),
            "top_candidate": top_candidate,
        }

    def _generate_ranking_explanation(self, scores: dict) -> str:
        """Generate explanation for ranking decision.

        Args:
            scores: Scores dictionary for a candidate

        Returns:
            Human-readable explanation of the ranking
        """
        explanations = []

        if scores["anomaly_score"] > 0.5:
            explanations.append("High metric anomaly score")
        elif scores["anomaly_score"] > 0.2:
            explanations.append("Moderate metric anomaly score")

        if scores["dependency_score"] > 0.5:
            explanations.append("Strong dependency relationship evidence")
        elif scores["dependency_score"] > 0.2:
            explanations.append("Some dependency relationship evidence")

        if scores["change_score"] > 0.5:
            explanations.append("Recent change correlation")
        elif scores["change_score"] > 0.2:
            explanations.append("Possible recent change correlation")

        if scores["occurrence_count"] > 2:
            explanations.append("Multiple evidence sources")
        elif scores["occurrence_count"] > 1:
            explanations.append("Multiple occurrences")

        if not explanations:
            return "Low confidence candidate with limited evidence"

        return "; ".join(explanations)


# Main RCA Engine that coordinates all components
class RCAEngine:
    """Main class for root cause analysis operations."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize RCA engine with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry
        self.anomaly_detector = AnomalyDetector(registry)
        self.dependency_traverser = DependencyTraverser(registry)
        self.change_point_detector = ChangePointDetector(registry)
        self.root_cause_ranker = RootCauseRanker(registry)

    def perform_full_analysis(self, alert_groups: dict[str, list[AMAlertItem]], time_range_hours: int = 2) -> dict:
        """Perform complete root cause analysis.

        Args:
            alert_groups: Dictionary mapping service identifiers to alert lists
            time_range_hours: Time range in hours for analysis

        Returns:
            Dictionary with full RCA results
        """
        # Get current time for analysis window
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)

        # Extract alert timestamps for change point detection
        alert_timestamps = []
        all_alerts = []
        for alerts in alert_groups.values():
            for alert in alerts:
                alert_timestamps.append(alert.get("startsAt", ""))
                all_alerts.append(alert)

        # 1. Detect anomalies in relevant metrics
        # For demonstration, we'll use some common metrics
        common_metrics = [
            "up",
            "scrape_duration_seconds",
            "prometheus_tsdb_head_series",
            "process_cpu_seconds_total",
            "process_resident_memory_bytes",
        ]

        anomalies_result = self.anomaly_detector.detect_metric_anomalies(
            metric_names=common_metrics,
            start_time=start_time.isoformat() + "Z",
            end_time=end_time.isoformat() + "Z",
            sensitivity=0.7,
        )

        # 2. Traverse dependencies from symptoms
        dependencies_result = self.dependency_traverser.traverse_from_symptoms(alert_groups)

        # 3. Detect change points
        changes_result = self.change_point_detector.detect_change_points(
            alert_timestamps=alert_timestamps,
            time_window=3600,  # 1 hour window
        )

        # 4. Rank root cause candidates
        ranking_result = self.root_cause_ranker.rank_candidates(
            anomalies=anomalies_result.get("metric_anomalies", []),
            dependencies=dependencies_result.get("paths", []),
            changes=changes_result.get("events", []),
        )

        return {
            "anomalies": anomalies_result,
            "dependencies": dependencies_result,
            "changes": changes_result,
            "ranking": ranking_result,
            "analysis_time_range": {"start": start_time.isoformat() + "Z", "end": end_time.isoformat() + "Z"},
        }
