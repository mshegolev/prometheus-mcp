# Architecture Patterns

**Domain:** Prometheus MCP Server v2.0 — feature integration architecture
**Researched:** 2026-06-08
**Confidence:** HIGH (based on direct codebase analysis + Prometheus/Alertmanager API docs)

## Current Architecture Snapshot

```
┌────────────────────────────────────────────────────────────────┐
│  MCP Client (Claude, Cursor, CI)                               │
│  ← stdio →                                                     │
├────────────────────────────────────────────────────────────────┤
│  FastMCP runtime (async event loop)                            │
│  ├── anyio.to_thread.run_sync → sync tool functions            │
│  └── lifespan: startup/shutdown hook                           │
├────────────────────────────────────────────────────────────────┤
│  server.py       │ Entry point, imports tools to register them │
│  _mcp.py         │ FastMCP instance, get_client() singleton    │
│  tools.py        │ 8 @mcp.tool functions (all synchronous)     │
│  client.py       │ PrometheusClient: requests Session + retry  │
│  models.py       │ TypedDict output schemas                    │
│  output.py       │ ok() / fail() dual-channel helpers          │
│  errors.py       │ HTTP error → actionable message mapping     │
└────────────────────────────────────────────────────────────────┘
         │
         ▼
    Prometheus HTTP API v1 (single instance)
```

**Key invariants to preserve:**
- All tools are synchronous `def` (FastMCP dispatches to worker threads)
- `get_client()` returns a thread-safe singleton PrometheusClient
- Every tool returns `output.ok(TypedDict, markdown)` or calls `output.fail(exc, action)`
- All operations are read-only (GET only)
- `models.py` TypedDict schemas drive `structured_output=True`

## Recommended Architecture for v2.0

```
┌────────────────────────────────────────────────────────────────┐
│  MCP Client (Claude, Cursor, CI)                               │
│  ← stdio →                                                     │
├────────────────────────────────────────────────────────────────┤
│  FastMCP runtime (async event loop)                            │
│  ├── anyio.to_thread.run_sync → sync tool functions            │
│  └── lifespan: startup/shutdown (close all clients + cache)    │
├────────────────────────────────────────────────────────────────┤
│  server.py             │ Entry point (unchanged)               │
│  _mcp.py               │ + get_alertmanager_client()           │
│                        │ + get_federation_clients()            │
│                        │ + lifespan closes new clients         │
│  tools.py              │ Existing 8 tools (UNCHANGED)          │
│  tools_alertmanager.py │ NEW: 2 Alertmanager tools             │
│  tools_cardinality.py  │ NEW: 1-2 cardinality tools            │
│  tools_federation.py   │ NEW: 1-2 federation tools             │
│  tools_health.py       │ NEW: 1 health check tool              │
│  client.py             │ + response size guard in _request()   │
│  alertmanager_client.py│ NEW: AlertmanagerClient (same pattern) │
│  cache.py              │ NEW: TTLCache for metric names         │
│  models.py             │ + new TypedDict schemas                │
│  output.py             │ (unchanged)                            │
│  errors.py             │ + Alertmanager error handling           │
└────────────────────────────────────────────────────────────────┘
         │                          │                    │
         ▼                          ▼                    ▼
    Prometheus API v1         Alertmanager API     Prometheus #2..N
    (primary instance)        (separate service)   (federation targets)
```

## Component-by-Component Integration Plan

### 1. Response Size Limits — MODIFY `client.py`

**What changes:** Add a response size guard inside `PrometheusClient._request()`.

**Why here:** Every HTTP response flows through `_request()`. Guarding at this layer protects all existing and future tools without per-tool changes.

**Implementation:**

```python
# In client.py

_DEFAULT_MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # 50 MB default

class PrometheusClient:
    def __init__(self, ..., max_response_bytes: int | None = None):
        # ... existing init ...
        if max_response_bytes is None:
            env_val = os.environ.get("PROMETHEUS_MAX_RESPONSE_BYTES", "")
            if env_val:
                max_response_bytes = int(env_val)
            else:
                max_response_bytes = _DEFAULT_MAX_RESPONSE_BYTES
        self.max_response_bytes = max_response_bytes

    def _request(self, method, endpoint, *, params=None):
        # ... existing retry logic ...
        response = self.session.request(...)
        # SIZE GUARD — check Content-Length header first (fast path),
        # fall back to len(response.content) for chunked responses
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > self.max_response_bytes:
            raise ResponseTooLargeError(
                f"Response for {endpoint} is {int(content_length)} bytes "
                f"(limit: {self.max_response_bytes}). Narrow your query."
            )
        if len(response.content) > self.max_response_bytes:
            raise ResponseTooLargeError(...)
        response.raise_for_status()
        return response
```

**New error class in `errors.py`:**
```python
class ResponseTooLargeError(Exception):
    """Response exceeded PROMETHEUS_MAX_RESPONSE_BYTES."""
```

Add corresponding handler in `errors.handle()` with actionable message telling the agent to narrow its query.

**Env var:** `PROMETHEUS_MAX_RESPONSE_BYTES` (default: 50MB, 0 = unlimited)

**Impact on existing code:** Minimal — adds a check before `raise_for_status()`. Existing tools unchanged. Error surfaces through existing `output.fail()` path.

**Build order priority:** **FIRST** — protects all subsequent tools.

---

### 2. Metric Name Caching — NEW `cache.py`, MODIFY `tools.py`

**What changes:** New `cache.py` module with a simple TTL cache. Modify `prometheus_list_metrics` to cache the full metric name list.

**Why a new module:** Cache logic is reusable (federation may need it too), and `tools.py` is already 1055 lines.

**Implementation:**

```python
# cache.py — NEW FILE

import threading
import time
from typing import Any

_DEFAULT_CACHE_TTL = 300  # 5 minutes


class TTLCache:
    """Thread-safe TTL cache for expensive Prometheus lookups.

    Designed for metric name lists on large instances (100K+ metrics)
    where /label/__name__/values takes seconds.
    """

    def __init__(self, ttl: float | None = None):
        env_ttl = os.environ.get("PROMETHEUS_CACHE_TTL", "")
        self.ttl = ttl or (float(env_ttl) if env_ttl else _DEFAULT_CACHE_TTL)
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self.ttl, value)

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)
```

**Integration in `_mcp.py`:** Add a `get_cache()` singleton alongside `get_client()`. Clean up in lifespan.

**Integration in `tools.py`:** `prometheus_list_metrics` checks cache before hitting Prometheus. Cache stores the raw `list[str]` from `/label/__name__/values`. Pattern filtering happens client-side on cached data (already the current design).

**Env var:** `PROMETHEUS_CACHE_TTL` (default: 300s, 0 = disabled)

**Impact on existing code:** `prometheus_list_metrics` gains a cache-hit fast path. Output unchanged. No API signature change.

**Build order priority:** **SECOND** — enables caching pattern reused by federation.

---

### 3. Health Check Tool — NEW `tools_health.py`

**What changes:** New tool file with a single `prometheus_health_check` tool.

**Why a new file:** Keeps `tools.py` (existing 8 tools) frozen. Health check is operationally distinct — used by k8s probes, not by agents investigating metrics.

**Implementation:**

```python
# tools_health.py — NEW FILE

@mcp.tool(
    name="prometheus_health_check",
    annotations={"title": "Health Check", "readOnlyHint": True, ...},
    structured_output=True,
)
def prometheus_health_check() -> HealthCheckOutput:
    """Check connectivity to Prometheus (and optionally Alertmanager).

    Designed for container orchestrator liveness probes and agent
    pre-flight checks. Hits GET /-/healthy on each configured endpoint.
    """
    results = {}
    # Check Prometheus
    try:
        client = get_client()
        # Use /-/healthy (returns 200 OK with "Prometheus Server is Healthy.")
        # This is NOT under /api/v1, so we need raw session access
        resp = client.session.get(
            f"{client.url}/-/healthy", timeout=5
        )
        results["prometheus"] = {
            "healthy": resp.status_code == 200,
            "status_code": resp.status_code,
            "url": client.url,
        }
    except Exception as exc:
        results["prometheus"] = {"healthy": False, "error": str(exc), ...}

    # Check Alertmanager if configured
    try:
        am_client = get_alertmanager_client()
        if am_client is not None:
            resp = am_client.session.get(
                f"{am_client.url}/-/healthy", timeout=5
            )
            results["alertmanager"] = {"healthy": ..., ...}
    except Exception:
        ...

    return output.ok(result, md)
```

**New model in `models.py`:**
```python
class ServiceHealth(TypedDict):
    healthy: bool
    status_code: int | None
    url: str
    error: str | None

class HealthCheckOutput(TypedDict):
    overall_healthy: bool
    services: dict[str, ServiceHealth]
```

**Note on `/-/healthy`:** This endpoint is outside `/api/v1`, so the tool needs to access `client.url` directly (not `client.api_url`). The existing `client.session` already has auth headers set, so this works. Consider adding a `health_check()` method to PrometheusClient rather than reaching into `session` directly.

**Integration in `server.py`:** Add `from prometheus_mcp import tools_health as _tools_health  # noqa: F401` alongside the existing tools import.

**Build order priority:** **THIRD** — depends on nothing, but Alertmanager health check depends on #4.

---

### 4. Alertmanager Client + Tools — NEW `alertmanager_client.py`, NEW `tools_alertmanager.py`

**What changes:** New HTTP client for Alertmanager API v2, new tool module with 2 tools.

**Why separate client:** Alertmanager is a different service at a different URL. Its API is v2 (not v1 like Prometheus) and returns different JSON shapes. Reusing PrometheusClient would require awkward conditional logic. Instead, create AlertmanagerClient following the same structural pattern (requests.Session, retry, auth, env-var config) but with its own URL and API prefix.

**New env vars:**
- `ALERTMANAGER_URL` (required for Alertmanager tools, optional for the server)
- `ALERTMANAGER_TOKEN`, `ALERTMANAGER_USERNAME`, `ALERTMANAGER_PASSWORD` (optional, defaults to Prometheus credentials if unset)
- `ALERTMANAGER_SSL_VERIFY` (optional, defaults to PROMETHEUS_SSL_VERIFY)
- `ALERTMANAGER_TIMEOUT` (optional, defaults to PROMETHEUS_TIMEOUT)

**AlertmanagerClient pattern (alertmanager_client.py):**

```python
class AlertmanagerClient:
    """Minimal Alertmanager HTTP API v2 client.

    Follows the same pattern as PrometheusClient: env-var config,
    requests.Session, retry, auth priority (Bearer > Basic > none).
    """

    def __init__(self, url=None, ...):
        raw_url = url or os.environ.get("ALERTMANAGER_URL", "")
        if not raw_url:
            raise ConfigError("ALERTMANAGER_URL is not set")
        self.url = _validate_url(raw_url)
        self.api_url = f"{self.url}/api/v2"
        # ... same session setup pattern as PrometheusClient ...

    def get(self, endpoint, params=None) -> Any:
        # Same as PrometheusClient.get() but against api/v2
        ...
```

**Consider extracting a base class:** PrometheusClient and AlertmanagerClient share ~70% of their `__init__` code (session setup, auth, SSL, retry). A `BaseHTTPClient` abstract class would reduce duplication:

```python
class BaseHTTPClient:
    """Common HTTP client logic: session, auth, retry, timeout."""
    def __init__(self, url, api_prefix, env_prefix, ...): ...
    def get(self, endpoint, params=None): ...
    def _request(self, method, endpoint, *, params=None): ...
    def close(self): ...

class PrometheusClient(BaseHTTPClient):
    def __init__(self, ...):
        super().__init__(url=..., api_prefix="/api/v1", env_prefix="PROMETHEUS")

class AlertmanagerClient(BaseHTTPClient):
    def __init__(self, ...):
        super().__init__(url=..., api_prefix="/api/v2", env_prefix="ALERTMANAGER")
```

**Recommendation:** Extract BaseHTTPClient. The duplication is mechanical and any bug fix (e.g., response size limit) must otherwise be applied twice.

**Singleton in `_mcp.py`:**

```python
_am_client: AlertmanagerClient | None = None
_am_client_lock = threading.Lock()
_am_client_attempted = False  # distinguish "not configured" from "not yet tried"

def get_alertmanager_client() -> AlertmanagerClient | None:
    """Return cached AlertmanagerClient, or None if ALERTMANAGER_URL is not set."""
    global _am_client, _am_client_attempted
    if not _am_client_attempted:
        with _am_client_lock:
            if not _am_client_attempted:
                try:
                    _am_client = AlertmanagerClient()
                except ConfigError:
                    _am_client = None  # not configured — this is fine
                _am_client_attempted = True
    return _am_client
```

**Tools (tools_alertmanager.py):**

| Tool | Alertmanager API | Purpose |
|------|-----------------|---------|
| `alertmanager_list_silences` | `GET /api/v2/silences` | List active/expired silences |
| `alertmanager_list_inhibitions` | `GET /api/v2/alerts` (filter) | Show inhibition rules and their status |

**Alertmanager API endpoints used (all GET, read-only):**
- `/api/v2/silences` — returns `[{id, status, matchers, createdBy, comment, startsAt, endsAt}]`
- `/api/v2/alerts` — returns `[{labels, annotations, status, inhibitedBy, silencedBy}]`
- `/api/v2/status` — returns `{cluster, config, uptime, versionInfo}`

**New models in `models.py`:**

```python
class SilenceItem(TypedDict):
    id: str
    status: str
    matchers: list[dict[str, str]]
    created_by: str
    comment: str
    starts_at: str
    ends_at: str

class ListSilencesOutput(TypedDict):
    total_count: int
    active_count: int
    expired_count: int
    pending_count: int
    silences: list[SilenceItem]

class AlertmanagerAlertItem(TypedDict):
    labels: dict[str, str]
    annotations: dict[str, str]
    status: str
    inhibited_by: list[str]
    silenced_by: list[str]

class ListAlertmanagerAlertsOutput(TypedDict):
    total_count: int
    active_count: int
    suppressed_count: int
    alerts: list[AlertmanagerAlertItem]
```

**Error handling in `errors.py`:** Add Alertmanager-specific messages. The error patterns are the same (HTTP 401/403/404/5xx) but the actionable hints should reference `ALERTMANAGER_URL` instead of `PROMETHEUS_URL`.

**Build order priority:** **FOURTH** — independent of caching/size limits but health check tool benefits from having this ready.

---

### 5. Cardinality Statistics — NEW `tools_cardinality.py`

**What changes:** New tool file with 1-2 cardinality tools using existing PrometheusClient.

**Prometheus TSDB Stats API:**
- `GET /api/v1/status/tsdb` — returns `{seriesCountByMetricName, labelValueCountByLabelName, memoryInBytesByLabelName, seriesCountByLabelValuePair, ...}`

This endpoint exists in Prometheus since v2.14 and provides pre-computed cardinality statistics without needing to enumerate series.

**Tools:**

| Tool | API Endpoint | Purpose |
|------|-------------|---------|
| `prometheus_cardinality_stats` | `GET /api/v1/status/tsdb` | Top metrics by series count, top labels by value count |

**Implementation approach:**

```python
# tools_cardinality.py — NEW FILE

@mcp.tool(
    name="prometheus_cardinality_stats",
    annotations={"title": "Cardinality Stats", "readOnlyHint": True, ...},
    structured_output=True,
)
def prometheus_cardinality_stats(
    top_n: Annotated[int, Field(default=20, ge=1, le=100, ...)] = 20,
) -> CardinalityStatsOutput:
    """Get TSDB cardinality statistics from Prometheus.

    Shows top metrics by series count, top labels by value count,
    and top label-value pairs by series count. Essential for
    investigating cardinality explosions and understanding which
    metrics/labels consume the most TSDB resources.
    """
    client = get_client()
    raw = client.get("/status/tsdb") or {}
    data = raw.get("data") or {}

    series_by_metric = data.get("seriesCountByMetricName") or []
    label_value_counts = data.get("labelValueCountByLabelName") or []
    series_by_label_pair = data.get("seriesCountByLabelValuePair") or []
    total_series = data.get("headStats", {}).get("numSeries", 0)

    # Shape and cap at top_n
    ...
```

**New models:**

```python
class CardinalityItem(TypedDict):
    name: str
    value: int

class CardinalityStatsOutput(TypedDict):
    total_series: int
    top_metrics_by_series: list[CardinalityItem]
    top_labels_by_value_count: list[CardinalityItem]
    top_label_pairs_by_series: list[CardinalityItem]
```

**No client changes needed** — uses existing `PrometheusClient.get()` with a different endpoint.

**Build order priority:** **FIFTH** — uses existing client, independent of other features.

---

### 6. Federation — NEW `tools_federation.py`, MODIFY `_mcp.py`

**What changes:** Multi-instance query support. Agent specifies which instance(s) to query, or queries all.

**This is the most architecturally significant change.** Currently, the server assumes exactly one Prometheus instance. Federation requires managing multiple PrometheusClient instances.

**Configuration approach:**

```
# Primary (existing, unchanged)
PROMETHEUS_URL=https://prometheus-primary.example.com

# Federation targets (new)
PROMETHEUS_FEDERATION_URLS=https://prom-us.example.com,https://prom-eu.example.com
PROMETHEUS_FEDERATION_NAMES=us-west,eu-central
```

Names are optional — if omitted, derive from hostname. Each federation target inherits the primary's auth config unless overridden.

**Client management in `_mcp.py`:**

```python
_federation_clients: dict[str, PrometheusClient] | None = None
_federation_lock = threading.Lock()

def get_federation_clients() -> dict[str, PrometheusClient]:
    """Return a dict of name → PrometheusClient for federation targets.

    Returns empty dict if PROMETHEUS_FEDERATION_URLS is not set.
    Clients share auth config with the primary instance.
    """
    global _federation_clients
    if _federation_clients is None:
        with _federation_lock:
            if _federation_clients is None:
                urls = os.environ.get("PROMETHEUS_FEDERATION_URLS", "")
                if not urls:
                    _federation_clients = {}
                else:
                    names = os.environ.get("PROMETHEUS_FEDERATION_NAMES", "")
                    # Parse and create clients...
                    _federation_clients = {...}
    return _federation_clients
```

**Tools:**

| Tool | Purpose |
|------|---------|
| `prometheus_federated_query` | Run same PromQL against multiple instances, return per-instance results |
| `prometheus_list_instances` | List configured instances (primary + federation) with health status |

```python
@mcp.tool(name="prometheus_federated_query", ...)
def prometheus_federated_query(
    query: str,
    instances: list[str] | None = None,  # None = all
    time: str | None = None,
) -> FederatedQueryOutput:
    """Execute a PromQL query across multiple Prometheus instances.

    Runs the same query against each instance sequentially and returns
    results grouped by instance name. Use prometheus_list_instances
    to discover available instance names.
    """
    clients = get_federation_clients()
    primary = get_client()

    targets: dict[str, PrometheusClient] = {"primary": primary, **clients}
    if instances:
        targets = {k: v for k, v in targets.items() if k in instances}

    results = {}
    for name, client in targets.items():
        try:
            raw = client.get("/query", params={"query": query, "time": time})
            results[name] = {"status": "success", "data": raw.get("data", {})}
        except Exception as exc:
            results[name] = {"status": "error", "error": str(exc)}

    return output.ok(result, md)
```

**Why sequential, not parallel:** Tools run in a single worker thread. Parallel HTTP within a sync tool would require `concurrent.futures.ThreadPoolExecutor` — added complexity for a feature that typically has 2-5 instances. Keep it simple initially; optimize if latency becomes a problem.

**New models:**

```python
class FederatedInstanceResult(TypedDict):
    instance: str
    status: str  # "success" or "error"
    error: str | None
    result_type: str | None
    result_count: int
    data: list[InstantSample]

class FederatedQueryOutput(TypedDict):
    query: str
    time: str | None
    instance_count: int
    success_count: int
    error_count: int
    results: list[FederatedInstanceResult]

class InstanceInfo(TypedDict):
    name: str
    url: str
    role: str  # "primary" or "federation"

class ListInstancesOutput(TypedDict):
    total_count: int
    instances: list[InstanceInfo]
```

**Lifespan cleanup:** `app_lifespan` must close federation clients on shutdown.

**Build order priority:** **SIXTH (LAST)** — most complex, depends on response size limits (to protect against large federated responses), builds on patterns established by Alertmanager client.

---

## Module Modification Summary

| Module | Change | Scope |
|--------|--------|-------|
| `client.py` | Add response size guard + `max_response_bytes` | 15-25 lines added |
| `_mcp.py` | Add `get_alertmanager_client()`, `get_federation_clients()`, `get_cache()`, update lifespan | ~50 lines added |
| `models.py` | Add TypedDict schemas for 6 new tool outputs | ~80 lines added |
| `errors.py` | Add `ResponseTooLargeError`, Alertmanager error hints | ~20 lines added |
| `server.py` | Import 4 new tool modules | 4 lines added |
| `tools.py` | Cache integration in `prometheus_list_metrics` | ~10 lines modified |
| `output.py` | **UNCHANGED** | — |
| `__init__.py` | **UNCHANGED** | — |

| New Module | Purpose | Estimated Size |
|------------|---------|---------------|
| `cache.py` | TTLCache class | ~50 lines |
| `alertmanager_client.py` | AlertmanagerClient (or BaseHTTPClient + refactor) | ~80-120 lines |
| `tools_health.py` | `prometheus_health_check` | ~60 lines |
| `tools_alertmanager.py` | `alertmanager_list_silences`, `alertmanager_list_inhibitions` | ~150 lines |
| `tools_cardinality.py` | `prometheus_cardinality_stats` | ~80 lines |
| `tools_federation.py` | `prometheus_federated_query`, `prometheus_list_instances` | ~120 lines |

## Data Flow Changes

### Current Data Flow (v1.0)
```
Agent → MCP tool → get_client() → PrometheusClient.get() → Prometheus API → JSON → shape → output.ok()
```

### v2.0 Data Flows

**Standard tools (unchanged):**
```
Agent → existing tool → get_client() → PrometheusClient.get() [+ size guard] → shape → output.ok()
```

**Cached metric list:**
```
Agent → prometheus_list_metrics → get_cache().get("metrics")
  HIT  → filter → output.ok()
  MISS → get_client() → Prometheus API → cache.set() → filter → output.ok()
```

**Alertmanager tools:**
```
Agent → alertmanager tool → get_alertmanager_client()
  None → output.fail("ALERTMANAGER_URL not configured")
  Some → AlertmanagerClient.get() → Alertmanager API v2 → shape → output.ok()
```

**Federation tools:**
```
Agent → prometheus_federated_query → get_federation_clients() + get_client()
  → for each instance: client.get("/query") → collect results
  → merge → output.ok()
```

**Health check:**
```
Agent → prometheus_health_check
  → client.session.get("/-/healthy") for Prometheus
  → am_client.session.get("/-/healthy") for Alertmanager (if configured)
  → merge → output.ok()
```

## Patterns to Follow

### Pattern 1: Tool Module Isolation
**What:** Each feature domain gets its own `tools_*.py` file.
**When:** Any new tool that represents a distinct API surface or capability.
**Why:** `tools.py` is already 1055 lines. Splitting by domain prevents the "everything in one file" anti-pattern while maintaining the same registration mechanism (import-time `@mcp.tool` decoration).

```python
# server.py — just add imports
from prometheus_mcp import tools as _tools              # noqa: F401 (existing)
from prometheus_mcp import tools_health as _th           # noqa: F401
from prometheus_mcp import tools_alertmanager as _ta      # noqa: F401
from prometheus_mcp import tools_cardinality as _tc       # noqa: F401
from prometheus_mcp import tools_federation as _tf        # noqa: F401
```

### Pattern 2: Graceful Optional Services
**What:** Alertmanager and federation are optional. Tools for unconfigured services should fail with a clear message, not crash the server.
**When:** Any service that may not be deployed.

```python
def _require_alertmanager() -> AlertmanagerClient:
    """Return AlertmanagerClient or raise ToolError with actionable message."""
    client = get_alertmanager_client()
    if client is None:
        raise ToolError(
            "Alertmanager is not configured. Set ALERTMANAGER_URL to use this tool. "
            "Example: ALERTMANAGER_URL=https://alertmanager.example.com"
        )
    return client
```

### Pattern 3: Same Output Contract
**What:** Every new tool follows the exact same output contract as existing tools.
**When:** Always.

```python
# EVERY tool ends with:
return output.ok(typed_dict_result, markdown_string)

# EVERY tool error path:
except Exception as exc:
    output.fail(exc, "descriptive action string")
```

### Pattern 4: Env-Var Configuration with Sensible Defaults
**What:** All new config via environment variables, with defaults that make the simplest deployment work.
**When:** Any new configurable behavior.

| Variable | Default | Purpose |
|----------|---------|---------|
| `PROMETHEUS_MAX_RESPONSE_BYTES` | 52428800 (50MB) | Response size limit |
| `PROMETHEUS_CACHE_TTL` | 300 (5 min) | Metric name cache TTL; 0 = disabled |
| `ALERTMANAGER_URL` | (none) | Alertmanager base URL |
| `ALERTMANAGER_TOKEN` | (none, falls back to PROMETHEUS_TOKEN) | Alertmanager Bearer token |
| `ALERTMANAGER_USERNAME` | (none, falls back to PROMETHEUS_USERNAME) | Alertmanager Basic auth user |
| `ALERTMANAGER_PASSWORD` | (none, falls back to PROMETHEUS_PASSWORD) | Alertmanager Basic auth pass |
| `ALERTMANAGER_SSL_VERIFY` | (falls back to PROMETHEUS_SSL_VERIFY) | Alertmanager SSL verify |
| `ALERTMANAGER_TIMEOUT` | (falls back to PROMETHEUS_TIMEOUT) | Alertmanager request timeout |
| `PROMETHEUS_FEDERATION_URLS` | (none) | Comma-separated federation URLs |
| `PROMETHEUS_FEDERATION_NAMES` | (none) | Comma-separated friendly names |

## Anti-Patterns to Avoid

### Anti-Pattern 1: Modifying Existing Tool Signatures
**What:** Changing parameters or output shape of the existing 8 tools.
**Why bad:** Breaks backward compatibility. Existing agent prompts/workflows depend on current signatures.
**Instead:** Add new tools with new names. The only acceptable modification to `tools.py` is adding cache logic inside `prometheus_list_metrics` (internal implementation change, same external API).

### Anti-Pattern 2: God Client
**What:** Adding Alertmanager methods to PrometheusClient.
**Why bad:** PrometheusClient targets Prometheus API v1. Alertmanager is API v2 with different JSON shapes, different error semantics, and different URL. Mixing them creates conditional logic everywhere.
**Instead:** Separate AlertmanagerClient. Consider a BaseHTTPClient for shared plumbing.

### Anti-Pattern 3: Async/Await in Tools
**What:** Making new tools `async def` because "they do HTTP".
**Why bad:** Existing tools are all synchronous. FastMCP's `anyio.to_thread.run_sync` handles them correctly. Mixing sync and async tools in the same server creates cognitive overhead and potential bugs. The `requests` library is synchronous anyway.
**Instead:** Keep all tools as `def`. Stay consistent.

### Anti-Pattern 4: In-Memory Cache Without TTL
**What:** Caching metric names forever.
**Why bad:** Prometheus instances add/remove metrics as services scale. Stale cache means missing metrics.
**Instead:** Always TTL-based. 5 minutes default. Environment variable override. Clear-on-shutdown.

### Anti-Pattern 5: Parallel HTTP in Sync Tools Without Bounds
**What:** Using ThreadPoolExecutor for federation queries without a max-worker limit.
**Why bad:** If someone configures 50 federation targets, you'd spawn 50 threads.
**Instead:** Sequential for now (simple, safe). If parallelism is needed later, cap at 5-10 workers.

## Build Order (Dependency-Driven)

```
Phase 1: Response Size Limits
  └── Modifies client.py (foundation for all HTTP)
  └── No dependencies

Phase 2: Metric Name Caching
  └── New cache.py
  └── Modifies tools.py (prometheus_list_metrics)
  └── Depends on: nothing (but phase 1 means cached responses are also size-guarded)

Phase 3: Health Check Tool
  └── New tools_health.py
  └── Depends on: nothing (but benefits from Alertmanager client in Phase 4)
  └── Can ship with Prometheus-only health check first, add Alertmanager later

Phase 4: Alertmanager Integration
  └── New alertmanager_client.py
  └── New tools_alertmanager.py
  └── Modifies _mcp.py (new singleton), errors.py (new handlers), models.py (new schemas)
  └── Depends on: response size limits (Phase 1) for protection
  └── Consider: BaseHTTPClient extraction as part of this phase

Phase 5: Cardinality Statistics
  └── New tools_cardinality.py
  └── Uses existing PrometheusClient
  └── Depends on: response size limits (Phase 1) — TSDB stats can be large

Phase 6: Federation
  └── New tools_federation.py
  └── Modifies _mcp.py (federation client pool)
  └── Depends on: response size limits (Phase 1), patterns from Alertmanager client (Phase 4)
  └── Most complex — benefits from all prior phases being stable
```

**Rationale for this order:**
1. **Size limits first** — defense in depth for everything that follows
2. **Caching second** — simple, self-contained, establishes the caching pattern
3. **Health check third** — simple tool, useful immediately for k8s deployments
4. **Alertmanager fourth** — introduces multi-service pattern, moderate complexity
5. **Cardinality fifth** — simple tool using existing client, but can reveal large data
6. **Federation last** — highest complexity, benefits from all patterns being established

## Scalability Considerations

| Concern | At 1 instance | At 5 instances (federation) | At 20 instances |
|---------|---------------|---------------------------|-----------------|
| Memory (client objects) | ~1KB per Session | ~5KB | ~20KB — negligible |
| Metric cache size | ~500KB for 100K metrics | N/A (cache per primary) | Same |
| Federation query latency | N/A | ~5x single query time (sequential) | Consider parallel with thread pool |
| Response size risk | Low (single instance) | 5x — size limits essential | 20x — must enforce limits |
| Connection count | 1 Session (pooled) | 5 Sessions | 20 Sessions (acceptable) |

## Sources

- Codebase analysis: direct reading of all 8 source modules (HIGH confidence)
- Prometheus HTTP API v1: https://prometheus.io/docs/prometheus/latest/querying/api/ (HIGH)
- Prometheus TSDB Status: https://prometheus.io/docs/prometheus/latest/querying/api/#tsdb-stats (HIGH)
- Alertmanager API v2: https://prometheus.io/docs/alerting/latest/clients/ (HIGH)
- FastMCP threading model: observed in `_mcp.py` comments and tool signatures (HIGH)
- MCP protocol conventions: https://modelcontextprotocol.io (HIGH)
