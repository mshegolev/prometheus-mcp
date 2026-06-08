# Technology Stack — v2.0 Additions

**Project:** prometheus-mcp
**Researched:** 2026-06-08
**Scope:** NEW dependencies and patterns needed for v2.0 milestone only

## Verdict: Zero New Runtime Dependencies

Every v2.0 feature can be implemented with the existing dependency set (`requests`, `pydantic`, `mcp`, `urllib3`). No new PyPI packages are needed. The Alertmanager HTTP API v2, Prometheus TSDB status endpoint, federation routing, health checks, metric caching, and response size limits are all achievable with stdlib + existing deps.

---

## Feature-by-Feature Stack Analysis

### 1. Alertmanager Integration

**API target:** Alertmanager HTTP API v2 (`/api/v2/alerts`, `/api/v2/silences`, `/api/v2/alerts/groups`, `/api/v2/status`)
**Spec source:** [OpenAPI v2 spec](https://github.com/prometheus/alertmanager/blob/master/api/v2/openapi.yaml) (Swagger 2.0)

| Need | Solution | New Dep? | Why |
|------|----------|----------|-----|
| HTTP client for Alertmanager | New `AlertmanagerClient` class reusing `requests.Session` pattern from `PrometheusClient` | No | Same HTTP+JSON pattern as Prometheus API; `requests>=2.31` already handles it |
| Separate URL configuration | `ALERTMANAGER_URL` env var (matches existing `PROMETHEUS_URL` pattern) | No | Alertmanager is a separate service at a different address |
| Auth for Alertmanager | Reuse same Bearer/Basic pattern with `ALERTMANAGER_TOKEN`, `ALERTMANAGER_USERNAME`, `ALERTMANAGER_PASSWORD` | No | Same auth model; corporate deployments often use different creds per service |
| Response parsing | Pydantic `TypedDict` models in `models.py` | No | `pydantic>=2.0` already used; follow existing `TypedDict` pattern |
| Silence matchers parsing | Stdlib — Alertmanager returns structured JSON, no special parsing needed | No | Response is plain JSON with `matchers`, `startsAt`, `endsAt`, `status.state` |

**Key Alertmanager v2 endpoints (read-only):**
- `GET /api/v2/alerts` — active alerts with silenced/inhibited status, fingerprints, receivers
- `GET /api/v2/silences` — active/pending/expired silences with matchers
- `GET /api/v2/alerts/groups` — alerts grouped by routing tree labels
- `GET /api/v2/status` — cluster health, version, config

**Integration point:** Create `AlertmanagerClient` in `client.py` (or a new `alertmanager_client.py`) following the same `_request`/`get` pattern as `PrometheusClient`. Separate lazy-init cache in `_mcp.py` with `get_alertmanager_client()`. New tools register on the same `mcp` FastMCP instance.

**What NOT to do:** Do NOT use a generated Swagger client library (e.g., `bravado`, `swagger-codegen` output). The Alertmanager API surface we need is 4 read-only GET endpoints — a generated client adds complexity, transitive dependencies, and maintenance burden for zero benefit.

### 2. TSDB Status / Cardinality Statistics

**API target:** Prometheus HTTP API v1 `GET /api/v1/status/tsdb`
**Spec source:** [Prometheus HTTP API docs](https://prometheus.io/docs/prometheus/latest/querying/api/#tsdb-stats) — stable since Prometheus 2.14+

| Need | Solution | New Dep? | Why |
|------|----------|----------|-----|
| HTTP request to TSDB status | Existing `PrometheusClient.get("/status/tsdb")` | No | Same API path pattern; returns standard JSON envelope |
| Parsing head stats, series-count-by-metric, label-value-counts, memory-by-label, series-count-by-label-pair | New `TypedDict` models | No | All data is flat JSON dicts/arrays of `{name, value}` pairs |
| Limit parameter | Pass `?limit=N` query param | No | Standard Prometheus query parameter |

**Response structure (from official docs):**
```json
{
  "headStats": {"numSeries": 508, "chunkCount": 937, "minTime": ..., "maxTime": ...},
  "seriesCountByMetricName": [{"name": "...", "value": 20}, ...],
  "labelValueCountByLabelName": [{"name": "...", "value": 211}, ...],
  "memoryInBytesByLabelName": [{"name": "...", "value": 8266}, ...],
  "seriesCountByLabelValuePair": [{"name": "job=prometheus", "value": 425}, ...]
}
```

**Integration point:** Add one new tool function in `tools.py` (or a new `tools_advanced.py`). Uses existing `get_client()` — no new client needed.

### 3. Multi-Prometheus Federation

**Architecture:** Multiple `PrometheusClient` instances, one per configured Prometheus URL.
**No external API to call** — federation here means the MCP server fans out requests to N Prometheus instances and merges results.

| Need | Solution | New Dep? | Why |
|------|----------|----------|-----|
| Multi-URL config | `PROMETHEUS_URLS` env var (comma-separated) alongside existing `PROMETHEUS_URL` | No | Stdlib `str.split(",")` is sufficient |
| Named instances | `name=url` format like `prod=https://prom1:9090,staging=https://prom2:9090` | No | Simple string parsing |
| Multiple client instances | Dict of `PrometheusClient` keyed by instance name | No | Same class, different constructor args |
| Concurrent fan-out | `concurrent.futures.ThreadPoolExecutor` from stdlib | No | `ThreadPoolExecutor` is Python 3.10+ stdlib; matches the existing synchronous threading model |
| Result merging | Custom merge logic in tool functions | No | Merge dicts/lists with instance-name labels |

**Integration point:** Extend `_mcp.py` with a `get_clients() -> dict[str, PrometheusClient]` alongside existing `get_client()`. Federation tools call all clients via `ThreadPoolExecutor.map()`, add an `instance_name` label to each result, and merge. Existing single-instance tools remain unchanged for backward compatibility.

**What NOT to do:** Do NOT add `asyncio`/`aiohttp` or `httpx[http2]` for concurrent requests. The codebase is deliberately synchronous with FastMCP handling the async-to-sync bridge. `ThreadPoolExecutor` preserves this model and avoids a dependency/architecture change.

### 4. Health Check Tool

**API targets:**
- Prometheus: `GET /-/healthy` (returns 200 + `Prometheus Server is Healthy.\n`) and `GET /-/ready` (returns 200 when ready)
- Alertmanager: `GET /-/healthy` and `GET /-/ready` (same convention)

| Need | Solution | New Dep? | Why |
|------|----------|----------|-----|
| HTTP health/ready check | Direct `requests.Session.get()` to `/-/healthy` and `/-/ready` (note: these are outside `/api/v1/`) | No | Simple GET returning 200 or non-200; no JSON parsing needed |
| Buildinfo for richer health | `PrometheusClient.get("/status/buildinfo")` and `GET /api/v2/status` for Alertmanager | No | Standard API endpoints |
| Server startup time | `PrometheusClient.get("/status/runtimeinfo")` returns `startTime`, `timeSeriesCount`, `goroutineCount` | No | Enriches health output for agent investigation |

**Integration point:** New `prometheus_health_check` tool. Must call health endpoints outside the `/api/v1` prefix — extend `PrometheusClient` with a `raw_get(path)` method that hits `{self.url}{path}` instead of `{self.api_url}{endpoint}`. Alternatively, add a private `_health_check()` method.

### 5. Metric Name Caching with TTL

**Purpose:** Cache the metric names list (`/api/v1/label/__name__/values`) so repeated calls from agents exploring a large Prometheus don't hammer the server.

| Need | Solution | New Dep? | Why |
|------|----------|----------|-----|
| In-memory cache with TTL | `functools.lru_cache` + manual TTL tracking, OR a simple dict + timestamp | No | stdlib; ~20 lines of code |
| Thread safety | `threading.Lock` (already used in `_mcp.py` for client cache) | No | Existing pattern |
| TTL configuration | `PROMETHEUS_CACHE_TTL` env var (seconds, default 300) | No | Follows existing env-var config pattern |
| Cache invalidation | Time-based expiry only (no event-driven invalidation possible with read-only API) | No | Prometheus metric names change slowly |

**Recommended implementation:** A `CachedStore` class or `@cached_with_ttl` decorator wrapping `PrometheusClient.get()` for the specific `/label/__name__/values` endpoint. NOT a general HTTP cache — only cache metric name listings, which are expensive on large instances (10k+ metrics) and change infrequently.

**What NOT to do:** Do NOT add `cachetools`, `diskcache`, or `dogpile.cache`. A TTL cache for one endpoint is trivially implemented in ~25 lines with stdlib. External cache libraries add dependency risk and are overkill for this use case.

### 6. HTTP Response Size Limits

**Purpose:** Defense-in-depth — prevent the MCP server from OOM-ing if Prometheus returns a multi-GB response (e.g., a poorly written range query requesting millions of points).

| Need | Solution | New Dep? | Why |
|------|----------|----------|-----|
| Response size limit | Stream response with `requests` `iter_content(chunk_size)` and abort when limit exceeded | No | `requests>=2.31` supports `stream=True` + `iter_content` natively |
| Configurable limit | `PROMETHEUS_MAX_RESPONSE_BYTES` env var (default 50MB) | No | Env-var config pattern |
| Content-Length pre-check | Read `Content-Length` header before streaming (if present) | No | Standard HTTP header |
| Graceful error | Raise a custom `ResponseTooLarge` error mapped to actionable ToolError | No | Extend existing `errors.py` pattern |

**Integration point:** Modify `PrometheusClient._request()` to optionally stream and enforce a byte limit. The change is backward-compatible — existing tools get protection automatically.

```python
# Sketch (not actual implementation):
def _request(self, method, endpoint, *, params=None, max_bytes=None):
    response = self.session.request(..., stream=bool(max_bytes))
    if max_bytes:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            response.close()
            raise ResponseTooLarge(...)
        # Read in chunks, abort if cumulative > max_bytes
    ...
```

---

## Recommended Stack (Complete v2.0)

### Runtime Dependencies — NO CHANGES

| Package | Version | Already In | Used For (v2.0) |
|---------|---------|-----------|-----------------|
| `mcp` | `>=1.2` | Yes | FastMCP server, tool registration, structured output |
| `requests` | `>=2.31` | Yes | HTTP client for Prometheus AND Alertmanager, streaming for size limits |
| `urllib3` | `>=2.0` | Yes | SSL warning suppression (existing) |
| `pydantic` | `>=2.0` | Yes | TypedDict schema generation for new tool outputs |
| `typing-extensions` | `>=4.5` | Yes (py<3.12) | TypedDict backport |

### Dev Dependencies — NO CHANGES

| Package | Version | Already In | Used For (v2.0) |
|---------|---------|-----------|-----------------|
| `pytest` | `>=7` | Yes | Testing new tools |
| `ruff` | `>=0.5` | Yes | Linting new code |
| `responses` | `>=0.25` | Yes | Mocking Alertmanager HTTP calls in tests |
| `pytest-cov` | `>=4` | Yes | Coverage for new tools |

### Stdlib Additions (no install needed)

| Module | Python | Used For |
|--------|--------|----------|
| `concurrent.futures` | 3.10+ | ThreadPoolExecutor for federation fan-out |
| `functools` or custom | 3.10+ | TTL cache for metric names |
| `threading` | 3.10+ | Lock for cache (pattern already in use) |
| `time` | 3.10+ | TTL expiry tracking (already imported) |
| `json` | 3.10+ | Potential Alertmanager response handling (already available) |

---

## Alternatives Considered

| Capability | Considered | Recommended | Why Not |
|------------|-----------|-------------|---------|
| Alertmanager client | `prometheus-alertmanager-api-client` PyPI package | Build in-house with `requests` | Package is unmaintained (last update 2022), wraps only 3 endpoints, adds transitive deps. Our surface is 4 GET calls. |
| Alertmanager client | Generated Swagger client (`bravado`) | Build in-house | Heavy dep chain (jsonschema, swagger-spec-validator, etc.), runtime code generation, complex for 4 GET endpoints |
| Async HTTP | `httpx` or `aiohttp` | Stay with `requests` + ThreadPoolExecutor | Would require architectural change; FastMCP already handles async-sync bridge; `requests` is proven in this codebase |
| Caching library | `cachetools>=5.3` | Stdlib TTL cache | One cache key (metric names). `cachetools` TTLCache is elegant but adds a dep for ~25 lines of stdlib code |
| Response streaming | `httpx` streaming | `requests` streaming | `requests` already supports `stream=True` + `iter_content`; no reason to switch HTTP libraries |
| Federation concurrency | `asyncio.gather` with `aiohttp` | `ThreadPoolExecutor` | Would break the synchronous tool model; ThreadPoolExecutor integrates cleanly with existing sync `get()` calls |

---

## New Environment Variables

| Variable | Default | Feature | Format |
|----------|---------|---------|--------|
| `ALERTMANAGER_URL` | (unset = disabled) | Alertmanager integration | `https://alertmanager.example.com` |
| `ALERTMANAGER_TOKEN` | (unset) | Alertmanager Bearer auth | String |
| `ALERTMANAGER_USERNAME` | (unset) | Alertmanager Basic auth | String |
| `ALERTMANAGER_PASSWORD` | (unset) | Alertmanager Basic auth | String |
| `ALERTMANAGER_SSL_VERIFY` | `true` | Alertmanager TLS verification | `true`/`false` |
| `PROMETHEUS_URLS` | (unset = single instance) | Federation | `name=url,name=url` or `url,url` |
| `PROMETHEUS_CACHE_TTL` | `300` | Metric name cache TTL | Seconds (integer) |
| `PROMETHEUS_MAX_RESPONSE_BYTES` | `52428800` (50MB) | Response size limit | Bytes (integer) |

---

## New Prometheus/Alertmanager API Endpoints Used

| Endpoint | Service | Feature | Existing in Client? |
|----------|---------|---------|-------------------|
| `GET /api/v1/status/tsdb` | Prometheus | Cardinality stats | No — add via existing `client.get()` |
| `GET /api/v1/status/buildinfo` | Prometheus | Health check enrichment | No — add via existing `client.get()` |
| `GET /api/v1/status/runtimeinfo` | Prometheus | Health check enrichment | No — add via existing `client.get()` |
| `GET /-/healthy` | Prometheus | Health check | No — needs raw URL (outside `/api/v1`) |
| `GET /-/ready` | Prometheus | Health check | No — needs raw URL (outside `/api/v1`) |
| `GET /api/v2/alerts` | Alertmanager | List alerts with silence/inhibition status | No — new client |
| `GET /api/v2/silences` | Alertmanager | List silences | No — new client |
| `GET /api/v2/alerts/groups` | Alertmanager | Alert groups by routing | No — new client |
| `GET /api/v2/status` | Alertmanager | Alertmanager health/status | No — new client |
| `GET /-/healthy` | Alertmanager | Health check | No — new client raw URL |
| `GET /-/ready` | Alertmanager | Health check | No — new client raw URL |

---

## Integration Architecture

```
Existing (unchanged)                    New (v2.0)
─────────────────────                   ──────────────────
                                        
PROMETHEUS_URL ──→ PrometheusClient     ALERTMANAGER_URL ──→ AlertmanagerClient
      │              │                          │                │
      │         get_client()                    │          get_alertmanager_client()
      │              │                          │                │
      ├── tools.py (8 existing tools)           ├── tools_alertmanager.py
      │     unchanged                           │     alertmanager_list_alerts
      │                                         │     alertmanager_list_silences
      ├── tools_advanced.py (new)               │     alertmanager_list_groups
      │     prometheus_tsdb_status              │     alertmanager_status
      │     prometheus_health_check             │
      │                                         │
      │   PROMETHEUS_URLS ──→ dict[str, Client] │
      ├── tools_federation.py (new)             │
      │     prometheus_federated_query          │
      │                                         │
      └── cache.py (new)                        └── (shares mcp instance)
            TTL cache for metric names              registered on same FastMCP
```

All new tool modules import and register on the same `mcp` FastMCP instance from `_mcp.py`. The `server.py` entry point imports them (same pattern as existing `tools.py` import).

---

## What NOT to Add

| Anti-Dependency | Why Avoid |
|-----------------|-----------|
| `aiohttp` / `httpx` | Architectural mismatch — codebase is synchronous by design |
| `cachetools` | One cache key doesn't justify a new dependency |
| `prometheus-api-client` | Heavyweight ORM-style library; we need raw HTTP calls |
| `bravado` / `swagger-codegen` output | Massive dep chain for 4 GET endpoints |
| `redis` / `memcached` | MCP server is single-process stdio; in-memory cache is correct |
| `marshmallow` / `attrs` | Pydantic 2 TypedDicts already handle serialization |
| `tenacity` | Existing retry logic in `PrometheusClient._request()` is sufficient; same pattern reused for `AlertmanagerClient` |

---

## pyproject.toml — Expected Changes

```toml
# NO dependency changes needed. Only version bump:
[project]
version = "2.0.0"  # was "0.1.0"
description = "MCP server for Prometheus and Alertmanager — query metrics, alerts, silences, cardinality, and federated instances (read-only)."
keywords = ["mcp", "prometheus", "alertmanager", "metrics", "observability", "promql", "monitoring", "claude", "anthropic", "cardinality", "federation"]
```

---

## Sources

| Source | URL | Confidence | What It Confirmed |
|--------|-----|------------|-------------------|
| Prometheus HTTP API docs | https://prometheus.io/docs/prometheus/latest/querying/api/ | HIGH | TSDB status endpoint format, available query params |
| Prometheus Management API | https://prometheus.io/docs/prometheus/latest/management_api/ | HIGH | `/-/healthy` and `/-/ready` endpoints |
| Alertmanager OpenAPI v2 spec | https://github.com/prometheus/alertmanager/blob/master/api/v2/openapi.yaml | HIGH | Full read-only API surface, response schemas |
| Alertmanager Alerts API docs | https://prometheus.io/docs/alerting/latest/alerts_api/ | HIGH | APIv2 is current; v1 removed in 0.27.0 |
| Existing codebase (`client.py`, `tools.py`, `_mcp.py`, `pyproject.toml`) | Local | HIGH | Patterns to follow, deps already available |
| `requests` library | https://requests.readthedocs.io/ | HIGH | `stream=True` + `iter_content()` for response size limits |
| Python stdlib `concurrent.futures` | https://docs.python.org/3.10/library/concurrent.futures.html | HIGH | `ThreadPoolExecutor` available in Python 3.10+ |
