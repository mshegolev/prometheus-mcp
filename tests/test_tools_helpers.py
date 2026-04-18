"""Unit tests for pure shaping helpers in :mod:`prometheus_mcp.tools`.

These functions take raw Prometheus API dicts and shape them into TypedDict
output schemas or perform simple logic. They have no I/O, so we exercise
them directly without mocking any HTTP client.
"""

from __future__ import annotations

from prometheus_mcp.tools import (
    _format_value,
    _shape_instant_sample,
    _shape_range_series,
    _truncation_hint,
)


class TestFormatValue:
    def test_none_returns_empty_string(self) -> None:
        assert _format_value(None) == ""

    def test_string_passthrough(self) -> None:
        assert _format_value("1.5") == "1.5"

    def test_int_converted(self) -> None:
        assert _format_value(42) == "42"

    def test_float_converted(self) -> None:
        assert _format_value(3.14) == "3.14"


class TestShapeInstantSample:
    def test_vector_item(self) -> None:
        item = {
            "metric": {"__name__": "up", "job": "prometheus", "instance": "localhost:9090"},
            "value": [1705312800.0, "1"],
        }
        sample = _shape_instant_sample(item)
        assert sample["labels"] == {"__name__": "up", "job": "prometheus", "instance": "localhost:9090"}
        assert sample["timestamp"] == 1705312800.0
        assert sample["value"] == "1"

    def test_scalar_list_format(self) -> None:
        # scalar: [timestamp, value]
        sample = _shape_instant_sample([1705312800.0, "42"])
        assert sample["labels"] == {}
        assert sample["timestamp"] == 1705312800.0
        assert sample["value"] == "42"

    def test_no_labels(self) -> None:
        item = {"metric": {}, "value": [0.0, "0"]}
        sample = _shape_instant_sample(item)
        assert sample["labels"] == {}

    def test_missing_value_field(self) -> None:
        item = {"metric": {"job": "test"}}
        sample = _shape_instant_sample(item)
        assert sample["timestamp"] == 0.0
        assert sample["value"] == ""

    def test_labels_converted_to_str(self) -> None:
        item = {"metric": {"code": 200}, "value": [1.0, "1"]}
        sample = _shape_instant_sample(item)
        assert sample["labels"]["code"] == "200"

    def test_non_dict_non_list_fallback(self) -> None:
        sample = _shape_instant_sample("raw_string")
        assert sample["labels"] == {}
        assert sample["value"] == "raw_string"


class TestShapeRangeSeries:
    def test_basic_series(self) -> None:
        item = {
            "metric": {"job": "node", "instance": "host1:9100"},
            "values": [
                [1705312800.0, "0.5"],
                [1705312860.0, "0.6"],
                [1705312920.0, "0.7"],
            ],
        }
        series = _shape_range_series(item)
        assert series["labels"] == {"job": "node", "instance": "host1:9100"}
        assert series["point_count"] == 3
        assert series["values"] == [
            [1705312800.0, "0.5"],
            [1705312860.0, "0.6"],
            [1705312920.0, "0.7"],
        ]

    def test_empty_values(self) -> None:
        item = {"metric": {}, "values": []}
        series = _shape_range_series(item)
        assert series["point_count"] == 0
        assert series["values"] == []

    def test_timestamps_converted_to_float(self) -> None:
        item = {"metric": {}, "values": [[1705312800, "1.0"]]}
        series = _shape_range_series(item)
        assert isinstance(series["values"][0][0], float)

    def test_missing_metric_key(self) -> None:
        item = {"values": [[1.0, "1"]]}
        series = _shape_range_series(item)
        assert series["labels"] == {}
        assert series["point_count"] == 1

    def test_no_values_key(self) -> None:
        item = {"metric": {"job": "test"}}
        series = _shape_range_series(item)
        assert series["point_count"] == 0
        assert series["values"] == []


class TestTruncationHint:
    def test_returns_markdown_hint(self) -> None:
        hint = _truncation_hint(100, 20, "metrics")
        assert "20" in hint
        assert "100" in hint
        assert "metrics" in hint
        assert "structured content" in hint

    def test_hint_format_for_series(self) -> None:
        hint = _truncation_hint(500, 20, "series")
        assert "series" in hint
        assert "500" in hint
