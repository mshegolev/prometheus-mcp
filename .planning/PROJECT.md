# prometheus-mcp

## What This Is

An MCP server that gives AI agents (Claude, Cursor, CI pipelines) read-only access to Prometheus and Alertmanager for autonomous error investigation in corporate networks. Used by SRE, DevOps, QA, testing, analytics, architecture teams, and automated CI/CD pipelines to query metrics, inspect alerts, explore targets, investigate incidents, and monitor cardinality — all through the Model Context Protocol over stdio.

## Core Value

AI agents can autonomously investigate production errors and infrastructure issues by querying Prometheus metrics, metadata, labels, alerts, targets, rules, cardinality, and Alertmanager state — without human intervention or direct API knowledge.

## Current Milestone: v2.0 Advanced Investigation & Operations

**Goal:** Extend prometheus-mcp with advanced investigation tools (cardinality, Alertmanager, federation) and operational hardening (health checks, caching, response limits).

**Target features:**
- Alertmanager silences and inhibitions
- Metric series count and cardinality statistics
- Federated queries across multiple Prometheus instances
- Health check tool for container orchestrator liveness probes
- Metric name caching with TTL for large Prometheus instances
- HTTP response size limits for defense-in-depth

## Requirements

### Validated

- ✓ List metric names with optional substring filter — `prometheus_list_metrics`
- ✓ Execute instant PromQL queries — `prometheus_query`
- ✓ Execute range PromQL queries with time-series data — `prometheus_query_range`
- ✓ List active and pending alerts — `prometheus_list_alerts`
- ✓ List scrape targets by health and job — `prometheus_list_targets`
- ✓ Dual-channel output (markdown + structured JSON)
- ✓ Bearer token and HTTP Basic authentication
- ✓ LLM-readable actionable error messages
- ✓ Docker container support
- ✓ Metric metadata introspection (HELP, TYPE, UNIT) — `prometheus_get_metric_metadata` (v1.0)
- ✓ Label value discovery for query building — `prometheus_list_label_values` (v1.0)
- ✓ Recording and alerting rule inspection — `prometheus_list_rules` (v1.0)
- ✓ Configurable HTTP timeout via PROMETHEUS_TIMEOUT (v1.0)
- ✓ HTTP retry logic for transient failures (v1.0)
- ✓ Shared test fixtures in conftest.py (v1.0)
- ✓ Comprehensive test coverage for untested paths (v1.0)

### Active

- [ ] Alertmanager silences and inhibitions query
- [ ] Metric series count and cardinality statistics
- [ ] Federated queries across multiple Prometheus instances
- [ ] Health check tool for container orchestrator liveness probes
- [ ] Metric name caching with TTL for large Prometheus instances
- [ ] HTTP response size limits for defense-in-depth

### Out of Scope

- Write operations to Prometheus — read-only by design
- Custom PromQL query builder — agents should write PromQL directly
- UI/frontend — this is a headless MCP server

## Context

- Existing codebase: ~1900 lines of production Python, 8 MCP tools, well-structured flat module layout
- Stack: Python 3.10+, FastMCP (mcp>=1.2), requests, Pydantic 2, Hatchling build
- Architecture: Single-process stdio MCP server, synchronous tools in async runtime via worker threads
- Client: PrometheusClient with retry logic and configurable timeout
- Quality: 180 tests passing, ruff linting, CI on 3 Python versions
- Published on PyPI as `prometheus-mcp` v0.1.0

## Constraints

- **Read-only**: All tools must remain read-only (GET requests only) — no mutations
- **Backward compatibility**: Existing 8 tools must not change their API signatures or output schemas
- **Python 3.10+**: Must support Python 3.10, 3.11, 3.12 (CI matrix)
- **Minimal new deps**: Prefer stdlib/existing deps; new deps only where essential (e.g., Alertmanager may need separate client config)
- **MCP protocol**: Must follow MCP conventions — stdio transport, structured output, tool annotations

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Add new tools (not modify existing) | Backward compatibility | Applied (v1.0) |
| Use existing PrometheusClient for new endpoints | Consistency, connection pooling reuse | Applied (v1.0) |
| Follow existing dual-channel output pattern | All tools should behave the same way | Applied (v1.0) |
| Keep synchronous tool functions | Matches existing threading model | Applied (v1.0) |
| Alertmanager as separate configurable URL | Different service, may not be deployed | Pending (v2.0) |
| Federation via multi-URL config | Each Prometheus is a separate client | Pending (v2.0) |

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
*Last updated: 2026-06-08 after milestone v2.0 start*
