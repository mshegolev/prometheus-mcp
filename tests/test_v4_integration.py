"""Integration tests for prometheus-mcp v4.0 features."""

import pytest

from prometheus_mcp.correlation import CorrelationEngine
from prometheus_mcp.dependency import DependencyMappingEngine
from prometheus_mcp.rca import RCAEngine
from prometheus_mcp.trend_analysis import analyze_trends, benchmark_resolution_times


class TestV4Integration:
    """Test v4.0 feature integration."""

    def test_module_imports(self):
        """Test that v4.0 modules can be imported."""
        # This test verifies that the modules exist and can be imported
        assert CorrelationEngine is not None
        assert RCAEngine is not None
        assert DependencyMappingEngine is not None

    def test_trend_analysis_functions(self):
        """Test that trend analysis functions can be called."""
        # Test with empty data
        alerts = []
        metrics = []

        trends = analyze_trends(alerts, metrics)
        assert isinstance(trends, dict)
        assert "analysis_timestamp" in trends

    def test_benchmark_resolution_times_function(self):
        """Test that benchmark resolution times function can be called."""
        # Test with empty data
        alerts = []

        benchmarks = benchmark_resolution_times(alerts)
        assert isinstance(benchmarks, dict)


if __name__ == "__main__":
    pytest.main([__file__])
