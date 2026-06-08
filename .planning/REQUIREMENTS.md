# Requirements: prometheus-mcp

**Defined:** 2026-06-08
**Core Value:** AI agents can autonomously investigate production errors by querying Prometheus metrics, metadata, labels, alerts, targets, rules, cardinality, and Alertmanager state — across multiple instances

## v3.0 Requirements

Requirements for milestone v3.0: Federation.

### Configuration

- [ ] **CFG-01**: Server loads a JSON config file (via PROMETHEUS_MCP_CONFIG env var) defining named Prometheus/Alertmanager instances with URLs, auth, and per-instance settings
- [ ] **CFG-02**: Config file has a `version: 1` field for future schema evolution, with clear errors on missing/unknown versions
- [ ] **CFG-03**: Each instance in config supports independent authentication (Bearer token or Basic auth credentials)
- [ ] **CFG-04**: Config file supports a `defaults` section for shared settings (timeout, ssl_verify, max_response_bytes, cache_ttl) inherited by instances
- [ ] **CFG-05**: Per-instance config can override defaults for timeout, max_response_bytes, and cache_ttl
- [ ] **CFG-06**: Config validation at startup produces actionable error messages referencing the config file path and instance name
- [ ] **CFG-07**: When no config file is specified, server operates in single-instance mode using existing env vars (PROMETHEUS_URL, etc.) — fully backward compatible with v2.0

### Instance Management

- [ ] **INST-01**: Server maintains a thread-safe client registry mapping instance names to PrometheusClient/AlertmanagerClient pairs with per-instance HTTP sessions
- [ ] **INST-02**: `federation_list_instances` tool returns all configured instances with names, URLs (no secrets), type (prometheus/alertmanager), and health status
- [ ] **INST-03**: Each instance has its own metric name TTL cache, isolated from other instances
- [ ] **INST-04**: Instance listing tool performs parallel health probes (/-/healthy) to show which instances are reachable

### Query Federation

- [ ] **FED-01**: All existing Prometheus tools accept an optional `instance` parameter to target a specific named instance
- [ ] **FED-02**: Fan-out queries execute the same PromQL across all (or a subset of) instances in parallel using ThreadPoolExecutor
- [ ] **FED-03**: Fan-out results inject `__prometheus_instance__` label into every metric sample to identify the source instance
- [ ] **FED-04**: Partial failure handling: if some instances fail during fan-out, return available results plus warnings listing failed instances — only raise ToolError if ALL instances fail
- [ ] **FED-05**: Fan-out supports subset targeting via an `instances` parameter (list of instance names to query)
- [ ] **FED-06**: Fan-out response size is capped globally (not per-instance) to prevent response explosion

### Alertmanager Federation

- [ ] **AMF-01**: Config file supports named Alertmanager instances with per-instance auth, same pattern as Prometheus instances
- [ ] **AMF-02**: All existing Alertmanager tools accept an optional `instance` parameter to target a specific Alertmanager
- [ ] **AMF-03**: Alertmanager fan-out queries across multiple instances with parallel execution and partial failure handling
- [ ] **AMF-04**: Alertmanager alert deduplication by fingerprint when fan-out returns the same alert from multiple HA cluster peers

## v2.0 Requirements (Completed)

### Alertmanager

- [x] **AM-01**: Agent can list Alertmanager silences with matchers, status, creator, and comment
- [x] **AM-02**: Agent can list Alertmanager alerts with suppressed/inhibited state, silence IDs
- [x] **AM-03**: Agent can get Alertmanager cluster status, version, uptime, and raw config YAML
- [x] **AM-04**: Agent can list alert groups showing how alerts are grouped for notification routing

### Cardinality

- [x] **CARD-01**: Agent can view TSDB statistics including total series count, top metrics by cardinality

### Operations

- [x] **OPS-01**: Agent can check Prometheus health and readiness for liveness probe verification
- [x] **OPS-02**: HTTP responses are capped at configurable byte limit
- [x] **OPS-03**: Metric name list responses are cached with configurable TTL

### Status

- [x] **STAT-01**: Agent can view Prometheus runtime info
- [x] **STAT-02**: Agent can view Prometheus build info

## v1.0 Requirements (Completed)

### Investigation Tools

- [x] **TOOL-01**: Agent can retrieve metric metadata (HELP text, TYPE, UNIT)
- [x] **TOOL-02**: Agent can list all values for a specific label
- [x] **TOOL-03**: Agent can inspect recording rules and alerting rules

### Reliability

- [x] **REL-01**: HTTP requests automatically retry once on transient 5xx errors
- [x] **REL-02**: HTTP timeout is configurable via PROMETHEUS_TIMEOUT

### Quality

- [x] **QUAL-01**: Shared test fixtures extracted to tests/conftest.py
- [x] **QUAL-02**: Tests cover prometheus_list_targets with state='dropped' and state='any'
- [x] **QUAL-03**: Tests cover PrometheusClient timeout behavior, empty responses, and session reuse

## Future Requirements

Deferred beyond v3.0.

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

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CFG-01 | TBD | Pending |
| CFG-02 | TBD | Pending |
| CFG-03 | TBD | Pending |
| CFG-04 | TBD | Pending |
| CFG-05 | TBD | Pending |
| CFG-06 | TBD | Pending |
| CFG-07 | TBD | Pending |
| INST-01 | TBD | Pending |
| INST-02 | TBD | Pending |
| INST-03 | TBD | Pending |
| INST-04 | TBD | Pending |
| FED-01 | TBD | Pending |
| FED-02 | TBD | Pending |
| FED-03 | TBD | Pending |
| FED-04 | TBD | Pending |
| FED-05 | TBD | Pending |
| FED-06 | TBD | Pending |
| AMF-01 | TBD | Pending |
| AMF-02 | TBD | Pending |
| AMF-03 | TBD | Pending |
| AMF-04 | TBD | Pending |

**Coverage:**
- v3.0 requirements: 21 total
- Mapped to phases: 0
- Unmapped: 21 (roadmap not yet created)

---
*Requirements defined: 2026-06-08*
*Last updated: 2026-06-08 after scoping*
