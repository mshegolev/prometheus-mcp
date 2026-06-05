# Requirements: prometheus-mcp

**Defined:** 2026-06-06
**Core Value:** AI agents can autonomously investigate production errors by querying Prometheus metrics, metadata, labels, alerts, targets, and rules

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Investigation Tools

- [ ] **TOOL-01**: Agent can retrieve metric metadata (HELP text, TYPE, UNIT) for any metric name to understand what it measures
- [ ] **TOOL-02**: Agent can list all values for a specific label (e.g., all jobs, all instances) to build targeted queries
- [ ] **TOOL-03**: Agent can inspect recording rules and alerting rules to understand the alerting configuration

### Reliability

- [ ] **REL-01**: HTTP requests automatically retry once on transient 5xx errors and connection resets with backoff
- [ ] **REL-02**: HTTP timeout is configurable via PROMETHEUS_TIMEOUT environment variable (default 30s)

### Quality

- [ ] **QUAL-01**: Shared test fixtures extracted to tests/conftest.py eliminating duplication
- [ ] **QUAL-02**: Tests cover prometheus_list_targets with state='dropped' and state='any' paths
- [ ] **QUAL-03**: Tests cover PrometheusClient timeout behavior, empty responses, and session reuse

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Investigation

- **ADV-01**: Agent can query Alertmanager silences and inhibitions
- **ADV-02**: Agent can discover metric series count and cardinality statistics
- **ADV-03**: Agent can perform federated queries across multiple Prometheus instances

### Operational

- **OPS-01**: Health check tool for container orchestrator liveness probes
- **OPS-02**: Metric name caching with TTL for large Prometheus instances
- **OPS-03**: HTTP response size limits for defense-in-depth

## Out of Scope

| Feature | Reason |
|---------|--------|
| Write operations to Prometheus | Read-only by design — zero risk of data modification |
| Alertmanager integration | Separate service, separate MCP server |
| Custom PromQL query builder | Agents should write PromQL directly |
| UI/frontend/dashboard | Headless MCP server — UI is the AI agent |
| Multi-Prometheus federation | Single instance per process; federation is v2+ |
| Migration from requests to httpx | Works fine with threading model, not needed for current scale |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TOOL-01 | Phase 1 | Pending |
| TOOL-02 | Phase 1 | Pending |
| TOOL-03 | Phase 1 | Pending |
| REL-01 | Phase 2 | Pending |
| REL-02 | Phase 2 | Pending |
| QUAL-01 | Phase 3 | Pending |
| QUAL-02 | Phase 3 | Pending |
| QUAL-03 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 8 total
- Mapped to phases: 8
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-06*
*Last updated: 2026-06-06 after initial definition*
