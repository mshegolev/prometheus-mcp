"""Trend analysis and benchmarking for Prometheus MCP.

This module provides functionality for historical pattern recognition,
capacity forecasting, and MTTR benchmarking to give AI agents temporal
context for incident investigation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from prometheus_mcp.models import AlertItem, RangeSeries

logger = logging.getLogger(__name__)


class PatternRecognizer:
    """Recognizes historical patterns in alerts and metrics."""

    def __init__(self):
        self.patterns: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def identify_recurring_schedules(self, alerts: List[AlertItem]) -> Dict[str, Dict[str, List[int]]]:
        """Identify recurring alert schedules based on alert timestamps.

        Args:
            alerts: List of alerts to analyze

        Returns:
            Dictionary mapping alert names to dictionaries with recurring hours and days
        """
        schedule_patterns: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: {"hours": [], "days": []})

        # Group alerts by name and extract hours
        alert_groups = defaultdict(list)
        for alert in alerts:
            active_at_str = alert.get("active_at")
            if active_at_str:
                try:
                    # Parse the ISO format timestamp
                    active_at = datetime.fromisoformat(active_at_str.replace("Z", "+00:00"))
                    alert_name = alert["labels"].get("alertname", "unknown")
                    alert_groups[alert_name].append(active_at)
                except ValueError:
                    # Skip invalid timestamps
                    continue

        # Identify recurring patterns (same hour of day, day of week, etc.)
        for alert_name, timestamps in alert_groups.items():
            hourly_counts = defaultdict(int)
            daily_counts = defaultdict(int)

            for ts in timestamps:
                hourly_counts[ts.hour] += 1
                daily_counts[ts.weekday()] += 1

            # Identify hours/day with significantly more alerts than average
            avg_hourly = sum(hourly_counts.values()) / len(hourly_counts) if hourly_counts else 0
            avg_daily = sum(daily_counts.values()) / len(daily_counts) if daily_counts else 0

            recurring_hours = [hour for hour, count in hourly_counts.items() if count > avg_hourly * 1.5]
            recurring_days = [day for day, count in daily_counts.items() if count > avg_daily * 1.5]

            if recurring_hours or recurring_days:
                schedule_patterns[alert_name] = {"hours": recurring_hours, "days": recurring_days}

        return dict(schedule_patterns)

    def identify_seasonal_behaviors(self, metrics: List[RangeSeries]) -> Dict[str, Dict[str, Any]]:
        """Identify seasonal patterns in metric data.

        Args:
            metrics: List of metric series to analyze

        Returns:
            Dictionary describing seasonal patterns for each metric
        """
        seasonal_patterns = {}

        for metric_series in metrics:
            metric_name = metric_series["labels"].get("__name__", "unknown")

            # Simple seasonal detection based on time-of-day patterns
            if not metric_series["values"]:
                continue

            # Group values by hour of day
            hourly_values = defaultdict(list)
            for point in metric_series["values"]:
                if len(point) >= 2:
                    timestamp, value = point[0], point[1]
                    try:
                        dt = datetime.fromtimestamp(float(timestamp))
                        hourly_values[dt.hour].append(float(value))
                    except (ValueError, TypeError):
                        # Skip invalid data points
                        continue

            # Calculate average for each hour
            hourly_averages = {hour: sum(values) / len(values) for hour, values in hourly_values.items() if values}

            if not hourly_averages:
                continue

            # Find peak and trough hours
            max_hour = max(hourly_averages.keys(), key=lambda x: hourly_averages[x])
            min_hour = min(hourly_averages.keys(), key=lambda x: hourly_averages[x])

            seasonal_patterns[metric_name] = {
                "peak_hour": max_hour,
                "trough_hour": min_hour,
                "variation": max(hourly_averages.values()) - min(hourly_averages.values()),
            }

        return seasonal_patterns


class ForecastingEngine:
    """Capacity forecasting engine based on usage trends."""

    def __init__(self):
        pass

    def predict_resource_exhaustion(
        self, metric_series: RangeSeries, threshold: float, forecast_horizon_hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """Predict when a resource might be exhausted based on current trends.

        Args:
            metric_series: Time series data for the resource
            threshold: Threshold value that indicates exhaustion
            forecast_horizon_hours: How far ahead to forecast

        Returns:
            Dictionary with forecast information or None if no exhaustion predicted
        """
        if not metric_series["values"]:
            return None

        # Simple linear regression for forecasting
        timestamps = []
        values = []
        for point in metric_series["values"]:
            if len(point) >= 2:
                try:
                    timestamps.append(float(point[0]))
                    values.append(float(point[1]))
                except (ValueError, TypeError):
                    continue

        if len(values) < 2:
            return None

        # Calculate trend (slope)
        x = list(range(len(values)))
        y = values

        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_xx = sum(x[i] * x[i] for i in range(n))

        if n * sum_xx - sum_x * sum_x == 0:
            return None

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
        intercept = (sum_y - slope * sum_x) / n

        # Predict when threshold will be reached
        if slope > 0:  # Increasing trend
            if values[-1] >= threshold:
                # Already exceeded threshold
                return {
                    "exhausted": True,
                    "time_to_exhaustion_hours": 0,
                    "current_value": values[-1],
                    "threshold": threshold,
                    "trend": slope,
                }
            else:
                # Calculate when it will be reached
                predicted_time_index = (threshold - intercept) / slope
                current_index = len(values) - 1
                time_to_exhaustion = (
                    (predicted_time_index - current_index) * ((timestamps[-1] - timestamps[0]) / len(timestamps)) / 3600
                )  # Convert to hours if timestamps exist

                if time_to_exhaustion <= forecast_horizon_hours and time_to_exhaustion > 0:
                    return {
                        "exhausted": False,
                        "time_to_exhaustion_hours": time_to_exhaustion,
                        "current_value": values[-1],
                        "threshold": threshold,
                        "trend": slope,
                    }

        return None

    def forecast_capacity_utilization(
        self, metric_series: RangeSeries, forecast_steps: int = 10
    ) -> List[Tuple[float, float]]:
        """Forecast future capacity utilization based on historical data.

        Args:
            metric_series: Time series data for capacity utilization
            forecast_steps: Number of future points to forecast

        Returns:
            List of (timestamp, predicted_value) tuples
        """
        if not metric_series["values"] or len(metric_series["values"]) < 2:
            return []

        # Simple linear extrapolation
        timestamps = []
        values = []
        for point in metric_series["values"]:
            if len(point) >= 2:
                try:
                    timestamps.append(float(point[0]))
                    values.append(float(point[1]))
                except (ValueError, TypeError):
                    continue

        if len(values) < 2:
            return []

        # Calculate trend
        x = list(range(len(values)))
        y = values

        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_xx = sum(x[i] * x[i] for i in range(n))

        if n * sum_xx - sum_x * sum_x == 0:
            # No trend, return last value for all future points
            last_timestamp = timestamps[-1] if timestamps else 0
            last_value = values[-1] if values else 0
            interval = 3600  # 1 hour default

            if len(timestamps) > 1:
                interval = timestamps[-1] - timestamps[-2]

            return [(last_timestamp + (i + 1) * interval, last_value) for i in range(forecast_steps)]

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
        intercept = (sum_y - slope * sum_x) / n

        # Generate forecast
        last_timestamp = timestamps[-1] if timestamps else 0
        interval = 3600  # 1 hour default

        if len(timestamps) > 1:
            interval = timestamps[-1] - timestamps[-2]

        forecast = []
        for i in range(1, forecast_steps + 1):
            future_x = len(values) - 1 + i
            predicted_value = slope * future_x + intercept
            future_timestamp = last_timestamp + i * interval
            forecast.append((future_timestamp, predicted_value))

        return forecast


class MTTRBenchmark:
    """MTTR (Mean Time To Resolution) benchmarking system."""

    def __init__(self):
        # Store historical resolution times by alert type
        self.resolution_times: Dict[str, List[float]] = defaultdict(list)

    def record_resolution_time(self, alert_name: str, resolution_seconds: float):
        """Record the resolution time for an alert.

        Args:
            alert_name: Name of the alert
            resolution_seconds: Time taken to resolve in seconds
        """
        self.resolution_times[alert_name].append(resolution_seconds)

    def compare_against_historical(self, alert_name: str, current_resolution_seconds: float) -> Dict[str, Any]:
        """Compare current resolution time against historical data.

        Args:
            alert_name: Name of the alert
            current_resolution_seconds: Current resolution time in seconds

        Returns:
            Dictionary with comparison results
        """
        historical_times = self.resolution_times.get(alert_name, [])

        if not historical_times:
            return {"comparison_available": False, "current_time": current_resolution_seconds}

        avg_time = sum(historical_times) / len(historical_times)
        min_time = min(historical_times)
        max_time = max(historical_times)

        comparison = "faster" if current_resolution_seconds < avg_time else "slower"
        percentage_diff = ((current_resolution_seconds - avg_time) / avg_time) * 100

        return {
            "comparison_available": True,
            "current_time": current_resolution_seconds,
            "historical_average": avg_time,
            "historical_min": min_time,
            "historical_max": max_time,
            "comparison": comparison,
            "percentage_difference": percentage_diff,
        }

    def get_benchmark_stats(self, alert_name: str) -> Optional[Dict[str, float]]:
        """Get benchmark statistics for an alert type.

        Args:
            alert_name: Name of the alert

        Returns:
            Dictionary with statistics or None if no data
        """
        times = self.resolution_times.get(alert_name, [])

        if not times:
            return None

        return {
            "count": len(times),
            "average": sum(times) / len(times),
            "median": sorted(times)[len(times) // 2],
            "min": min(times),
            "max": max(times),
            "std_dev": (sum((t - sum(times) / len(times)) ** 2 for t in times) / len(times)) ** 0.5,
        }


class DeviationDetector:
    """Detects deviations from established patterns."""

    def __init__(self, pattern_recognizer: PatternRecognizer):
        self.pattern_recognizer = pattern_recognizer
        self.baselines: Dict[str, Dict[str, Any]] = {}

    def set_baseline(self, metric_name: str, baseline_data: Dict[str, Any]):
        """Set baseline data for a metric.

        Args:
            metric_name: Name of the metric
            baseline_data: Baseline data for comparison
        """
        self.baselines[metric_name] = baseline_data

    def detect_pattern_breaks(self, current_data: Dict[str, Any], metric_name: str) -> Optional[Dict[str, Any]]:
        """Detect if current data deviates significantly from baseline.

        Args:
            current_data: Current metric data
            metric_name: Name of the metric

        Returns:
            Dictionary with deviation information or None if no significant deviation
        """
        baseline = self.baselines.get(metric_name)

        if not baseline:
            return None

        # Simple threshold-based deviation detection
        current_value = current_data.get("value", 0)
        baseline_value = baseline.get("value", 0)
        threshold = baseline.get("threshold", baseline_value * 0.1)  # 10% default

        if abs(current_value - baseline_value) > threshold:
            return {
                "deviation_detected": True,
                "current_value": current_value,
                "baseline_value": baseline_value,
                "deviation_amount": current_value - baseline_value,
                "threshold": threshold,
            }

        return None


class RemediationSuggester:
    """Provides remediation suggestions based on historical data."""

    def __init__(self):
        # Store historical resolution techniques
        self.resolution_techniques: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def add_resolution_technique(self, alert_type: str, technique: Dict[str, Any]):
        """Add a successful resolution technique for an alert type.

        Args:
            alert_type: Type of alert
            technique: Dictionary describing the resolution technique
        """
        self.resolution_techniques[alert_type].append(technique)

    def suggest_remediations(self, alert_type: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Suggest remediation approaches based on historical data.

        Args:
            alert_type: Type of alert
            context: Current context information

        Returns:
            List of suggested remediation approaches
        """
        techniques = self.resolution_techniques.get(alert_type, [])

        # Simple matching based on context
        suggestions = []
        for technique in techniques:
            # Add all techniques for now - in a real implementation,
            # we would match based on context similarity
            suggestions.append(
                {
                    "approach": technique.get("approach", "Unknown"),
                    "steps": technique.get("steps", []),
                    "success_rate": technique.get("success_rate", 0.0),
                    "notes": technique.get("notes", ""),
                }
            )

        # Sort by success rate
        suggestions.sort(key=lambda x: x["success_rate"], reverse=True)

        return suggestions


# Main interface functions
def analyze_trends(alerts: List[AlertItem], metrics: List[RangeSeries]) -> Dict[str, Any]:
    """Analyze trends in alerts and metrics.

    Args:
        alerts: List of alerts to analyze
        metrics: List of metric series to analyze

    Returns:
        Dictionary with trend analysis results
    """
    pattern_recognizer = PatternRecognizer()
    forecasting_engine = ForecastingEngine()

    # Perform analyses
    recurring_schedules = pattern_recognizer.identify_recurring_schedules(alerts)
    seasonal_behaviors = pattern_recognizer.identify_seasonal_behaviors(metrics)

    # Forecast for a few key metrics (those with names indicating usage)
    forecasts = {}
    for metric_series in metrics[:5]:  # Limit to first 5 for performance
        metric_name = metric_series["labels"].get("__name__", "")
        if any(keyword in metric_name.lower() for keyword in ["cpu", "memory", "disk", "usage"]):
            forecast = forecasting_engine.forecast_capacity_utilization(metric_series)
            if forecast:
                forecasts[metric_name] = forecast

    # Compile results
    results = {
        "recurring_schedules": recurring_schedules,
        "seasonal_behaviors": seasonal_behaviors,
        "forecasts": forecasts,
        "analysis_timestamp": datetime.now().isoformat(),
    }

    return results


def benchmark_resolution_times(alerts: List[AlertItem]) -> Dict[str, Any]:
    """Benchmark alert resolution times.

    Args:
        alerts: List of alerts with start and end times

    Returns:
        Dictionary with benchmarking results
    """
    mttr_benchmark = MTTRBenchmark()

    results = {}
    for alert in alerts:
        alert_name = alert["labels"].get("alertname", "unknown")
        # Note: AlertItem doesn't have explicit start/end times, so we'll use active_at
        # as a proxy. In a real implementation, we'd need actual resolution timestamps.
        active_at_str = alert.get("active_at")
        if active_at_str:
            try:
                active_at = datetime.fromisoformat(active_at_str.replace("Z", "+00:00"))
                # For demonstration, we'll simulate resolution time based on current time
                # Make datetime.now() timezone aware
                now = datetime.now().replace(tzinfo=active_at.tzinfo)
                resolution_time = (now - active_at).total_seconds()
                mttr_benchmark.record_resolution_time(alert_name, resolution_time)
                comparison = mttr_benchmark.compare_against_historical(alert_name, resolution_time)
                results[alert_name] = comparison
            except (ValueError, TypeError):
                # Skip invalid timestamps
                continue

    return results


def detect_deviations(current_metrics: List[RangeSeries], baselines: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect deviations from established baselines.

    Args:
        current_metrics: Current metric data
        baselines: Baseline data for comparison

    Returns:
        List of detected deviations
    """
    pattern_recognizer = PatternRecognizer()
    deviation_detector = DeviationDetector(pattern_recognizer)

    # Set baselines
    for metric_name, baseline_data in baselines.items():
        deviation_detector.set_baseline(metric_name, baseline_data)

    # Detect deviations
    deviations = []
    for metric_series in current_metrics:
        metric_name = metric_series["labels"].get("__name__", "")
        if metric_series["values"]:
            # Get the last value
            last_point = metric_series["values"][-1]
            if len(last_point) >= 2:
                try:
                    current_value = float(last_point[1])  # Last value
                    current_data = {"value": current_value}
                    deviation = deviation_detector.detect_pattern_breaks(current_data, metric_name)
                    if deviation:
                        deviations.append({"metric_name": metric_name, "deviation": deviation})
                except (ValueError, TypeError):
                    # Skip invalid data points
                    continue

    return deviations
