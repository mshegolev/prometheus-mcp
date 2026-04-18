"""TypedDict output schemas for every MCP tool.

These schemas are read by FastMCP (``structured_output=True``) to generate
a JSON-Schema ``outputSchema`` for each tool. Clients that support
structured data use that schema to validate the ``structuredContent``
payload; clients that don't use the markdown ``content`` block instead.

**Python / Pydantic compat note.** We deliberately avoid
``Required`` / ``NotRequired`` qualifiers: Pydantic 2.13+ mishandles them
during runtime schema generation on Py < 3.12 (see
https://errors.pydantic.dev/2.13/u/typed-dict-version). Optional fields use
``| None`` convention; the code always sets the key (``None`` when absent).
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict


# ── Metrics list ──────────────────────────────────────────────────────────────


class ListMetricsOutput(TypedDict):
    total_count: int
    returned_count: int
    truncated: bool
    pattern: str | None
    metrics: list[str]


# ── Instant query ─────────────────────────────────────────────────────────────


class InstantSample(TypedDict):
    labels: dict[str, str]
    timestamp: float
    value: str


class QueryOutput(TypedDict):
    query: str
    time: str | None
    result_type: str
    result_count: int
    data: list[InstantSample]


# ── Range query ───────────────────────────────────────────────────────────────


class RangeSeries(TypedDict):
    labels: dict[str, str]
    point_count: int
    values: list[list[float | str]]


class QueryRangeOutput(TypedDict):
    query: str
    start: str
    end: str
    step: str
    result_type: str
    series_count: int
    total_points: int
    truncated: bool
    data: list[RangeSeries]


# ── Alerts ────────────────────────────────────────────────────────────────────


class AlertItem(TypedDict):
    labels: dict[str, str]
    annotations: dict[str, str]
    state: str
    active_at: str
    value: str


class AlertStateSummary(TypedDict):
    state: str
    count: int


class ListAlertsOutput(TypedDict):
    total_count: int
    firing_count: int
    pending_count: int
    state_summary: list[AlertStateSummary]
    alerts: list[AlertItem]


# ── Targets ───────────────────────────────────────────────────────────────────


class TargetItem(TypedDict):
    job: str
    instance: str
    health: str
    last_scrape_duration_ms: float
    last_error: str | None
    labels: dict[str, str]


class TargetJobSummary(TypedDict):
    job: str
    total: int
    up: int
    down: int
    unknown: int


class ListTargetsOutput(TypedDict):
    state_filter: str
    total_count: int
    up_count: int
    down_count: int
    unknown_count: int
    job_summary: list[TargetJobSummary]
    targets: list[TargetItem]
