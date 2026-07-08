# Requirements: prometheus-mcp

**Defined:** 2026-06-08
**Core Value:** AI agents can autonomously investigate production errors by querying Prometheus metrics, metadata, labels, alerts, targets, rules, cardinality, and Alertmanager state — across multiple instances

## v5.0 Requirements (Active)

Requirements for milestone v5.0: Real Metric-Driven Intelligence.
Carries forward the v4.0 deferred debt — DEP/TRE/RCA-03/FED shipped as simulation in v4.0.

### Dependency Mapping (Real)

- [ ] **DEP-R01**: AI agent can discover service-to-service dependencies from live Prometheus traffic/request metrics that carry `source`/`destination` (or equivalent) labels — no simulation, no mock probes
- [ ] **DEP-R02**: `prometheus_map_service_dependencies` tool registered on server; accepts `instance`, optional label matchers, and time window; returns a dependency graph (nodes = services, edges = traffic volume / error rate) in markdown + structured JSON

### Root Cause Analysis — Change Points (Real)

- [ ] **RCA-R04**: Change-point detection backed by real Prometheus metric deltas — `*_build_info` label-set changes and `process_start_time_seconds` jumps identify restarts/deployments; replaces the stub that previously returned an empty result; integrated into `correlate_alerts_across_instances(enable_rca=True)` pipeline

### Trend Analysis & MTTR (Real)

- [ ] **TRE-R01**: Trend analysis engine queries `ALERTS` metric via `query_range` to compute real historical alert patterns, recurrence schedules, and approximate MTTR from alert-onset to alert-resolved transitions — no clock-based simulation
- [ ] **TRE-R02**: `prometheus_trend_analysis` tool registered on server; accepts `instance`, alert name filter, lookback window; returns trend report (recurrence, avg duration, MTTR estimate) in markdown + structured JSON

### Federation Analyze Alerts (Real)

- [ ] **FED-R01**: `federation_analyze_alerts` tool rewritten against real APIs (`InstanceRegistry`, `CorrelationEngine`, `RCAEngine(registry)`, FastMCP output conventions); registered on `server.py`; replaces EXPERIMENTAL `tools_federation_v4.py` stub; end-to-end flow: fetch alerts → correlate → optional RCA → dependency context → trend summary → unified output

### Quality & Release

- [ ] **QUAL-R01**: Every v5.0 phase has a VERIFICATION.md before being marked complete; all tests pass (`pytest -q` green, 0 ruff errors); version bumped to 0.5.0; released to PyPI via CI; `CHANGELOG.md` updated

## v4.0 Requirements

Requirements for milestone v4.0: Advanced Alert Correlation.

### Alert Correlation

- [ ] **COR-01**: Cross-instance alert matching to identify related alerts that fire simultaneously or in sequence across different Prometheus instances
- [ ] **COR-02**: Alert grouping by service to bundle related alerts into service-level incident analysis
- [ ] **COR-03**: Cascading alert detection to identify alert propagation patterns indicating dependency failures

### Root Cause Analysis

- [ ] **RCA-01**: Anomaly detection in metrics to identify unusual patterns preceding alert storms
- [ ] **RCA-02**: Dependency chain traversal to trace through service dependencies to find failure origins
- [ ] **RCA-03**: Change point detection to identify recent changes correlating with alert onset

### Service Dependencies

- [ ] **DEP-01**: Dynamic dependency mapping to discover and visualize service dependencies based on metric correlations
- [ ] **DEP-02**: Cross-cluster dependency awareness to understand interoperation between services in different clusters/regions
- [ ] **DEP-03**: Dependency health probing to assess stability of service dependencies under various conditions

### Trend Analysis

- [ ] **TRE-01**: Historical alert pattern recognition to identify recurring alert patterns and seasonal behaviors
- [ ] **TRE-02**: Capacity and growth trend analysis to predict resource exhaustion based on usage trends
- [ ] **TRE-03**: Mean time to recovery benchmarking to compare incident resolution times against historical benchmarks

## v3.0 Requirements (Completed)

### Configuration

- [x] **CFG-01**: Server loads a JSON config file (via PROMETHEUS_MCP_CONFIG env var) defining named Prometheus/Alertmanager instances with URLs, auth, and per-instance settings
- [x] **CFG-02**: Config file has a `version: 1` field for future schema evolution, with clear errors on missing/unknown versions
- [x] **CFG-03**: Each instance in config supports independent authentication (Bearer token or Basic auth credentials)
- [x] **CFG-04**: Config file supports a `defaults` section for shared settings (timeout, ssl_verify, max_response_bytes, cache_ttl) inherited by instances
- [x] **CFG-05**: Per-instance config can override defaults for timeout, max_response_bytes, and cache_ttl
- [x] **CFG-06**: Config validation at startup produces actionable error messages referencing the config file path and instance name
- [x] **CFG-07**: When no config file is specified, server operates in single-instance mode using existing env vars (PROMETHEUS_URL, etc.) — fully backward compatible with v2.0

### Instance Management

- [x] **INST-01**: Server maintains a thread-safe client registry mapping instance names to PrometheusClient/AlertmanagerClient pairs with per-instance HTTP sessions
- [x] **INST-02**: `federation_list_instances` tool returns all configured instances with names, URLs (no secrets), type (prometheus/alertmanager), and health status
- [x] **INST-03**: Each instance has its own metric name TTL cache, isolated from other instances
- [x] **INST-04**: Instance listing tool performs parallel health probes (/-/healthy) to show which instances are reachable

### Query Federation

- [x] **FED-01**: All existing Prometheus tools accept an optional `instance` parameter to target a specific named instance
- [x] **FED-02**: Fan-out queries execute the same PromQL across all (or a subset of) instances in parallel using ThreadPoolExecutor
- [x] **FED-03**: Fan-out results inject `__prometheus_instance__` label into every metric sample to identify the source instance
- [x] **FED-04**: Partial failure handling: if some instances fail during fan-out, return available results plus warnings listing failed instances — only raise ToolError if ALL instances fail
- [x] **FED-05**: Fan-out supports subset targeting via an `instances` parameter (list of instance names to query)
- [x] **FED-06**: Fan-out response size is capped globally (not per-instance) to prevent response explosion

### Alertmanager Federation

- [x] **AMF-01**: Config file supports named Alertmanager instances with per-instance auth, same pattern as Prometheus instances
- [x] **AMF-02**: All existing Alertmanager tools accept an optional `instance` parameter to target a specific Alertmanager
- [x] **AMF-03**: Alertmanager fan-out queries across multiple instances with parallel execution and partial failure handling
- [x] **AMF-04**: Alertmanager alert deduplication by fingerprint when fan-out returns the same alert from multiple HA cluster peers

## v2.0 Requirements (Completed)

- [x] **AM-01**: Agent can list Alertmanager silences with matchers, status, creator, and comment
- [x] **AM-02**: Agent can list Alertmanager alerts with suppressed/inhibited state, silence IDs
- [x] **AM-03**: Agent can get Alertmanager cluster status, version, uptime, and raw config YAML
- [x] **AM-04**: Agent can list alert groups showing how alerts are grouped for notification routing
- [x] **CARD-01**: Agent can view TSDB statistics including total series count, top metrics by cardinality
- [x] **OPS-01**: Agent can check Prometheus health and readiness for liveness probe verification
- [x] **OPS-02**: HTTP responses are capped at configurable byte limit
- [x] **OPS-03**: Metric name list responses are cached with configurable TTL
- [x] **STAT-01**: Agent can view Prometheus runtime info
- [x] **STAT-02**: Agent can view Prometheus build info
- [x] **TOOL-01**: Agent can retrieve metric metadata (HELP text, TYPE, UNIT)
- [x] **TOOL-02**: Agent can list all values for a specific label
- [x] **TOOL-03**: Agent can inspect recording rules and alerting rules
- [x] **REL-01**: HTTP requests automatically retry once on transient 5xx errors
- [x] **REL-02**: HTTP timeout is configurable via PROMETHEUS_TIMEOUT
- [x] **QUAL-01**: Shared test fixtures extracted to tests/conftest.py
- [x] **QUAL-02**: Tests cover prometheus_list_targets with state='dropped' and state='any'
- [x] **QUAL-03**: Tests cover PrometheusClient timeout behavior, empty responses, and session reuse

## Future Requirements

Deferred beyond v4.0.

- **ADV-03**: Automatic federation discovery via DNS/Consul/K8s
- **CFG-08**: Environment variable substitution in config file values (${VAR} syntax)
- **CFG-09**: Config file hot-reload via SIGHUP or file watcher
- **FED-07**: Per-instance fan-out timeout (shorter than per-client timeout) with total fan-out deadline

## Out of Scope

| Feature | Reason |
|---------|--------|
| Write operations to Prometheus/Alertmanager | Read-only by design — safety critical |
| Alertmanager silence create/delete | Write operation; AI agents must not silently suppress alerts |
| Custom PromQL query builder | Agents should write PromQL directly |
| UI/frontend/dashboard | Headless MCP server |
| Cross-instance PromQL evaluation | Requires full PromQL engine (Thanos/Cortex territory) |
| Automatic instance discovery | Static config; users can generate JSON from their service discovery |
| YAML config file format | Would require pyyaml dependency; JSON is stdlib |
| HA replica deduplication | Use Thanos for HA dedup; MCP returns raw results with instance labels |
| Result aggregation across instances | Return raw labeled results; let AI agent reason about patterns |
| Config file encryption/vault | Use restricted file permissions (0600); same model as env var secrets |
| Automated incident response | Focus remains on investigative tools; response is external concern |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CFG-01 | 1 | ✅ Complete |
| CFG-02 | 1 | ✅ Complete |
| CFG-03 | 1 | ✅ Complete |
| CFG-04 | 1 | ✅ Complete |
| CFG-05 | 1 | ✅ Complete |
| CFG-06 | 1 | ✅ Complete |
| CFG-07 | 1 | ✅ Complete |
| INST-01 | 2 | ✅ Complete |
| INST-02 | 5 | ✅ Complete |
| INST-03 | 2 | ✅ Complete |
| INST-04 | 5 | ✅ Complete |
| FED-01 | 5 | ✅ Complete |
| FED-02 | 4 | ✅ Complete |
| FED-03 | 4 | ✅ Complete |
| FED-04 | 4 | ✅ Complete |
| FED-05 | 5 | ✅ Complete |
| FED-06 | 4 | ✅ Complete |
| AMF-01 | 6 | ✅ Complete |
| AMF-02 | 6 | ✅ Complete |
| AMF-03 | 6 | ✅ Complete |
| AMF-04 | 6 | ✅ Complete |
| COR-01 | TBD | Pending |
| COR-02 | TBD | Pending |
| COR-03 | TBD | Pending |
| RCA-01 | TBD | Pending |
| RCA-02 | TBD | Pending |
| RCA-03 | TBD | Pending |
| DEP-01 | TBD | Pending |
| DEP-02 | TBD | Pending |
| DEP-03 | TBD | Pending |
| TRE-01 | TBD | ⚠ Simulation in v4.0 |
| TRE-02 | TBD | ⚠ Simulation in v4.0 |
| TRE-03 | TBD | ⚠ Simulation in v4.0 |
| DEP-R01 | 14 | ○ Pending (v5.0) |
| DEP-R02 | 14 | ○ Pending (v5.0) |
| RCA-R04 | 15 | ○ Pending (v5.0) |
| TRE-R01 | 16 | ○ Pending (v5.0) |
| TRE-R02 | 16 | ○ Pending (v5.0) |
| FED-R01 | 17 | ○ Pending (v5.0) |
| QUAL-R01 | 18 | ○ Pending (v5.0) |

**Coverage:**
- v3.0 requirements: 21 total, 21 completed
- v4.0 requirements: 12 total (COR satisfied; RCA-01/02 partial; DEP/TRE/RCA-03 simulation)
- v5.0 requirements: 7 total, 0 completed

---
*Requirements defined: 2026-06-08*
*Last updated: 2026-07-08 after v5.0 scoping (DEP/TRE/RCA-03/FED carried from v4.0 debt)*
