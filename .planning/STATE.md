---
gsd_state_version: 1.0
milestone: v5.0
milestone_name: Real Metric-Driven Intelligence
status: planning
last_updated: "2026-07-08T00:00:00.000Z"
last_activity: 2026-07-08
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

**Project:** prometheus-mcp
**Milestone:** v5.0 Real Metric-Driven Intelligence
**Updated:** 2026-07-08

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-08)

**Core value:** AI agents can autonomously investigate production errors by querying Prometheus metrics, metadata, labels, alerts, targets, rules, cardinality, and Alertmanager state — across multiple instances

**Current focus:** v5.0 roadmap defined; ready to begin Phase 14

## Context from v4.0

**Post-milestone reconciliation (2026-07-08):** The v4.0 code was marked
complete on 2026-06-18 but had gaps found and fixed afterwards, shipped as
patch releases:

- v0.4.1 — the v4 correlation/federation tools were never registered on the
  server; wired them in + hardened registry access.

- v0.4.2 — fixed a registry lazy-init regression (79 failing tests) and the
  repo-wide lint gate; CI green.

- v0.4.3 — RCA change-point detection no longer fabricates events; the
  unregistered, simulation-heavy modules (`tools_federation_v4`, `dependency`,
  `trend_analysis`) are flagged EXPERIMENTAL.

**Known EXPERIMENTAL debt (carried into v5.0):**
- `dependency.py` — simulated dependency mapping, not backed by real Prometheus metrics
- `trend_analysis.py` — simulated trend/MTTR, not backed by real `ALERTS` queries
- `tools_federation_v4.py` — references non-existent APIs; never registered on server
- `RCAEngine` change-point detection — stub returns empty results for real data

## Current Position

Phase: 14 (not started)
Plan: —
Status: Planning complete; ready to execute
Last activity: 2026-07-08 — Roadmap written for v5.0 (phases 14-18)

## Progress

### v4.0 Phases (complete)

| # | Phase | Status |
|---|-------|--------|
| 8 | Correlation Engine Foundation | ✅ Complete |
| 9 | Root Cause Analysis Tools | ✅ Complete |
| 10 | Dependency Mapping & Health | ✅ Complete (EXPERIMENTAL) |
| 11 | Trend Analysis & Benchmarking | ✅ Complete (EXPERIMENTAL) |
| 12 | Integration & Enhancement | ✅ Complete |
| 13 | v4.0 Test & Release Prep | ✅ Complete |

### v5.0 Phases (active milestone)

| # | Phase | Status |
|---|-------|--------|
| 14 | Real Dependency Mapping | ○ Not started |
| 15 | Metric-Driven Change Points | ○ Not started |
| 16 | Real Trend Analysis & MTTR | ○ Not started |
| 17 | Rewrite federation_analyze_alerts | ○ Not started |
| 18 | v5.0 Test, Verify & Release | ○ Not started |

## v5.0 Requirements Coverage

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEP-R01 | 14 | ○ Pending |
| DEP-R02 | 14 | ○ Pending |
| RCA-R04 | 15 | ○ Pending |
| TRE-R01 | 16 | ○ Pending |
| TRE-R02 | 16 | ○ Pending |
| FED-R01 | 17 | ○ Pending |
| QUAL-R01 | 18 | ○ Pending |

**Coverage:** 7/7 requirements mapped ✓

## Accumulated Context

### Key Decisions (v5.0)

| Decision | Rationale |
|----------|-----------|
| Replace EXPERIMENTAL modules entirely | Simulated logic has no value in production; clean replacement is safer than monkey-patching |
| Use existing `PrometheusClient.query_range` for all real data | Consistent with existing retry/timeout/auth logic; no new HTTP layer |
| Register new tools in `server.py` (not a separate v5 file) | Avoids the v4 anti-pattern where tools in separate files were never wired in |
| VERIFICATION.md per phase before marking complete | Lesson from v4.0: phase "complete" markers without verifiable evidence led to hidden debt |

### Anti-Patterns to Avoid (from v4.0 lessons)

- Marking phases complete before tools are registered on `server.py`
- Simulating data and calling it "implementation"
- Writing modules that reference APIs that don't exist
- Skipping VERIFICATION.md — visible evidence is mandatory for each phase

## Recent Activity

- 2026-07-08: v5.0 roadmap written — 5 phases (14-18), 7 requirements mapped
- 2026-07-08: v5.0 milestone started; PROJECT.md and REQUIREMENTS.md updated
- 2026-07-08: Artifacts reconciled with reality — v0.4.3 patch noted, EXPERIMENTAL flags confirmed

## Session

**Last session:** 2026-07-08
**Stopped at:** Roadmap creation complete
**Resume file:** None
**Next action:** `/gsd-plan-phase 14`
