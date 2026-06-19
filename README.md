# prometheus-mcp

<!-- mcp-name: io.github.mshegolev/prometheus-mcp -->

[![PyPI version](https://img.shields.io/pypi/v/prometheus-mcp.svg)](https://pypi.org/project/prometheus-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/prometheus-mcp.svg)](https://pypi.org/project/prometheus-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/mshegolev/prometheus-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/mshegolev/prometheus-mcp/actions/workflows/test.yml)

**MCP server for [Prometheus](https://prometheus.io/) metrics and observability.**
Give Claude (or any MCP-capable agent) read access to your Prometheus instance — query metrics with PromQL, inspect active alerts, and explore scrape targets — without leaving the conversation.

## Why another Prometheus MCP?

The existing Prometheus integrations require custom scripts or direct API knowledge. This server:

- Speaks the standard [Model Context Protocol](https://modelcontextprotocol.io/) over **stdio** — works with Claude Desktop, Claude Code, Cursor, and any MCP client.
- Is **read-only**: all 5 tools carry `readOnlyHint: true` — zero risk of modifying Prometheus data.
- Returns **dual-channel output**: structured JSON (`structuredContent`) for programmatic use + Markdown (`content`) for human-readable display.
- Has **actionable error messages** that name the exact env var to fix and suggest a next step.
- Supports **Bearer token**, **HTTP Basic auth**, or **no auth** (common for internal deployments).

## Tools

| Tool | Endpoint | Description |
|------|----------|-------------|
| `prometheus_list_metrics` | `GET /api/v1/label/__name__/values` | List all metric names with optional substring filter (cap 500) |
| `prometheus_query` | `GET /api/v1/query` | Execute an instant PromQL query |
| `prometheus_query_range` | `GET /api/v1/query_range` | Execute a PromQL range query returning time-series |
| `prometheus_list_alerts` | `GET /api/v1/alerts` | List active and pending alerts |
| `prometheus_list_targets` | `GET /api/v1/targets` | List scrape targets by health and job |

## v4.0 Advanced Alert Correlation Features

Version 4.0 introduces powerful new capabilities for AI agents to autonomously investigate production errors:

### Cross-Instance Alert Correlation
- Automatically identify related alerts across multiple Prometheus instances
- Group alerts by service identifiers to understand incident scope
- Detect cascading alert patterns with directional dependency inference

### Root Cause Analysis
- Anomaly detection in metrics with automatic seasonality adjustment
- Dependency chain traversal from symptoms to potential root causes
- Change point detection correlating alerts with recent deployments or config changes
- Ranked root cause candidates based on evidence strength and impact analysis

### Dependency Mapping & Health
- Dynamic service dependency maps built from traffic correlation analysis
- Cross-cluster dependency visualization showing service interoperation
- Synthetic health probing to assess dependency resilience
- Load shedding recommendations based on dependency fragility

### Trend Analysis & Benchmarking
- Historical pattern recognition for recurring alert schedules
- Capacity forecasting to predict resource exhaustion
- MTTR benchmarking comparing resolution times against historical data
- Deviation detection triggering higher-priority notifications for pattern breaks

### Integrated Analysis Tool
- New `federation_analyze_alerts` tool combining all v4.0 features
- Unified output format optimized for AI agent consumption
- Comprehensive incident context in a single tool call

## Installation

```bash
pip install prometheus-mcp
```

Or run directly without installing:

```bash
uvx prometheus-mcp
```

## Configuration

All configuration is via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PROMETHEUS_URL` | **Yes** | — | Prometheus server URL, e.g. `https://prometheus.example.com` (no trailing slash) |
| `PROMETHEUS_TOKEN` | No | — | Bearer token (takes precedence over Basic auth) |
| `PROMETHEUS_USERNAME` | No | — | HTTP Basic auth username |
| `PROMETHEUS_PASSWORD` | No | — | HTTP Basic auth password |
| `PROMETHEUS_SSL_VERIFY` | No | `true` | Set `false` for self-signed certificates |

Copy `.env.example` to `.env` and fill in your values.

## Claude Desktop / Claude Code setup

Add to your MCP config (`claude_desktop_config.json` or `.claude/mcp.json`):

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "prometheus-mcp",
      "env": {
        "PROMETHEUS_URL": "https://prometheus.example.com",
        "PROMETHEUS_TOKEN": "your-token-here"
      }
    }
  }
}
```

Or with `uvx` (no install required):

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "uvx",
      "args": ["prometheus-mcp"],
      "env": {
        "PROMETHEUS_URL": "https://prometheus.example.com"
      }
    }
  }
}
```

## Docker

```bash
docker run --rm -e PROMETHEUS_URL=https://prometheus.example.com prometheus-mcp
```

## Example queries

Once configured, ask Claude:

- "What metrics does Prometheus have about HTTP requests?"
- "What is the current request rate for the payment service?"
- "Show me CPU usage over the last hour with 5-minute resolution"
- "Are there any firing alerts? What's their severity?"
- "Which scrape targets are currently down and why?"
- "How many node-exporter instances are up?"

## Tool usage guide

### `prometheus_list_metrics`

Returns all metric names Prometheus knows about. Use `pattern` to filter by substring (case-insensitive). **Start here** when you don't know which metrics are available. Output is capped at 500 metrics with a truncation hint.

### `prometheus_query`

Execute an instant PromQL expression and get current values. Returns result type (vector/scalar/matrix/string), sample count, and per-sample labels and values.

Parameters:
- `query` (required) — PromQL expression, e.g. `up`, `rate(http_requests_total[5m])`
- `time` (optional) — RFC3339 or Unix timestamp; defaults to now

### `prometheus_query_range`

Execute a PromQL expression over a time window. Returns one series per matching time series with timestamped values. Total data points across all series are capped at 5000.

Parameters:
- `query` (required) — PromQL expression
- `start` / `end` (required) — RFC3339 or Unix timestamps
- `step` (required) — resolution like `15s`, `1m`, `5m`

Prometheus rejects steps that would produce > 11,000 points per series (HTTP 422). Increase step or narrow the range if this happens.

**Note:** The Prometheus range API does not support filtering by branch or commit — filters are expressed purely in PromQL label matchers.

### `prometheus_list_alerts`

Returns all active/pending alerts with labels (including `alertname`, `severity`), state, activation time, and current value. Includes a state summary (firing vs pending counts).

### `prometheus_list_targets`

Returns scrape targets with job name, instance address, health (`up`/`down`/`unknown`), last scrape duration in milliseconds, and any error message. Includes a per-job summary. Filter by `state`: `active` (default), `dropped`, or `any`.

## Performance characteristics

- All tools use a single persistent `requests.Session` with connection pooling.
- The session has `trust_env = False` to bypass environment proxies (Prometheus is typically an internal service).
- Requests time out after 30 seconds.
- `prometheus_query_range` caps output at 5000 total points across all series — use a larger step for long windows.
- `prometheus_list_metrics` returns up to 500 metrics after filtering.

## Development

```bash
git clone https://github.com/mshegolev/prometheus-mcp
cd prometheus-mcp
pip install -e '.[dev]'
pytest tests/ -v
ruff check src tests
ruff format src tests
```

## API Specification

This project includes an OpenAPI 3.0 specification in the `specs/` directory that documents all MCP tools exposed by the server.

To validate the specification:
```bash
python3 specs/validate_spec.py
```

## License

MIT — see [LICENSE](LICENSE).
