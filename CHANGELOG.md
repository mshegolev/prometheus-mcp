# Changelog

All notable changes to `prometheus-mcp` will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
versioning: [SemVer](https://semver.org/).

## [0.2.0] — 2026-06-08

### Added

- `prometheus_get_metric_metadata` — get metric HELP text, TYPE, and UNIT
- `prometheus_list_label_values` — list all values for a label with optional match filter
- `prometheus_list_rules` — list recording and alerting rules by group
- `prometheus_health_check` — check Prometheus liveness (/-/healthy) and readiness (/-/ready)
- `prometheus_get_cardinality` — TSDB stats: series count, top metrics by cardinality, top labels
- `prometheus_get_runtime_info` — goroutines, time series count, storage retention
- `prometheus_get_build_info` — Prometheus version, Go version, revision
- `alertmanager_list_silences` — list silences with matchers, status, creator
- `alertmanager_list_alerts` — list alerts with suppressed/inhibited state and silence IDs
- `alertmanager_get_status` — Alertmanager cluster status, version, config
- `alertmanager_list_alert_groups` — alert groups with routing topology
- Automatic retry (1 retry, 1s backoff) for transient 5xx/ConnectionError/Timeout failures
- Configurable HTTP timeout via `PROMETHEUS_TIMEOUT` (default 30s)
- Response size limits via `PROMETHEUS_MAX_RESPONSE_BYTES` (default 10MB)
- Metric name caching with TTL via `PROMETHEUS_CACHE_TTL` (default 300s)
- `AlertmanagerClient` for Alertmanager API v2 (separate URL, same auth pattern)
- `get_raw()` method on PrometheusClient for management endpoints outside /api/v1
- Shared test fixtures in `tests/conftest.py`
- TTL cache module (`cache.py`) with thread-safe monotonic-clock expiry

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
