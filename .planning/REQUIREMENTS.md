# Requirements: prometheus-mcp

**Defined:** 2026-06-08
**Core Value:** AI agents can autonomously investigate production errors by querying Prometheus metrics, metadata, labels, alerts, targets, rules, cardinality, and Alertmanager state

## v2.0 Requirements

Requirements for milestone v2.0: Advanced Investigation & Operations.

### Alertmanager

- [ ] **AM-01**: Agent can list Alertmanager silences with matchers, status (active/pending/expired), creator, and comment
- [ ] **AM-02**: Agent can list Alertmanager alerts with suppressed/inhibited state, silence IDs, and inhibition IDs
- [ ] **AM-03**: Agent can get Alertmanager cluster status, version, uptime, and raw config YAML
- [ ] **AM-04**: Agent can list alert groups showing how alerts are grouped for notification routing

### Cardinality

- [ ] **CARD-01**: Agent can view TSDB statistics including total series count, top metrics by cardinality, top labels by value count, and memory usage by label

### Operations

- [ ] **OPS-01**: Agent can check Prometheus health (/-/healthy) and readiness (/-/ready) for liveness probe verification
- [ ] **OPS-02**: HTTP responses are capped at a configurable byte limit (PROMETHEUS_MAX_RESPONSE_BYTES, default 10MB) to prevent OOM from runaway queries
- [ ] **OPS-03**: Metric name list responses are cached with configurable TTL (PROMETHEUS_CACHE_TTL, default 300s) for performance on large instances

### Status

- [ ] **STAT-01**: Agent can view Prometheus runtime info (goroutine count, time series count, storage retention, start time)
- [ ] **STAT-02**: Agent can view Prometheus build info (version, Go version, revision, build date)

## v1.0 Requirements (Completed)

### Investigation Tools

- [x] **TOOL-01**: Agent can retrieve metric metadata (HELP text, TYPE, UNIT) for any metric name
- [x] **TOOL-02**: Agent can list all values for a specific label to build targeted queries
- [x] **TOOL-03**: Agent can inspect recording rules and alerting rules

### Reliability

- [x] **REL-01**: HTTP requests automatically retry once on transient 5xx errors and connection resets
- [x] **REL-02**: HTTP timeout is configurable via PROMETHEUS_TIMEOUT environment variable

### Quality

- [x] **QUAL-01**: Shared test fixtures extracted to tests/conftest.py
- [x] **QUAL-02**: Tests cover prometheus_list_targets with state='dropped' and state='any'
- [x] **QUAL-03**: Tests cover PrometheusClient timeout behavior, empty responses, and session reuse

## Future Requirements

Deferred beyond v2.0.

- **FED-01**: Federated multi-instance PromQL queries across multiple Prometheus instances (deferred to v3.0)
- **ADV-03**: Automatic federation discovery via DNS/Consul/K8s

## Out of Scope

| Feature | Reason |
|---------|--------|
| Write operations to Prometheus/Alertmanager | Read-only by design — safety critical |
| Alertmanager silence create/delete | Write operation; AI agents must not silently suppress alerts |
| Custom PromQL query builder | Agents should write PromQL directly |
| UI/frontend/dashboard | Headless MCP server |
| Query result caching | Time-varying data must always be fresh; only metric names are safe to cache |
| Alertmanager routing tree parser | Return raw config; let AI agent interpret |
| Federation auto-discovery | Static URL list; discovery is the deployment tool's job |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OPS-02 | Phase 4 | Pending |
| OPS-03 | Phase 4 | Pending |
| OPS-01 | Phase 5 | Pending |
| CARD-01 | Phase 5 | Pending |
| STAT-01 | Phase 5 | Pending |
| STAT-02 | Phase 5 | Pending |
| AM-01 | Phase 6 | Pending |
| AM-02 | Phase 6 | Pending |
| AM-03 | Phase 6 | Pending |
| AM-04 | Phase 6 | Pending |

**Coverage:**
- v2.0 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-08*
*Last updated: 2026-06-08 after scoping*
