# Roadmap: prometheus-mcp v2.0

**Created:** 2026-06-08
**Milestone:** v2.0
**Phases:** 4 (continuing from v1.0 Phase 3)
**Granularity:** coarse

## Phase Overview

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 4 | Client Hardening | Add response size limits and metric name caching to the HTTP client layer | OPS-02, OPS-03 | 4 |
| 5 | Prometheus Status Tools | Add health check, cardinality, runtime info, and build info tools | OPS-01, CARD-01, STAT-01, STAT-02 | 5 |
| 6 | Alertmanager Integration | Add AlertmanagerClient and 4 Alertmanager tools | AM-01, AM-02, AM-03, AM-04 | 5 |
| 7 | v2.0 Test & Release Prep | Comprehensive test coverage for all new code, version bump | — | 4 |

## Phase 4: Client Hardening

**Goal:** Harden the HTTP client layer with response size limits and metric name caching, providing the foundation for all subsequent tool phases.

**Requirements:** OPS-02, OPS-03

**Success Criteria:**
1. HTTP responses exceeding PROMETHEUS_MAX_RESPONSE_BYTES (default 10MB) raise a ToolError with a clear message about the limit
2. PROMETHEUS_MAX_RESPONSE_BYTES is configurable via environment variable and documented in .env.example and server.json
3. prometheus_list_metrics uses a TTL cache for metric names; repeated calls within PROMETHEUS_CACHE_TTL (default 300s) return cached data without HTTP request
4. Cache is thread-safe and invalidates correctly after TTL expiry

**Dependencies:** None (builds on existing client.py)

**UI hint:** no

---

## Phase 5: Prometheus Status Tools

**Goal:** Add 4 new Prometheus tools for health checking, cardinality investigation, and runtime/build information — all using the existing PrometheusClient.

**Requirements:** OPS-01, CARD-01, STAT-01, STAT-02

**Success Criteria:**
1. `prometheus_health_check` tool returns health and readiness status from /-/healthy and /-/ready (note: management endpoints, not /api/v1)
2. `prometheus_get_cardinality` tool returns TSDB stats including series count, top metrics by cardinality, top labels by value count from /api/v1/status/tsdb
3. `prometheus_get_runtime_info` tool returns goroutine count, time series count, storage retention from /api/v1/status/runtimeinfo
4. `prometheus_get_build_info` tool returns Prometheus version, Go version, revision from /api/v1/status/buildinfo
5. All 4 tools have dual-channel output, read-only annotations, structured_output=True, and integration tests

**Dependencies:** Phase 4 (response size limits protect these new endpoints)

**UI hint:** no

---

## Phase 6: Alertmanager Integration

**Goal:** Add AlertmanagerClient (separate from PrometheusClient) and 4 Alertmanager tools, enabling AI agents to investigate alert suppression, silences, and routing.

**Requirements:** AM-01, AM-02, AM-03, AM-04

**Success Criteria:**
1. New `AlertmanagerClient` in `alertmanager_client.py` reads ALERTMANAGER_URL from env, supports Bearer/Basic auth (same pattern as PrometheusClient), uses Alertmanager API v2 base path
2. `alertmanager_list_silences` tool returns silences with matchers, status, creator, comment from GET /api/v2/silences
3. `alertmanager_list_alerts` tool returns alerts with suppressed/inhibited state, silence IDs from GET /api/v2/alerts
4. `alertmanager_get_status` tool returns cluster status, version, config from GET /api/v2/status
5. `alertmanager_list_alert_groups` tool returns alert groups with routing info from GET /api/v2/alerts/groups

**Dependencies:** Phase 4 (response size limits), Phase 5 (pattern established for new tool files)

**UI hint:** no

---

## Phase 7: v2.0 Test & Release Prep

**Goal:** Ensure comprehensive test coverage for all v2.0 code, update protocol tests for all new tools, and prepare for release.

**Requirements:** None (quality phase)

**Success Criteria:**
1. All new tools registered in test_protocol.py EXPECTED_TOOLS and pass schema validation
2. Integration tests with mocked HTTP cover happy path and error paths for all new tools
3. AlertmanagerClient has unit tests matching PrometheusClient test coverage
4. Version bumped to 0.2.0 in pyproject.toml, __init__.py, server.json, and CHANGELOG.md updated

**Dependencies:** Phase 4, Phase 5, Phase 6

**UI hint:** no

---

*Roadmap created: 2026-06-08*
*Last updated: 2026-06-08 after initial creation*
