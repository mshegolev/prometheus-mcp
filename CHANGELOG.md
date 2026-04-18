# Changelog

All notable changes to `prometheus-mcp` will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
versioning: [SemVer](https://semver.org/).

## [0.1.0] — 2026-04-18

### Added

- `prometheus_list_metrics` — list all metric names with optional substring filter (cap 500)
- `prometheus_query` — instant PromQL query with optional time parameter
- `prometheus_query_range` — range PromQL query with time-series output (cap 5000 points)
- `prometheus_list_alerts` — list active alerts grouped by state + severity
- `prometheus_list_targets` — list scrape targets summarised by job + health
- HTTP Basic auth and Bearer token auth support (Bearer takes precedence)
- SSL verification toggle via `PROMETHEUS_SSL_VERIFY`
- Thread-safe lazy client cache (double-checked locking)
- Structured output (`outputSchema`) for all 5 tools via FastMCP `structured_output=True`
- Markdown rendering with truncation hints for large result sets
- Actionable error messages for 401/403/404/400/422/429/5xx/ConnectionError/Timeout
