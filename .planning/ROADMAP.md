# Roadmap: prometheus-mcp v4.0 + v5.0

**Created:** 2026-06-18
**Last updated:** 2026-07-08 — v5.0 phases 14-18 added
**Phases:** 11 total (8-13 complete, 14-18 active)
**Granularity:** coarse

---

## v4.0 Phase Overview

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 8 | Correlation Engine Foundation | Core infrastructure for cross-instance alert analysis with pattern detection and grouping | COR-01, COR-02, COR-03 | 5 |
| 9 | Root Cause Analysis Tools | Implement anomaly detection, dependency traversal, and change point identification | RCA-01, RCA-02, RCA-03 | 5 |
| 10 | Dependency Mapping & Health | Build dynamic service dependency maps with cross-cluster awareness and health probing | DEP-01, DEP-02, DEP-03 | 5 |
| 11 | Trend Analysis & Benchmarking | Add historical pattern recognition, capacity forecasting, and MTTR benchmarking | TRE-01, TRE-02, TRE-03 | 5 |
| 12 | Integration & Enhancement | Integrate all v4.0 features with existing federation, add new tools, enhance output | — | 4 |
| 13 | v4.0 Test & Release Prep | Comprehensive testing, version bump, documentation updates | — | 4 |

## Phase 8: Correlation Engine Foundation

**Goal:** Build the core infrastructure for cross-instance alert analysis, enabling AI agents to identify related alerts across clusters and group them for holistic incident analysis.

**Requirements:** COR-01, COR-02, COR-03

**Success Criteria:**
1. New `correlation.py` module with cross-instance alert matching using temporal windows and label similarity scoring
2. Alert grouping algorithm that clusters related alerts by service identifiers across all instances
3. Cascading alert detection with directional dependency inference and correlation strength metrics
4. Integration with existing federation infrastructure to access alerts from all configured instances
5. Dual-channel output (markdown + structured JSON) following existing patterns with instance attribution

**Dependencies:** Phase 2 (registry.py), Phase 4 (federation.py)

**UI hint:** no

---
## Phase 9: Root Cause Analysis Tools

**Goal:** Implement tools for anomaly detection in metrics, dependency chain traversal, and change point detection to help AI agents identify underlying causes of alert cascades.

**Requirements:** RCA-01, RCA-02, RCA-03

**Success Criteria:**
1. Anomaly detection engine that monitors key metrics for statistical outliers with seasonality adjustment
2. Dependency traversal algorithm that traces service dependencies from symptoms to potential root causes
3. Change point detection that correlates recent deployments/config changes with alert onset timing
4. Ranking system for root cause candidates based on proximity, evidence strength, and impact analysis
5. Integration with existing tools to enrich alert context with root cause analysis insights

**Dependencies:** Phase 8 (correlation.py), Phase 4 (federation.py)

**UI hint:** no

**Plans:** 3 plans

Plans:
- [x] 09-01-PLAN.md — Implement root cause analysis engine with anomaly detection and dependency traversal
- [x] 09-02-PLAN.md — Implement change point detection and candidate ranking system
- [x] 09-03-PLAN.md — Create comprehensive tests for root cause analysis components

---

## Phase 10: Dependency Mapping & Health

**Goal:** Create dynamic service dependency maps with cross-cluster awareness and implement health probing to assess dependency stability.

**Requirements:** DEP-01, DEP-02, DEP-03

**Success Criteria:**
1. ✅ Dynamic dependency mapper that discovers service relationships through traffic correlation analysis
2. ✅ Cross-cluster dependency visualization showing interoperation between services in different regions
3. ✅ Synthetic health probing system that assesses dependency resilience under various conditions
4. ✅ Real-time dependency maps that differentiate between normal and failure-state interactions
5. ✅ Load shedding recommendations based on dependency fragility assessments

**Dependencies:** Phase 9 (root cause analysis), Phase 4 (federation.py)

**UI hint:** no

**Plans:** 3 plans

Plans:
- [x] 10-01-PLAN.md — Implement dynamic dependency mapper with traffic correlation analysis
- [x] 10-02-PLAN.md — Implement cross-cluster visualization and synthetic health probing
- [x] 10-03-PLAN.md — Implement load shedding recommendations and create comprehensive tests

---

## Phase 11: Trend Analysis & Benchmarking

**Goal:** Add historical pattern recognition, capacity forecasting, and MTTR benchmarking to provide AI agents with temporal context for incident investigation.

**Requirements:** TRE-01, TRE-02, TRE-03

**Success Criteria:**
1. ✅ Historical alert pattern recognizer that identifies recurring schedules and seasonal behaviors
2. ✅ Capacity forecasting engine that predicts resource exhaustion based on usage trends
3. ✅ MTTR benchmarking system that compares incident resolution times against historical data
4. ✅ Deviation detection that triggers higher-priority notifications for pattern breaks
5. ✅ Remediation suggestions based on historical resolution techniques and best practices

**Dependencies:** Phase 8 (correlation.py), Phase 10 (dependency mapping)

**UI hint:** no

**Plans:** 1 plan

Plans:
- [x] 11-01-PLAN.md — Implement trend analysis and benchmarking components with comprehensive tests

---

## Phase 12: Integration & Enhancement

**Goal:** Fully integrate all v4.0 features with existing federation capabilities, add new MCP tools, and enhance output formats for better AI agent consumption.

**Requirements:** None (integration phase)

**Success Criteria:**
1. ✅ New `federation_analyze_alerts` tool combining correlation, RCA, and dependency features
2. ✅ Enhanced existing tools with optional correlation context parameters
3. ✅ Unified output format that combines alerts, metrics, dependencies, and trends
4. ⭕ Performance optimization for large-scale correlation across many instances
5. ⭕ Comprehensive documentation with examples for all new features

**Dependencies:** Phases 8-11

**UI hint:** no

**Plans:** 1 plan

Plans:
- [x] 12-01-PLAN.md — Implement integrated federation analysis tool and enhance existing tools

---

## Phase 13: v4.0 Test & Release Prep

**Goal:** Comprehensive testing of all v4.0 features, version bump, and documentation updates to prepare for release.

**Requirements:** None (quality phase)

**Success Criteria:**
1. ✅ Integration test covering full correlation workflow: alert matching → grouping → RCA → dependency analysis
2. ⭕ Performance test with 10+ instances and 1000+ alerts to validate scalability
3. ✅ All new modules (correlation, rca, dependency, trend) have unit tests with >80% coverage
4. ✅ Version bumped to 0.4.0 in pyproject.toml, __init__.py; CHANGELOG.md updated with v4.0 features
5. ✅ Documentation updated with v4.0 features, examples, and migration guide from v3.0

**Dependencies:** Phase 12

**UI hint:** no

**Plans:** 1 plan

Plans:
- [x] 13-01-PLAN.md — Prepare v4.0 release with testing, version updates, and documentation

---

## v4.0 Phase Completion

All v4.0 phases are complete and shipped (released as v0.4.3 on PyPI).

- [x] Phase 8: Correlation Engine Foundation (completed 2026-06-18)
- [x] Phase 9: Root Cause Analysis Tools (completed 2026-06-18)
- [x] Phase 10: Dependency Mapping & Health (completed 2026-06-18)
- [x] Phase 11: Trend Analysis & Benchmarking (completed 2026-06-18)
- [x] Phase 12: Integration & Enhancement (completed 2026-06-18)
- [x] Phase 13: v4.0 Test & Release Prep (completed 2026-06-18)

> Note: Phases 10 and 11 shipped simulated logic (flagged EXPERIMENTAL in code);
> making them production-real is deferred to v5.0. See STATE.md.

---

## v5.0 Phase Overview

**Milestone:** v5.0 Real Metric-Driven Intelligence
**Goal:** Replace EXPERIMENTAL simulated modules with real Prometheus-native implementations, register all new tools on the server, and ship as v0.5.0.

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 14 | Real Dependency Mapping | Replace simulation with real traffic-metric dependency discovery; register tool | DEP-R01, DEP-R02 | 5 |
| 15 | Metric-Driven Change Points | Replace stub with real `*_build_info`/`process_start_time_seconds` delta detection | RCA-R04 | 4 |
| 16 | Real Trend Analysis & MTTR | Replace simulation with real `ALERTS` metric queries; register tool | TRE-R01, TRE-R02 | 5 |
| 17 | Rewrite federation_analyze_alerts | Rewrite against real engine/client APIs; register on server | FED-R01 | 4 |
| 18 | v5.0 Test, Verify & Release | VERIFICATION.md per phase, all tests green, version 0.5.0, PyPI release | QUAL-R01 | 5 |

## Phase 14: Real Dependency Mapping

**Goal:** Replace the EXPERIMENTAL simulated dependency module with a real implementation that queries live Prometheus traffic metrics carrying source/destination labels, and register `prometheus_map_service_dependencies` on the server.

**Requirements:** DEP-R01, DEP-R02

**Success Criteria:**
1. `prometheus_map_service_dependencies` tool is registered in `server.py` and callable via MCP without error
2. The tool issues a real `query_range` (or `query`) call against Prometheus for metrics carrying `source`/`destination` (or equivalent) labels — no mock data, no hardcoded graph
3. The response contains a dependency graph (nodes = services, edges = traffic volume / error rate) in both markdown and structured JSON following the existing dual-channel output pattern
4. The tool accepts `instance`, optional label matchers, and `time_window` parameters as specified in DEP-R02
5. Unit tests verify the dependency graph construction logic against a mocked PrometheusClient response; the existing EXPERIMENTAL `dependency.py` stub is either replaced or clearly superseded

**Dependencies:** Phase 13 (v4.0 complete), existing `PrometheusClient`, `InstanceRegistry`

**UI hint:** no

---

## Phase 15: Metric-Driven Change Points

**Goal:** Replace the change-point stub that previously returned empty results with a real implementation that detects service restarts and deployments by tracking `*_build_info` label-set changes and `process_start_time_seconds` jumps in Prometheus, and integrate the result into the existing `correlate_alerts_across_instances(enable_rca=True)` pipeline.

**Requirements:** RCA-R04

**Success Criteria:**
1. Change-point detection queries real Prometheus metrics (`*_build_info` and/or `process_start_time_seconds`) via `query_range` — no fabricated events, no hardcoded timestamps
2. A build-info label-set change (e.g., `version` label flip) is correctly identified as a deployment change point with the actual timestamp from the metric
3. A `process_start_time_seconds` jump above a configurable threshold is correctly identified as a restart change point
4. Change points detected are surfaced in the `correlate_alerts_across_instances(enable_rca=True)` output under the `change_points` key in structured JSON

**Dependencies:** Phase 14, existing `RCAEngine`, `PrometheusClient`

**UI hint:** no

---

## Phase 16: Real Trend Analysis & MTTR

**Goal:** Replace the simulated trend analysis with a real implementation that queries the `ALERTS` metric via `query_range` to compute historical alert patterns and MTTR from actual alert-onset to alert-resolved transitions, and register `prometheus_trend_analysis` on the server.

**Requirements:** TRE-R01, TRE-R02

**Success Criteria:**
1. Trend analysis engine issues a real `query_range` call for the `ALERTS` metric (or equivalent time-series) — no clock-based simulation, no synthetic data generation
2. MTTR is computed from actual alert-onset to alert-resolved transitions detected in the time-series data, not estimated from constants
3. The recurrence schedule (e.g., "fires every weekday at 09:00") is derived from observed firing timestamps in the `ALERTS` metric history
4. `prometheus_trend_analysis` tool is registered in `server.py`, accepts `instance`, alert name filter, and lookback window parameters, and returns a trend report in markdown + structured JSON
5. Unit tests mock a `query_range` response containing `ALERTS` series transitions and verify that MTTR, recurrence, and avg duration fields are computed correctly

**Dependencies:** Phase 15, existing `PrometheusClient`, `InstanceRegistry`

**UI hint:** no

---

## Phase 17: Rewrite federation_analyze_alerts

**Goal:** Rewrite `federation_analyze_alerts` to use the real `InstanceRegistry`, `CorrelationEngine`, `RCAEngine`, and `PrometheusClient` APIs (replacing the EXPERIMENTAL `tools_federation_v4.py` stub that references non-existent APIs), and register the tool on `server.py` so it is reachable via MCP.

**Requirements:** FED-R01

**Success Criteria:**
1. `federation_analyze_alerts` is registered in `server.py` and executes end-to-end without `AttributeError` or `NotImplementedError` — the EXPERIMENTAL `tools_federation_v4.py` is no longer the active implementation
2. The tool pipeline covers: fetch alerts from all instances via `InstanceRegistry` → correlate via `CorrelationEngine` → optional RCA via `RCAEngine` → dependency context via Phase 14 mapper → trend summary via Phase 16 engine → unified markdown + JSON output
3. The tool returns structured JSON with keys `correlated_groups`, `change_points` (if `enable_rca=True`), `dependency_context`, and `trend_summary`
4. An integration test drives the full pipeline with mocked clients and verifies the output schema matches the structured JSON contract

**Dependencies:** Phases 14, 15, 16; `CorrelationEngine`, `RCAEngine`, `InstanceRegistry`

**UI hint:** no

---

## Phase 18: v5.0 Test, Verify & Release

**Goal:** Produce a VERIFICATION.md for each v5.0 phase, ensure all tests pass with zero ruff errors, bump the version to 0.5.0, update CHANGELOG.md, and release to PyPI via CI.

**Requirements:** QUAL-R01

**Success Criteria:**
1. A `VERIFICATION.md` file exists for each of Phases 14-17, documenting what was implemented, how it was tested, and what observable evidence confirms the phase success criteria are met
2. `pytest -q` exits 0 with all tests green across Python 3.10, 3.11, and 3.12 (no skips hiding failures)
3. `ruff check .` exits 0 with zero errors on the full codebase
4. Version is bumped to `0.5.0` in `pyproject.toml` and `src/prometheus_mcp/__init__.py`; `CHANGELOG.md` has a `## [0.5.0]` section listing all v5.0 changes
5. The `0.5.0` package is published to PyPI (or a CI release workflow is triggered and completes successfully); the EXPERIMENTAL flags are removed from the modules that are now production-real

**Dependencies:** Phases 14-17

**UI hint:** no

---

## v5.0 Phase Completion

- [ ] Phase 14: Real Dependency Mapping
- [ ] Phase 15: Metric-Driven Change Points
- [ ] Phase 16: Real Trend Analysis & MTTR
- [ ] Phase 17: Rewrite federation_analyze_alerts
- [ ] Phase 18: v5.0 Test, Verify & Release

---

*Roadmap created: 2026-06-18*
*Last updated: 2026-07-08 — v5.0 phases 14-18 added (milestone: Real Metric-Driven Intelligence)*
