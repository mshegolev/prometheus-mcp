# Phase 1: Investigation Tools - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous mode)

<domain>
## Phase Boundary

Add 3 new MCP tools that enable AI agents to autonomously investigate errors by discovering metric metadata, label values, and alerting/recording rules. These wrap Prometheus HTTP API v1 endpoints not yet covered by the server.

### Prometheus API Endpoints to Wrap

1. **`GET /api/v1/metadata`** → `prometheus_get_metric_metadata`
   - Returns metric metadata (HELP, TYPE, UNIT) for all or filtered metrics
   - Query params: `metric` (optional filter), `limit` (optional)
   - Response: `{"data": {"metric_name": [{"type": "counter", "help": "...", "unit": ""}]}}`

2. **`GET /api/v1/label/{label_name}/values`** → `prometheus_list_label_values`
   - Returns all values for a given label name
   - Already used internally by `prometheus_list_metrics` (for `__name__`), but not exposed as a general tool
   - Query params: `match[]` (optional series selector filter)
   - Response: `{"data": ["value1", "value2", ...]}`

3. **`GET /api/v1/rules`** → `prometheus_list_rules`
   - Returns recording and alerting rules grouped by group
   - Query params: `type` (optional: "alert" or "record")
   - Response: `{"data": {"groups": [{"name": "...", "rules": [...]}]}}`

</domain>

<decisions>
## Implementation Decisions

### OpenCode's Discretion
All implementation choices follow existing codebase patterns:

1. **Module placement:** New tool functions go in `src/prometheus_mcp/tools.py` following existing `@mcp.tool` decorator pattern
2. **Output schemas:** New TypedDicts in `src/prometheus_mcp/models.py` following existing naming convention (PascalCase with descriptive suffixes)
3. **Dual-channel output:** Every tool returns both markdown and structured JSON via `output.ok()`
4. **Error handling:** Same `try/except Exception` → `output.fail()` pattern
5. **Test placement:** Integration tests in `tests/test_tools_integration.py`, protocol tests updated in `tests/test_protocol.py`
6. **No new client methods needed:** Use existing `client.get(endpoint, params)` pattern

</decisions>

<code_context>
## Existing Code Insights

- **Where to add tools:** `src/prometheus_mcp/tools.py` (after line 693, the last tool)
- **Where to add models:** `src/prometheus_mcp/models.py` (after existing TypedDicts)
- **Client API:** `get_client().get("/endpoint", params={...})` returns parsed JSON dict
- **Output pattern:** `output.ok(typed_dict_result, markdown_string)` for success, `output.fail(exc, "action description")` for errors
- **Existing label values call:** `client.get("/label/__name__/values")` used in `prometheus_list_metrics` — similar pattern for general label values
- **Tool annotations:** All tools use `readOnlyHint: True`, `destructiveHint: False`, `idempotentHint: True`, `openWorldHint: True`
- **Caps:** `_METRICS_CAP = 500`, `_MD_ITEM_LIMIT = 20` for truncation

</code_context>

<specifics>
## Specific Ideas

### prometheus_get_metric_metadata
- Parameter: `metric` (optional, filter to specific metric name)
- Returns: dict of metric name → list of metadata entries (type, help, unit)
- Cap metadata entries at 500 metrics (like `_METRICS_CAP`)
- Markdown: table format with metric name, type, help text

### prometheus_list_label_values
- Parameters: `label` (required, the label name), `match` (optional, series selector like `up` or `{job="node"}`)
- Returns: sorted list of label values with count
- Cap at 500 values
- Markdown: bullet list of values

### prometheus_list_rules
- Parameter: `type` (optional: "alert", "record", or None for both)
- Returns: rule groups with rules, including alert state for alerting rules
- Markdown: grouped by rule group name, showing rule name/expr/type

</specifics>

<deferred>
## Deferred Ideas

- Metric series count/cardinality (v2 — ADV-02)
- Rule evaluation history (not available via Prometheus API)
- Label name discovery (`/api/v1/labels` endpoint — could add later)

</deferred>
