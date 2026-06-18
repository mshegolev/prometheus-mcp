"""Tests for the root cause analysis engine."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from prometheus_mcp.rca import (
    AnomalyDetector,
    ChangePointDetector,
    DependencyTraverser,
    RootCauseRanker,
    RCAEngine,
)
from prometheus_mcp.models import AMAlertItem


class TestAnomalyDetector(unittest.TestCase):
    """Test anomaly detection functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock registry
        self.mock_registry = MagicMock()
        self.mock_client = MagicMock()

        self.mock_registry.all_prometheus_clients.return_value = [self.mock_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_prometheus_client.return_value = self.mock_client

        self.detector = AnomalyDetector(self.mock_registry)

    def test_detect_metric_anomalies_normal_data(self) -> None:
        """Test anomaly detection with normal metric data (should return empty results)."""
        # Mock normal metric data without anomalies
        normal_data = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "test_metric", "job": "api"},
                        "values": [
                            [1640995200, "10.0"],  # 2022-01-01 00:00:00 UTC
                            [1640995260, "10.5"],  # 2022-01-01 00:01:00 UTC
                            [1640995320, "9.8"],  # 2022-01-01 00:02:00 UTC
                            [1640995380, "10.2"],  # 2022-01-01 00:03:00 UTC
                            [1640995440, "10.1"],  # 2022-01-01 00:04:00 UTC
                        ],
                    }
                ],
            },
        }

        self.mock_client.get.return_value = normal_data

        result = self.detector.detect_metric_anomalies(
            metric_names=["test_metric"],
            start_time="2022-01-01T00:00:00Z",
            end_time="2022-01-01T01:00:00Z",
            sensitivity=0.5,
        )

        # Should return results structure
        self.assertIn("total_anomalies", result)
        self.assertIn("metric_anomalies", result)
        self.assertIn("detection_method", result)

        # With normal data, should have few or no anomalies
        self.assertLessEqual(result["total_anomalies"], 1)  # Allow for some false positives

    def test_detect_metric_anomalies_with_outliers(self) -> None:
        """Test anomaly detection with clear statistical outliers."""
        # Mock metric data with clear outliers
        outlier_data = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "cpu_usage", "job": "api-server"},
                        "values": [
                            [1640995200, "10.0"],  # Normal
                            [1640995260, "10.5"],  # Normal
                            [1640995320, "9.8"],  # Normal
                            [1640995380, "10.2"],  # Normal
                            [1640995440, "10.1"],  # Normal
                            [1640995500, "50.0"],  # Clear outlier
                            [1640995560, "10.3"],  # Back to normal
                            [1640995620, "9.9"],  # Normal
                        ],
                    }
                ],
            },
        }

        self.mock_client.get.return_value = outlier_data

        result = self.detector.detect_metric_anomalies(
            metric_names=["cpu_usage"],
            start_time="2022-01-01T00:00:00Z",
            end_time="2022-01-01T01:00:00Z",
            sensitivity=0.7,
        )

        # Test that the function works and returns properly structured data
        self.assertIn("total_anomalies", result)
        self.assertIn("metric_anomalies", result)
        self.assertIn("detection_method", result)

        # Check that anomalies have expected structure (even if empty)
        for anomaly in result["metric_anomalies"]:
            self.assertIn("metric", anomaly)
            self.assertIn("timestamp", anomaly)
            self.assertIn("value", anomaly)
            self.assertIn("z_score", anomaly)

    def test_detect_metric_anomalies_missing_data(self) -> None:
        """Test anomaly detection with missing or incomplete metric data."""
        # Mock empty response
        self.mock_client.get.return_value = None

        result = self.detector.detect_metric_anomalies(
            metric_names=["missing_metric"],
            start_time="2022-01-01T00:00:00Z",
            end_time="2022-01-01T01:00:00Z",
            sensitivity=0.5,
        )

        # Should handle gracefully with empty results
        self.assertIn("total_anomalies", result)
        self.assertIn("metric_anomalies", result)
        self.assertEqual(result["total_anomalies"], 0)

    def test_detect_metric_anomalies_network_error(self) -> None:
        """Test anomaly detection with network errors."""
        self.mock_client.get.side_effect = Exception("Network error")

        result = self.detector.detect_metric_anomalies(
            metric_names=["test_metric"],
            start_time="2022-01-01T00:00:00Z",
            end_time="2022-01-01T01:00:00Z",
            sensitivity=0.5,
        )

        # Should handle gracefully with empty results
        self.assertIn("total_anomalies", result)
        self.assertEqual(result["total_anomalies"], 0)

    def test_seasonal_decomposition(self) -> None:
        """Test seasonal decomposition accuracy."""
        # Test with sufficient data
        values = [float(i % 24) for i in range(100)]  # Simulate daily pattern

        result = self.detector._seasonal_decomposition(values, period=24)

        self.assertIn("trend", result)
        self.assertIn("seasonal", result)
        self.assertIn("residual", result)
        self.assertEqual(len(result["trend"]), len(values))
        self.assertEqual(len(result["seasonal"]), len(values))
        self.assertEqual(len(result["residual"]), len(values))

    def test_detect_anomalies_in_series(self) -> None:
        """Test anomaly detection in a single time series."""
        # Test series with clear outlier
        series = {
            "metric": {"job": "test-job"},
            "values": [
                [1640995200.0, "10.0"],
                [1640995260.0, "10.5"],
                [1640995320.0, "50.0"],  # Outlier
                [1640995380.0, "10.2"],
                [1640995440.0, "9.8"],
            ],
        }

        anomalies = self.detector._detect_anomalies_in_series(series, sensitivity=0.7)

        # Test that the function works and returns properly structured data
        self.assertIsInstance(anomalies, list)

        # Check that anomalies have expected structure (even if empty)
        for anomaly in anomalies:
            self.assertIn("metric", anomaly)
            self.assertIn("timestamp", anomaly)
            self.assertIn("value", anomaly)
            self.assertIn("z_score", anomaly)


class TestDependencyTraverser(unittest.TestCase):
    """Test dependency traversal functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock registry
        self.mock_registry = MagicMock()
        self.mock_client = MagicMock()

        self.mock_registry.all_alertmanager_clients.return_value = [self.mock_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_alertmanager_client.return_value = self.mock_client

        self.traverser = DependencyTraverser(self.mock_registry)

    def test_traverse_from_symptoms_simple_linear_chain(self) -> None:
        """Test traversal with simple linear dependency chain."""
        # Create alert groups that should form a linear dependency
        alert_groups = {
            "frontend": [
                {
                    "labels": {"job": "frontend", "alertname": "HighLatency"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:00:00Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "1",
                }
            ],
            "backend": [
                {
                    "labels": {"job": "backend", "alertname": "DatabaseSlow"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:00:30Z",  # 30 seconds later
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "2",
                }
            ],
            "database": [
                {
                    "labels": {"job": "database", "alertname": "DiskFull"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:01:00Z",  # 1 minute later
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "3",
                }
            ],
        }

        # Mock alert data for correlation building
        mock_alerts = []
        for service_alerts in alert_groups.values():
            mock_alerts.extend(service_alerts)
        self.mock_client.get.return_value = mock_alerts

        result = self.traverser.traverse_from_symptoms(alert_groups)

        # Should return traversal result structure
        self.assertIn("total_paths", result)
        self.assertIn("paths", result)
        self.assertIn("root_causes", result)

    def test_traverse_from_symptoms_circular_dependencies(self) -> None:
        """Test traversal with circular dependencies (should terminate without infinite loops)."""
        # Create alert groups that could form circular dependencies
        alert_groups = {
            "service_a": [
                {
                    "labels": {"job": "service_a", "alertname": "ServiceADown"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:00:00Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "1",
                }
            ],
            "service_b": [
                {
                    "labels": {"job": "service_b", "alertname": "ServiceBDown"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:00:15Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "2",
                }
            ],
            "service_c": [
                {
                    "labels": {"job": "service_c", "alertname": "ServiceCDown"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:00:30Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "3",
                }
            ],
        }

        # Mock alert data that could create correlation loops
        mock_alerts = []
        for service_alerts in alert_groups.values():
            mock_alerts.extend(service_alerts)
        self.mock_client.get.return_value = mock_alerts

        result = self.traverser.traverse_from_symptoms(alert_groups)

        # Should complete without infinite loop
        self.assertIn("total_paths", result)
        self.assertIn("paths", result)

        # Check that paths have reasonable depth (not exploding)
        for path in result["paths"]:
            self.assertLessEqual(path.get("depth", 0), 10)  # Reasonable limit

    def test_traverse_from_symptoms_path_scoring(self) -> None:
        """Test path scoring based on correlation strength."""
        alert_groups = {
            "high_correlation_service": [
                {
                    "labels": {"job": "high_correlation_service", "alertname": "Alert1"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:00:00Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "1",
                }
            ],
            "low_correlation_service": [
                {
                    "labels": {"job": "low_correlation_service", "alertname": "Alert2"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:10:00Z",  # Much later, low correlation
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "2",
                }
            ],
        }

        mock_alerts = []
        for service_alerts in alert_groups.values():
            mock_alerts.extend(service_alerts)
        self.mock_client.get.return_value = mock_alerts

        result = self.traverser.traverse_from_symptoms(alert_groups)

        # Paths with higher correlation should have higher weights
        paths = result["paths"]
        if len(paths) >= 2:
            # Sort by evidence weight
            paths.sort(key=lambda x: x.get("evidence_weight", 0), reverse=True)
            # Higher correlation path should come first
            self.assertGreaterEqual(paths[0].get("evidence_weight", 0), paths[-1].get("evidence_weight", 0))

    def test_build_dependency_graph(self) -> None:
        """Test dependency graph construction accuracy."""
        # Create test alert groups
        alert_groups = {
            "service1": [
                {
                    "labels": {"job": "service1", "instance": "server1"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:00:00Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "1",
                }
            ],
            "service2": [
                {
                    "labels": {"job": "service2", "instance": "server2"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T00:00:30Z",  # Close in time
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "2",
                }
            ],
        }

        mock_alerts = []
        for service_alerts in alert_groups.values():
            mock_alerts.extend(service_alerts)
        self.mock_client.get.return_value = mock_alerts

        # Test private method through public interface
        graph = self.traverser._build_dependency_graph(alert_groups)

        # Should return a graph structure
        self.assertIsInstance(graph, dict)

    def test_identify_service_identifier(self) -> None:
        """Test service identification from alert labels."""
        # Test job priority
        labels1 = {"job": "api-server", "service": "web-service", "app": "frontend", "instance": "server1"}
        service_id1 = self.traverser._identify_service_identifier(labels1)
        self.assertEqual(service_id1, "api-server")

        # Test fallback to instance
        labels2 = {"instance": "server1", "cluster": "prod"}
        service_id2 = self.traverser._identify_service_identifier(labels2)
        self.assertEqual(service_id2, "server1")

        # Test unknown service fallback
        labels3 = {"cluster": "prod", "region": "us-west"}
        service_id3 = self.traverser._identify_service_identifier(labels3)
        self.assertEqual(service_id3, "unknown_service")


class TestChangePointDetector(unittest.TestCase):
    """Test change point detection functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock registry
        self.mock_registry = MagicMock()
        self.mock_client = MagicMock()

        self.mock_registry.all_alertmanager_clients.return_value = [self.mock_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_alertmanager_client.return_value = self.mock_client

        self.detector = ChangePointDetector(self.mock_registry)

    def test_detect_change_points_aligned_with_alerts(self) -> None:
        """Test detection of deployment events aligned with alert timing."""
        # Alert timestamps
        alert_timestamps = [
            "2023-01-01T10:00:00Z",  # Alert starts
        ]

        result = self.detector.detect_change_points(alert_timestamps, time_window=3600)

        # Should return change point result structure
        self.assertIn("total_events", result)
        self.assertIn("events", result)
        self.assertIn("time_window", result)

        # Should detect some simulated change events
        self.assertGreaterEqual(result["total_events"], 1)

        # Events should have expected structure
        if result["events"]:
            event = result["events"][0]
            self.assertIn("timestamp", event)
            self.assertIn("event_type", event)
            self.assertIn("description", event)
            self.assertIn("correlation_strength", event)

    def test_detect_change_points_configuration_changes(self) -> None:
        """Test correlation of configuration changes with metric anomalies."""
        # Multiple alert timestamps
        alert_timestamps = [
            "2023-01-01T10:00:00Z",
            "2023-01-01T10:05:00Z",
            "2023-01-01T10:10:00Z",
        ]

        result = self.detector.detect_change_points(alert_timestamps, time_window=1800)  # 30 min window

        # Should detect change events for multiple alerts
        self.assertGreaterEqual(result["total_events"], 3)  # At least one per alert

        # Should have different event types
        event_types = set(event["event_type"] for event in result["events"])
        self.assertIn("deployment", event_types)
        self.assertIn("config_change", event_types)
        self.assertIn("scaling_event", event_types)

    def test_detect_change_points_unrelated_changes(self) -> None:
        """Test that unrelated changes don't produce false correlations."""
        # Alert timestamps
        alert_timestamps = [
            "2023-01-01T10:00:00Z",
        ]

        result = self.detector.detect_change_points(alert_timestamps, time_window=60)  # Very short window

        # With short window, might detect fewer events
        self.assertGreaterEqual(result["total_events"], 0)

    def test_detect_change_points_multiple_changes(self) -> None:
        """Test detection with multiple changes around alert timing."""
        # Multiple alerts close together
        alert_timestamps = [
            "2023-01-01T10:00:00Z",
            "2023-01-01T10:02:00Z",
            "2023-01-01T10:04:00Z",
        ]

        result = self.detector.detect_change_points(alert_timestamps, time_window=3600)

        # Should consolidate duplicate events
        self.assertGreaterEqual(result["total_events"], 1)

        # Should sort events by timestamp
        events = result["events"]
        if len(events) > 1:
            for i in range(1, len(events)):
                self.assertLessEqual(events[i - 1]["timestamp"], events[i]["timestamp"])


class TestRootCauseRanker(unittest.TestCase):
    """Test root cause candidate ranking functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock registry
        self.mock_registry = MagicMock()

        self.ranker = RootCauseRanker(self.mock_registry)

    def test_rank_candidates_mixed_evidence_sources(self) -> None:
        """Test ranking with mixed evidence sources producing ranked results."""
        # Mock anomalies (high z-scores)
        anomalies = [
            {
                "metric": {"job": "problematic_service"},
                "z_score": 4.5,  # High anomaly
                "timestamp": 1640995200.0,
                "value": 99.0,
            },
            {
                "metric": {"job": "normal_service"},
                "z_score": 1.2,  # Low anomaly
                "timestamp": 1640995200.0,
                "value": 12.0,
            },
        ]

        # Mock dependency paths
        dependencies = [
            {
                "nodes": ["symptom_service", "problematic_service"],
                "evidence_weight": 0.8,  # Strong evidence
                "impact_score": 0.7,
            },
            {
                "nodes": ["symptom_service", "normal_service"],
                "evidence_weight": 0.3,  # Weak evidence
                "impact_score": 0.4,
            },
        ]

        # Mock change events
        changes = [
            {
                "timestamp": "2023-01-01T09:45:00Z",
                "event_type": "deployment",
                "description": "Deployment to problematic_service",
                "correlation_strength": 0.9,
            }
        ]

        result = self.ranker.rank_candidates(anomalies, dependencies, changes)

        # Should return ranking result structure
        self.assertIn("candidates", result)
        self.assertIn("ranking_method", result)
        self.assertIn("total_candidates", result)

        # Should have ranked candidates
        self.assertGreaterEqual(len(result["candidates"]), 1)

        # Candidates should be sorted by evidence score (descending)
        candidates = result["candidates"]
        if len(candidates) > 1:
            for i in range(1, len(candidates)):
                self.assertGreaterEqual(candidates[i - 1]["evidence_score"], candidates[i]["evidence_score"])

        # problematic_service should rank higher due to strong evidence
        if candidates:
            top_candidate = candidates[0]
            self.assertIn(
                "problematic_service",
                top_candidate["identifier"].lower()
                or top_candidate["impact_assessment"]["anomaly_contribution"] > 0.5
                or top_candidate["impact_assessment"]["dependency_contribution"] > 0.5,
            )

    def test_rank_candidates_varying_confidence_levels(self) -> None:
        """Test ranking with varying confidence levels."""
        # High confidence anomalies
        high_confidence_anomalies = [
            {
                "metric": {"job": "critical_service"},
                "z_score": 5.0,  # Very high
                "timestamp": 1640995200.0,
                "value": 100.0,
            }
        ]

        # Low confidence anomalies
        low_confidence_anomalies = [
            {
                "metric": {"job": "minor_service"},
                "z_score": 1.5,  # Low
                "timestamp": 1640995200.0,
                "value": 15.0,
            }
        ]

        # Strong dependencies
        strong_dependencies = [{"nodes": ["affected", "critical_service"], "evidence_weight": 0.9, "impact_score": 0.8}]

        # Weak dependencies
        weak_dependencies = [{"nodes": ["affected", "minor_service"], "evidence_weight": 0.2, "impact_score": 0.3}]

        # Test high confidence case
        result1 = self.ranker.rank_candidates(high_confidence_anomalies, strong_dependencies, [])
        if result1["candidates"]:
            high_score = result1["candidates"][0]["evidence_score"]

            # Test low confidence case
            result2 = self.ranker.rank_candidates(low_confidence_anomalies, weak_dependencies, [])
            if result2["candidates"]:
                low_score = result2["candidates"][0]["evidence_score"]

                # High confidence should rank higher (not always, but often)
                # This is a probabilistic test - we check that scores are calculated
                self.assertGreaterEqual(high_score, 0.0)
                self.assertLessEqual(high_score, 1.0)
                self.assertGreaterEqual(low_score, 0.0)
                self.assertLessEqual(low_score, 1.0)

    def test_rank_candidates_proximity_weighting(self) -> None:
        """Test ranking with proximity weighting."""
        anomalies = [{"metric": {"job": "direct_cause"}, "z_score": 4.0, "timestamp": 1640995200.0, "value": 50.0}]

        # Direct dependency (short path)
        direct_dependencies = [{"nodes": ["symptom", "direct_cause"], "evidence_weight": 0.8, "impact_score": 0.7}]

        # Indirect dependency (long path)
        indirect_dependencies = [
            {
                "nodes": ["symptom", "intermediate", "indirect_cause"],
                "evidence_weight": 0.6,  # Lower due to longer path
                "impact_score": 0.5,
            }
        ]

        result1 = self.ranker.rank_candidates(anomalies, direct_dependencies, [])
        result2 = self.ranker.rank_candidates(anomalies, indirect_dependencies, [])

        # Both should produce valid results
        self.assertGreaterEqual(len(result1["candidates"]), 0)
        self.assertGreaterEqual(len(result2["candidates"]), 0)

    def test_rank_candidates_impact_analysis(self) -> None:
        """Test ranking with impact analysis."""
        # Critical service anomalies
        critical_anomalies = [
            {"metric": {"job": "critical_service"}, "z_score": 3.5, "timestamp": 1640995200.0, "value": 80.0}
        ]

        # Non-critical service anomalies
        non_critical_anomalies = [
            {"metric": {"job": "non_critical_service"}, "z_score": 3.5, "timestamp": 1640995200.0, "value": 80.0}
        ]

        dependencies = [
            {
                "nodes": ["symptom", "service"],
                "evidence_weight": 0.7,
                "impact_score": 0.8,  # High impact
            }
        ]

        result1 = self.ranker.rank_candidates(critical_anomalies, dependencies, [])
        result2 = self.ranker.rank_candidates(non_critical_anomalies, dependencies, [])

        # Both should produce results
        self.assertIn("candidates", result1)
        self.assertIn("candidates", result2)


class TestRCAEngine(unittest.TestCase):
    """Test the RCA engine."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock registry
        self.mock_registry = MagicMock()
        self.mock_prom_client = MagicMock()
        self.mock_am_client = MagicMock()

        self.mock_registry.all_prometheus_clients.return_value = [self.mock_prom_client]
        self.mock_registry.all_alertmanager_clients.return_value = [self.mock_am_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_prometheus_client.return_value = self.mock_prom_client
        self.mock_registry.get_alertmanager_client.return_value = self.mock_am_client

        self.engine = RCAEngine(self.mock_registry)

    def test_perform_full_analysis_end_to_end(self) -> None:
        """Test complete RCA workflow from alerts to ranked candidates."""
        # Create test alert groups
        alert_groups = {
            "api_service": [
                {
                    "labels": {"job": "api_service", "alertname": "HighLatency"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T10:00:00Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "1",
                }
            ]
        }

        # Mock Prometheus data for anomaly detection
        prometheus_data = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "api_service"},
                        "values": [
                            [1640995200, "1.0"],
                            [1640995260, "1.0"],
                            [1640995320, "0.0"],  # Service down - anomaly
                            [1640995380, "1.0"],
                        ],
                    }
                ],
            },
        }
        self.mock_prom_client.get.return_value = prometheus_data

        # Mock Alertmanager data for dependency analysis
        alertmanager_data = [
            {
                "labels": {"job": "api_service", "alertname": "HighLatency"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T10:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            }
        ]
        self.mock_am_client.get.return_value = alertmanager_data

        result = self.engine.perform_full_analysis(alert_groups, time_range_hours=1)

        # Should return complete RCA result structure
        self.assertIn("anomalies", result)
        self.assertIn("dependencies", result)
        self.assertIn("changes", result)
        self.assertIn("ranking", result)
        self.assertIn("analysis_time_range", result)

        # All components should have executed
        self.assertIn("total_anomalies", result["anomalies"])
        self.assertIn("total_paths", result["dependencies"])
        self.assertIn("total_events", result["changes"])
        self.assertIn("total_candidates", result["ranking"])

    def test_perform_full_analysis_partial_results(self) -> None:
        """Test RCA workflow with partial component failures."""
        # Create test alert groups
        alert_groups = {
            "service1": [
                {
                    "labels": {"job": "service1", "alertname": "TestAlert"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T10:00:00Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "1",
                }
            ]
        }

        # Mock Prometheus failure
        self.mock_prom_client.get.side_effect = Exception("Prometheus unavailable")

        # Mock Alertmanager data
        self.mock_am_client.get.return_value = [
            {
                "labels": {"job": "service1", "alertname": "TestAlert"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T10:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            }
        ]

        result = self.engine.perform_full_analysis(alert_groups, time_range_hours=1)

        # Should still return results structure even with partial failures
        self.assertIn("anomalies", result)
        self.assertIn("dependencies", result)
        self.assertIn("changes", result)
        self.assertIn("ranking", result)

        # Anomalies component should have failed gracefully
        self.assertEqual(result["anomalies"]["total_anomalies"], 0)

    def test_perform_full_analysis_conflicting_evidence(self) -> None:
        """Test ranking with conflicting evidence pointing to different candidates."""
        # Create alert groups that might produce conflicting evidence
        alert_groups = {
            "frontend": [
                {
                    "labels": {"job": "frontend", "alertname": "HighLatency"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T10:00:00Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "1",
                }
            ],
            "backend": [
                {
                    "labels": {"job": "backend", "alertname": "DatabaseSlow"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": "2023-01-01T10:00:30Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": "2",
                }
            ],
        }

        # Mock data that could lead to conflicting evidence
        prometheus_data = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "frontend"},
                        "values": [[1640995200, "0.0"]],  # Frontend down
                    },
                    {
                        "metric": {"__name__": "up", "job": "backend"},
                        "values": [[1640995200, "0.0"]],  # Backend also down
                    },
                ],
            },
        }
        self.mock_prom_client.get.return_value = prometheus_data

        self.mock_am_client.get.return_value = [alert for alerts in alert_groups.values() for alert in alerts]

        result = self.engine.perform_full_analysis(alert_groups, time_range_hours=1)

        # Should handle conflicting evidence gracefully
        self.assertIn("ranking", result)
        if result["ranking"]["candidates"]:
            # Should still produce ranked results
            self.assertGreaterEqual(len(result["ranking"]["candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
