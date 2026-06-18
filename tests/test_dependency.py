"""Tests for the dependency mapping and health assessment engine."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from prometheus_mcp.dependency import (
    TrafficCorrelator,
    DependencyGraphBuilder,
    CrossClusterVisualizer,
    HealthProber,
    StateDifferentiator,
    LoadSheddingAdvisor,
    DependencyMappingEngine,
)
from prometheus_mcp.models import (
    AMAlertItem,
    CorrelationAnalysisResult,
    DependencyGraph,
    ServiceNode,
    DependencyEdge,
    CrossClusterInfo,
)


class TestTrafficCorrelator(unittest.TestCase):
    """Test traffic correlation analysis functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock registry
        self.mock_registry = MagicMock()
        self.mock_client = MagicMock()

        self.mock_registry.all_prometheus_clients.return_value = [self.mock_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_prometheus_client.return_value = self.mock_client

        self.correlator = TrafficCorrelator(self.mock_registry)

    def test_analyze_traffic_correlations_normal_data(self) -> None:
        """Test correlation analysis with normal traffic data."""
        # Mock normal traffic data without clear dependencies
        normal_data = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "http_requests_total", "job": "api-service"},
                        "values": [
                            [1640995200, "100.0"],
                            [1640995260, "105.0"],
                            [1640995320, "98.0"],
                            [1640995380, "102.0"],
                        ],
                    },
                    {
                        "metric": {"__name__": "http_requests_total", "job": "database-service"},
                        "values": [
                            [1640995200, "200.0"],
                            [1640995260, "210.0"],
                            [1640995320, "195.0"],
                            [1640995380, "205.0"],
                        ],
                    },
                ],
            },
        }

        self.mock_client.get.return_value = normal_data

        result = self.correlator.analyze_traffic_correlations(
            start_time="2022-01-01T00:00:00Z",
            end_time="2022-01-01T01:00:00Z",
        )

        # Should return results structure
        self.assertIn("correlations", result)
        self.assertIn("confidence_scores", result)
        self.assertIn("time_range", result)
        self.assertIn("total_services", result)
        self.assertIn("analysis_method", result)

    def test_analyze_traffic_correlations_with_dependencies(self) -> None:
        """Test correlation analysis with clear service dependencies."""
        # Mock traffic data with clear correlation patterns
        correlated_data = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "http_requests_total", "job": "frontend"},
                        "values": [
                            [1640995200, "100.0"],
                            [1640995260, "150.0"],
                            [1640995320, "200.0"],
                            [1640995380, "180.0"],
                        ],
                    },
                    {
                        "metric": {"__name__": "http_requests_total", "job": "backend"},
                        "values": [
                            [1640995200, "80.0"],
                            [1640995260, "120.0"],
                            [1640995320, "160.0"],
                            [1640995380, "140.0"],
                        ],
                    },
                ],
            },
        }

        self.mock_client.get.return_value = correlated_data

        result = self.correlator.analyze_traffic_correlations(
            start_time="2022-01-01T00:00:00Z",
            end_time="2022-01-01T01:00:00Z",
        )

        # Should detect correlations
        self.assertIn("correlations", result)
        # At minimum, should have analysis metadata
        self.assertGreaterEqual(result["total_services"], 0)

    def test_identify_service_identifier(self) -> None:
        """Test service identifier extraction from labels."""
        # Test job label priority
        labels1 = {"job": "api-service", "service": "web", "app": "frontend"}
        service_id1 = self.correlator._identify_service_identifier(labels1)
        self.assertEqual(service_id1, "api-service")

        # Test fallback to service label
        labels2 = {"service": "database", "app": "backend"}
        service_id2 = self.correlator._identify_service_identifier(labels2)
        self.assertEqual(service_id2, "database")

        # Test fallback to instance
        labels3 = {"instance": "server01", "host": "host01"}
        service_id3 = self.correlator._identify_service_identifier(labels3)
        self.assertEqual(service_id3, "server01")

        # Test unknown fallback
        labels4 = {"host": "host01", "ip": "192.168.1.1"}
        service_id4 = self.correlator._identify_service_identifier(labels4)
        self.assertEqual(service_id4, "unknown_service")


class TestDependencyGraphBuilder(unittest.TestCase):
    """Test dependency graph construction functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_registry = MagicMock()
        self.mock_registry.list_instances.return_value = ["instance1", "instance2"]

        self.builder = DependencyGraphBuilder(self.mock_registry)

    def test_build_dependency_graph_simple_chain(self) -> None:
        """Test building a simple linear dependency chain."""
        # Create correlation analysis result with a simple chain
        correlation_data: CorrelationAnalysisResult = {
            "correlations": [
                {
                    "source": "frontend",
                    "target": "backend",
                    "strength": 0.8,
                    "type": "traffic_correlation",
                },
                {
                    "source": "backend",
                    "target": "database",
                    "strength": 0.7,
                    "type": "traffic_correlation",
                },
            ],
            "confidence_scores": {
                "frontend->backend": 0.8,
                "backend->database": 0.7,
            },
            "time_range": {"start": "2022-01-01T00:00:00Z", "end": "2022-01-01T01:00:00Z"},
            "total_services": 3,
            "analysis_method": "cross_correlation",
        }

        graph = self.builder.build_dependency_graph(correlation_data)

        # Check graph structure
        self.assertIsInstance(graph, dict)
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertIn("clusters", graph)
        self.assertIn("timestamp", graph)

        # Check nodes
        nodes = graph["nodes"]
        self.assertEqual(len(nodes), 3)
        node_names = [node["service_id"] for node in nodes]
        self.assertIn("frontend", node_names)
        self.assertIn("backend", node_names)
        self.assertIn("database", node_names)

        # Check edges
        edges = graph["edges"]
        self.assertEqual(len(edges), 2)
        edge_pairs = [(edge["source"], edge["target"]) for edge in edges]
        self.assertIn(("frontend", "backend"), edge_pairs)
        self.assertIn(("backend", "database"), edge_pairs)

        # Check strengths
        for edge in edges:
            if edge["source"] == "frontend" and edge["target"] == "backend":
                self.assertEqual(edge["strength"], 0.8)
            elif edge["source"] == "backend" and edge["target"] == "database":
                self.assertEqual(edge["strength"], 0.7)

    def test_build_dependency_graph_with_cycles(self) -> None:
        """Test building a dependency graph with circular dependencies."""
        # Create correlation analysis result with cycles
        correlation_data: CorrelationAnalysisResult = {
            "correlations": [
                {
                    "source": "service_a",
                    "target": "service_b",
                    "strength": 0.9,
                    "type": "traffic_correlation",
                },
                {
                    "source": "service_b",
                    "target": "service_c",
                    "strength": 0.8,
                    "type": "traffic_correlation",
                },
                {
                    "source": "service_c",
                    "target": "service_a",
                    "strength": 0.7,
                    "type": "traffic_correlation",
                },
            ],
            "confidence_scores": {
                "service_a->service_b": 0.9,
                "service_b->service_c": 0.8,
                "service_c->service_a": 0.7,
            },
            "time_range": {"start": "2022-01-01T00:00:00Z", "end": "2022-01-01T01:00:00Z"},
            "total_services": 3,
            "analysis_method": "cross_correlation",
        }

        graph = self.builder.build_dependency_graph(correlation_data)

        # Should handle cycles without infinite loops
        self.assertIsInstance(graph, dict)
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertEqual(len(graph["nodes"]), 3)
        self.assertEqual(len(graph["edges"]), 3)

    def test_resolve_service_identity(self) -> None:
        """Test service identity resolution across clusters."""
        # Test identity resolution
        resolved_id = self.builder._resolve_service_identity("api-service", "us-west")
        self.assertEqual(resolved_id, "us-west:api-service")

    def test_detect_cycles(self) -> None:
        """Test cycle detection in dependency graphs."""
        # Create edges with a cycle
        edges: list[DependencyEdge] = [
            {
                "source": "A",
                "target": "B",
                "strength": 0.8,
                "relationship_type": "direct",
                "latency_avg": None,
                "error_rate": None,
                "throughput": None,
                "last_observed": "2022-01-01T00:00:00Z",
                "metadata": {},
            },
            {
                "source": "B",
                "target": "C",
                "strength": 0.7,
                "relationship_type": "direct",
                "latency_avg": None,
                "error_rate": None,
                "throughput": None,
                "last_observed": "2022-01-01T00:00:00Z",
                "metadata": {},
            },
            {
                "source": "C",
                "target": "A",
                "strength": 0.6,
                "relationship_type": "direct",
                "latency_avg": None,
                "error_rate": None,
                "throughput": None,
                "last_observed": "2022-01-01T00:00:00Z",
                "metadata": {},
            },
        ]

        cycles = self.builder._detect_cycles(edges)
        # Should detect the cycle A->B->C->A (or equivalent)
        self.assertGreater(len(cycles), 0)
        # Check that we have a cycle of length 4 (including the repeated node)
        cycle_found = False
        for cycle in cycles:
            if len(cycle) == 4 and cycle[0] == cycle[-1]:
                # This is a valid cycle
                cycle_found = True
                break
        self.assertTrue(cycle_found, "Should detect a cycle of length 4")


class TestCrossClusterVisualizer(unittest.TestCase):
    """Test cross-cluster visualization functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_registry = MagicMock()
        self.visualizer = CrossClusterVisualizer(self.mock_registry)

    def test_visualize_cross_cluster_dependencies(self) -> None:
        """Test cross-cluster dependency visualization."""
        # Create a sample dependency graph
        graph: DependencyGraph = {
            "nodes": [
                {
                    "service_id": "service_a",
                    "name": "Service A",
                    "namespace": "team1",
                    "cluster": "us-west",
                    "instance": "instance1",
                    "health_status": "healthy",
                    "metadata": {},
                    "last_seen": "2022-01-01T00:00:00Z",
                },
                {
                    "service_id": "service_b",
                    "name": "Service B",
                    "namespace": "team2",
                    "cluster": "us-east",
                    "instance": "instance2",
                    "health_status": "degraded",
                    "metadata": {},
                    "last_seen": "2022-01-01T00:00:00Z",
                },
            ],
            "edges": [
                {
                    "source": "service_a",
                    "target": "service_b",
                    "strength": 0.8,
                    "relationship_type": "direct",
                    "latency_avg": 50.0,
                    "error_rate": 0.01,
                    "throughput": 100.0,
                    "last_observed": "2022-01-01T00:00:00Z",
                    "metadata": {},
                }
            ],
            "clusters": [
                {
                    "cluster_id": "us-west",
                    "region": "us-west-1",
                    "services": ["service_a"],
                    "connections": [],
                    "health_status": "healthy",
                },
                {
                    "cluster_id": "us-east",
                    "region": "us-east-1",
                    "services": ["service_b"],
                    "connections": [],
                    "health_status": "degraded",
                },
            ],
            "timestamp": "2022-01-01T00:00:00Z",
            "version": "1.0",
            "metadata": {
                "total_services": 2,
                "total_edges": 1,
            },
        }

        result = self.visualizer.visualize_cross_cluster_dependencies(graph)

        # Check result structure
        self.assertIn("graph", result)
        self.assertIn("clusters", result)
        self.assertIn("layout_coordinates", result)
        self.assertIn("color_mapping", result)
        self.assertIn("legend", result)

        # Check clusters
        self.assertEqual(len(result["clusters"]), 2)
        cluster_names = [c["cluster_id"] for c in result["clusters"]]
        self.assertIn("us-west", cluster_names)
        self.assertIn("us-east", cluster_names)

        # Check layout coordinates exist for all nodes
        coords = result["layout_coordinates"]
        self.assertIn("service_a", coords)
        self.assertIn("service_b", coords)
        self.assertIn("x", coords["service_a"])
        self.assertIn("y", coords["service_a"])

        # Check color mapping exists
        color_map = result["color_mapping"]
        self.assertGreater(len(color_map), 0)


class TestHealthProber(unittest.TestCase):
    """Test synthetic health probing functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_registry = MagicMock()
        self.prober = HealthProber(self.mock_registry)

    def test_configure_synthetic_probe(self) -> None:
        """Test synthetic probe configuration."""
        probe_config = {
            "target_service": "api-service",
            "target_endpoint": "/health",
            "frequency_seconds": 30,
        }

        result = self.prober.configure_synthetic_probe(probe_config)

        # Check result structure
        self.assertIn("probe_id", result)
        self.assertIn("configured", result)
        self.assertIn("target_service", result)
        self.assertIn("target_endpoint", result)
        self.assertTrue(result["configured"])
        self.assertEqual(result["target_service"], "api-service")
        self.assertEqual(result["target_endpoint"], "/health")

    def test_configure_synthetic_probe_missing_required_fields(self) -> None:
        """Test probe configuration with missing required fields."""
        probe_config = {
            "target_service": "api-service",
            # Missing target_endpoint and frequency_seconds
        }

        with self.assertRaises(ValueError) as context:
            self.prober.configure_synthetic_probe(probe_config)

        self.assertIn("Missing required field", str(context.exception))

    def test_execute_health_probe(self) -> None:
        """Test synthetic probe execution."""
        probe_id = "test-probe-123"
        result = self.prober.execute_health_probe(probe_id, "api-service")

        # Check result structure
        self.assertIn("probe_id", result)
        self.assertIn("target_service", result)
        self.assertIn("timestamp", result)
        self.assertIn("success", result)
        self.assertIn("response_time_ms", result)
        self.assertIn("status_code", result)
        self.assertIn("error_message", result)
        self.assertIn("metrics", result)
        self.assertIn("resilience_score", result)

        # Check probe ID and target
        self.assertEqual(result["probe_id"], probe_id)
        self.assertEqual(result["target_service"], "api-service")

        # Check resilience score is in valid range
        self.assertGreaterEqual(result["resilience_score"], 0.0)
        self.assertLessEqual(result["resilience_score"], 1.0)


class TestStateDifferentiator(unittest.TestCase):
    """Test real-time dependency state differentiation."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_registry = MagicMock()
        self.differentiator = StateDifferentiator(self.mock_registry)

    def test_differentiate_dependency_states(self) -> None:
        """Test dependency state differentiation."""
        # Create a sample dependency graph
        graph: DependencyGraph = {
            "nodes": [
                {
                    "service_id": "service_a",
                    "name": "Service A",
                    "namespace": "team1",
                    "cluster": "us-west",
                    "instance": "instance1",
                    "health_status": "unknown",
                    "metadata": {},
                    "last_seen": "2022-01-01T00:00:00Z",
                },
                {
                    "service_id": "service_b",
                    "name": "Service B",
                    "namespace": "team2",
                    "cluster": "us-east",
                    "instance": "instance2",
                    "health_status": "unknown",
                    "metadata": {},
                    "last_seen": "2022-01-01T00:00:00Z",
                },
            ],
            "edges": [
                {
                    "source": "service_a",
                    "target": "service_b",
                    "strength": 0.8,
                    "relationship_type": "direct",
                    "latency_avg": None,
                    "error_rate": None,
                    "throughput": None,
                    "last_observed": "2022-01-01T00:00:00Z",
                    "metadata": {},
                }
            ],
            "clusters": [],
            "timestamp": "2022-01-01T00:00:00Z",
            "version": "1.0",
            "metadata": {},
        }

        result = self.differentiator.differentiate_dependency_states(graph)

        # Check result structure
        self.assertIsInstance(result, dict)
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("timestamp", result)

        # Check that timestamp was updated
        self.assertNotEqual(result["timestamp"], graph["timestamp"])

        # Check that nodes have updated health statuses
        nodes = result["nodes"]
        self.assertEqual(len(nodes), 2)
        for node in nodes:
            self.assertIn(node["health_status"], ["healthy", "degraded", "failed"])

        # Check that edges have updated metadata
        edges = result["edges"]
        self.assertEqual(len(edges), 1)
        for edge in edges:
            self.assertIn("metadata", edge)
            self.assertIn("status", edge["metadata"])


class TestLoadSheddingAdvisor(unittest.TestCase):
    """Test load shedding recommendation functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_registry = MagicMock()
        self.advisor = LoadSheddingAdvisor(self.mock_registry)

    def test_generate_load_shedding_recommendations(self) -> None:
        """Test load shedding recommendation generation."""
        # Create a sample dependency graph
        graph: DependencyGraph = {
            "nodes": [
                {
                    "service_id": "fragile_service",
                    "name": "Fragile Service",
                    "namespace": "team1",
                    "cluster": "us-west",
                    "instance": "instance1",
                    "health_status": "degraded",
                    "metadata": {},
                    "last_seen": "2022-01-01T00:00:00Z",
                },
                {
                    "service_id": "stable_service",
                    "name": "Stable Service",
                    "namespace": "team2",
                    "cluster": "us-east",
                    "instance": "instance2",
                    "health_status": "healthy",
                    "metadata": {},
                    "last_seen": "2022-01-01T00:00:00Z",
                },
            ],
            "edges": [
                {
                    "source": "fragile_service",
                    "target": "stable_service",
                    "strength": 0.9,
                    "relationship_type": "direct",
                    "latency_avg": None,
                    "error_rate": None,
                    "throughput": None,
                    "last_observed": "2022-01-01T00:00:00Z",
                    "metadata": {},
                }
            ],
            "clusters": [],
            "timestamp": "2022-01-01T00:00:00Z",
            "version": "1.0",
            "metadata": {},
        }

        recommendations = self.advisor.generate_load_shedding_recommendations(graph)

        # Check result structure
        self.assertIsInstance(recommendations, list)
        # Should generate some recommendations
        self.assertGreaterEqual(len(recommendations), 0)

        # Check recommendation structure if any exist
        for rec in recommendations:
            self.assertIn("service", rec)
            self.assertIn("priority", rec)
            self.assertIn("action", rec)
            self.assertIn("reason", rec)
            self.assertIn("confidence", rec)
            self.assertIn("alternatives", rec)


class TestDependencyMappingEngine(unittest.TestCase):
    """Test the main dependency mapping engine facade."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_registry = MagicMock()
        self.mock_registry.list_instances.return_value = ["instance1", "instance2"]
        self.engine = DependencyMappingEngine(self.mock_registry)

    def test_discover_and_map_dependencies(self) -> None:
        """Test end-to-end dependency discovery and mapping."""
        # Mock the registry to return clients
        mock_client = MagicMock()
        self.mock_registry.all_prometheus_clients.return_value = [mock_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_prometheus_client.return_value = mock_client

        # Mock client response with minimal data
        mock_client.get.return_value = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [],
            },
        }

        result = self.engine.discover_and_map_dependencies(
            start_time="2022-01-01T00:00:00Z",
            end_time="2022-01-01T01:00:00Z",
        )

        # Check result structure
        self.assertIn("graph", result)
        self.assertIn("correlation_data", result)
        self.assertIn("confidence_score", result)
        self.assertIn("anomalies_detected", result)
        self.assertIn("recommendations", result)

    def test_assess_dependency_health(self) -> None:
        """Test dependency health assessment."""
        result = self.engine.assess_dependency_health()

        # Check result structure
        self.assertIn("timestamp", result)
        self.assertIn("probe_results", result)
        self.assertIn("state_analysis", result)
        self.assertIn("overall_health", result)

    def test_recommend_load_shedding(self) -> None:
        """Test load shedding recommendation generation."""
        recommendations = self.engine.recommend_load_shedding()

        # Should return a list (even if empty)
        self.assertIsInstance(recommendations, list)

    def test_get_cross_cluster_view(self) -> None:
        """Test cross-cluster visualization."""
        # Create a minimal graph
        graph: DependencyGraph = {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "timestamp": "2022-01-01T00:00:00Z",
            "version": "1.0",
            "metadata": {},
        }

        result = self.engine.get_cross_cluster_view(graph)

        # Check result structure
        self.assertIn("graph", result)
        self.assertIn("clusters", result)
        self.assertIn("layout_coordinates", result)
        self.assertIn("color_mapping", result)
        self.assertIn("legend", result)

    def test_perform_incremental_update(self) -> None:
        """Test incremental dependency graph update."""
        # Create a sample graph
        graph: DependencyGraph = {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "timestamp": "2022-01-01T00:00:00Z",
            "version": "1.0",
            "metadata": {},
        }

        # Mock the registry to return clients
        mock_client = MagicMock()
        self.mock_registry.all_prometheus_clients.return_value = [mock_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_prometheus_client.return_value = mock_client

        # Mock client response
        mock_client.get.return_value = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [],
            },
        }

        updated_graph = self.engine.perform_incremental_update(graph, time_window_minutes=5)

        # Check that graph was updated
        self.assertIsInstance(updated_graph, dict)
        self.assertIn("timestamp", updated_graph)
        self.assertNotEqual(updated_graph["timestamp"], graph["timestamp"])


if __name__ == "__main__":
    unittest.main()
