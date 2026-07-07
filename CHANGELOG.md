# Changelog

All notable changes to `prometheus-mcp` will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed

- **RCA change-point detection no longer fabricates events.** With
  `correlate_alerts_across_instances(enable_rca=True)`, `RCAEngine` ran
  `ChangePointDetector.detect_change_points`, which invented deployment /
  config / scaling events (fixed 15/30/45-minute offsets, hardcoded
  `correlation_strength` of 0.8/0.6/0.4, `affected_services: ["unknown_service"]`)
  for every alert timestamp — plausible-looking data returned to users as
  fact. It now returns an empty result (no external change source is wired
  up) while still validating input timestamps, so a real detector can drop in
  without changing the interface. Downstream ranking contributes no
  change-score when there are no events.

## [0.4.2] — 2026-07-07

### Fixed

- **Registry lazy-init regression (79 failing tests).** The v3.0 Federation
  refactor replaced the lazy-initialised client singleton with an
  `InstanceRegistry` that is only populated by `app_lifespan`. As a result
  `get_client()` / `get_alertmanager_client()` raised
  `RuntimeError: Registry not initialized` whenever a tool function was called
  without the server lifespan running — which is exactly how the integration,
  status, alertmanager and client-cache tests invoke them. Restored the
  pre-v3.0 contract via a thread-safe `_mcp._ensure_registry()` that lazily
  builds the registry from `PROMETHEUS_MCP_CONFIG` (federation) or the
  `PROMETHEUS_*` env vars (v2.0 legacy mode) on first use. `get_registry()`
  (federation/correlation tools) intentionally stays strict.
- **Protocol contract test** (`test_protocol.py`) updated to include the four
  v4.0 correlation/federation tools now registered by `server.py`, with their
  annotations and parameter sets; renamed from `test_all_sixteen_tools_*`.
- **Client-cache test** reset the removed `_client`/`_client_lock` globals;
  updated to reset the renamed `_registry`/`_registry_lock`.
- **Lint gate green.** Fixed repo-wide ruff findings that failed CI before
  pytest even ran: bare `except:` → `except Exception:`, `zip(..., strict=...)`,
  `raise ... from None`, F401 on the RCA availability-probe imports (now
  `# noqa`), and removed two dead local assignments.

## [0.4.1] — 2026-07-07

### Fixed

- **v4.0 correlation/federation tools were never registered.** `server.py`
  imported only `tools`, `tools_alertmanager`, and `tools_status`, so the
  `@mcp.tool` decorators in `tools_correlation` and `tools_federation` never
  ran against the live server. The four tools
  (`correlate_alerts_across_instances`, `group_alerts_by_service`,
  `detect_cascading_alerts`, `federation_list_instances`) are now wired into
  `server.py` and exposed. Unit tests passed only because they imported the
  modules directly.
- **Frozen `None` registry.** `tools_correlation` and `tools_federation_v4`
  captured `from _mcp import _registry` by value at import time, when it is
  still `None` (it is assigned during lifespan startup). Tools now call a new
  `_mcp.get_registry()` accessor that reads the live global at call time.
- **`federation_list_instances` import crash.** Its return type was a fieldless
  `dict` subclass used with `structured_output=True`, which FastMCP cannot turn
  into an output schema (`InvalidSignature`). Replaced with a proper
  `ListInstancesOutput` TypedDict in `models.py`. Also dropped a bogus
  `mcp.state.get("registry")` lookup (`mcp` has no `state` attribute).

### Added

- `tests/test_server_registration.py`: smoke test asserting the exact set of
  tools the server entry point exposes — guards against unregistered modules.

### Known issues

- **`federation_analyze_alerts` (`tools_federation_v4`) is NOT registered.** Its
  implementation references APIs that do not exist (`PrometheusClient.list_alerts`/
  `query`/`instance_name`, `RCAEngine(clients)` vs the real `(registry)`
  constructor, `output.warn`, `output.ok(content=…, structured_content=…)`,
  `CorrelationResult.dict()`, `registry.get_all_clients()`). It must be rewritten
  against the real engine/client APIs before it can be exposed.

## [0.4.0] — 2026-06-18

### Added

- **Advanced Alert Correlation**: Cross-instance alert analysis with pattern detection and grouping
  - Temporal window matching and label similarity scoring for related alerts
  - Service-based alert grouping across all federated instances
  - Cascading alert detection with directional dependency inference
  - Correlation strength metrics with dual-channel output (markdown + JSON)

- **Root Cause Analysis Tools**: Anomaly detection, dependency traversal, and change point identification
  - Statistical outlier detection in metrics with seasonality adjustment
  - Service dependency chain traversal from symptoms to potential root causes
  - Change point detection correlating deployments/config changes with alert onset
  - Root cause candidate ranking based on proximity, evidence strength, and impact

- **Dependency Mapping & Health**: Dynamic service dependency maps with cross-cluster awareness
  - Traffic correlation analysis for discovering service relationships
  - Cross-cluster dependency visualization showing interoperation between services
  - Synthetic health probing assessing dependency resilience under various conditions
  - Load shedding recommendations based on dependency fragility assessments

- **Trend Analysis & Benchmarking**: Historical pattern recognition and capacity forecasting
  - Recurring schedule identification and seasonal behavior detection
  - Resource exhaustion prediction based on usage trends
  - MTTR benchmarking comparing resolution times against historical data
  - Deviation detection triggering higher-priority notifications for pattern breaks

- **Integrated Federation Analysis**: Unified tool combining all v4.0 features
  - New `federation_analyze_alerts` tool for comprehensive incident investigation
  - Enhanced existing tools with optional correlation context parameters
  - Unified output format combining alerts, metrics, dependencies, and trends

## [0.3.0] — 2026-06-18

### Added

- **Federation Support**: Multi-instance Prometheus queries with fan-out execution
  - Config file support for named Prometheus instances with per-instance auth
  - `instance` parameter added to all 16 Prometheus tools for targeted queries
  - Fan-out queries across all instances with `instance="all"` parameter
  - Subset targeting with `instances=[...]` parameter for specific instance groups
  - Result merging with `__prometheus_instance__` label injection for source attribution
  - Partial failure handling: return available results with error annotations
  - Global response size caps applied post-merge (500 metrics, 5000 range points)

- **Alertmanager Federation**: Multi-instance Alertmanager support with fan-out queries
  - Config file support for named Alertmanager instances with per-instance auth
  - `instance` parameter added to all 4 Alertmanager tools for targeted queries
  - Fan-out queries across all Alertmanager instances with `instance="all"`
  - Alert deduplication by fingerprint when identical alerts from HA cluster peers
  - `__alertmanager_instance__` label injection for source attribution
  - Unified health monitoring for mixed Prometheus/Alertmanager instances

- **Instance Discovery**: New `federation_list_instances` tool for multi-instance awareness
  - List all configured Prometheus and Alertmanager instances with URLs and types
  - Parallel health probing (/-/healthy) to show reachability status
  - Response time measurements and error details for each instance
  - Federation mode detection and instance count reporting

- **Core Infrastructure**: Thread-safe registry and federation modules
  - `InstanceRegistry` for managing N PrometheusClient + AlertmanagerClient pairs
  - Per-instance authentication, TTL caches, and session lifecycle management
  - `federation.py` with ThreadPoolExecutor-based fan-out execution
  - Configurable worker pools, timeout handling, and structured error reporting

- **Backward Compatibility**: Zero behavioral change when no config file is present
  - Legacy mode creates single "default" entry from environment variables
  - All existing tool signatures and behavior preserved
  - Environment variable fallback for seamless v2.0 → v3.0 migration

## [0.2.0] — 2026-06-08

### Added

- `prometheus_get_metric_metadata` — get metric HELP text, TYPE, and UNIT
- `prometheus_list_label_values` — list all values for a label with optional match filter
- `prometheus_list_rules` — list recording and alerting rules by group
- `prometheus_health_check` — check Prometheus liveness (/-/healthy) and readiness (/-/ready)
- `prometheus_get_cardinality` — TSDB stats: series count, top metrics by cardinality, top labels
- `prometheus_get_runtime_info` — goroutines, time series count, storage retention
- `prometheus_get_build_info` — Prometheus version, Go version, revision
- `alertmanager_list_silences` — list silences with matchers, status, creator
- `alertmanager_list_alerts` — list alerts with suppressed/inhibited state and silence IDs
- `alertmanager_get_status` — Alertmanager cluster status, version, config
- `alertmanager_list_alert_groups` — alert groups with routing topology
- Automatic retry (1 retry, 1s backoff) for transient 5xx/ConnectionError/Timeout failures
- Configurable HTTP timeout via `PROMETHEUS_TIMEOUT` (default 30s)
- Response size limits via `PROMETHEUS_MAX_RESPONSE_BYTES` (default 10MB)
- Metric name caching with TTL via `PROMETHEUS_CACHE_TTL` (default 300s)
- `AlertmanagerClient` for Alertmanager API v2 (separate URL, same auth pattern)
- `get_raw()` method on PrometheusClient for management endpoints outside /api/v1
- Shared test fixtures in `tests/conftest.py`
- TTL cache module (`cache.py`) with thread-safe monotonic-clock expiry

## [0.1.0] — 2026-04-18

### Added

- `prometheus_list_metrics` — list all metric names with optional substring filter (cap 500)
- `prometheus_query` — instant PromQL query with optional time parameter
- `prometheus_query_range` — range PromQL query with time-series output (cap 5000 points)
- `prometheus_list_alerts` — list active alerts grouped by state + severity
- `prometheus_list_targets` — list scrape targets summarised by job + health
- HTTP Basic auth and Bearer token auth support (Bearer takes precedence)
- SSL verification toggle via `PROMETHEUS_SSL_VERIFY`
- Thread-safe lazy client cache (double-checked locking)
- Structured output (`outputSchema`) for all 5 tools via FastMCP `structured_output=True`
- Markdown rendering with truncation hints for large result sets
- Actionable error messages for 401/403/404/400/422/429/5xx/ConnectionError/Timeout
