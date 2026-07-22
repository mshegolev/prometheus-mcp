"""MCP tool for real service-dependency mapping (v5.0 Phase 14, DEP-R01/R02).

Registers ``prometheus_map_service_dependencies`` — a dual-channel tool that
builds a service dependency graph from a live Prometheus traffic metric
carrying source/destination labels. Supersedes the EXPERIMENTAL, simulated
:mod:`prometheus_mcp.dependency` module.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from prometheus_mcp import output
from prometheus_mcp._mcp import get_client, mcp
from prometheus_mcp.dependency_map import DependencyMapError, ServiceDependencyMapper
from prometheus_mcp.models import ServiceDependencyMapResult

_MD_EDGE_LIMIT = 25


@mcp.tool(
    name="prometheus_map_service_dependencies",
    annotations={
        "title": "Map Service Dependencies",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def prometheus_map_service_dependencies(
    *,
    metric: Annotated[
        str,
        Field(
            default="istio_requests_total",
            min_length=1,
            max_length=200,
            description=(
                "Traffic counter carrying source/destination labels. Defaults to Istio's "
                "'istio_requests_total'. For other meshes/instrumentation set this plus "
                "source_label/destination_label (e.g. metric='request_total', "
                "source_label='source', destination_label='destination')."
            ),
        ),
    ] = "istio_requests_total",
    source_label: Annotated[
        str,
        Field(
            default="source_workload",
            min_length=1,
            max_length=100,
            description="Metric label whose value identifies the calling service (edge source).",
        ),
    ] = "source_workload",
    destination_label: Annotated[
        str,
        Field(
            default="destination_workload",
            min_length=1,
            max_length=100,
            description="Metric label whose value identifies the called service (edge target).",
        ),
    ] = "destination_workload",
    time_window: Annotated[
        str,
        Field(
            default="5m",
            min_length=2,
            max_length=20,
            description="Look-back window for the rate() (e.g. '5m', '1h'). Default '5m'.",
        ),
    ] = "5m",
    step: Annotated[
        str,
        Field(
            default="1m",
            min_length=1,
            max_length=20,
            description="query_range resolution step (e.g. '30s', '1m'). Default '1m'.",
        ),
    ] = "1m",
    matchers: Annotated[
        dict[str, str] | None,
        Field(
            default=None,
            description=(
                "Optional extra label matchers to scope the query, e.g. "
                '{"namespace": "prod"}. Values are escaped against PromQL injection.'
            ),
        ),
    ] = None,
    error_matcher: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
            description=(
                "Optional PromQL matcher fragment selecting error traffic, e.g. "
                "'response_code=~\"5..\"'. When set, each edge gains an error_rate."
            ),
        ),
    ] = None,
    instance: Annotated[
        str | None,
        Field(default=None, description="Target instance name (omit for default instance)."),
    ] = None,
) -> ServiceDependencyMapResult:
    """Map service-to-service dependencies from live Prometheus traffic metrics.

    Aggregates ``rate(<metric>[<window>])`` by (source_label, destination_label)
    via ``query_range`` and turns each returned series into a directed
    dependency edge (nodes = services, edge weight = mean request rate). No
    simulation — every node/edge comes from real series. When ``error_matcher``
    is supplied a second query derives a per-edge error rate.

    Use this to:
    - Discover which services call which, and how heavily.
    - Spot high-error dependencies during an incident.

    Examples:
        - "Map dependencies for the prod namespace over the last 15 minutes"
          → ``matchers={"namespace": "prod"}``, ``time_window="15m"``.
        - "Which edges are erroring?"
          → ``error_matcher='response_code=~"5.."'``.

    Returns:
        ServiceDependencyMapResult with ``nodes`` and directed ``edges``
        (sorted by throughput), plus the query parameters used.
    """
    try:
        client = get_client(instance)
        mapper = ServiceDependencyMapper(client)
        result = mapper.map_dependencies(
            metric=metric,
            source_label=source_label,
            destination_label=destination_label,
            time_window=time_window,
            step=step,
            matchers=matchers,
            error_matcher=error_matcher,
            instance=instance,
        )
        return output.ok(result, _format_dependency_map(result))
    except DependencyMapError as exc:
        output.fail(exc, "mapping service dependencies")
    except Exception as exc:
        output.fail(exc, "mapping service dependencies")


def _format_dependency_map(result: ServiceDependencyMapResult) -> str:
    """Render the dependency map as markdown (dual-channel companion)."""
    md = [
        "# Service Dependency Map",
        "",
        f"**Metric:** `{result['metric']}` | **Window:** {result['time_window']} | **Step:** {result['step']}",
        f"**Services:** {result['node_count']} | **Dependencies:** {result['edge_count']}",
        "",
    ]
    if result["error_matcher"]:
        md.append(f"**Error selector:** `{result['error_matcher']}`")
        md.append("")

    if not result["edges"]:
        md.append(
            "_No source→destination series matched. Check that the metric carries "
            f"`{result['source_label']}`/`{result['destination_label']}` labels and that the "
            "window/matchers select data._"
        )
        return "\n".join(md)

    md.append("## Dependencies (source → target)")
    for edge in result["edges"][:_MD_EDGE_LIMIT]:
        line = f"- **{edge['source']}** → **{edge['target']}** — {edge['throughput']:.4g} req/s"
        if edge["error_rate"] is not None:
            line += f", error rate {edge['error_rate'] * 100:.1f}%"
        md.append(line)
    if result["edge_count"] > _MD_EDGE_LIMIT:
        md.append(f"  _... and {result['edge_count'] - _MD_EDGE_LIMIT} more edges (see structured output)_")

    return "\n".join(md)
