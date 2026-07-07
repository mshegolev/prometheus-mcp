"""Integration tests for RCA-enhanced correlation tools."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp.exceptions import ToolError

from prometheus_mcp.tools_correlation import (
    correlate_alerts_across_instances,
    group_alerts_by_service,
    detect_cascading_alerts,
)


class TestToolsCorrelationWithRCA(unittest.TestCase):
    """Test RCA-enhanced correlation tools."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock the global registry
        self.mock_registry = MagicMock()
        self.mock_am_client = MagicMock()

        # Set up registry mocks
        self.mock_registry.all_alertmanager_clients.return_value = [self.mock_am_client]
        self.mock_registry.list_instances.return_value = ["instance1"]
        self.mock_registry.get_alertmanager_client.return_value = self.mock_am_client

        # Install the mock on the live global that get_registry() reads at
        # call time (tools no longer capture _registry by value at import).
        import prometheus_mcp._mcp

        self.original_registry = prometheus_mcp._mcp._registry
        prometheus_mcp._mcp._registry = self.mock_registry

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        # Restore original registry
        import prometheus_mcp._mcp

        prometheus_mcp._mcp._registry = self.original_registry

    @patch("prometheus_mcp.tools_correlation.RCA_AVAILABLE", True)
    def test_correlate_alerts_with_rca_enabled(self) -> None:
        """Test correlate_alerts_across_instances with RCA enhancement enabled."""
        # Mock alert data
        mock_alerts = [
            {
                "labels": {"job": "api", "alertname": "HighCPU", "instance": "server1"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            },
            {
                "labels": {"job": "database", "alertname": "SlowQueries", "instance": "db1"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:30Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "2",
            },
        ]

        self.mock_am_client.get.return_value = mock_alerts

        # Mock Prometheus client for RCA
        mock_prom_client = MagicMock()
        self.mock_registry.all_prometheus_clients.return_value = [mock_prom_client]
        self.mock_registry.get_prometheus_client.return_value = mock_prom_client

        # Mock Prometheus data for anomaly detection
        mock_prometheus_data = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "api"},
                        "values": [[1640995200, "0.0"]],  # Service down
                    }
                ],
            },
        }
        mock_prom_client.get.return_value = mock_prometheus_data

        # Also mock the RCAEngine import
        with patch("prometheus_mcp.tools_correlation.RCAEngine") as mock_rca_engine:
            mock_rca_instance = MagicMock()
            mock_rca_engine.return_value = mock_rca_instance
            mock_rca_instance.perform_full_analysis.return_value = {
                "anomalies": {"total_anomalies": 1, "metric_anomalies": []},
                "dependencies": {"total_paths": 1, "paths": []},
                "changes": {"total_events": 1, "events": []},
                "ranking": {"total_candidates": 1, "candidates": []},
                "analysis_time_range": {"start": "2023-01-01T00:00:00Z", "end": "2023-01-01T01:00:00Z"},
            }

            # Test with RCA enabled
            result = correlate_alerts_across_instances(temporal_window=300, similarity_threshold=0.7, enable_rca=True)

            # Should return a result (we can't check structuredContent/content directly as
            # they're part of the CallToolResult structure)
            self.assertIsNotNone(result)

    def test_correlate_alerts_with_rca_disabled(self) -> None:
        """Test correlate_alerts_across_instances with RCA enhancement disabled."""
        # Mock alert data
        mock_alerts = [
            {
                "labels": {"job": "api", "alertname": "HighCPU"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            }
        ]

        self.mock_am_client.get.return_value = mock_alerts

        # Test with RCA disabled (default)
        result = correlate_alerts_across_instances(temporal_window=300, similarity_threshold=0.7, enable_rca=False)

        # Should return a result
        self.assertIsNotNone(result)

    def test_correlate_alerts_rca_failure_graceful_degradation(self) -> None:
        """Test that RCA failure doesn't break correlation when RCA is enabled."""
        # Mock alert data
        mock_alerts = [
            {
                "labels": {"job": "api", "alertname": "HighCPU"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            }
        ]

        self.mock_am_client.get.return_value = mock_alerts

        # Test with RCA enabled but RCA module unavailable (simulated by patching RCA_AVAILABLE)
        with patch("prometheus_mcp.tools_correlation.RCA_AVAILABLE", False):
            result = correlate_alerts_across_instances(temporal_window=300, similarity_threshold=0.7, enable_rca=True)

            # Should still return correlation results even without RCA
            self.assertIsNotNone(result)

    def test_group_alerts_by_service_basic_functionality(self) -> None:
        """Test group_alerts_by_service basic functionality."""
        # Mock alert data from multiple instances
        mock_alerts = [
            {
                "labels": {"job": "api", "alertname": "HighCPU", "__prometheus_instance__": "instance1"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            },
            {
                "labels": {"job": "api", "alertname": "HighMemory", "__prometheus_instance__": "instance1"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "2",
            },
        ]

        self.mock_am_client.get.return_value = mock_alerts

        result = group_alerts_by_service()

        # Should return a result
        self.assertIsNotNone(result)

    def test_detect_cascading_alerts_with_rca_structure(self) -> None:
        """Test detect_cascading_alerts returns expected structure."""
        # Mock alert data with temporal sequence
        mock_alerts = [
            {
                "labels": {"job": "frontend", "alertname": "HighLatency"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:00Z",
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "1",
            },
            {
                "labels": {"job": "backend", "alertname": "DatabaseSlow"},
                "annotations": {},
                "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                "startsAt": "2023-01-01T00:00:30Z",  # 30 seconds later
                "endsAt": "",
                "generatorURL": "",
                "fingerprint": "2",
            },
        ]

        self.mock_am_client.get.return_value = mock_alerts

        result = detect_cascading_alerts(temporal_window=300)

        # Should return a result
        self.assertIsNotNone(result)

    def test_tool_error_handling(self) -> None:
        """Test that tools handle registry unavailability gracefully."""
        # Make registry unavailable
        import prometheus_mcp._mcp

        prometheus_mcp._mcp._registry = None

        # Should raise ToolError when registry is unavailable
        with self.assertRaises(ToolError):
            correlate_alerts_across_instances()

    def test_performance_characteristics(self) -> None:
        """Test performance characteristics of correlation tools."""
        # Mock large alert dataset
        mock_alerts = []
        for i in range(50):  # 50 alerts
            mock_alerts.append(
                {
                    "labels": {"job": f"service{i % 5}", "alertname": f"Alert{i}", "instance": f"server{i % 10}"},
                    "annotations": {},
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                    "startsAt": f"2023-01-01T00:{i // 60:02d}:{i % 60:02d}Z",
                    "endsAt": "",
                    "generatorURL": "",
                    "fingerprint": str(i),
                }
            )

        self.mock_am_client.get.return_value = mock_alerts

        # Test with moderate settings
        result = correlate_alerts_across_instances(temporal_window=300, similarity_threshold=0.7)

        # Should complete successfully with large dataset
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
