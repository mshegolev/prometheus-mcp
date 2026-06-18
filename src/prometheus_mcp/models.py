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
from typing import Any

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


# ── Metric metadata ──────────────────────────────────────────────────────────


class MetadataEntry(TypedDict):
    type: str
    help: str
    unit: str


class GetMetricMetadataOutput(TypedDict):
    metric: str | None
    total_count: int
    returned_count: int
    truncated: bool
    metadata: dict[str, list[MetadataEntry]]


# ── Label values ─────────────────────────────────────────────────────────────


class ListLabelValuesOutput(TypedDict):
    label: str
    match: str | None
    total_count: int
    returned_count: int
    truncated: bool
    values: list[str]


# ── Rules ────────────────────────────────────────────────────────────────────


class RuleItem(TypedDict):
    name: str
    query: str
    type: str
    state: str | None
    labels: dict[str, str]
    health: str | None


class RuleGroupItem(TypedDict):
    name: str
    file: str
    rule_count: int
    rules: list[RuleItem]


class ListRulesOutput(TypedDict):
    type_filter: str | None
    total_groups: int
    total_rules: int
    recording_count: int
    alerting_count: int
    groups: list[RuleGroupItem]


# ── Health check ─────────────────────────────────────────────────────────────


class HealthCheckOutput(TypedDict):
    healthy: bool
    healthy_status_code: int
    ready: bool
    ready_status_code: int


# ── Cardinality / TSDB stats ────────────────────────────────────────────────


class CardinalityTopItem(TypedDict):
    name: str
    value: int


class CardinalityOutput(TypedDict):
    num_series: int
    num_label_pairs: int
    chunk_count: int
    min_time: int
    max_time: int
    top_metrics_by_series: list[CardinalityTopItem]
    top_labels_by_value_count: list[CardinalityTopItem]
    top_labels_by_memory_bytes: list[CardinalityTopItem]


# ── Runtime info ─────────────────────────────────────────────────────────────


class RuntimeInfoOutput(TypedDict):
    start_time: str
    goroutine_count: int
    time_series_count: int
    storage_retention: str
    corruptionCount: int
    reloadConfigSuccess: bool
    lastConfigTime: str


# ── Build info ───────────────────────────────────────────────────────────────


class BuildInfoOutput(TypedDict):
    version: str
    revision: str
    branch: str
    buildUser: str
    buildDate: str
    goVersion: str


# ── Root Cause Analysis ──────────────────────────────────────────────────────


class AnomalyDetectionResult(TypedDict):
    total_anomalies: int
    metric_anomalies: list[dict]
    detection_method: str
    sensitivity: float
    time_range: dict[str, str]


class DependencyTraversalPath(TypedDict):
    nodes: list[str]
    edges: list[dict]
    evidence_weight: float
    impact_score: float


class DependencyTraversalResult(TypedDict):
    total_paths: int
    paths: list[DependencyTraversalPath]
    root_causes: list[dict]
    traversal_depth: int


class ChangePointEvent(TypedDict):
    timestamp: str
    event_type: str
    description: str
    correlation_strength: float
    affected_services: list[str]


class ChangePointDetectionResult(TypedDict):
    total_events: int
    events: list[ChangePointEvent]
    time_window: dict[str, str]
    correlation_threshold: float


class RootCauseCandidate(TypedDict):
    identifier: str
    evidence_score: float
    impact_assessment: dict[str, Any]
    confidence_interval: dict[str, float]
    ranking_explanation: str


class RootCauseRankingResult(TypedDict):
    candidates: list[RootCauseCandidate]
    ranking_method: str
    total_candidates: int
    top_candidate: str | None


# ── Alertmanager silences ────────────────────────────────────────────────────


class SilenceMatcher(TypedDict):
    name: str
    value: str
    isRegex: bool
    isEqual: bool


class SilenceItem(TypedDict):
    id: str
    status: str
    matchers: list[SilenceMatcher]
    createdBy: str
    comment: str
    startsAt: str
    endsAt: str
    updatedAt: str


class ListSilencesOutput(TypedDict):
    total_count: int
    active_count: int
    pending_count: int
    expired_count: int
    silences: list[SilenceItem]


# ── Alertmanager alerts ──────────────────────────────────────────────────────


class AMAlertStatus(TypedDict):
    state: str
    silencedBy: list[str]
    inhibitedBy: list[str]


class AMAlertItem(TypedDict):
    labels: dict[str, str]
    annotations: dict[str, str]
    status: AMAlertStatus
    startsAt: str
    endsAt: str
    generatorURL: str
    fingerprint: str


class ListAMAlertsOutput(TypedDict):
    total_count: int
    active_count: int
    suppressed_count: int
    unprocessed_count: int
    alerts: list[AMAlertItem]


# ── Alertmanager status ──────────────────────────────────────────────────────


class AMStatusOutput(TypedDict):
    cluster_status: str
    version_info: dict[str, str]
    uptime: str
    config_yaml: str


# ── Alertmanager alert groups ────────────────────────────────────────────────


class AMAlertGroupItem(TypedDict):
    labels: dict[str, str]
    receiver: str
    alert_count: int


class ListAMAlertGroupsOutput(TypedDict):
    total_groups: int
    total_alerts: int
    groups: list[AMAlertGroupItem]


# ── Correlation Engine ───────────────────────────────────────────────────────


class CorrelatedAlert(TypedDict):
    alert: AMAlertItem
    instance: str
    correlation_score: float


class CorrelationGroup(TypedDict):
    group_id: str
    alerts: list[CorrelatedAlert]
    service_identifier: str
    correlation_strength: float


class CascadeRelationship(TypedDict):
    parent: CorrelatedAlert
    child: CorrelatedAlert
    dependency_strength: float
    temporal_delay: float


class CorrelationResult(TypedDict):
    total_correlations: int
    correlated_alerts: list[CorrelatedAlert]
    groups: list[CorrelationGroup]
    cascades: list[CascadeRelationship]
    instance_attribution: dict[str, int]
    rca_enhancement: dict[str, Any] | None


class AlertGroupResult(TypedDict):
    total_groups: int
    groups: dict[str, list[AMAlertItem]]
    ungrouped_count: int


class CascadeDetectionResult(TypedDict):
    total_cascades: int
    cascades: list[CascadeRelationship]
    root_causes: list[CorrelatedAlert]
