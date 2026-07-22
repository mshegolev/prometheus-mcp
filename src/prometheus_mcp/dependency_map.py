"""Real service-dependency mapping backed by live Prometheus traffic metrics.

This module implements DEP-R01/DEP-R02 for the v5.0 milestone. Unlike the
EXPERIMENTAL :mod:`prometheus_mcp.dependency` module (which simulates health
probes, failure states and layout coordinates), everything here is derived
from real ``query_range`` responses.

**How it works.** Service meshes and RPC middleware export a traffic counter
whose series carry a *source* and *destination* label (e.g. Istio's
``istio_requests_total{source_workload,destination_workload}``, Linkerd's
``response_total``, or any custom ``*_requests_total{source,destination}``).
We ask Prometheus to aggregate the per-second rate of that counter by the
source/destination pair over a look-back window::

    sum by (<source>, <destination>) (rate(<metric>{<matchers>}[<step>]))

Each returned series is one directed dependency edge; its mean value over the
window is the edge throughput. When an ``error_matcher`` is supplied we run a
second, identically-shaped query with the error selector folded in and derive
a per-edge error rate. No mock data, no hardcoded graph.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from prometheus_mcp.models import (
    DependencyMapEdge,
    DependencyMapNode,
    ServiceDependencyMapResult,
)

if TYPE_CHECKING:
    from prometheus_mcp.client import PrometheusClient

logger = logging.getLogger(__name__)

_LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class DependencyMapError(ValueError):
    """Raised for invalid dependency-mapping arguments (bad label/matcher)."""


def _validate_label_name(name: str, *, kind: str) -> str:
    """Validate a PromQL label name; raise :class:`DependencyMapError` if bad."""
    if not _LABEL_NAME_RE.match(name):
        raise DependencyMapError(
            f"Invalid {kind} {name!r}: must match [a-zA-Z_][a-zA-Z0-9_]* (PromQL label name rules)"
        )
    return name


def _validate_metric_name(metric: str) -> str:
    """Validate a PromQL metric name (same charset as label names, plus ':')."""
    if not re.match(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$", metric):
        raise DependencyMapError(
            f"Invalid metric name {metric!r}: must match [a-zA-Z_:][a-zA-Z0-9_:]* (PromQL metric name rules)"
        )
    return metric


def _escape_label_value(value: str) -> str:
    """Escape a value for embedding inside a double-quoted PromQL matcher.

    Guards against PromQL injection (T-34-02-B style): backslashes and double
    quotes are escaped and newlines are rejected so a value cannot terminate
    the string literal or the selector.
    """
    if "\n" in value or "\r" in value:
        raise DependencyMapError("matcher values must not contain newlines")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_selector(matchers: dict[str, str] | None, *, extra: str | None = None) -> str:
    """Build a ``{k="v",...}`` PromQL selector from validated/escaped matchers.

    ``extra`` is a caller-supplied raw matcher fragment (e.g. an error
    selector like ``response_code=~"5.."``) appended verbatim.
    """
    parts: list[str] = []
    for key, raw_value in (matchers or {}).items():
        _validate_label_name(key, kind="matcher label")
        parts.append(f'{key}="{_escape_label_value(str(raw_value))}"')
    if extra:
        parts.append(extra)
    if not parts:
        return ""
    return "{" + ",".join(parts) + "}"


def _mean_and_count(values: list[list]) -> tuple[float, int]:
    """Return (mean, count) of parseable float samples from a matrix series.

    ``values`` is Prometheus' ``[[ts, "value"], ...]`` shape. NaN/Inf and
    unparseable points are ignored so a single bad sample can't poison an edge.
    """
    floats: list[float] = []
    for point in values:
        if len(point) < 2:
            continue
        try:
            f = float(point[1])
        except (TypeError, ValueError):
            continue
        if f != f or f in (float("inf"), float("-inf")):  # NaN / Inf guard
            continue
        floats.append(f)
    if not floats:
        return 0.0, 0
    return sum(floats) / len(floats), len(floats)


class ServiceDependencyMapper:
    """Builds a real service-dependency graph from a Prometheus traffic metric."""

    def __init__(self, client: PrometheusClient) -> None:
        """Initialize with a live :class:`PrometheusClient` for one instance."""
        self.client = client

    def map_dependencies(
        self,
        *,
        metric: str,
        source_label: str,
        destination_label: str,
        time_window: str,
        step: str,
        matchers: dict[str, str] | None = None,
        error_matcher: str | None = None,
        instance: str | None = None,
    ) -> ServiceDependencyMapResult:
        """Discover source→destination dependencies from a live traffic metric.

        Args:
            metric: Traffic counter carrying source/destination labels.
            source_label: Label whose value is the calling service.
            destination_label: Label whose value is the called service.
            time_window: Look-back window for the ``rate()`` (e.g. "5m").
            step: ``query_range`` resolution step (e.g. "1m").
            matchers: Optional extra label matchers to scope the query.
            error_matcher: Optional raw PromQL fragment selecting error traffic
                (e.g. ``response_code=~"5.."``); enables per-edge error rate.
            instance: Instance name recorded in the result (None = default).

        Returns:
            A :class:`ServiceDependencyMapResult` with nodes and directed edges.

        Raises:
            DependencyMapError: If a label/metric name is malformed.
        """
        _validate_metric_name(metric)
        _validate_label_name(source_label, kind="source label")
        _validate_label_name(destination_label, kind="destination label")

        now = datetime.now(tz=timezone.utc).timestamp()
        window_seconds = _parse_window_seconds(time_window)
        start = now - window_seconds
        end = now

        selector = _build_selector(matchers)
        total_expr = f"sum by ({source_label}, {destination_label}) (rate({metric}{selector}[{time_window}]))"
        total_by_edge = self._query_edges(total_expr, source_label, destination_label, start, end, step)

        error_by_edge: dict[tuple[str, str], float] = {}
        if error_matcher:
            error_selector = _build_selector(matchers, extra=error_matcher)
            error_expr = (
                f"sum by ({source_label}, {destination_label}) (rate({metric}{error_selector}[{time_window}]))"
            )
            for edge, (throughput, _count) in self._query_edges(
                error_expr, source_label, destination_label, start, end, step
            ).items():
                error_by_edge[edge] = throughput

        edges: list[DependencyMapEdge] = []
        in_degree: dict[str, set[str]] = {}
        out_degree: dict[str, set[str]] = {}
        for (src, dst), (throughput, count) in total_by_edge.items():
            error_rate: float | None = None
            if error_matcher:
                err_tp = error_by_edge.get((src, dst), 0.0)
                error_rate = min(1.0, err_tp / throughput) if throughput > 0 else 0.0
            edges.append(
                {
                    "source": src,
                    "target": dst,
                    "throughput": throughput,
                    "sample_count": count,
                    "error_rate": error_rate,
                }
            )
            out_degree.setdefault(src, set()).add(dst)
            in_degree.setdefault(dst, set()).add(src)

        edges.sort(key=lambda e: e["throughput"], reverse=True)

        service_ids = set(in_degree) | set(out_degree)
        nodes: list[DependencyMapNode] = [
            {
                "service_id": sid,
                "in_degree": len(in_degree.get(sid, set())),
                "out_degree": len(out_degree.get(sid, set())),
            }
            for sid in sorted(service_ids)
        ]

        return {
            "metric": metric,
            "source_label": source_label,
            "destination_label": destination_label,
            "time_window": time_window,
            "step": step,
            "instance": instance,
            "error_matcher": error_matcher,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }

    def _query_edges(
        self,
        expr: str,
        source_label: str,
        destination_label: str,
        start: float,
        end: float,
        step: str,
    ) -> dict[tuple[str, str], tuple[float, int]]:
        """Run a range query and fold matrix series into {(src, dst): (mean, count)}."""
        raw = (
            self.client.get(
                "/query_range",
                params={"query": expr, "start": start, "end": end, "step": step},
            )
            or {}
        )
        result = (raw.get("data") or {}).get("result") or []
        by_edge: dict[tuple[str, str], tuple[float, int]] = {}
        for series in result:
            if not isinstance(series, dict):
                continue
            labels = series.get("metric") or {}
            src = labels.get(source_label)
            dst = labels.get(destination_label)
            if not src or not dst:
                # Series without both endpoints can't form a directed edge.
                continue
            mean, count = _mean_and_count(series.get("values") or [])
            # Same (src,dst) can appear once per series; fold defensively.
            prev = by_edge.get((src, dst))
            if prev is None:
                by_edge[(src, dst)] = (mean, count)
            else:
                by_edge[(src, dst)] = (prev[0] + mean, prev[1] + count)
        return by_edge


def _parse_window_seconds(window: str) -> float:
    """Parse a Prometheus duration string (s/m/h/d/w) into seconds.

    Falls back to 300s for anything unrecognised so the tool degrades to a
    sensible 5-minute window rather than erroring on an exotic duration.
    """
    match = re.fullmatch(r"(\d+)([smhdw])", window.strip())
    if not match:
        return 300.0
    value = int(match.group(1))
    unit = match.group(2)
    factor = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    return float(value * factor)
