"""Tests for the correlation engine."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from prometheus_mcp.correlation import (
    AlertGrouper,
    AlertMatcher,
    CascadeDetector,
    CorrelationEngine,
)
from prometheus_mcp.models import AMAlertItem


class TestAlertMatcher(unittest.TestCase):
    """Test alert matching functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.matcher = AlertMatcher()

    def test_calculate_temporal_similarity_within_window(self) -> None:
        """Test temporal similarity when alerts are within window."""
        # Create two alerts 2 minutes apart
        now = datetime.now(timezone.utc)
        alert1: AMAlertItem = {
            "labels": {},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": now.isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }
        alert2: AMAlertItem = {
            "labels": {},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": (now - timedelta(minutes=2)).isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }

        # Should be similar within 5 minute window
        result = self.matcher.calculate_temporal_similarity(alert1, alert2, 300)
        self.assertTrue(result)

    def test_calculate_temporal_similarity_outside_window(self) -> None:
        """Test temporal similarity when alerts are outside window."""
        # Create two alerts 10 minutes apart
        now = datetime.now(timezone.utc)
        alert1: AMAlertItem = {
            "labels": {},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": now.isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }
        alert2: AMAlertItem = {
            "labels": {},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": (now - timedelta(minutes=10)).isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }

        # Should not be similar within 5 minute window
        result = self.matcher.calculate_temporal_similarity(alert1, alert2, 300)
        self.assertFalse(result)

    def test_calculate_label_similarity_identical(self) -> None:
        """Test label similarity with identical labels."""
        labels1 = {"job": "api", "instance": "server1", "alertname": "HighCPU"}
        labels2 = {"job": "api", "instance": "server1", "alertname": "HighCPU"}

        similarity = self.matcher.calculate_label_similarity(labels1, labels2)
        self.assertEqual(similarity, 1.0)

    def test_calculate_label_similarity_partial(self) -> None:
        """Test label similarity with partially matching labels."""
        labels1 = {"job": "api", "instance": "server1", "alertname": "HighCPU"}
        labels2 = {"job": "api", "instance": "server2", "alertname": "HighMemory"}

        similarity = self.matcher.calculate_label_similarity(labels1, labels2)
        # Should be 1/5 since only 'job' matches out of 5 total key-value pairs
        self.assertAlmostEqual(similarity, 0.2, places=2)

    def test_calculate_label_similarity_no_match(self) -> None:
        """Test label similarity with no matching labels."""
        labels1 = {"job": "api", "instance": "server1"}
        labels2 = {"service": "database", "host": "db1"}

        similarity = self.matcher.calculate_label_similarity(labels1, labels2)
        self.assertEqual(similarity, 0.0)

    def test_calculate_label_similarity_empty(self) -> None:
        """Test label similarity with empty labels."""
        similarity = self.matcher.calculate_label_similarity({}, {})
        self.assertEqual(similarity, 1.0)


class TestAlertGrouper(unittest.TestCase):
    """Test alert grouping functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.grouper = AlertGrouper()

    def test_identify_service_identifier_job_priority(self) -> None:
        """Test service identification with job priority."""
        labels = {"job": "api-server", "service": "web-service", "app": "frontend", "instance": "server1"}

        service_id = self.grouper.identify_service_identifier(labels)
        self.assertEqual(service_id, "api-server")

    def test_identify_service_identifier_fallback_to_instance(self) -> None:
        """Test service identification falling back to instance."""
        labels = {"instance": "server1", "cluster": "prod"}

        service_id = self.grouper.identify_service_identifier(labels)
        self.assertEqual(service_id, "server1")

    def test_identify_service_identifier_unknown_service(self) -> None:
        """Test service identification with unknown service."""
        labels = {"cluster": "prod", "region": "us-west"}

        service_id = self.grouper.identify_service_identifier(labels)
        self.assertEqual(service_id, "unknown_service")

    def test_group_related_alerts(self) -> None:
        """Test grouping alerts by service identifier."""
        alerts: list[AMAlertItem] = [
            {
                "labels": {"job": "api", "instance": "server1"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            },
            {
                "labels": {"job": "api", "instance": "server2"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "2",
            },
            {
                "labels": {"job": "database", "instance": "db1"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "3",
            },
        ]

        groups = self.grouper.group_related_alerts(alerts)
        self.assertEqual(len(groups), 2)
        self.assertIn("api", groups)
        self.assertIn("database", groups)
        self.assertEqual(len(groups["api"]), 2)
        self.assertEqual(len(groups["database"]), 1)


class TestCascadeDetector(unittest.TestCase):
    """Test cascade detection functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.detector = CascadeDetector()

    def test_infer_dependency_direction_causal(self) -> None:
        """Test dependency inference when parent causes child."""
        now = datetime.now(timezone.utc)
        parent: AMAlertItem = {
            "labels": {},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": now.isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }
        child: AMAlertItem = {
            "labels": {},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": (now + timedelta(seconds=30)).isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }

        is_causal, strength = self.detector.infer_dependency_direction(parent, child)
        self.assertTrue(is_causal)
        self.assertGreater(strength, 0)

    def test_infer_dependency_direction_non_causal(self) -> None:
        """Test dependency inference when parent does not cause child."""
        now = datetime.now(timezone.utc)
        parent: AMAlertItem = {
            "labels": {},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": (now + timedelta(seconds=30)).isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }
        child: AMAlertItem = {
            "labels": {},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": now.isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }

        is_causal, strength = self.detector.infer_dependency_direction(parent, child)
        self.assertFalse(is_causal)
        self.assertEqual(strength, 0.0)

    def test_calculate_correlation_strength(self) -> None:
        """Test correlation strength calculation."""
        now = datetime.now(timezone.utc)
        alert1: AMAlertItem = {
            "labels": {"job": "api", "instance": "server1"},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": now.isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }
        alert2: AMAlertItem = {
            "labels": {"job": "api", "instance": "server2"},
            "annotations": {},
            "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
            "startsAt": (now + timedelta(seconds=30)).isoformat(),
            "endsAt": "",
            "generatorURL": "",
            "fingerprint": "",
        }

        strength = self.detector.calculate_correlation_strength(alert1, alert2)
        self.assertGreaterEqual(strength, 0.0)
        self.assertLessEqual(strength, 1.0)


class TestCorrelationEngine(unittest.TestCase):
    """Test the correlation engine."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock registry
        self.mock_registry = MagicMock()
        self.mock_client = MagicMock()

        # Set up mock alerts
        now = datetime.now(timezone.utc)
        self.mock_alerts = [
            {
                "labels": {"job": "api", "instance": "server1", "alertname": "HighCPU"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": now.isoformat(),
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            },
            {
                "labels": {"job": "api", "instance": "server2", "alertname": "HighMemory"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": (now + timedelta(seconds=30)).isoformat(),
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "2",
            },
        ]

        self.mock_client.get.return_value = self.mock_alerts
        self.mock_registry.all_alertmanager_clients.return_value = [self.mock_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_alertmanager_client.return_value = self.mock_client

    def test_correlate_alerts_across_instances(self) -> None:
        """Test cross-instance alert correlation."""
        engine = CorrelationEngine(self.mock_registry)

        result = engine.correlate_alerts_across_instances(temporal_window=300, similarity_threshold=0.5)

        # Should return a correlation result
        self.assertIn("total_correlations", result)
        self.assertIn("correlated_alerts", result)
        self.assertIn("groups", result)
        self.assertIn("cascades", result)
        self.assertIn("instance_attribution", result)

    def test_group_alerts_by_service(self) -> None:
        """Test alert grouping by service."""
        engine = CorrelationEngine(self.mock_registry)

        result = engine.group_alerts_by_service(self.mock_alerts)

        # Should return a group result
        self.assertIn("total_groups", result)
        self.assertIn("groups", result)
        self.assertIn("ungrouped_count", result)

    def test_detect_cascading_alerts(self) -> None:
        """Test cascading alert detection."""
        engine = CorrelationEngine(self.mock_registry)

        result = engine.detect_cascading_alerts(self.mock_alerts)

        # Should return a cascade detection result
        self.assertIn("total_cascades", result)
        self.assertIn("cascades", result)
        self.assertIn("root_causes", result)


if __name__ == "__main__":
    unittest.main()
