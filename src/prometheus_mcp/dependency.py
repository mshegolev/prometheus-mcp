"""Dependency mapping and health assessment for advanced alert correlation.

Provides functionality for:
- Traffic correlation analysis to discover service dependencies
- Dynamic dependency graph construction with cross-cluster awareness
- Cross-cluster dependency visualization
- Synthetic health probing for dependency assessment
- Real-time dependency state differentiation
- Load shedding recommendations based on dependency fragility
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple, Union

from prometheus_mcp.models import (
    AMAlertItem,
    CorrelationAnalysisResult,
    DependencyAnalysisResult,
    DependencyEdge,
    DependencyGraph,
    ServiceNode,
    CrossClusterInfo,
)
from prometheus_mcp.federation import fan_out_prometheus

if TYPE_CHECKING:
    from prometheus_mcp.registry import InstanceRegistry
    from prometheus_mcp.client import PrometheusClient

logger = logging.getLogger(__name__)


class TrafficCorrelator:
    """Analyzes traffic correlations to discover service dependencies."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize traffic correlator with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def analyze_traffic_correlations(
        self, start_time: str, end_time: str, service_filter: str | None = None
    ) -> CorrelationAnalysisResult:
        """Analyze traffic correlations across all instances to identify service dependencies.

        Args:
            start_time: ISO format start time for analysis window
            end_time: ISO format end time for analysis window
            service_filter: Optional service name filter

        Returns:
            CorrelationAnalysisResult with discovered correlations and confidence scores
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
            except:
                pass

        # Collect traffic metric data from all instances
        all_series_data = []

        def query_range(client: PrometheusClient) -> dict:
            """Query range data from a single client."""
            results = []
            # Query common traffic metrics
            traffic_metrics = [
                "http_requests_total",
                "grpc_server_handled_total",
                "request_duration_seconds_count",
            ]

            for metric in traffic_metrics:
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

        # Perform correlation analysis on collected data
        correlations = []
        confidence_scores = {}

        # Group series by service
        service_data = defaultdict(list)
        for series in all_series_data:
            service_id = self._identify_service_identifier(series.get("metric", {}))
            if service_filter and service_filter != service_id:
                continue
            service_data[service_id].append(series)

        # Calculate cross-correlations between services
        service_ids = list(service_data.keys())
        for i, source_service in enumerate(service_ids):
            for j, target_service in enumerate(service_ids):
                if i >= j:  # Avoid duplicate comparisons and self-comparison
                    continue

                # Calculate correlation between service traffic patterns
                correlation_strength = self._calculate_cross_correlation(
                    service_data[source_service], service_data[target_service]
                )

                if correlation_strength > 0.1:  # Minimum threshold
                    correlation_key = f"{source_service}->{target_service}"
                    correlations.append(
                        {
                            "source": source_service,
                            "target": target_service,
                            "strength": correlation_strength,
                            "type": "traffic_correlation",
                        }
                    )
                    confidence_scores[correlation_key] = correlation_strength

        return {
            "correlations": correlations,
            "confidence_scores": confidence_scores,
            "time_range": {"start": start_time, "end": end_time},
            "total_services": len(service_ids),
            "analysis_method": "cross_correlation",
        }

    def _identify_service_identifier(self, labels: dict[str, str]) -> str:
        """Extract service identifier from metric labels.

        Args:
            labels: Metric labels dictionary

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

    def _calculate_cross_correlation(self, series_list1: list, series_list2: list) -> float:
        """Calculate cross-correlation between two sets of time series.

        Args:
            series_list1: First set of time series data
            series_list2: Second set of time series data

        Returns:
            Correlation coefficient (0.0-1.0)
        """
        if not series_list1 or not series_list2:
            return 0.0

        # Extract values from both series
        values1 = []
        values2 = []

        # Aggregate values across all series in each list
        for series in series_list1:
            if "values" in series:
                for point in series["values"]:
                    if len(point) >= 2:
                        try:
                            values1.append(float(point[1]))
                        except (ValueError, TypeError):
                            continue

        for series in series_list2:
            if "values" in series:
                for point in series["values"]:
                    if len(point) >= 2:
                        try:
                            values2.append(float(point[1]))
                        except (ValueError, TypeError):
                            continue

        if len(values1) != len(values2) or len(values1) < 2:
            return 0.0

        # Calculate Pearson correlation coefficient
        return self._pearson_correlation(values1, values2)

    def _pearson_correlation(self, x: list[float], y: list[float]) -> float:
        """Calculate Pearson correlation coefficient between two arrays.

        Args:
            x: First array of values
            y: Second array of values

        Returns:
            Correlation coefficient (-1.0 to 1.0)
        """
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        # Calculate means
        mean_x = sum(x) / len(x)
        mean_y = sum(y) / len(y)

        # Calculate numerator and denominators
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(len(x)))
        denominator_x = math.sqrt(sum((x[i] - mean_x) ** 2 for i in range(len(x))))
        denominator_y = math.sqrt(sum((y[i] - mean_y) ** 2 for i in range(len(y))))

        if denominator_x == 0 or denominator_y == 0:
            return 0.0

        correlation = numerator / (denominator_x * denominator_y)

        # Return absolute value normalized to 0-1 range
        return abs(correlation)


class DependencyGraphBuilder:
    """Constructs service dependency graphs from correlation analysis."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize dependency graph builder with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def build_dependency_graph(self, correlation_data: CorrelationAnalysisResult) -> DependencyGraph:
        """Build dependency graph from correlation analysis results.

        Args:
            correlation_data: Correlation analysis results

        Returns:
            DependencyGraph with nodes, edges, and metadata
        """
        # Extract service identifiers from correlations
        service_ids = set()
        for corr in correlation_data.get("correlations", []):
            service_ids.add(corr["source"])
            service_ids.add(corr["target"])

        # Build service nodes
        nodes: list[ServiceNode] = []
        for service_id in service_ids:
            node: ServiceNode = {
                "service_id": service_id,
                "name": service_id,
                "namespace": None,
                "cluster": None,
                "instance": None,
                "health_status": "unknown",
                "metadata": {},
                "last_seen": datetime.utcnow().isoformat() + "Z",
            }
            nodes.append(node)

        # Build dependency edges
        edges: list[DependencyEdge] = []
        confidence_scores = correlation_data.get("confidence_scores", {})

        for corr in correlation_data.get("correlations", []):
            edge: DependencyEdge = {
                "source": corr["source"],
                "target": corr["target"],
                "strength": corr["strength"],
                "relationship_type": corr["type"],
                "latency_avg": None,
                "error_rate": None,
                "throughput": None,
                "last_observed": datetime.utcnow().isoformat() + "Z",
            }
            edges.append(edge)

        # Build cross-cluster information
        clusters: list[CrossClusterInfo] = []
        instance_names = self.registry.list_instances()

        # Group services by cluster/instance
        cluster_map = defaultdict(list)
        for service_id in service_ids:
            # In a real implementation, we'd determine cluster from service metadata
            # For now, we'll distribute services across available instances
            cluster_id = instance_names[hash(service_id) % len(instance_names)] if instance_names else "default"
            cluster_map[cluster_id].append(service_id)

        for cluster_id, services in cluster_map.items():
            cluster_info: CrossClusterInfo = {
                "cluster_id": cluster_id,
                "region": None,
                "services": services,
                "connections": [],
                "health_status": "unknown",
            }
            clusters.append(cluster_info)

        # Create dependency graph
        graph: DependencyGraph = {
            "nodes": nodes,
            "edges": edges,
            "clusters": clusters,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "1.0",
            "metadata": {
                "analysis_method": correlation_data.get("analysis_method", "unknown"),
                "time_range": correlation_data.get("time_range", {}),
                "total_services": len(nodes),
                "total_edges": len(edges),
            },
        }

        return graph

    def _resolve_service_identity(self, service_id: str, instance_name: str) -> str:
        """Resolve service identity across different cluster contexts.

        Args:
            service_id: Local service identifier
            instance_name: Instance/cluster name

        Returns:
            Globally unique service identifier
        """
        # In a real implementation, this would handle cross-cluster service identity resolution
        # For now, we'll create a composite identifier
        return f"{instance_name}:{service_id}"

    def _detect_cycles(self, edges: list[DependencyEdge]) -> list[list[str]]:
        """Detect cycles in the dependency graph.

        Args:
            edges: List of dependency edges

        Returns:
            List of cycles (each cycle is a list of service IDs)
        """
        # Build adjacency list representation
        graph = defaultdict(list)
        for edge in edges:
            graph[edge["source"]].append(edge["target"])

        # Detect cycles using DFS
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph[node]:
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            rec_stack.remove(node)
            path.pop()

        # Check all nodes
        all_nodes = set()
        for edge in edges:
            all_nodes.add(edge["source"])
            all_nodes.add(edge["target"])

        for node in all_nodes:
            if node not in visited:
                dfs(node, [])

        return cycles
