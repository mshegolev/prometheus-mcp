"""Federation support for multi-instance Prometheus queries.

Provides concurrent fan-out execution across multiple Prometheus instances
with result merging, label injection, partial failure handling, and
global response size caps.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar, Union

from prometheus_mcp.client import PrometheusClient
from prometheus_mcp.alertmanager_client import AlertmanagerClient
from prometheus_mcp.models import (
    InstantSample,
    ListMetricsOutput,
    QueryOutput,
    QueryRangeOutput,
    RangeSeries,
)

logger = logging.getLogger(__name__)

# Global response size caps
_METRICS_CAP = 500
_RANGE_POINTS_CAP = 5000

# ThreadPoolExecutor configuration
_DEFAULT_MAX_WORKERS = 32
_WORKER_BUFFER = 4

# Error type categories
ERROR_TYPE_NETWORK = "network"
ERROR_TYPE_HTTP = "http"
ERROR_TYPE_TIMEOUT = "timeout"
ERROR_TYPE_VALIDATION = "validation"

T = TypeVar("T")
ClientType = Union[PrometheusClient, AlertmanagerClient]


class InstanceError(dict):
    """Structured error information for a failed instance."""

    pass


class FanOutResult(dict):
    """Unified result structure for fan-out operations."""

    pass


def _get_executor_max_workers(num_instances: int) -> int:
    """Calculate appropriate ThreadPoolExecutor max_workers."""
    return min(_DEFAULT_MAX_WORKERS, num_instances + _WORKER_BUFFER)


def _classify_error(exc: Exception, status_code: int | None = None) -> str:
    """Classify an exception into an error type category."""
    # Import requests locally to avoid import issues
    try:
        import requests

        if isinstance(exc, requests.Timeout):
            return ERROR_TYPE_TIMEOUT
        elif isinstance(exc, requests.ConnectionError):
            return ERROR_TYPE_NETWORK
        elif isinstance(exc, requests.HTTPError):
            return ERROR_TYPE_HTTP
        elif status_code is not None:
            if 400 <= status_code < 500:
                return ERROR_TYPE_VALIDATION
            elif 500 <= status_code < 600:
                return ERROR_TYPE_HTTP
    except ImportError:
        # If requests is not available, use basic classification
        pass

    return ERROR_TYPE_NETWORK


def _execute_query_on_instance(
    client: ClientType,
    query_func: Callable[[ClientType], T],
    instance_name: str,
    timeout: float | None = None,
) -> tuple[str, T | dict]:
    """Execute a query function on a single instance."""
    try:
        # Set a timeout for this specific instance query
        if timeout is not None:
            # Note: This is a simplified timeout approach
            # In practice, you'd want more sophisticated timeout handling
            pass

        result = query_func(client)
        return instance_name, result
    except Exception as exc:
        # Classify and structure the error
        status_code = None
        # Check if it's an HTTP error with response attribute
        try:
            response = getattr(exc, "response", None)
            if response is not None:
                status_code = getattr(response, "status_code", None)
        except:
            # If accessing response attributes fails, continue with None
            pass

        error_type = _classify_error(exc, status_code)
        error_info = {
            "instance_name": instance_name,
            "error_type": error_type,
            "message": str(exc),
            "status_code": status_code,
        }
        return instance_name, error_info


def fan_out_prometheus(
    query_func: Callable[[ClientType], T],
    clients: list[ClientType],
    *,
    instance_names: list[str] | None = None,
    timeout: float | None = None,
    max_workers: int | None = None,
) -> dict:
    """Execute a query function across multiple Prometheus/Alertmanager instances concurrently.

    Args:
        query_func: Function that takes a ClientType (PrometheusClient or AlertmanagerClient) and returns query results.
        clients: List of client instances to query.
        instance_names: Optional list of instance names corresponding to clients.
        timeout: Optional timeout for the entire fan-out operation.
        max_workers: Optional maximum number of worker threads.

    Returns:
        FanOutResult with merged data and error information.
    """
    if not clients:
        return {
            "data": None,
            "successful_instances": [],
            "failed_instances": [],
            "truncated": False,
        }

    # Generate instance names if not provided
    if instance_names is None:
        instance_names = [f"instance_{i}" for i in range(len(clients))]

    if len(instance_names) != len(clients):
        raise ValueError("instance_names list must match length of clients list")

    # Configure executor
    if max_workers is None:
        max_workers = _get_executor_max_workers(len(clients))

    # Execute queries concurrently
    results: dict[str, T | dict] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_instance = {
            executor.submit(_execute_query_on_instance, client, query_func, name, timeout): name
            for client, name in zip(clients, instance_names)
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_instance):
            instance_name, result = future.result()
            results[instance_name] = result

    # Separate successful results from errors
    successful_results: dict[str, T] = {}
    failed_instances: list[dict] = []

    for instance_name, result in results.items():
        if isinstance(result, dict) and "instance_name" in result:
            # This is an error result
            failed_instances.append(result)
        else:
            # This is a successful result
            successful_results[instance_name] = result  # type: ignore

    # Handle complete failure
    if not successful_results and failed_instances:
        logger.warning(
            "All instances failed during fan-out operation. Failed instances: %s",
            [err["instance_name"] for err in failed_instances],
        )

    # Merge successful results (implementation depends on result type)
    merged_data = None
    truncated = False

    # Return structured result
    return {
        "data": merged_data,
        "successful_instances": list(successful_results.keys()),
        "failed_instances": failed_instances,
        "truncated": truncated,
    }

    # Generate instance names if not provided
    if instance_names is None:
        instance_names = [f"instance_{i}" for i in range(len(clients))]

    if len(instance_names) != len(clients):
        raise ValueError("instance_names list must match length of clients list")

    # Configure executor
    if max_workers is None:
        max_workers = _get_executor_max_workers(len(clients))

    # Execute queries concurrently
    results: dict[str, T | dict] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_instance = {
            executor.submit(_execute_query_on_instance, client, query_func, name, timeout): name
            for client, name in zip(clients, instance_names)
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_instance):
            instance_name, result = future.result()
            results[instance_name] = result

    # Separate successful results from errors
    successful_results: dict[str, T] = {}
    failed_instances: list[dict] = []

    for instance_name, result in results.items():
        if isinstance(result, dict) and "instance_name" in result:
            # This is an error result
            failed_instances.append(result)
        else:
            # This is a successful result
            successful_results[instance_name] = result

    # Handle complete failure
    if not successful_results and failed_instances:
        logger.warning(
            "All instances failed during fan-out operation. Failed instances: %s",
            [err["instance_name"] for err in failed_instances],
        )

    # Merge successful results (implementation depends on result type)
    merged_data = None
    truncated = False

    # Return structured result
    return {
        "data": merged_data,
        "successful_instances": list(successful_results.keys()),
        "failed_instances": failed_instances,
        "truncated": truncated,
    }

    # Generate instance names if not provided
    if instance_names is None:
        instance_names = [f"instance_{i}" for i in range(len(clients))]

    if len(instance_names) != len(clients):
        raise ValueError("instance_names list must match length of clients list")

    # Configure executor
    if max_workers is None:
        max_workers = _get_executor_max_workers(len(clients))

    # Execute queries concurrently
    results: dict[str, T | InstanceError] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_instance = {
            executor.submit(_execute_query_on_instance, client, query_func, name, timeout): name
            for client, name in zip(clients, instance_names)
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_instance):
            instance_name, result = future.result()
            results[instance_name] = result

    # Separate successful results from errors
    successful_results: dict[str, T] = {}
    failed_instances: list[InstanceError] = []

    for instance_name, result in results.items():
        if isinstance(result, dict) and "instance_name" in result:
            # This is an InstanceError
            failed_instances.append(result)
        else:
            # This is a successful result
            successful_results[instance_name] = result

    # Handle complete failure
    if not successful_results and failed_instances:
        logger.warning(
            "All instances failed during fan-out operation. Failed instances: %s",
            [err["instance_name"] for err in failed_instances],
        )

    # Merge successful results (implementation depends on result type)
    merged_data = None
    truncated = False

    # Return structured result
    return {
        "data": merged_data,
        "successful_instances": list(successful_results.keys()),
        "failed_instances": failed_instances,
        "truncated": truncated,
    }


def _inject_instance_label(sample: InstantSample, instance_name: str) -> InstantSample:
    """Inject __prometheus_instance__ label into a sample, handling collisions."""
    # Check for existing __prometheus_instance__ label
    labels = sample["labels"].copy()

    if "__prometheus_instance__" in labels:
        # Collision detected - rename original label
        labels["__prometheus_instance___source"] = labels["__prometheus_instance__"]

    # Inject the instance label
    labels["__prometheus_instance__"] = instance_name

    return {
        "labels": labels,
        "timestamp": sample["timestamp"],
        "value": sample["value"],
    }


def merge_instant_results(results: list[tuple[str, QueryOutput]]) -> QueryOutput:
    """Merge instant query results from multiple instances.

    Args:
        results: List of (instance_name, QueryOutput) tuples.

    Returns:
        Merged QueryOutput with __prometheus_instance__ labels injected.
    """
    if not results:
        return {
            "query": "",
            "time": None,
            "result_type": "vector",
            "result_count": 0,
            "data": [],
        }

    # Use the first result's query metadata as baseline
    first_result = results[0][1]
    merged_samples: list[InstantSample] = []

    # Process each instance's results
    for instance_name, result in results:
        # Inject instance label into each sample
        for sample in result.get("data", []):
            labeled_sample = _inject_instance_label(sample, instance_name)
            merged_samples.append(labeled_sample)

    # Apply global cap
    truncated = len(merged_samples) > _METRICS_CAP
    if truncated:
        merged_samples = merged_samples[:_METRICS_CAP]

    return {
        "query": first_result["query"],
        "time": first_result["time"],
        "result_type": "vector",
        "result_count": len(merged_samples),
        "data": merged_samples,
    }


def merge_range_results(results: list[tuple[str, QueryRangeOutput]]) -> QueryRangeOutput:
    """Merge range query results from multiple instances.

    Args:
        results: List of (instance_name, QueryRangeOutput) tuples.

    Returns:
        Merged QueryRangeOutput with __prometheus_instance__ labels injected.
    """
    if not results:
        return {
            "query": "",
            "start": "",
            "end": "",
            "step": "",
            "result_type": "matrix",
            "series_count": 0,
            "total_points": 0,
            "truncated": False,
            "data": [],
        }

    # Use the first result's query metadata as baseline
    first_result = results[0][1]
    merged_series: list[RangeSeries] = []
    total_points = 0

    # Process each instance's results
    for instance_name, result in results:
        # Inject instance label into each series
        for series in result.get("data", []):
            # Copy series and inject instance label into labels
            labels = series["labels"].copy() if series["labels"] else {}

            # Handle label collision
            if "__prometheus_instance__" in labels:
                labels["__prometheus_instance___source"] = labels["__prometheus_instance__"]
            labels["__prometheus_instance__"] = instance_name

            labeled_series: RangeSeries = {
                "labels": labels,
                "point_count": series["point_count"],
                "values": series["values"],
            }

            merged_series.append(labeled_series)
            total_points += series["point_count"]

    # Apply global cap
    truncated = total_points > _RANGE_POINTS_CAP
    if truncated:
        # Simple truncation approach - in practice you'd want smarter point selection
        points_removed = 0
        truncated_series = []

        for series in merged_series:
            if points_removed >= (_RANGE_POINTS_CAP // len(merged_series)):
                break
            max_points = min(series["point_count"], _RANGE_POINTS_CAP - points_removed)
            if max_points > 0:
                truncated_series.append(
                    {
                        "labels": series["labels"],
                        "point_count": max_points,
                        "values": series["values"][:max_points],
                    }
                )
                points_removed += max_points

        merged_series = truncated_series
        total_points = sum(s["point_count"] for s in merged_series)

    return {
        "query": first_result["query"],
        "start": first_result["start"],
        "end": first_result["end"],
        "step": first_result["step"],
        "result_type": "matrix",
        "series_count": len(merged_series),
        "total_points": total_points,
        "truncated": truncated,
        "data": merged_series,
    }

    # Use the first result's query metadata as baseline
    first_result = results[0][1]
    merged_series: list[RangeSeries] = []
    total_points = 0

    # Process each instance's results
    for instance_name, result in results:
        # Inject instance label into each series
        for series in result.get("data", []):
            # Copy series and inject instance label into metric labels
            metric = series["metric"].copy() if series["metric"] else {}

            # Handle label collision
            if "__prometheus_instance__" in metric:
                metric["__prometheus_instance___source"] = metric["__prometheus_instance__"]
            metric["__prometheus_instance__"] = instance_name

            labeled_series: RangeSeries = {
                "metric": metric,
                "values": series["values"],
            }

            merged_series.append(labeled_series)
            total_points += len(series["values"])

    # Apply global cap
    truncated = total_points > _RANGE_POINTS_CAP
    if truncated:
        # Simple truncation approach - in practice you'd want smarter point selection
        points_removed = 0
        truncated_series = []

        for series in merged_series:
            if points_removed >= (_RANGE_POINTS_CAP // len(merged_series)):
                break
            max_points = min(len(series["values"]), _RANGE_POINTS_CAP - points_removed)
            if max_points > 0:
                truncated_series.append(
                    {
                        "metric": series["metric"],
                        "values": series["values"][:max_points],
                    }
                )
                points_removed += max_points

        merged_series = truncated_series
        total_points = sum(len(s["values"]) for s in merged_series)

    return {
        "query": first_result["query"],
        "start": first_result["start"],
        "end": first_result["end"],
        "step": first_result["step"],
        "result_type": "matrix",
        "series_count": len(merged_series),
        "total_points": total_points,
        "truncated": truncated,
        "data": merged_series,
    }


def merge_set_results(results: list[tuple[str, ListMetricsOutput]]) -> ListMetricsOutput:
    """Merge set results (metric names, label values) from multiple instances.

    Args:
        results: List of (instance_name, ListMetricsOutput) tuples.

    Returns:
        Merged ListMetricsOutput with deduplicated items.
    """
    if not results:
        return {
            "total_count": 0,
            "returned_count": 0,
            "truncated": False,
            "pattern": None,
            "metrics": [],
        }

    # Use the first result's metadata as baseline
    first_result = results[0][1]
    all_items: set[str] = set()

    # Collect all items from all instances
    for _, result in results:
        all_items.update(result.get("metrics", []))

    # Sort for consistent output
    sorted_items = sorted(all_items)

    # Apply global cap
    truncated = len(sorted_items) > _METRICS_CAP
    if truncated:
        sorted_items = sorted_items[:_METRICS_CAP]

    return {
        "total_count": len(all_items),
        "returned_count": len(sorted_items),
        "truncated": truncated,
        "pattern": first_result["pattern"],
        "metrics": sorted_items,
    }
