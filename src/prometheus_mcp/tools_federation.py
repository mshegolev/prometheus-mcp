"""MCP tools for federation discovery and multi-instance coordination.

Provides instance discovery and health monitoring for federated Prometheus setups.
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any, Literal

from prometheus_mcp import output
from prometheus_mcp._mcp import mcp
from prometheus_mcp.client import PrometheusClient

logger = logging.getLogger(__name__)

# Health probe configuration
_HEALTH_PROBE_TIMEOUT = 5.0
_DEFAULT_MAX_WORKERS = 32
_WORKER_BUFFER = 4


class InstanceHealth(dict):
    """Health status information for a single instance."""

    pass


class InstanceInfo(dict):
    """Discovery information for a single instance."""

    pass


class ListInstancesOutput(dict):
    """Structured output for federation_list_instances tool."""

    pass


def _get_executor_max_workers(num_instances: int) -> int:
    """Calculate appropriate ThreadPoolExecutor max_workers."""
    return min(_DEFAULT_MAX_WORKERS, num_instances + _WORKER_BUFFER)


def _probe_instance_health(client: PrometheusClient, instance_name: str, url: str) -> InstanceHealth:
    """Probe a single instance's health endpoint."""
    start_time = time.perf_counter()

    try:
        # Probe the health endpoint
        response = client.session.get(f"{url}/-/healthy", timeout=_HEALTH_PROBE_TIMEOUT)
        response_time_ms = (time.perf_counter() - start_time) * 1000

        if response.status_code == 200:
            return {
                "name": instance_name,
                "url": url,
                "type": "prometheus",
                "reachable": True,
                "response_time_ms": round(response_time_ms, 2),
                "error": None,
            }
        else:
            return {
                "name": instance_name,
                "url": url,
                "type": "prometheus",
                "reachable": False,
                "response_time_ms": round(response_time_ms, 2),
                "error": f"HTTP {response.status_code}: {response.reason}",
            }
    except Exception as exc:
        response_time_ms = (time.perf_counter() - start_time) * 1000
        error_msg = str(exc)

        # Truncate very long error messages
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."

        return {
            "name": instance_name,
            "url": url,
            "type": "prometheus",
            "reachable": False,
            "response_time_ms": round(response_time_ms, 2),
            "error": error_msg,
        }


def _probe_all_instances_health(clients_and_names: list[tuple[PrometheusClient, str, str]]) -> list[InstanceHealth]:
    """Probe health of all instances concurrently."""
    if not clients_and_names:
        return []

    # Configure executor
    max_workers = _get_executor_max_workers(len(clients_and_names))
    health_results: list[InstanceHealth] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all health probe tasks
        future_to_instance = {
            executor.submit(_probe_instance_health, client, name, url): name for client, name, url in clients_and_names
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_instance):
            try:
                result = future.result()
                health_results.append(result)
            except Exception as exc:
                # This shouldn't happen since _probe_instance_health catches exceptions
                logger.warning("Unexpected error during health probe: %s", exc)

    return health_results


@mcp.tool(
    name="federation_list_instances",
    description="List all configured Prometheus and Alertmanager instances with health status",
    annotations={
        "title": "List Federated Instances",
        "readOnlyHint": True,
        "idempotentHint": True,
    },
    structured_output=True,
)
def federation_list_instances() -> ListInstancesOutput:
    """List all configured Prometheus and Alertmanager instances with health status.

    Returns health information including reachability, response times, and error details
    for all configured instances. URLs are shown without secrets (tokens are redacted).

    Use this tool to:
    - Discover available instances in a federated setup
    - Check which instances are currently reachable
    - Identify performance issues or connectivity problems
    - Verify configuration before running targeted queries

    Returns:
        dict with ``instances`` (list of instance info) and ``federation_enabled`` (bool).
    """
    try:
        # Get registry from app state
        registry = mcp.state.get("registry")
        if registry is None:
            # This shouldn't happen in normal operation
            return output.ok(
                {
                    "instances": [],
                    "federation_enabled": False,
                    "total_count": 0,
                },
                "## Federated Instances\n\nNo federation configuration found.",
            )

        # Get instance information
        instance_names = registry.list_instances()

        # Prepare clients and URLs for health probing
        clients_and_names = []
        instance_infos = []

        for name in instance_names:
            try:
                # Try to get Prometheus client
                prom_client = registry.get_prometheus_client(name)
                prom_url = prom_client.url
                instance_infos.append(
                    {
                        "name": name,
                        "prometheus_url": prom_url,
                        "alertmanager_url": "",
                        "type": "prometheus" if prom_url else "mixed",
                    }
                )
                if prom_url:
                    clients_and_names.append((prom_client, name, prom_url))
            except Exception:
                # Instance has no Prometheus URL, try Alertmanager
                try:
                    am_client = registry.get_alertmanager_client(name)
                    am_url = am_client.url
                    instance_infos.append(
                        {
                            "name": name,
                            "prometheus_url": "",
                            "alertmanager_url": am_url,
                            "type": "alertmanager",
                        }
                    )
                    if am_url:
                        clients_and_names.append((am_client, name, am_url))
                except Exception:
                    # Instance has neither - this shouldn't happen but handle gracefully
                    instance_infos.append(
                        {
                            "name": name,
                            "prometheus_url": "",
                            "alertmanager_url": "",
                            "type": "unknown",
                        }
                    )

        # Perform health probes
        health_results = _probe_all_instances_health(clients_and_names)

        # Merge health info with instance info
        health_map = {health["name"]: health for health in health_results}
        merged_instances = []

        for info in instance_infos:
            name = info["name"]
            health = health_map.get(
                name,
                {
                    "name": name,
                    "url": info["prometheus_url"] or info["alertmanager_url"],
                    "type": info["type"],
                    "reachable": False,
                    "response_time_ms": None,
                    "error": "No health probe performed",
                },
            )

            merged_instances.append(
                {
                    "name": name,
                    "prometheus_url": info["prometheus_url"],
                    "alertmanager_url": info["alertmanager_url"],
                    "type": info["type"],
                    "reachable": health["reachable"],
                    "response_time_ms": health["response_time_ms"],
                    "error": health["error"],
                }
            )

        # Sort by instance name for consistent output
        merged_instances.sort(key=lambda x: x["name"])

        result: ListInstancesOutput = {
            "instances": merged_instances,
            "federation_enabled": len(merged_instances) > 1,
            "total_count": len(merged_instances),
        }

        # Generate markdown output
        md = "## Federated Instances\n\n"
        if not merged_instances:
            md += "No instances configured.\n"
        else:
            md += f"Found {len(merged_instances)} instance(s):\n\n"
            for instance in merged_instances:
                name = instance["name"]
                instance_type = instance["type"]
                reachable = "✅" if instance["reachable"] else "❌"

                md += f"- **{name}** ({instance_type}) {reachable}\n"

                if instance["prometheus_url"]:
                    md += f"  - Prometheus: {instance['prometheus_url']}\n"
                if instance["alertmanager_url"]:
                    md += f"  - Alertmanager: {instance['alertmanager_url']}\n"

                if instance["reachable"]:
                    if instance["response_time_ms"] is not None:
                        md += f"  - Response time: {instance['response_time_ms']:.2f}ms\n"
                else:
                    if instance["error"]:
                        md += f"  - Error: {instance['error']}\n"

        return output.ok(result, md)

    except Exception as exc:
        return output.fail(exc, "listing federated instances")
