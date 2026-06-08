# Feature Landscape

**Domain:** Prometheus/Alertmanager MCP server — v2.0 milestone
**Researched:** 2026-06-08
**Scope:** NEW features only — Alertmanager integration, cardinality stats, federation, health checks, metric caching, response size limits

## Table Stakes

Features that users of a v2.0 Prometheus MCP server expect. Missing = milestone feels incomplete.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|--------------|------------|------------|-------|
| **Alertmanager silences list** (`alertmanager_list_silences`) | Incident responders need to know what's silenced — a silenced alert is invisible and "Is X silenced?" is the #1 question during handoffs | Medium | New `AlertmanagerClient` class | Alertmanager API v2 `GET /api/v2/silences` with optional `filter` param. Returns `gettableSilences` array with matchers, timestamps, status (active/pending/expired), createdBy, comment. Separate service URL from Prometheus — needs `ALERTMANAGER_URL` env var |
| **Alertmanager alerts list** (`alertmanager_list_alerts`) | Complements existing `prometheus_list_alerts` — Alertmanager shows suppressed/inhibited state, routing, silence IDs that Prometheus doesn't expose | Medium | New `AlertmanagerClient` class | Alertmanager API v2 `GET /api/v2/alerts` with `active`, `silenced`, `inhibited`, `unprocessed`, `filter`, `receiver` query params. Response includes `status.state` (unprocessed/active/suppressed), `status.silencedBy[]`, `status.inhibitedBy[]` — critical for understanding WHY an alert is or isn't firing |
| **TSDB cardinality statistics** (`prometheus_get_cardinality`) | Cardinality explosions are the #1 operational Prometheus problem. Agents investigating slow queries or OOM need this | Low | Existing `PrometheusClient` | Prometheus API `GET /api/v1/status/tsdb` with optional `limit` param. Returns `headStats` (numSeries, chunkCount, minTime, maxTime), `seriesCountByMetricName`, `labelValueCountByLabelName`, `memoryInBytesByLabelName`, `seriesCountByLabelValuePair`. Stable endpoint, straightforward GET |
| **Health check tool** (`prometheus_health_check`) | K8s liveness/readiness probes need this; agents need to verify "is Prometheus actually up?" before investigating blank query results | Low | Existing `PrometheusClient` | Prometheus `GET /-/healthy` (always 200) and `GET /-/ready` (200 when ready). Note: these are on the management API, NOT under `/api/v1/` — the client.get() method appends `/api/v1` prefix, so this needs a separate raw request path or a new method |
| **Response size limits** | Defense-in-depth against runaway queries returning 100MB+ JSON that crashes the MCP client or consumes all LLM context | Low | Existing `PrometheusClient` | Read response body in chunks, abort at configurable byte limit. `PROMETHEUS_MAX_RESPONSE_BYTES` env var with sensible default (e.g., 10MB). Apply at the HTTP layer in `client.py` before JSON parsing |
| **Metric name caching** | Large Prometheus instances (500K+ metrics) make `prometheus_list_metrics` slow (2-5s). Repeated calls during investigation waste time on identical data | Medium | Existing `_mcp.py` globals | Cache the `GET /api/v1/label/__name__/values` response with a configurable TTL. `PROMETHEUS_CACHE_TTL` env var (default 300s). Thread-safe cache with lock. Invalidation on TTL expiry only — Prometheus metric names change slowly |

## Differentiators

Features that set this MCP server apart from basic Prometheus tooling. Not expected at table stakes, but highly valued by power users.

| Feature | Value Proposition | Complexity | Depends On | Notes |
|---------|-------------------|------------|------------|-------|
| **Alertmanager status** (`alertmanager_get_status`) | Shows cluster health, version, config — useful for "is Alertmanager itself healthy?" questions during incidents | Low | New `AlertmanagerClient` class | Alertmanager API v2 `GET /api/v2/status`. Returns cluster status (ready/settling/disabled), version info, uptime, config YAML. Simple read-only GET |
| **Alertmanager alert groups** (`alertmanager_list_alert_groups`) | Shows how alerts are grouped for notification routing — answers "why did I get one notification instead of many?" or "what's grouped with this alert?" | Medium | New `AlertmanagerClient` class | Alertmanager API v2 `GET /api/v2/alerts/groups` with same filter params as alerts. Returns groups with labels, receiver, and nested alert arrays. Useful for understanding routing topology |
| **Prometheus runtime info** (`prometheus_get_runtime_info`) | Exposes `timeSeriesCount`, `goroutineCount`, `storageRetention`, `startTime` — helpful for "why is Prometheus slow?" investigations | Low | Existing `PrometheusClient` | Prometheus API `GET /api/v1/status/runtimeinfo`. JSON fields may change between Prometheus versions — return raw data and let the agent interpret |
| **Federated multi-instance query** | Query the same PromQL across multiple Prometheus instances and get unified results — essential for multi-cluster environments | High | Major architecture change | NOT a Prometheus federation endpoint call — this is MCP-level: configure N Prometheus URLs, create N clients, fan-out the same query to all, merge results with source labels. `PROMETHEUS_URLS` env var (comma-separated) or per-instance config. Each instance needs its own auth config |
| **Build info** (`prometheus_get_build_info`) | Shows Prometheus version, Go version, revision — answers "what version of Prometheus is running?" | Low | Existing `PrometheusClient` | Prometheus API `GET /api/v1/status/buildinfo`. Trivial GET, stable since v2.14 |

## Anti-Features

Features to explicitly NOT build in v2.0.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Alertmanager silence create/delete** | Violates read-only constraint. Creating/deleting silences is a write operation (`POST /api/v2/silences`, `DELETE /api/v2/silence/{id}`). Accidentally silencing alerts via an AI agent is a safety hazard | Keep read-only. List silences only. If an agent needs to create a silence, it should output the curl command for human execution |
| **Alertmanager alert posting** | `POST /api/v2/alerts` creates alerts — write operation, violates read-only design. Agents should never autonomously create alerts | Keep read-only. List and inspect alerts only |
| **Custom Alertmanager routing tree parser** | Parsing the YAML config to show routing trees is complex, fragile across AM versions, and better served by the `alertmanager_get_status` tool returning raw config | Return raw config YAML in `alertmanager_get_status`; let the AI agent parse it |
| **Prometheus config reload** | `POST /-/reload` is a write/mutation operation on the management API | Out of scope forever per read-only constraint |
| **Full federation scrape endpoint** | `GET /federate?match[]=...` returns exposition format (not JSON) — Prometheus-to-Prometheus, not useful for MCP agents. Parsing exposition format adds complexity for no MCP benefit | Use fan-out multi-instance PromQL queries instead. Each Prometheus instance already has the `/api/v1/query` endpoint |
| **Prometheus TSDB snapshot/compaction** | `POST /api/v2/admin/tsdb/snapshot` and similar admin endpoints are write operations | Out of scope per read-only constraint |
| **In-memory caching of query results** | Caching actual query results (not just metric names) is dangerous — Prometheus data is time-varying. A cached `rate()` from 60 seconds ago is stale and misleading | Cache ONLY metric name lists (slow-changing). Query results must always be fresh |
| **Automatic federation discovery** | Auto-discovering Prometheus instances via DNS, Consul, or K8s is massive scope creep. Federation config should be explicit | Static URL list via env var. Discovery is the deployment tool's job |
| **Write-back for response limits** | Truncating responses silently without telling the agent leads to wrong conclusions | Always include truncation metadata (count, total, truncated flag) in structured output — existing pattern already does this |

## Feature Dependencies

```
alertmanager_list_silences ──┐
alertmanager_list_alerts ────┤
alertmanager_list_alert_groups ──┤── All require AlertmanagerClient (new class)
alertmanager_get_status ─────┘    └── Requires ALERTMANAGER_URL env var
                                       └── Requires error handling for AM-specific errors

prometheus_get_cardinality ──── Uses existing PrometheusClient.get("/status/tsdb")
                                └── New TypedDict models in models.py

prometheus_health_check ─────── Needs new client method (not /api/v1 prefixed)
                                └── GET /-/healthy and GET /-/ready are management endpoints

prometheus_get_runtime_info ─── Uses existing PrometheusClient.get("/status/runtimeinfo")
prometheus_get_build_info ───── Uses existing PrometheusClient.get("/status/buildinfo")

response_size_limits ────────── Modifies PrometheusClient._request() in client.py
                                └── Must apply BEFORE json() parsing (stream + size check)

metric_name_cache ───────────── Modifies _mcp.py (new _metrics_cache global)
                                └── Modifies prometheus_list_metrics() in tools.py
                                └── Thread-safe TTL cache (threading.Lock + time.monotonic)

federated_multi_instance ────── Requires multi-client architecture change
                                ├── New env var parsing (PROMETHEUS_URLS)
                                ├── Client registry/pool instead of singleton
                                ├── Fan-out logic in tool layer
                                └── Result merging with source labels
```

## Feature Detail: Alertmanager Integration

### AlertmanagerClient Design

A new `AlertmanagerClient` class in a new `alertmanager_client.py` module, mirroring `PrometheusClient` patterns:
- Env vars: `ALERTMANAGER_URL` (required for AM tools, optional globally), `ALERTMANAGER_TOKEN`, `ALERTMANAGER_USERNAME`, `ALERTMANAGER_PASSWORD`
- Or: reuse Prometheus auth if `ALERTMANAGER_TOKEN` is not set (common in same-cluster deployments)
- Base path: `{ALERTMANAGER_URL}/api/v2` (NOT v1 — v1 was removed in AM 0.27.0)
- Same retry/timeout logic as PrometheusClient
- Lazy singleton in `_mcp.py` — separate from Prometheus client
- **Graceful absence**: If `ALERTMANAGER_URL` is not set, AM tools should return a clear error: "Alertmanager URL not configured — set ALERTMANAGER_URL env var"

### Silences Tool (`alertmanager_list_silences`)

- **Endpoint**: `GET /api/v2/silences`
- **Params**: optional `filter` (matcher expressions like `alertname="MyAlert"`)
- **Response shape**: Array of `gettableSilence` objects with `id`, `status.state` (expired/active/pending), `matchers[]`, `startsAt`, `endsAt`, `createdBy`, `comment`, `updatedAt`
- **Structured output**: `SilenceItem` TypedDict with `id`, `state`, `matchers` (list of `{name, value, isRegex, isEqual}`), `starts_at`, `ends_at`, `created_by`, `comment`
- **Markdown**: Show active silences first, with matcher details and creator/comment

### Alerts Tool (`alertmanager_list_alerts`)

- **Endpoint**: `GET /api/v2/alerts`
- **Params**: `active` (bool), `silenced` (bool), `inhibited` (bool), `unprocessed` (bool), `filter` (matcher array), `receiver` (regex)
- **Response shape**: Array of `gettableAlert` with `labels`, `annotations`, `status.state` (unprocessed/active/suppressed), `status.silencedBy[]`, `status.inhibitedBy[]`, `fingerprint`, `startsAt`, `endsAt`, `receivers[]`
- **Key difference from `prometheus_list_alerts`**: Shows suppression status — which silence IDs are muting each alert, which inhibition rules apply

## Feature Detail: Cardinality Statistics

### TSDB Status Tool (`prometheus_get_cardinality`)

- **Endpoint**: `GET /api/v1/status/tsdb`
- **Params**: optional `limit` (default 10, max 10000) — limits items in each category
- **Response sections**:
  - `headStats`: numSeries, chunkCount, minTime, maxTime
  - `seriesCountByMetricName`: top N metrics by series count (cardinality hotspots)
  - `labelValueCountByLabelName`: top N labels by distinct value count
  - `memoryInBytesByLabelName`: top N labels by memory usage
  - `seriesCountByLabelValuePair`: top N label=value pairs by series count
- **AI agent use case**: "Why is Prometheus using so much memory?" → check top metrics by series count. "Which label is causing cardinality explosion?" → check `labelValueCountByLabelName`

## Feature Detail: Health Check

### Health Check Tool (`prometheus_health_check`)

- **Endpoints**: `GET /-/healthy` (liveness) and `GET /-/ready` (readiness)
- **Important**: These are NOT under `/api/v1/` — they're management endpoints at the root path
- **Implementation**: Need a new `PrometheusClient.check_health()` method that hits `{self.url}/-/healthy` and `{self.url}/-/ready` (bypassing `api_url`)
- **Response**: Boolean `healthy` and `ready` flags, plus HTTP status codes
- **Use case**: Agent checks health before running queries — avoids confusing "connection refused" errors. Also usable as K8s probe when the MCP server is deployed as a sidecar

## Feature Detail: Metric Name Caching

### Cache Strategy

- **What to cache**: The response from `GET /api/v1/label/__name__/values` (metric name list)
- **Why only this**: Metric names change slowly (new deploys, new exporters). Query results change every second — never cache those
- **TTL**: Configurable via `PROMETHEUS_CACHE_TTL` env var, default 300 seconds (5 minutes)
- **Invalidation**: TTL-only. No event-based invalidation (Prometheus has no change notification API)
- **Thread safety**: Module-level `_metrics_cache` dict + `_cache_lock` (threading.Lock) + `_cache_timestamp` (float, `time.monotonic()`)
- **Cache bypass**: New `force_refresh` param on `prometheus_list_metrics` tool (default False)
- **Memory**: Metric name lists are typically 1-50K strings × ~30 bytes each = 30KB–1.5MB. Negligible
- **Where**: In `_mcp.py` alongside the client cache, or in a new `_cache.py` module

### Cache Implementation Pattern

```
If force_refresh or cache is None or (monotonic() - cache_timestamp) > ttl:
    with _cache_lock:
        # Double-checked: another thread may have refreshed while we waited
        if force_refresh or cache is None or (monotonic() - cache_timestamp) > ttl:
            cache = client.get("/label/__name__/values")
            cache_timestamp = monotonic()
return cache
```

## Feature Detail: Response Size Limits

### Implementation Strategy

- **Where**: In `PrometheusClient._request()` method, after getting the response but before `.json()`
- **How**: Check `Content-Length` header first (fast path). If absent, read body in chunks with a byte counter
- **Limit**: `PROMETHEUS_MAX_RESPONSE_BYTES` env var, default 10MB (10_485_760 bytes)
- **On exceed**: Raise a descriptive error: "Response too large (>10MB). Narrow the query: use tighter label matchers, shorter time range, or larger step. Current limit: PROMETHEUS_MAX_RESPONSE_BYTES=10485760"
- **Interaction with existing caps**: This is defense-in-depth below the existing `_METRICS_CAP` and `_RANGE_POINTS_CAP` which operate on parsed data. Response size limit operates on raw bytes before parsing — catches cases where Prometheus returns enormous JSON before the tool layer can cap items

## Feature Detail: Federation (Multi-Instance)

### Architecture Options

**Option A (recommended): Fan-out at tool level**
- Configure `PROMETHEUS_URLS=http://prom1:9090,http://prom2:9090,http://prom3:9090`
- Each URL gets its own `PrometheusClient` instance (own auth, own timeout)
- New tool variants: `prometheus_federated_query`, `prometheus_federated_query_range`
- Fan-out: call all instances concurrently (threading), merge results, add `__prometheus_instance__` label
- Original single-instance tools remain unchanged

**Option B: Transparent fan-out on existing tools**
- All existing tools automatically query all configured instances
- Risky: changes behavior of existing tools, breaks backward compatibility

**Recommendation**: Option A. Add new tools, don't modify existing ones. This matches the project's "add new tools, not modify existing" key decision.

### Complexity Factors
- Per-instance auth config (each Prometheus may have different tokens)
- Per-instance error handling (one instance down shouldn't fail the whole query)
- Result merging semantics (duplicate series from different instances)
- Config syntax for multiple URLs with per-URL auth
- Thread pool for concurrent fan-out

## MVP Recommendation

**Prioritize (implement first):**
1. **TSDB cardinality statistics** — Low complexity, high investigation value, uses existing client, single new tool
2. **Health check tool** — Low complexity, high operational value, small client change
3. **Response size limits** — Low complexity, defense-in-depth, modifies existing client only
4. **Metric name caching** — Medium complexity, quality-of-life improvement, contained change

**Implement next:**
5. **Alertmanager silences + alerts** — Medium complexity, requires new client class, new env vars, 2+ new tools
6. **Alertmanager status** — Low complexity, free once AlertmanagerClient exists

**Defer or phase separately:**
7. **Federated multi-instance** — High complexity, architecture change, new config model. Consider as a separate v2.1 milestone unless multi-cluster is a hard requirement

## Sources

- Prometheus HTTP API: https://prometheus.io/docs/prometheus/latest/querying/api/ (HIGH confidence — official docs)
- Prometheus TSDB status endpoint: `/api/v1/status/tsdb` section of above (HIGH confidence)
- Prometheus Management API: https://prometheus.io/docs/prometheus/latest/management_api/ (HIGH confidence — `/-/healthy`, `/-/ready`)
- Alertmanager API v2 OpenAPI spec: https://github.com/prometheus/alertmanager/blob/master/api/v2/openapi.yaml (HIGH confidence — canonical spec)
- Alertmanager concepts (silences, inhibitions, grouping): https://prometheus.io/docs/alerting/latest/alertmanager/ (HIGH confidence)
- Prometheus Federation: https://prometheus.io/docs/prometheus/latest/federation/ (HIGH confidence)
- Existing codebase architecture: `.planning/codebase/ARCHITECTURE.md` (HIGH confidence — verified against source)
