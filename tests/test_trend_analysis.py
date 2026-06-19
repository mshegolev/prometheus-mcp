"""Tests for the trend analysis module."""

import pytest
from datetime import datetime
from unittest.mock import Mock

from prometheus_mcp.trend_analysis import (
    PatternRecognizer,
    ForecastingEngine,
    MTTRBenchmark,
    DeviationDetector,
    RemediationSuggester,
    analyze_trends,
    benchmark_resolution_times,
    detect_deviations,
)
from prometheus_mcp.models import AlertItem, RangeSeries


class TestPatternRecognizer:
    """Test the PatternRecognizer class."""

    def test_identify_recurring_schedules(self):
        """Test identifying recurring alert schedules."""
        recognizer = PatternRecognizer()

        # Create alerts with recurring patterns - more alerts at hour 9 than other hours
        alerts = [
            {
                "labels": {"alertname": "HighCPU"},
                "annotations": {},
                "state": "active",
                "active_at": "2026-06-18T09:00:00+00:00",
                "value": "1",
            },
            {
                "labels": {"alertname": "HighCPU"},
                "annotations": {},
                "state": "active",
                "active_at": "2026-06-19T09:00:00+00:00",
                "value": "1",
            },
            {
                "labels": {"alertname": "HighCPU"},
                "annotations": {},
                "state": "active",
                "active_at": "2026-06-20T09:00:00+00:00",
                "value": "1",
            },
            {
                "labels": {"alertname": "HighCPU"},
                "annotations": {},
                "state": "active",
                "active_at": "2026-06-21T09:00:00+00:00",
                "value": "1",
            },
            # Add some alerts at different hours to establish a baseline
            {
                "labels": {"alertname": "HighCPU"},
                "annotations": {},
                "state": "active",
                "active_at": "2026-06-18T10:00:00+00:00",
                "value": "1",
            },
            {
                "labels": {"alertname": "HighCPU"},
                "annotations": {},
                "state": "active",
                "active_at": "2026-06-19T11:00:00+00:00",
                "value": "1",
            },
        ]

        patterns = recognizer.identify_recurring_schedules(alerts)
        assert "HighCPU" in patterns
        assert 9 in patterns["HighCPU"]["hours"]

    def test_identify_seasonal_behaviors(self):
        """Test identifying seasonal behaviors in metrics."""
        recognizer = PatternRecognizer()

        # Create metric series with clear pattern
        metric_series = {
            "labels": {"__name__": "cpu_usage"},
            "point_count": 4,
            "values": [
                [datetime(2026, 6, 18, 9, 0, 0).timestamp(), "20.0"],
                [datetime(2026, 6, 18, 12, 0, 0).timestamp(), "80.0"],
                [datetime(2026, 6, 18, 15, 0, 0).timestamp(), "30.0"],
                [datetime(2026, 6, 18, 18, 0, 0).timestamp(), "25.0"],
            ],
        }

        patterns = recognizer.identify_seasonal_behaviors([metric_series])
        assert "cpu_usage" in patterns
        assert "peak_hour" in patterns["cpu_usage"]


class TestForecastingEngine:
    """Test the ForecastingEngine class."""

    def test_predict_resource_exhaustion(self):
        """Test predicting resource exhaustion."""
        engine = ForecastingEngine()

        # Create increasing metric series
        metric_series = {
            "labels": {"__name__": "disk_usage_percent"},
            "point_count": 4,
            "values": [
                [datetime(2026, 6, 18, 9, 0, 0).timestamp(), "20.0"],
                [datetime(2026, 6, 18, 10, 0, 0).timestamp(), "30.0"],
                [datetime(2026, 6, 18, 11, 0, 0).timestamp(), "40.0"],
                [datetime(2026, 6, 18, 12, 0, 0).timestamp(), "50.0"],
            ],
        }

        # Predict exhaustion at 80%
        prediction = engine.predict_resource_exhaustion(metric_series, 80.0, 24)
        # Should predict exhaustion since trend is increasing
        assert prediction is not None

    def test_forecast_capacity_utilization(self):
        """Test forecasting capacity utilization."""
        engine = ForecastingEngine()

        # Create metric series with clear trend
        metric_series = {
            "labels": {"__name__": "memory_usage"},
            "point_count": 3,
            "values": [
                [datetime(2026, 6, 18, 9, 0, 0).timestamp(), "20.0"],
                [datetime(2026, 6, 18, 10, 0, 0).timestamp(), "30.0"],
                [datetime(2026, 6, 18, 11, 0, 0).timestamp(), "40.0"],
            ],
        }

        forecast = engine.forecast_capacity_utilization(metric_series, 3)
        assert len(forecast) == 3
        # Future values should be higher than last known value (40.0)
        assert all(val > 40.0 for _, val in forecast)


class TestMTTRBenchmark:
    """Test the MTTRBenchmark class."""

    def test_record_and_compare_resolution_times(self):
        """Test recording and comparing resolution times."""
        benchmark = MTTRBenchmark()

        # Record historical times
        benchmark.record_resolution_time("HighCPU", 300)  # 5 minutes
        benchmark.record_resolution_time("HighCPU", 600)  # 10 minutes

        # Compare current time
        comparison = benchmark.compare_against_historical("HighCPU", 450)  # 7.5 minutes
        assert comparison["comparison_available"] is True
        assert comparison["current_time"] == 450
        assert "historical_average" in comparison


class TestDeviationDetector:
    """Test the DeviationDetector class."""

    def test_detect_pattern_breaks(self):
        """Test detecting pattern breaks."""
        pattern_recognizer = PatternRecognizer()
        detector = DeviationDetector(pattern_recognizer)

        # Set baseline
        detector.set_baseline("cpu_usage", {"value": 50.0, "threshold": 10.0})

        # Detect deviation
        deviation = detector.detect_pattern_breaks({"value": 75.0}, "cpu_usage")
        assert deviation is not None
        assert deviation["deviation_detected"] is True
        assert deviation["deviation_amount"] == 25.0


class TestRemediationSuggester:
    """Test the RemediationSuggester class."""

    def test_suggest_remediations(self):
        """Test suggesting remediations."""
        suggester = RemediationSuggester()

        # Add a technique
        technique = {
            "approach": "Scale up instances",
            "steps": ["Increase replica count", "Monitor resource usage"],
            "success_rate": 0.85,
            "notes": "Works well for CPU-bound applications",
        }
        suggester.add_resolution_technique("HighCPU", technique)

        # Get suggestions
        suggestions = suggester.suggest_remediations("HighCPU", {})
        assert len(suggestions) == 1
        assert suggestions[0]["approach"] == "Scale up instances"


class TestMainInterfaceFunctions:
    """Test the main interface functions."""

    def test_analyze_trends(self):
        """Test the analyze_trends function."""
        # Create test data
        alerts = [
            {
                "labels": {"alertname": "HighCPU"},
                "annotations": {},
                "state": "active",
                "active_at": "2026-06-18T09:00:00Z",
                "value": "1",
            }
        ]

        metrics = [
            {
                "labels": {"__name__": "cpu_usage"},
                "point_count": 2,
                "values": [
                    [datetime(2026, 6, 18, 9, 0, 0).timestamp(), "20.0"],
                    [datetime(2026, 6, 18, 12, 0, 0).timestamp(), "80.0"],
                ],
            }
        ]

        results = analyze_trends(alerts, metrics)
        assert "recurring_schedules" in results
        assert "seasonal_behaviors" in results
        assert "analysis_timestamp" in results

    def test_benchmark_resolution_times(self):
        """Test the benchmark_resolution_times function."""
        alerts = [
            {
                "labels": {"alertname": "HighCPU"},
                "annotations": {},
                "state": "active",
                "active_at": "2026-06-18T09:00:00Z",
                "value": "1",
            }
        ]

        results = benchmark_resolution_times(alerts)
        assert isinstance(results, dict)

    def test_detect_deviations(self):
        """Test the detect_deviations function."""
        metrics = [
            {
                "labels": {"__name__": "cpu_usage"},
                "point_count": 1,
                "values": [
                    [datetime(2026, 6, 18, 9, 0, 0).timestamp(), "75.0"],
                ],
            }
        ]

        baselines = {"cpu_usage": {"value": 50.0, "threshold": 10.0}}

        deviations = detect_deviations(metrics, baselines)
        assert isinstance(deviations, list)
