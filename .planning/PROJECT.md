# prometheus-mcp

## What This Is

An MCP server that gives AI agents (Claude, Cursor, CI pipelines) read-only access to Prometheus for autonomous error investigation in corporate networks. Used by SRE, DevOps, QA, testing, analytics, architecture teams, and automated CI/CD pipelines to query metrics, inspect alerts, explore targets, and investigate incidents — all through the Model Context Protocol over stdio.

## Core Value

AI agents can autonomously investigate production errors and infrastructure issues by querying Prometheus metrics, metadata, labels, alerts, targets, and rules — without human intervention or direct API knowledge.

## Requirements

### Validated

- ✓ List metric names with optional substring filter — existing (`prometheus_list_metrics`)
- ✓ Execute instant PromQL queries — existing (`prometheus_query`)
- ✓ Execute range PromQL queries with time-series data — existing (`prometheus_query_range`)
- ✓ List active and pending alerts — existing (`prometheus_list_alerts`)
- ✓ List scrape targets by health and job — existing (`prometheus_list_targets`)
- ✓ Dual-channel output (markdown + structured JSON) — existing
- ✓ Bearer token and HTTP Basic authentication — existing
- ✓ LLM-readable actionable error messages — existing
- ✓ Docker container support — existing

### Active

- [ ] Metric metadata introspection (HELP text, TYPE, UNIT)
- [ ] Label value discovery for query building
- [ ] Recording and alerting rule inspection
- [ ] Configurable HTTP timeout via environment variable
- [ ] HTTP retry logic for transient failures
- [ ] Shared test fixtures in conftest.py
- [ ] Comprehensive test coverage for untested paths

### Out of Scope

- Write operations to Prometheus — read-only by design
- Alertmanager integration — separate MCP server concern
- Custom PromQL query builder — agents should write PromQL directly
- UI/frontend — this is a headless MCP server
- Multi-Prometheus federation — single instance per server process

## Context

- Existing codebase: ~1100 lines of production Python, 5 MCP tools, well-structured flat module layout
- Stack: Python 3.10+, FastMCP (mcp>=1.2), requests, Pydantic 2, Hatchling build
- Architecture: Single-process stdio MCP server, synchronous tools in async runtime via worker threads
- Key gap: No metric metadata, label discovery, or rule inspection — agents must guess metric types and label values
- Quality: Good test coverage (~1350 lines of tests), ruff linting, CI on 3 Python versions
- Published on PyPI as `prometheus-mcp` v0.1.0

## Constraints

- **Read-only**: All tools must remain read-only (GET requests only) — no mutations to Prometheus
- **Backward compatibility**: Existing 5 tools must not change their API signatures or output schemas
- **Python 3.10+**: Must support Python 3.10, 3.11, 3.12 (CI matrix)
- **No new runtime deps**: Prefer stdlib/existing deps (requests, pydantic) over new packages
- **MCP protocol**: Must follow MCP conventions — stdio transport, structured output, tool annotations

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Add new tools (not modify existing) | Backward compatibility for current users | — Pending |
| Use existing PrometheusClient for new endpoints | Consistency, connection pooling reuse | — Pending |
| Follow existing dual-channel output pattern | All tools should behave the same way | — Pending |
| Keep synchronous tool functions | Matches existing threading model | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-06 after initialization*
