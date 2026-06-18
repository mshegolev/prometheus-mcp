"""Unit tests for federation fan-out and merge functionality."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from prometheus_mcp.client import PrometheusClient
from prometheus_mcp.federation import (
    fan_out_prometheus,
    merge_instant_results,
    merge_range_results,
    merge_set_results,
)


class TestFanOutPrometheus:
    """Tests for the fan_out_prometheus function."""

    def test_empty_clients_list(self) -> None:
        """fan_out_prometheus with empty clients list returns empty result."""
        result = fan_out_prometheus(lambda client: {}, [])

        assert result["data"] is None
        assert result["successful_instances"] == []
        assert result["failed_instances"] == []
        assert result["truncated"] is False

    def test_single_successful_instance(self) -> None:
        """fan_out_prometheus with single successful instance works."""
        mock_client = Mock(spec=PrometheusClient)
        mock_result = {"data": "test"}

        def query_func(client):
            assert client is mock_client
            return mock_result

        result = fan_out_prometheus(query_func, [mock_client], instance_names=["test"])

        assert result["data"] is None  # Not merged yet
        assert result["successful_instances"] == ["test"]
        assert result["failed_instances"] == []
        assert result["truncated"] is False

    def test_instance_name_mismatch_raises(self) -> None:
        """fan_out_prometheus raises ValueError when instance_names length mismatches."""
        mock_client = Mock(spec=PrometheusClient)

        with pytest.raises(ValueError, match="instance_names list must match length"):
            fan_out_prometheus(lambda client: {}, [mock_client], instance_names=["a", "b"])


class TestMergeInstantResults:
    """Tests for merge_instant_results function."""

    def test_empty_results(self) -> None:
        """merge_instant_results with empty results returns empty QueryOutput."""
        result = merge_instant_results([])

        assert result["query"] == ""
        assert result["result_type"] == "vector"
        assert result["result_count"] == 0
        assert result["data"] == []

    def test_single_instance_results(self) -> None:
        """merge_instant_results with single instance injects __prometheus_instance__ label."""
        sample = {
            "labels": {"job": "test"},
            "timestamp": 1234567890.0,
            "value": "1.0",
        }
        query_result = {
            "query": "up",
            "time": None,
            "result_type": "vector",
            "result_count": 1,
            "data": [sample],
        }

        result = merge_instant_results([("instance1", query_result)])

        assert result["query"] == "up"
        assert result["result_count"] == 1
        assert len(result["data"]) == 1

        merged_sample = result["data"][0]
        assert merged_sample["labels"]["job"] == "test"
        assert merged_sample["labels"]["__prometheus_instance__"] == "instance1"
        assert merged_sample["timestamp"] == 1234567890.0
        assert merged_sample["value"] == "1.0"

    def test_label_collision_handling(self) -> None:
        """merge_instant_results handles existing __prometheus_instance__ label."""
        sample = {
            "labels": {"__prometheus_instance__": "original"},
            "timestamp": 1234567890.0,
            "value": "1.0",
        }
        query_result = {
            "query": "up",
            "time": None,
            "result_type": "vector",
            "result_count": 1,
            "data": [sample],
        }

        result = merge_instant_results([("instance1", query_result)])

        merged_sample = result["data"][0]
        assert merged_sample["labels"]["__prometheus_instance__"] == "instance1"
        assert merged_sample["labels"]["__prometheus_instance___source"] == "original"


class TestMergeRangeResults:
    """Tests for merge_range_results function."""

    def test_empty_results(self) -> None:
        """merge_range_results with empty results returns empty QueryRangeOutput."""
        result = merge_range_results([])

        assert result["query"] == ""
        assert result["result_type"] == "matrix"
        assert result["series_count"] == 0
        assert result["total_points"] == 0
        assert result["data"] == []

    def test_single_instance_results(self) -> None:
        """merge_range_results with single instance injects __prometheus_instance__ label."""
        series = {
            "labels": {"job": "test"},
            "point_count": 2,
            "values": [[1234567890.0, "1.0"], [1234567891.0, "2.0"]],
        }
        range_result = {
            "query": "up",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-01T01:00:00Z",
            "step": "60",
            "result_type": "matrix",
            "series_count": 1,
            "total_points": 2,
            "truncated": False,
            "data": [series],
        }

        result = merge_range_results([("instance1", range_result)])

        assert result["query"] == "up"
        assert result["series_count"] == 1
        assert result["total_points"] == 2
        assert len(result["data"]) == 1

        merged_series = result["data"][0]
        assert merged_series["labels"]["job"] == "test"
        assert merged_series["labels"]["__prometheus_instance__"] == "instance1"
        assert merged_series["point_count"] == 2
        assert len(merged_series["values"]) == 2


class TestMergeSetResults:
    """Tests for merge_set_results function."""

    def test_empty_results(self) -> None:
        """merge_set_results with empty results returns empty ListMetricsOutput."""
        result = merge_set_results([])

        assert result["total_count"] == 0
        assert result["returned_count"] == 0
        assert result["truncated"] is False
        assert result["metrics"] == []

    def test_single_instance_results(self) -> None:
        """merge_set_results with single instance returns sorted metrics."""
        list_result = {
            "total_count": 3,
            "returned_count": 3,
            "truncated": False,
            "pattern": None,
            "metrics": ["metric_c", "metric_a", "metric_b"],
        }

        result = merge_set_results([("instance1", list_result)])

        assert result["total_count"] == 3
        assert result["returned_count"] == 3
        assert result["truncated"] is False
        assert result["metrics"] == ["metric_a", "metric_b", "metric_c"]

    def test_multiple_instances_deduplication(self) -> None:
        """merge_set_results deduplicates metrics across instances."""
        list_result1 = {
            "total_count": 2,
            "returned_count": 2,
            "truncated": False,
            "pattern": None,
            "metrics": ["metric_a", "metric_b"],
        }
        list_result2 = {
            "total_count": 2,
            "returned_count": 2,
            "truncated": False,
            "pattern": None,
            "metrics": ["metric_b", "metric_c"],
        }

        result = merge_set_results([("instance1", list_result1), ("instance2", list_result2)])

        assert result["total_count"] == 3  # a, b, c
        assert result["returned_count"] == 3
        assert result["truncated"] is False
        assert result["metrics"] == ["metric_a", "metric_b", "metric_c"]
