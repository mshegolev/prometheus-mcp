# Roadmap: prometheus-mcp v3.0

**Created:** 2026-06-16
**Milestone:** v3.0
**Phases:** 7
**Granularity:** coarse

## Phase Overview

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | Config Schema & Loading | JSON config file parsing, validation, backward-compatible env-var fallback | CFG-01, CFG-02, CFG-04, CFG-06, CFG-07 | 5 |
| 2 | Instance Registry & Client Management | Thread-safe registry managing N client pairs with per-instance auth and caches | CFG-03, CFG-05, INST-01, INST-03 | 5 |
| 3 | Core Wiring | Replace singleton clients in _mcp.py with registry pattern, backward-compat gate | — | 3 |
| 4 | Federation Fan-Out & Merge | Concurrent fan-out queries with ThreadPoolExecutor, result merging, partial failure handling | FED-02, FED-03, FED-04, FED-06 | 5 |
| 5 | Instance Discovery & Tool Modifications | federation_list_instances tool + instance parameter on all 16 existing tools | INST-02, INST-04, FED-01, FED-05 | 5 |
| 6 | Alertmanager Federation | Alertmanager multi-instance with fan-out, deduplication by fingerprint | AMF-01, AMF-02, AMF-03, AMF-04 | 4 |
| 7 | v3.0 Test & Release Prep | End-to-end integration tests, version bump, CHANGELOG, release docs | — | 4 |

## Phase 1: Config Schema & Loading

**Goal:** Implement JSON config file parsing with Pydantic validation, defaults inheritance, schema versioning (version: 1), and backward-compatible single-instance mode when no config file is present.

**Requirements:** CFG-01, CFG-02, CFG-04, CFG-06, CFG-07

**Success Criteria:**
1. New `config.py` module loads JSON config file specified by PROMETHEUS_MCP_CONFIG env var with Pydantic validation
2. Config schema has `version: 1` field; missing/unknown versions produce actionable error messages referencing config file path
3. `defaults` section in config provides shared settings (timeout, ssl_verify, max_response_bytes, cache_ttl) inherited by instances
4. When PROMETHEUS_MCP_CONFIG is unset, server operates in single-instance mode using existing env vars — zero behavioral change from v2.0
5. Config validation errors are actionable, referencing file path and instance name (not raw Pydantic errors)

**Dependencies:** None (foundation phase)

**UI hint:** no

---

## Phase 2: Instance Registry & Client Management

**Goal:** Build thread-safe InstanceRegistry that creates and manages N PrometheusClient + AlertmanagerClient pairs with per-instance authentication, per-instance TTL caches, and proper session lifecycle.

**Requirements:** CFG-03, CFG-05, INST-01, INST-03

**Success Criteria:**
1. InstanceRegistry creates per-instance PrometheusClient with independent auth (Bearer/Basic) from config
2. Each instance has its own requests.Session (never shared) and per-instance TTLCache
3. Per-instance config overrides defaults for timeout, max_response_bytes, and cache_ttl
4. Registry provides get_prometheus_client(name), get_alertmanager_client(name), list_instances(), all_prometheus_clients(), close_all()
5. Legacy mode: when no config file, registry creates single "default" entry from env vars — identical to v2.0 behavior

**Dependencies:** Phase 1 (config.py)

**UI hint:** no

---

## Phase 3: Core Wiring

**Goal:** Replace singleton client pattern in _mcp.py with registry-based pattern. This is the backward-compatibility gate — ALL existing tests must pass after this change.

**Requirements:** None (internal refactoring)

**Success Criteria:**
1. _mcp.py uses InstanceRegistry instead of _client/_am_client globals; get_client(instance?) and get_alertmanager_client(instance?) route through registry
2. app_lifespan loads config at startup (eager), creates registry, closes all sessions on shutdown
3. ALL existing tests pass unchanged when PROMETHEUS_MCP_CONFIG is not set (backward-compat gate)

**Dependencies:** Phase 2 (registry.py)

**UI hint:** no

---

## Phase 4: Federation Fan-Out & Merge

**Goal:** Implement concurrent fan-out query execution across multiple Prometheus instances using ThreadPoolExecutor, with result merging strategies per query type, __prometheus_instance__ label injection, partial failure handling, and global response size caps.

**Requirements:** FED-02, FED-03, FED-04, FED-06

**Success Criteria:**
1. New `federation.py` module with fan_out_prometheus() using ThreadPoolExecutor for concurrent queries
2. Merge functions for instant queries, range queries, set values (metrics/labels), and per-instance results (TSDB, health)
3. __prometheus_instance__ label injected into every metric sample during merging (with collision check)
4. Partial failure: return available results + error annotations for failed instances; only raise ToolError if ALL instances fail
5. Global response size caps apply post-merge (not per-instance) — 500 metrics, 5000 range points across all instances

**Dependencies:** Phase 2 (registry.py for client lists)

**UI hint:** no

---

## Phase 5: Instance Discovery & Tool Modifications

**Goal:** Add federation_list_instances discovery tool and optional `instance` parameter to all 16 existing tools for targeted and fan-out queries.

**Requirements:** INST-02, INST-04, FED-01, FED-05

**Success Criteria:**
1. New `tools_federation.py` with federation_list_instances tool returning instance names, URLs, health status, and federation mode flag
2. Instance listing performs parallel health probes (/-/healthy) to show reachability
3. All 8 Prometheus tools in tools.py accept optional `instance` parameter (None=default, name=specific, "all"=fan-out)
4. All 4 status tools in tools_status.py accept optional `instance` parameter
5. Fan-out supports subset targeting via `instances` parameter (list of instance names)

**Dependencies:** Phase 3 (_mcp.py wiring), Phase 4 (federation.py for fan-out)

**UI hint:** no

---

## Phase 6: Alertmanager Federation

**Goal:** Add Alertmanager multi-instance support with fan-out queries, alert deduplication by fingerprint, and __alertmanager_instance__ label injection.

**Requirements:** AMF-01, AMF-02, AMF-03, AMF-04

**Success Criteria:**
1. Config file supports named Alertmanager instances with per-instance auth (same pattern as Prometheus instances)
2. All 4 Alertmanager tools accept optional `instance` parameter for targeted and fan-out queries
3. Alertmanager fan-out queries execute in parallel with partial failure handling
4. Alert deduplication by fingerprint when fan-out returns same alert from multiple HA cluster peers

**Dependencies:** Phase 4 (federation.py), Phase 5 (tool modification pattern)

**UI hint:** no

---

## Phase 7: v3.0 Test & Release Prep

**Goal:** End-to-end integration tests covering full federation workflow, version bump, CHANGELOG update, and release documentation.

**Requirements:** None (quality phase)

**Success Criteria:**
1. Integration test: config file with 2+ instances, fan-out query, partial failure, verify merged results with instance labels
2. Protocol test updated: federation_list_instances in EXPECTED_TOOLS, schema validation passes
3. All new modules (config, registry, federation, tools_federation) have unit tests with >80% coverage
4. Version bumped to 0.3.0 in pyproject.toml, __init__.py; CHANGELOG.md updated with v3.0 features; .env.example documents PROMETHEUS_MCP_CONFIG

**Dependencies:** Phase 1-6

**UI hint:** no

---

*Roadmap created: 2026-06-16*
*Last updated: 2026-06-16 after initial creation*
