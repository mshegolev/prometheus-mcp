# Phase 14 — Real Dependency Mapping — VERIFICATION

**Milestone:** v5.0 Real Metric-Driven Intelligence
**Requirements:** DEP-R01, DEP-R02
**Date:** 2026-07-22
**Branch:** `feat/v5.0-slice-260722`

> The v4.0 audit named *missing verification* as the root cause of hidden debt
> (simulated modules shipped as "done"). This note exists so Phase 14 is not
> marked complete on faith — each success criterion is tied to concrete
> evidence.

## What shipped

- `src/prometheus_mcp/dependency_map.py` — `ServiceDependencyMapper`, a **real**
  implementation that aggregates
  `sum by (<source>, <destination>) (rate(<metric>{<matchers>}[<window>]))`
  via `PrometheusClient.get("/query_range", ...)` and folds each returned
  matrix series into a directed dependency edge. Optional `error_matcher`
  triggers a second identically-shaped query for per-edge error rate.
- `src/prometheus_mcp/tools_dependency.py` — registers
  `prometheus_map_service_dependencies` (dual-channel: structured
  `ServiceDependencyMapResult` + markdown).
- `src/prometheus_mcp/models.py` — new lean, simulation-free result types
  (`DependencyMapNode`, `DependencyMapEdge`, `ServiceDependencyMapResult`).
- `src/prometheus_mcp/server.py` — imports `tools_dependency` so the tool is
  actually attached to the FastMCP instance (the exact wiring bug that hit v4).
- Tests: `tests/test_tools_dependency.py` (16 cases); registration guard
  updated in `tests/test_server_registration.py`.

## Success criteria → evidence

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Tool registered in `server.py` and callable via MCP | ✅ | `test_server_registration.py::test_all_expected_tools_registered` now lists `prometheus_map_service_dependencies`; `test_tool_returns_dual_channel_result` calls it end-to-end. |
| 2 | Real `query_range` for source/destination-labelled metrics; no mock data / hardcoded graph | ✅ | `test_map_dependencies_uses_query_range_with_aggregation` asserts the exact PromQL and endpoint; graph is built purely from mocked matrix responses. No `random`/simulation code in `dependency_map.py`. |
| 3 | Dependency graph (nodes = services, edges = traffic volume / error rate) in markdown + structured JSON | ✅ | `test_tool_returns_dual_channel_result` checks both `structuredContent` and `content[0].text`; `test_map_dependencies_computes_error_rate_with_second_query` verifies edge error rate. |
| 4 | Accepts `instance`, label matchers, `time_window` | ✅ | Tool signature exposes all three; `test_map_dependencies_applies_matchers` and `..._uses_query_range_with_aggregation` (window/step) cover them. |
| 5 | Unit tests vs mocked `PrometheusClient`; EXPERIMENTAL `dependency.py` superseded | ✅ | 16 tests all mock the client. The old `dependency.py` is left untouched but is **superseded**: the new tool does not import it, and it remains unregistered/EXPERIMENTAL (final removal deferred to Phase 18). |

## Test results

- `python3 -m pytest -q` → **403 passed** (baseline 387 + 16 new), ~3s.
- `ruff check` on all changed files → clean.

## Deliberate scope boundaries

- `server.json` version corrected `0.2.0` → `0.4.3` (matches current release;
  the `0.5.0` release bump belongs to Phase 18).
- The old simulated `dependency.py` was **not** deleted (it is still imported by
  the unregistered `tools_federation_v4.py`, a Phase 17 concern). Superseded,
  not removed — removal + EXPERIMENTAL-flag cleanup is Phase 18 work.

## Deferred to later v5.0 phases (NOT done here)

- **Phase 15 (RCA-R04):** real change-point detection via `*_build_info` /
  `process_start_time_seconds` — RCA change-point stub still returns empty.
- **Phase 16 (TRE-R01/R02):** real trend/MTTR from the `ALERTS` metric;
  register `prometheus_trend_analysis` — `trend_analysis.py` still simulated.
- **Phase 17 (FED-R01):** rewrite + register `federation_analyze_alerts` —
  `tools_federation_v4.py` still references non-existent APIs, unregistered.
- **Phase 18 (QUAL-R01):** VERIFICATION.md for phases 15-17, remove
  EXPERIMENTAL flags on now-real modules, bump to `0.5.0`, tag release.
