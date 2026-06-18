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
    rca_enhancement: dict[str, Any] | None


class CascadeDetectionResult(TypedDict):
    total_cascades: int
    cascades: list[CascadeRelationship]
    root_causes: list[CorrelatedAlert]
    rca_enhancement: dict[str, Any] | None


# ── Dependency Mapping & Health ──────────────────────────────────────────────


class ServiceNode(TypedDict):
    """Represents a service in the dependency graph.

    Attributes:
        service_id: Unique identifier for the service
        name: Display name of the service
        namespace: Namespace/team that owns the service
        cluster: Cluster/region where the service runs
        instance: Specific instance name
        health_status: Current health status (healthy, degraded, failed)
        metadata: Additional service metadata
        last_seen: Timestamp when service was last observed
    """

    service_id: str
    name: str
    namespace: str | None
    cluster: str | None
    instance: str | None
    health_status: str
    metadata: dict[str, Any]
    last_seen: str


class DependencyEdge(TypedDict):
    """Represents a dependency relationship between services.

    Attributes:
        source: Source service identifier
        target: Target service identifier
        strength: Confidence/weight of the dependency relationship (0.0-1.0)
        relationship_type: Type of dependency (direct, transitive, inferred)
        latency_avg: Average latency of requests between services
        error_rate: Error rate of requests between services
        throughput: Requests per second between services
        last_observed: Timestamp when dependency was last observed
        metadata: Additional edge metadata
    """

    source: str
    target: str
    strength: float
    relationship_type: str
    latency_avg: float | None
    error_rate: float | None
    throughput: float | None
    last_observed: str
    metadata: dict[str, Any]


class CrossClusterInfo(TypedDict):
    """Information about cross-cluster service relationships.

    Attributes:
        cluster_id: Identifier for the cluster
        region: Geographic region of the cluster
        services: List of services in this cluster
        connections: List of cross-cluster connections
        health_status: Overall health of the cluster
    """

    cluster_id: str
    region: str | None
    services: list[str]
    connections: list[dict[str, Any]]
    health_status: str


class DependencyGraph(TypedDict):
    """Complete dependency graph representation.

    Attributes:
        nodes: List of service nodes in the graph
        edges: List of dependency relationships
        clusters: Cross-cluster information
        timestamp: Timestamp when graph was generated
        version: Version of the graph schema
        metadata: Additional graph metadata
    """

    nodes: list[ServiceNode]
    edges: list[DependencyEdge]
    clusters: list[CrossClusterInfo]
    timestamp: str
    version: str
    metadata: dict[str, Any]


class CorrelationAnalysisResult(TypedDict):
    """Result of traffic correlation analysis.

    Attributes:
        correlations: List of discovered correlations
        confidence_scores: Confidence scores for each correlation
        time_range: Time range of analysis
        total_services: Total number of services analyzed
        analysis_method: Method used for correlation analysis
    """

    correlations: list[dict[str, Any]]
    confidence_scores: dict[str, float]
    time_range: dict[str, str]
    total_services: int
    analysis_method: str


class DependencyAnalysisResult(TypedDict):
    """Complete dependency analysis result.

    Attributes:
        graph: Constructed dependency graph
        correlation_data: Raw correlation analysis data
        confidence_score: Overall confidence in the analysis
        anomalies_detected: Any anomalies in dependency patterns
        recommendations: Recommendations based on analysis
    """

    graph: DependencyGraph
    correlation_data: CorrelationAnalysisResult
    confidence_score: float
    anomalies_detected: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]


class ClusterInfo(TypedDict):
    """Information about a cluster for visualization.

    Attributes:
        cluster_id: Unique identifier for the cluster
        name: Display name of the cluster
        region: Geographic region of the cluster
        status: Current status of the cluster (healthy, degraded, failed)
        services: Number of services in the cluster
        dependencies: Number of cross-cluster dependencies
        metadata: Additional cluster metadata
    """

    cluster_id: str
    name: str
    region: str | None
    status: str
    services: int
    dependencies: int
    metadata: dict[str, Any]


class VisualizationResult(TypedDict):
    """Result of cross-cluster dependency visualization.

    Attributes:
        graph: Dependency graph with visualization metadata
        clusters: Cluster information for visualization
        layout_coordinates: Coordinates for graph layout
        color_mapping: Color scheme for different cluster/service types
        legend: Legend information for the visualization
    """

    graph: DependencyGraph
    clusters: list[ClusterInfo]
    layout_coordinates: dict[str, dict[str, float]]
    color_mapping: dict[str, str]
    legend: dict[str, str]


class SyntheticProbe(TypedDict):
    """Configuration for a synthetic health probe.

    Attributes:
        probe_id: Unique identifier for the probe
        target_service: Target service to probe
        target_endpoint: Specific endpoint to probe
        frequency_seconds: How often to run the probe
        timeout_seconds: Timeout for probe requests
        payload: Optional payload to send with the probe
        headers: Optional headers to include with the probe
        expected_response: Expected response pattern
        metadata: Additional probe metadata
    """

    probe_id: str
    target_service: str
    target_endpoint: str
    frequency_seconds: int
    timeout_seconds: int
    payload: str | None
    headers: dict[str, str] | None
    expected_response: str | None
    metadata: dict[str, Any]


class HealthProbeResult(TypedDict):
    """Result of a synthetic health probe execution.

    Attributes:
        probe_id: Identifier of the probe that was executed
        target_service: Service that was probed
        timestamp: When the probe was executed
        success: Whether the probe succeeded
        response_time_ms: Response time in milliseconds
        status_code: HTTP status code (if applicable)
        error_message: Error message if probe failed
        metrics: Additional metrics from the probe
        resilience_score: Calculated resilience score (0.0-1.0)
    """

    probe_id: str
    target_service: str
    timestamp: str
    success: bool
    response_time_ms: float | None
    status_code: int | None
    error_message: str | None
    metrics: dict[str, Any]
    resilience_score: float


class LoadSheddingRecommendation(TypedDict):
    """Recommendation for load shedding based on dependency fragility.

    Attributes:
        service: Service identifier for the recommendation
        priority: Priority level (high, medium, low)
        action: Recommended action (reduce_load, monitor_closely, protect_path)
        reason: Reason for the recommendation
        confidence: Confidence score in the recommendation (0.0-1.0)
        alternatives: Alternative approaches to consider
        estimated_impact: Estimated impact of following the recommendation
        implementation_guide: Guide for implementing the recommendation
    """

    service: str
    priority: str
    action: str
    reason: str
    confidence: float
    alternatives: list[dict[str, Any]]
    estimated_impact: dict[str, Any] | None
    implementation_guide: list[str] | None
