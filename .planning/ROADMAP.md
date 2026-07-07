# Roadmap: prometheus-mcp v4.0

**Created:** 2026-06-18
**Milestone:** v4.0 Advanced Alert Correlation
**Phases:** 6
**Granularity:** coarse

## Phase Overview

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

## Phase Completion

All v4.0 phases are complete and shipped (released as v0.4.3 on PyPI).

- [x] Phase 8: Correlation Engine Foundation (completed 2026-06-18)
- [x] Phase 9: Root Cause Analysis Tools (completed 2026-06-18)
- [x] Phase 10: Dependency Mapping & Health (completed 2026-06-18)
- [x] Phase 11: Trend Analysis & Benchmarking (completed 2026-06-18)
- [x] Phase 12: Integration & Enhancement (completed 2026-06-18)
- [x] Phase 13: v4.0 Test & Release Prep (completed 2026-06-18)

> Note: Phases 10 and 11 shipped simulated logic (flagged EXPERIMENTAL in code);
> making them production-real is deferred to a future milestone. See STATE.md.

---

*Roadmap created: 2026-06-18*
*Last updated: 2026-07-08 — phase-completion markers added; artifacts reconciled with released reality*