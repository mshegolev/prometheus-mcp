# Roadmap: prometheus-mcp v1.0

**Created:** 2026-06-06
**Milestone:** v1.0
**Phases:** 3
**Granularity:** coarse

## Phase Overview

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | Investigation Tools | Add 3 new MCP tools for metric metadata, label discovery, and rule inspection | TOOL-01, TOOL-02, TOOL-03 | 3 |
| 2 | Reliability Hardening | Add retry logic and configurable timeouts for enterprise use | REL-01, REL-02 | 3 |
| 3 | Test Quality | Extract shared fixtures and fill coverage gaps | QUAL-01, QUAL-02, QUAL-03 | 3 |

## Phase 1: Investigation Tools

**Goal:** Add 3 new MCP tools that enable AI agents to autonomously investigate errors by discovering metric metadata, label values, and alerting/recording rules.

**Requirements:** TOOL-01, TOOL-02, TOOL-03

**Success Criteria:**
1. `prometheus_get_metric_metadata` tool returns HELP, TYPE, and UNIT for queried metrics with dual-channel output
2. `prometheus_list_label_values` tool returns all values for a given label name with optional metric filter and dual-channel output
3. `prometheus_list_rules` tool returns both recording and alerting rules grouped by group name with dual-channel output
4. All 3 new tools registered in test_protocol.py EXPECTED_TOOLS and pass schema validation
5. Integration tests with mocked HTTP cover happy path and error paths for each new tool

**Dependencies:** None (builds on existing architecture)

**UI hint:** no

---

## Phase 2: Reliability Hardening

**Goal:** Make the HTTP client production-ready for corporate environments with retry logic for transient failures and configurable timeouts.

**Requirements:** REL-01, REL-02

**Success Criteria:**
1. Transient HTTP errors (5xx, ConnectionError, Timeout) trigger one automatic retry with 1-second backoff before failing
2. PROMETHEUS_TIMEOUT environment variable controls the HTTP request timeout (default remains 30s)
3. Retry behavior is tested with mocked HTTP responses (5xx → success, 5xx → 5xx exhausted)
4. PROMETHEUS_TIMEOUT is documented in .env.example, server.json, and errors.py config message

**Dependencies:** None (independent of Phase 1)

**UI hint:** no

---

## Phase 3: Test Quality

**Goal:** Eliminate test fixture duplication and fill identified coverage gaps for untested code paths.

**Requirements:** QUAL-01, QUAL-02, QUAL-03

**Success Criteria:**
1. tests/conftest.py contains the shared client-reset fixture, both test_tools_integration.py and test_mcp_client_cache.py use it
2. Tests exercise prometheus_list_targets with state='dropped' and state='any' and verify correct response structure
3. Tests cover PrometheusClient with custom timeout, empty HTTP response body, and verify session reuse across multiple get() calls
4. All existing tests still pass (no regressions from refactoring)

**Dependencies:** Phase 1, Phase 2 (new code from earlier phases needs test coverage too)

**UI hint:** no

---

*Roadmap created: 2026-06-06*
*Last updated: 2026-06-06 after initial creation*
