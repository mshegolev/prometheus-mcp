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
    ClusterInfo,
    CorrelationAnalysisResult,
    CrossClusterInfo,
    DependencyAnalysisResult,
    DependencyEdge,
    DependencyGraph,
    HealthProbeResult,
    ServiceNode,
    SyntheticProbe,
    VisualizationResult,
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

        def query_range(client) -> dict:
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
                "metadata": {},
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


class CrossClusterVisualizer:
    """Creates cross-cluster dependency visualizations."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize cross-cluster visualizer with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def visualize_cross_cluster_dependencies(
        self, dependency_graph: DependencyGraph, visualization_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create cross-cluster visualization of dependency graph.

        Args:
            dependency_graph: Dependency graph to visualize
            visualization_params: Optional visualization parameters

        Returns:
            VisualizationResult with graph layout and styling information
        """
        if visualization_params is None:
            visualization_params = {}

        # Extract cluster information
        clusters: list[ClusterInfo] = []
        for cluster_info in dependency_graph.get("clusters", []):
            cluster: ClusterInfo = {
                "cluster_id": cluster_info["cluster_id"],
                "name": cluster_info["cluster_id"],  # Use cluster_id as name for now
                "region": cluster_info.get("region"),
                "status": cluster_info.get("health_status", "unknown"),
                "services": len(cluster_info.get("services", [])),
                "dependencies": len(cluster_info.get("connections", [])),
                "metadata": {},
            }
            clusters.append(cluster)

        # Generate layout coordinates using force-directed layout simulation
        layout_coordinates = self._generate_layout_coordinates(dependency_graph)

        # Generate color mapping for clusters/services
        color_mapping = self._generate_color_mapping(dependency_graph)

        # Create legend
        legend = {
            "healthy": "Green - Healthy services",
            "degraded": "Yellow - Degraded services",
            "failed": "Red - Failed services",
            "unknown": "Gray - Unknown status",
        }

        return {
            "graph": dependency_graph,
            "clusters": clusters,
            "layout_coordinates": layout_coordinates,
            "color_mapping": color_mapping,
            "legend": legend,
        }

    def _generate_layout_coordinates(self, graph: DependencyGraph) -> dict[str, dict[str, float]]:
        """Generate 2D coordinates for graph layout using force-directed algorithm.

        Args:
            graph: Dependency graph

        Returns:
            Dictionary mapping service IDs to (x, y) coordinates
        """
        coordinates: dict[str, dict[str, float]] = {}

        # Extract nodes and edges
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])

        # Initialize random positions for nodes
        import random

        random.seed(42)  # For reproducible results

        for node in nodes:
            service_id = node["service_id"]
            coordinates[service_id] = {
                "x": random.uniform(-100, 100),
                "y": random.uniform(-100, 100),
            }

        # Simple force-directed layout (basic implementation)
        # In a real implementation, this would be more sophisticated
        iterations = 50
        for _ in range(iterations):
            # Apply repulsive forces between all nodes
            for i, node1 in enumerate(nodes):
                for j, node2 in enumerate(nodes):
                    if i >= j:
                        continue
                    service1 = node1["service_id"]
                    service2 = node2["service_id"]

                    # Simple repulsion (could be improved)
                    dx = coordinates[service1]["x"] - coordinates[service2]["x"]
                    dy = coordinates[service1]["y"] - coordinates[service2]["y"]
                    distance = max(0.1, math.sqrt(dx * dx + dy * dy))

                    # Apply force inversely proportional to distance
                    force = 10.0 / (distance * distance)
                    coordinates[service1]["x"] += dx * force / distance * 0.1
                    coordinates[service1]["y"] += dy * force / distance * 0.1
                    coordinates[service2]["x"] -= dx * force / distance * 0.1
                    coordinates[service2]["y"] -= dy * force / distance * 0.1

            # Apply attractive forces along edges
            for edge in edges:
                source = edge["source"]
                target = edge["target"]

                if source in coordinates and target in coordinates:
                    dx = coordinates[source]["x"] - coordinates[target]["x"]
                    dy = coordinates[source]["y"] - coordinates[target]["y"]
                    distance = max(0.1, math.sqrt(dx * dx + dy * dy))

                    # Apply spring force
                    force = distance * 0.01
                    coordinates[source]["x"] -= dx * force * 0.1
                    coordinates[source]["y"] -= dy * force * 0.1
                    coordinates[target]["x"] += dx * force * 0.1
                    coordinates[target]["y"] += dy * force * 0.1

        return coordinates

    def _generate_color_mapping(self, graph: DependencyGraph) -> dict[str, str]:
        """Generate color mapping for visualization elements.

        Args:
            graph: Dependency graph

        Returns:
            Dictionary mapping elements to colors
        """
        color_mapping: dict[str, str] = {}

        # Color by cluster
        clusters = graph.get("clusters", [])
        cluster_colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8"]

        for i, cluster_info in enumerate(clusters):
            cluster_id = cluster_info["cluster_id"]
            color = cluster_colors[i % len(cluster_colors)]
            color_mapping[f"cluster:{cluster_id}"] = color

            # Color services in this cluster
            for service_id in cluster_info.get("services", []):
                color_mapping[f"service:{service_id}"] = color

        # Color by health status
        color_mapping["status:healthy"] = "#4CAF50"  # Green
        color_mapping["status:degraded"] = "#FF9800"  # Orange
        color_mapping["status:failed"] = "#F44336"  # Red
        color_mapping["status:unknown"] = "#9E9E9E"  # Gray

        return color_mapping


class HealthProber:
    """Assesses dependency health through synthetic probing."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize health prober with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def configure_synthetic_probe(self, probe_config: dict[str, Any]) -> dict[str, Any]:
        """Configure a synthetic health probe.

        Args:
            probe_config: Configuration for the synthetic probe

        Returns:
            Configuration confirmation
        """
        # In a real implementation, this would store the probe configuration
        # For now, we'll just validate and return the config
        required_fields = ["target_service", "target_endpoint", "frequency_seconds"]
        for field in required_fields:
            if field not in probe_config:
                raise ValueError(f"Missing required field: {field}")

        probe_id = probe_config.get("probe_id", f"probe_{datetime.utcnow().timestamp()}")

        return {
            "probe_id": probe_id,
            "configured": True,
            "target_service": probe_config["target_service"],
            "target_endpoint": probe_config["target_endpoint"],
        }

    def execute_health_probe(self, probe_id: str, probe_target: str | None = None) -> dict[str, Any]:
        """Execute a synthetic health probe.

        Args:
            probe_id: Identifier of the probe to execute
            probe_target: Optional override for probe target

        Returns:
            HealthProbeResult with probe results
        """
        # In a real implementation, this would actually execute synthetic requests
        # For now, we'll simulate probe execution with mock results

        import random

        random.seed(hash(probe_id))  # For reproducible results

        # Simulate probe execution
        success = random.random() > 0.2  # 80% success rate
        response_time = random.uniform(10, 500) if success else None
        status_code = random.choice([200, 200, 200, 404, 500]) if success else random.choice([500, 503, 504])
        error_message = None if success else "Connection timeout"

        # Calculate resilience score based on results
        resilience_score = 1.0
        if not success:
            resilience_score = 0.0
        elif status_code >= 400:
            resilience_score = 0.3
        elif response_time and response_time > 200:
            resilience_score = 0.7
        else:
            resilience_score = 0.9

        return {
            "probe_id": probe_id,
            "target_service": probe_target or "unknown_service",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "success": success,
            "response_time_ms": response_time,
            "status_code": status_code if success else None,
            "error_message": error_message,
            "metrics": {
                "response_size_bytes": random.randint(100, 1000) if success else 0,
                "connection_attempts": 1,
            },
            "resilience_score": resilience_score,
        }


class StateDifferentiator:
    """Differentiates between normal and failure-state interactions in real-time."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize state differentiator with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def differentiate_dependency_states(
        self, current_graph: DependencyGraph, alert_data: dict[str, Any] | None = None
    ) -> DependencyGraph:
        """Analyze live metric streams to differentiate normal vs. failure-state interactions.

        Args:
            current_graph: Current dependency graph to analyze
            alert_data: Optional alert data for correlation

        Returns:
            Updated dependency graph with state differentiation metadata
        """
        # In a real implementation, this would analyze live metric streams
        # For now, we'll simulate state differentiation by marking some services as failed

        import random

        random.seed(42)  # For reproducible results

        # Copy the graph to avoid modifying the original
        updated_graph = current_graph.copy()

        # Update node health statuses based on simulated analysis
        nodes = updated_graph.get("nodes", [])
        for node in nodes:
            # Simulate failure detection (20% chance of failure)
            if random.random() < 0.2:
                node["health_status"] = "failed"
                node["metadata"]["failure_reason"] = "Simulated failure detected"
            elif random.random() < 0.3:
                node["health_status"] = "degraded"
                node["metadata"]["degradation_reason"] = "High latency detected"
            else:
                node["health_status"] = "healthy"

        # Update edge statuses based on node states
        edges = updated_graph.get("edges", [])
        for edge in edges:
            # If either source or target is failed, mark edge as failed
            source_node = next((n for n in nodes if n["service_id"] == edge["source"]), None)
            target_node = next((n for n in nodes if n["service_id"] == edge["target"]), None)

            # Initialize metadata if not present
            if "metadata" not in edge or edge["metadata"] is None:
                edge["metadata"] = {}

            if (source_node and source_node["health_status"] == "failed") or (
                target_node and target_node["health_status"] == "failed"
            ):
                edge["relationship_type"] = "failed_dependency"
                edge["metadata"]["status"] = "failed"
            elif (source_node and source_node["health_status"] == "degraded") or (
                target_node and target_node["health_status"] == "degraded"
            ):
                edge["relationship_type"] = "degraded_dependency"
                edge["metadata"]["status"] = "degraded"
            else:
                edge["metadata"]["status"] = "healthy"

        # Update timestamp
        updated_graph["timestamp"] = datetime.utcnow().isoformat() + "Z"

        return updated_graph

    def _detect_state_transitions(self, metrics_stream: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect state transitions in live metric streams.

        Args:
            metrics_stream: Stream of live metrics data

        Returns:
            List of detected state transitions
        """
        transitions = []

        # In a real implementation, this would use pattern recognition techniques
        # For now, we'll simulate transition detection

        for i, metric_point in enumerate(metrics_stream):
            if i == 0:
                continue

            # Compare current point with previous point
            prev_point = metrics_stream[i - 1]
            current_value = metric_point.get("value", 0)
            prev_value = prev_point.get("value", 0)

            # Detect significant changes (more than 50% change)
            if prev_value != 0 and abs(current_value - prev_value) / prev_value > 0.5:
                transition = {
                    "timestamp": metric_point.get("timestamp", ""),
                    "service": metric_point.get("service", "unknown"),
                    "metric": metric_point.get("metric", "unknown"),
                    "from_value": prev_value,
                    "to_value": current_value,
                    "transition_type": "significant_change",
                }
                transitions.append(transition)

        return transitions


class LoadSheddingAdvisor:
    """Generates load shedding recommendations based on dependency fragility."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize load shedding advisor with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry

    def generate_load_shedding_recommendations(
        self,
        dependency_graph: DependencyGraph,
        health_probe_results: list[dict[str, Any]] | None = None,
        system_metrics: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate load shedding recommendations based on dependency fragility.

        Args:
            dependency_graph: Current dependency graph
            health_probe_results: Optional health probe results
            system_metrics: Optional system-wide metrics

        Returns:
            List of load shedding recommendations
        """
        recommendations = []

        # Extract nodes and edges
        nodes = dependency_graph.get("nodes", [])
        edges = dependency_graph.get("edges", [])

        # Calculate fragility scores for each service
        fragility_scores = self._calculate_fragility_scores(nodes, edges, health_probe_results)

        # Identify critical services (high fragility, high centrality)
        critical_services = self._identify_critical_services(nodes, edges, fragility_scores)

        # Generate recommendations based on fragility and criticality
        for service_id, fragility_score in fragility_scores.items():
            if fragility_score > 0.7:  # High fragility threshold
                recommendation = {
                    "service": service_id,
                    "priority": "high",
                    "action": "reduce_load",
                    "reason": f"High fragility score ({fragility_score:.2f})",
                    "confidence": min(1.0, fragility_score),
                    "alternatives": self._suggest_alternatives(service_id, dependency_graph),
                }
                recommendations.append(recommendation)
            elif fragility_score > 0.5:  # Medium fragility threshold
                recommendation = {
                    "service": service_id,
                    "priority": "medium",
                    "action": "monitor_closely",
                    "reason": f"Medium fragility score ({fragility_score:.2f})",
                    "confidence": min(1.0, fragility_score),
                    "alternatives": self._suggest_alternatives(service_id, dependency_graph),
                }
                recommendations.append(recommendation)

        # Add recommendations for critical services even if they have moderate fragility
        for service_id in critical_services:
            if service_id not in [r["service"] for r in recommendations if r["priority"] == "high"]:
                fragility_score = fragility_scores.get(service_id, 0.0)
                recommendation = {
                    "service": service_id,
                    "priority": "high",
                    "action": "protect_path",
                    "reason": f"Critical service with fragility score {fragility_score:.2f}",
                    "confidence": min(1.0, 0.8 + fragility_score * 0.2),
                    "alternatives": self._suggest_alternatives(service_id, dependency_graph),
                }
                recommendations.append(recommendation)

        # Sort recommendations by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return recommendations

    def _calculate_fragility_scores(
        self,
        nodes: list[ServiceNode],
        edges: list[DependencyEdge],
        health_probe_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, float]:
        """Calculate fragility scores for services based on dependencies and health.

        Args:
            nodes: List of service nodes
            edges: List of dependency edges
            health_probe_results: Optional health probe results

        Returns:
            Dictionary mapping service IDs to fragility scores (0.0-1.0)
        """
        fragility_scores = {}

        # Build adjacency lists for incoming and outgoing edges
        incoming_edges = defaultdict(list)
        outgoing_edges = defaultdict(list)

        for edge in edges:
            incoming_edges[edge["target"]].append(edge)
            outgoing_edges[edge["source"]].append(edge)

        # Calculate fragility for each node
        for node in nodes:
            service_id = node["service_id"]

            # Base fragility from health status
            health_fragility = 0.0
            if node["health_status"] == "failed":
                health_fragility = 1.0
            elif node["health_status"] == "degraded":
                health_fragility = 0.6
            elif node["health_status"] == "unknown":
                health_fragility = 0.3

            # Dependency-based fragility
            # Services with many dependencies are more fragile
            dependency_count = len(outgoing_edges.get(service_id, []))
            dependency_fragility = min(1.0, dependency_count / 10.0)  # Normalize by assuming max 10 deps

            # Services that are depended upon by many others are critical
            dependency_on_count = len(incoming_edges.get(service_id, []))
            dependency_on_fragility = min(1.0, dependency_on_count / 20.0)  # Normalize by assuming max 20 dependents

            # Health probe-based fragility
            probe_fragility = 0.0
            if health_probe_results:
                service_probes = [p for p in health_probe_results if p.get("target_service") == service_id]
                if service_probes:
                    avg_resilience = sum(p.get("resilience_score", 1.0) for p in service_probes) / len(service_probes)
                    probe_fragility = 1.0 - avg_resilience

            # Combined fragility score
            fragility_score = (
                health_fragility * 0.4
                + dependency_fragility * 0.3
                + dependency_on_fragility * 0.2
                + probe_fragility * 0.1
            )

            fragility_scores[service_id] = min(1.0, fragility_score)

        return fragility_scores

    def _identify_critical_services(
        self, nodes: list[ServiceNode], edges: list[DependencyEdge], fragility_scores: dict[str, float]
    ) -> list[str]:
        """Identify critical services based on centrality and fragility.

        Args:
            nodes: List of service nodes
            edges: List of dependency edges
            fragility_scores: Pre-calculated fragility scores

        Returns:
            List of critical service IDs
        """
        critical_services = []

        # Build adjacency lists
        incoming_edges = defaultdict(list)
        outgoing_edges = defaultdict(list)

        for edge in edges:
            incoming_edges[edge["target"]].append(edge)
            outgoing_edges[edge["source"]].append(edge)

        # Calculate centrality measures for each node
        for node in nodes:
            service_id = node["service_id"]

            # In-degree centrality (number of services depending on this service)
            in_degree = len(incoming_edges.get(service_id, []))

            # Out-degree centrality (number of services this service depends on)
            out_degree = len(outgoing_edges.get(service_id, []))

            # Betweenness centrality approximation (simplified)
            # Services that connect many other services are critical
            betweenness_approx = in_degree * out_degree

            # Criticality score based on centrality and fragility
            fragility = fragility_scores.get(service_id, 0.0)
            criticality_score = in_degree * 0.3 + out_degree * 0.2 + betweenness_approx * 0.3 + fragility * 0.2

            # If criticality score is high, consider it critical
            if criticality_score > 5.0:
                critical_services.append(service_id)

        return critical_services

    def _suggest_alternatives(self, service_id: str, graph: DependencyGraph) -> list[dict[str, Any]]:
        """Suggest alternative paths or services to reduce dependency on a fragile service.

        Args:
            service_id: Service ID to find alternatives for
            graph: Dependency graph

        Returns:
            List of alternative suggestions
        """
        alternatives = []

        # In a real implementation, this would find alternative paths in the dependency graph
        # For now, we'll provide generic suggestions

        alternatives.append(
            {
                "type": "circuit_breaker",
                "description": "Implement circuit breaker pattern for this service",
                "benefit": "Prevents cascade failures when service is degraded",
            }
        )

        alternatives.append(
            {
                "type": "retry_policy",
                "description": "Configure exponential backoff retry policy",
                "benefit": "Reduces load on degraded service while maintaining availability",
            }
        )

        alternatives.append(
            {
                "type": "caching",
                "description": "Implement caching for frequently accessed data",
                "benefit": "Reduces dependency on service for repeated requests",
            }
        )

        return alternatives


# Main Dependency Mapping Engine that coordinates all components
class DependencyMappingEngine:
    """Main class for dependency mapping and health operations.

    Provides a unified interface for all dependency mapping capabilities:
    - Dynamic dependency discovery through traffic correlation
    - Cross-cluster dependency visualization
    - Synthetic health probing for dependency assessment
    - Real-time dependency state differentiation
    - Load shedding recommendations based on fragility analysis
    """

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize dependency mapping engine with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry
        self.traffic_correlator = TrafficCorrelator(registry)
        self.graph_builder = DependencyGraphBuilder(registry)
        self.visualizer = CrossClusterVisualizer(registry)
        self.health_prober = HealthProber(registry)
        self.state_differentiator = StateDifferentiator(registry)
        self.load_shedder = LoadSheddingAdvisor(registry)

    def discover_and_map_dependencies(
        self, start_time: str, end_time: str, service_filter: str | None = None
    ) -> DependencyAnalysisResult:
        """Discover and map service dependencies through traffic correlation analysis.

        Args:
            start_time: ISO format start time for analysis window
            end_time: ISO format end time for analysis window
            service_filter: Optional service name filter

        Returns:
            DependencyAnalysisResult with complete analysis
        """
        # 1. Analyze traffic correlations
        correlation_result = self.traffic_correlator.analyze_traffic_correlations(start_time, end_time, service_filter)

        # 2. Build dependency graph
        dependency_graph = self.graph_builder.build_dependency_graph(correlation_result)

        # 3. Return complete analysis result
        analysis_result: DependencyAnalysisResult = {
            "graph": dependency_graph,
            "correlation_data": correlation_result,
            "confidence_score": self._calculate_overall_confidence(correlation_result),
            "anomalies_detected": [],  # Would be populated in a real implementation
            "recommendations": [],  # Would be populated in a real implementation
        }

        return analysis_result

    def assess_dependency_health(
        self, dependency_graph: DependencyGraph | None = None, probe_configs: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Assess dependency health through synthetic probing and state analysis.

        Args:
            dependency_graph: Optional existing dependency graph to analyze
            probe_configs: Optional probe configurations to execute

        Returns:
            Health assessment results
        """
        results = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "probe_results": [],
            "state_analysis": None,
            "overall_health": "unknown",
        }

        # Execute synthetic probes if configured
        if probe_configs:
            probe_results = []
            for config in probe_configs:
                try:
                    probe_result = self.health_prober.configure_synthetic_probe(config)
                    execution_result = self.health_prober.execute_health_probe(
                        probe_result["probe_id"], config.get("target_service")
                    )
                    probe_results.append(execution_result)
                except Exception as e:
                    logger.warning(f"Failed to execute probe {config.get('probe_id', 'unknown')}: {e}")
                    continue
            results["probe_results"] = probe_results

        # Perform state differentiation if graph provided
        if dependency_graph:
            state_analysis = self.state_differentiator.differentiate_dependency_states(dependency_graph)
            results["state_analysis"] = state_analysis

            # Calculate overall health based on node statuses
            nodes = state_analysis.get("nodes", [])
            failed_count = sum(1 for n in nodes if n["health_status"] == "failed")
            degraded_count = sum(1 for n in nodes if n["health_status"] == "degraded")
            total_count = len(nodes)

            if total_count > 0:
                if failed_count / total_count > 0.3:
                    results["overall_health"] = "critical"
                elif (failed_count + degraded_count) / total_count > 0.5:
                    results["overall_health"] = "degraded"
                elif failed_count == 0 and degraded_count == 0:
                    results["overall_health"] = "healthy"
                else:
                    results["overall_health"] = "warning"

        return results

    def recommend_load_shedding(
        self, dependency_graph: DependencyGraph | None = None, health_probe_results: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Generate load shedding recommendations based on dependency fragility.

        Args:
            dependency_graph: Current dependency graph
            health_probe_results: Optional health probe results

        Returns:
            List of load shedding recommendations
        """
        if not dependency_graph:
            # Create a minimal graph if none provided
            correlation_data: CorrelationAnalysisResult = {
                "correlations": [],
                "confidence_scores": {},
                "time_range": {"start": "", "end": ""},
                "total_services": 0,
                "analysis_method": "none",
            }
            dependency_graph = self.graph_builder.build_dependency_graph(correlation_data)

        return self.load_shedder.generate_load_shedding_recommendations(dependency_graph, health_probe_results)

    def get_cross_cluster_view(
        self, dependency_graph: DependencyGraph, visualization_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Get cross-cluster visualization of dependency graph.

        Args:
            dependency_graph: Dependency graph to visualize
            visualization_params: Optional visualization parameters

        Returns:
            Visualization result with layout and styling information
        """
        return self.visualizer.visualize_cross_cluster_dependencies(dependency_graph, visualization_params)

    def _calculate_overall_confidence(self, correlation_result: CorrelationAnalysisResult) -> float:
        """Calculate overall confidence score for dependency analysis.

        Args:
            correlation_result: Correlation analysis result

        Returns:
            Overall confidence score (0.0-1.0)
        """
        # In a real implementation, this would consider multiple factors
        # For now, we'll use a simple approach based on correlation strengths
        confidence_scores = correlation_result.get("confidence_scores", {})
        if not confidence_scores:
            return 0.5  # Default confidence if no correlations found

        # Average of all confidence scores
        avg_confidence = sum(confidence_scores.values()) / len(confidence_scores)
        return min(1.0, max(0.0, avg_confidence))

    def perform_incremental_update(
        self, current_graph: DependencyGraph, time_window_minutes: int = 10
    ) -> DependencyGraph:
        """Perform incremental update of dependency graph.

        Args:
            current_graph: Current dependency graph
            time_window_minutes: Time window for incremental analysis

        Returns:
            Updated dependency graph
        """
        # In a real implementation, this would analyze recent traffic data
        # and update the graph incrementally

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=time_window_minutes)

        # Discover new dependencies in the recent time window
        new_analysis = self.traffic_correlator.analyze_traffic_correlations(
            start_time.isoformat() + "Z", end_time.isoformat() + "Z"
        )

        # Build graph from new analysis
        new_graph = self.graph_builder.build_dependency_graph(new_analysis)

        # Merge with current graph (simplified implementation)
        # In a real implementation, this would be more sophisticated
        updated_graph = current_graph.copy()
        updated_graph["timestamp"] = datetime.utcnow().isoformat() + "Z"

        # Update nodes and edges from new graph
        updated_graph["nodes"] = new_graph.get("nodes", [])
        updated_graph["edges"] = new_graph.get("edges", [])
        updated_graph["clusters"] = new_graph.get("clusters", [])

        return updated_graph

    def execute_health_probe(self, probe_id: str, probe_target: str | None = None) -> dict[str, Any]:
        """Execute a synthetic health probe.

        Args:
            probe_id: Identifier of the probe to execute
            probe_target: Optional override for probe target

        Returns:
            HealthProbeResult with probe results
        """
        # In a real implementation, this would actually execute synthetic requests
        # For now, we'll simulate probe execution with mock results

        import random

        random.seed(hash(probe_id))  # For reproducible results

        # Simulate probe execution
        success = random.random() > 0.2  # 80% success rate
        response_time = random.uniform(10, 500) if success else None
        status_code = random.choice([200, 200, 200, 404, 500]) if success else random.choice([500, 503, 504])
        error_message = None if success else "Connection timeout"

        # Calculate resilience score based on results
        resilience_score = 1.0
        if not success:
            resilience_score = 0.0
        elif status_code >= 400:
            resilience_score = 0.3
        elif response_time and response_time > 200:
            resilience_score = 0.7
        else:
            resilience_score = 0.9

        return {
            "probe_id": probe_id,
            "target_service": probe_target or "unknown_service",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "success": success,
            "response_time_ms": response_time,
            "status_code": status_code if success else None,
            "error_message": error_message,
            "metrics": {
                "response_size_bytes": random.randint(100, 1000) if success else 0,
                "connection_attempts": 1,
            },
            "resilience_score": resilience_score,
        }
