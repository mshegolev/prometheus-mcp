# Architecture: Federation Integration

**Domain:** Multi-instance Prometheus/Alertmanager federation for MCP server
**Researched:** 2026-06-08
**Overall confidence:** HIGH (analysis based on reading every line of existing codebase — all 14 source files, all test fixtures, pyproject.toml)

## Executive Summary

Federation adds a new conceptual layer — **instance routing** — between the MCP tool surface and the HTTP clients. Today each tool calls `get_client()` → gets the single `PrometheusClient` → makes one HTTP call. Federation changes this to: each tool calls a **resolver** → gets one or many clients → fans out HTTP calls → merges results. The critical design constraint is **backward compatibility**: when no config file is present, the server must behave identically to v0.2.0.

The architecture introduces 4 new modules (`config.py`, `registry.py`, `federation.py`, `tools_federation.py`) and modifies 2 existing modules (`_mcp.py`, `models.py`). Existing tool modules (`tools.py`, `tools_status.py`, `tools_alertmanager.py`) gain an optional `instance` parameter but their core logic is unchanged — the routing happens below them in the resolver layer.

## Current Architecture (As-Is)

```
┌─────────────────────────────────────────────────────────┐
│  MCP Client (Claude, Cursor, CI pipeline)                │
│  ← stdio transport →                                     │
├─────────────────────────────────────────────────────────┤
│  FastMCP runtime (async event loop)                      │
│  anyio.to_thread.run_sync → synchronous tool functions   │
│  lifespan: startup/shutdown hook (app_lifespan)          │
├─────────────────────────────────────────────────────────┤
│  server.py       │ Entry point, imports tool modules     │
│  _mcp.py         │ FastMCP instance, get_client() →      │
│                  │   singleton PrometheusClient           │
│                  │ get_alertmanager_client() →            │
│                  │   singleton AlertmanagerClient         │
│                  │ app_lifespan → close sessions          │
│  tools.py        │ 8 @mcp.tool: query, range, alerts,   │
│                  │   targets, metrics, metadata, labels, │
│                  │   rules                                │
│  tools_status.py │ 4 @mcp.tool: health, cardinality,    │
│                  │   runtime info, build info             │
│  tools_alertmanager.py │ 4 @mcp.tool: silences, AM      │
│                  │   alerts, AM status, alert groups      │
│  client.py       │ PrometheusClient: requests.Session,   │
│                  │   retry logic, size limits, env config │
│  alertmanager_   │ AlertmanagerClient: same pattern,     │
│    client.py     │   API v2, env config                  │
│  cache.py        │ TTLCache: singleton, metric names     │
│  models.py       │ TypedDict output schemas (all tools)  │
│  output.py       │ ok() / fail() dual-channel helpers    │
│  errors.py       │ HTTP error → actionable LLM messages  │
└─────────────────────────────────────────────────────────┘
         │                            │
         ▼                            ▼
    Prometheus HTTP API v1      Alertmanager API v2
    (single instance)           (single instance)
```

**Key structural facts from code analysis:**

1. **Single-client singletons.** `_mcp.py` (line 18-23) holds `_client: PrometheusClient | None` and `_am_client: AlertmanagerClient | None` as module globals with thread-safe lazy init via `threading.Lock()`.

2. **Config via env vars exclusively.** `PrometheusClient.__init__()` reads `PROMETHEUS_URL`, `PROMETHEUS_TOKEN`, `PROMETHEUS_USERNAME`, `PROMETHEUS_PASSWORD`, `PROMETHEUS_SSL_VERIFY`, `PROMETHEUS_TIMEOUT`, `PROMETHEUS_MAX_RESPONSE_BYTES`. `AlertmanagerClient` reads `ALERTMANAGER_URL` + its own auth vars. No config file.

3. **Synchronous tools in async runtime.** All 16 `@mcp.tool` functions are `def` (not `async def`). FastMCP runs them in worker threads via `anyio.to_thread.run_sync`. Each tool invocation already runs in its own thread.

4. **Clients are already parameterized.** `PrometheusClient.__init__` accepts `url`, `token`, `username`, `password`, `ssl_verify`, `timeout`, `max_response_bytes` — all with env-var fallbacks. This means we can create multiple instances with different configs without modifying the class.

5. **Dual-channel output.** Every tool returns `output.ok(result_dict, markdown_string)` → `CallToolResult(content=[TextContent(...)], structuredContent=dict(...))`.

6. **Lifespan manages cleanup.** `app_lifespan()` is an async context manager that closes client sessions on shutdown.

7. **Metric caching is singleton-based.** `cache.py` provides a global `TTLCache` keyed by fixed string `"__name__values"` — not per-instance.

8. **No client abstraction layer.** Tools call `get_client()` → `client.get("/query", params=...)` directly. There is no service layer between tools and HTTP clients.

## Target Architecture (To-Be)

```
┌─────────────────────────────────────────────────────────────┐
│  MCP Client (Claude, Cursor, CI pipeline)                    │
│  ← stdio transport →                                         │
├─────────────────────────────────────────────────────────────┤
│  FastMCP runtime (unchanged)                                 │
├─────────────────────────────────────────────────────────────┤
│  server.py (+ import tools_federation)                       │
│                                                              │
│  _mcp.py (MODIFIED)                                          │
│  ├── get_registry() → InstanceRegistry singleton             │
│  ├── get_client(instance?) → routes through registry         │
│  ├── get_alertmanager_client(instance?) → routes through     │
│  │   registry                                                │
│  └── app_lifespan → loads config, creates registry,          │
│      closes ALL sessions on shutdown                         │
│                                                              │
│  tools.py (MODIFIED — add instance param to 8 tools)         │
│  tools_status.py (MODIFIED — add instance param to 4 tools)  │
│  tools_alertmanager.py (MODIFIED — add instance to 4 tools)  │
│  tools_federation.py (NEW — federation_list_instances)        │
│                                                              │
│  config.py (NEW) ──→ registry.py (NEW) ──→ federation.py(NEW)│
│  │ parse JSON config  │ manage N client    │ fan_out()       │
│  │ validate instances  │ pairs + caches    │ merge_*()       │
│  │ apply defaults      │ lifecycle         │ ThreadPool      │
│                                                              │
│  client.py (UNCHANGED)                                       │
│  alertmanager_client.py (UNCHANGED)                          │
│  cache.py (UNCHANGED — TTLCache instances reused per-entry)  │
│  models.py (MODIFIED — add federation output types)          │
│  output.py (UNCHANGED)                                       │
│  errors.py (MODIFIED — add federation error messages)        │
└─────────────────────────────────────────────────────────────┘
         │                    │                   │
         ▼                    ▼                   ▼
    Prometheus #1        Prometheus #2      Alertmanager #1
    (us-west)            (eu-central)       (us-west)
         │                                        │
         ▼                                        ▼
    Alertmanager #1                         Alertmanager #2
    (mapped to us-west)                     (mapped to eu-central)
```

## New Components

### 1. `config.py` — Configuration Loading

**Purpose:** Parse and validate the JSON config file describing named instances.

**Config file schema:**
```json
{
  "instances": {
    "us-west": {
      "prometheus_url": "https://prom-usw.corp.example.com",
      "prometheus_token": "...",
      "alertmanager_url": "https://am-usw.corp.example.com",
      "alertmanager_token": "...",
      "ssl_verify": true,
      "timeout": 30,
      "max_response_bytes": 10485760
    },
    "eu-central": {
      "prometheus_url": "https://prom-eu.corp.example.com",
      "prometheus_username": "reader",
      "prometheus_password": "...",
      "ssl_verify": false
    }
  },
  "defaults": {
    "timeout": 30,
    "ssl_verify": true,
    "max_response_bytes": 10485760
  }
}
```

**Design decisions:**

| Decision | Rationale |
|----------|-----------|
| JSON (not YAML) | Zero new dependencies — `json` is stdlib. YAML would require `pyyaml`. PROJECT.md constraint: "Minimal new deps." |
| `defaults` section | Avoids repeating timeout/SSL for every instance. Per-instance values override defaults. |
| Auth fields mirror env var names (lowercased) | Muscle memory — users already know `PROMETHEUS_TOKEN` → `prometheus_token`. |
| Alertmanager optional per instance | Many setups have Prometheus without Alertmanager (current code: `AlertmanagerClient` raises `ConfigError` if URL missing). |
| Config file path via `PROMETHEUS_MCP_CONFIG` env var | Consistent with existing env-var config pattern. Empty/unset = no federation = legacy single-instance mode. |

**Loading strategy: at startup (in lifespan), not lazy.**

Rationale: Config errors (bad JSON, missing URLs) must fail fast at startup, not on first tool call mid-investigation. The lifespan already runs before any tool invocation. Loading during lifespan means the registry is ready before any worker thread touches it — no need for double-checked locking on the registry itself.

```python
# config.py — key types
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class InstanceConfig:
    name: str
    prometheus_url: str
    prometheus_token: str = ""
    prometheus_username: str = ""
    prometheus_password: str = ""
    alertmanager_url: str = ""
    alertmanager_token: str = ""
    alertmanager_username: str = ""
    alertmanager_password: str = ""
    ssl_verify: bool = True
    timeout: float = 30.0
    max_response_bytes: int = 10 * 1024 * 1024

@dataclass(frozen=True)
class FederationConfig:
    instances: dict[str, InstanceConfig]
    defaults: dict[str, Any] = field(default_factory=dict)

def load_config(path: str) -> FederationConfig:
    """Parse JSON config file, apply defaults, validate URLs.
    
    Raises ConfigError on missing file, invalid JSON, or missing required fields.
    """
    ...
```

**Why `dataclass(frozen=True)` not Pydantic:** Config is loaded once at startup and never mutated. Frozen dataclasses are simple, have no runtime overhead, and don't require Pydantic model schema generation. Pydantic is for tool I/O schemas; config is internal.

---

### 2. `registry.py` — Instance Registry

**Purpose:** Manage the lifecycle of multiple `PrometheusClient` + `AlertmanagerClient` pairs, keyed by instance name.

```python
# registry.py — key interface
from dataclasses import dataclass
from prometheus_mcp.cache import TTLCache
from prometheus_mcp.client import PrometheusClient
from prometheus_mcp.alertmanager_client import AlertmanagerClient
from prometheus_mcp.config import FederationConfig, InstanceConfig

@dataclass
class InstanceEntry:
    """One named instance with its client pair and cache."""
    config: InstanceConfig
    prometheus: PrometheusClient
    alertmanager: AlertmanagerClient | None  # None if no AM URL configured
    cache: TTLCache  # per-instance metric name cache

@dataclass(frozen=True)
class InstanceInfo:
    """Metadata returned by the discovery tool."""
    name: str
    prometheus_url: str
    has_alertmanager: bool

class InstanceRegistry:
    """Thread-safe registry of named Prometheus/Alertmanager client pairs.
    
    Created once at startup. Not mutated after creation (entries are fixed).
    Thread-safe because reads of dict[str, InstanceEntry] are safe once 
    the dict is populated, and it's populated before any tool runs.
    """

    def __init__(self, config: FederationConfig | None = None) -> None:
        self._instances: dict[str, InstanceEntry] = {}
        self._default_name: str | None = None
        self._federation_mode: bool = False
        
        if config is not None and config.instances:
            self._federation_mode = True
            for name, inst_config in config.instances.items():
                prom = PrometheusClient(
                    url=inst_config.prometheus_url,
                    token=inst_config.prometheus_token,
                    username=inst_config.prometheus_username,
                    password=inst_config.prometheus_password,
                    ssl_verify=inst_config.ssl_verify,
                    timeout=inst_config.timeout,
                    max_response_bytes=inst_config.max_response_bytes,
                )
                am = self._try_create_am(inst_config)
                self._instances[name] = InstanceEntry(
                    config=inst_config,
                    prometheus=prom,
                    alertmanager=am,
                    cache=TTLCache(),
                )
            # First instance is the default
            self._default_name = next(iter(config.instances))
        else:
            # Legacy mode: single instance from env vars
            self._instances["default"] = InstanceEntry(
                config=InstanceConfig(name="default", prometheus_url="(env)"),
                prometheus=PrometheusClient(),  # reads env vars
                alertmanager=self._try_create_am_from_env(),
                cache=TTLCache(),
            )
            self._default_name = "default"

    @property
    def federation_mode(self) -> bool:
        return self._federation_mode

    def get_prometheus_client(self, name: str | None = None) -> PrometheusClient:
        """Return client for named instance. None → default instance."""
        target = name or self._default_name
        entry = self._instances.get(target)
        if entry is None:
            raise ConfigError(
                f"Instance {target!r} not found. "
                f"Available: {', '.join(sorted(self._instances.keys()))}. "
                "Use federation_list_instances to see configured instances."
            )
        return entry.prometheus

    def get_alertmanager_client(self, name: str | None = None) -> AlertmanagerClient:
        """Return AM client for named instance. Raises ConfigError if no AM."""
        target = name or self._default_name
        entry = self._instances.get(target)
        if entry is None:
            raise ConfigError(f"Instance {target!r} not found. ...")
        if entry.alertmanager is None:
            raise ConfigError(
                f"Instance {target!r} has no Alertmanager configured. "
                "Add alertmanager_url to the instance config."
            )
        return entry.alertmanager

    def get_cache(self, name: str | None = None) -> TTLCache:
        """Return per-instance cache. None → default instance's cache."""
        target = name or self._default_name
        return self._instances[target].cache

    def list_instances(self) -> list[InstanceInfo]:
        """Return metadata about all registered instances."""
        return [
            InstanceInfo(
                name=name,
                prometheus_url=entry.config.prometheus_url,
                has_alertmanager=entry.alertmanager is not None,
            )
            for name, entry in self._instances.items()
        ]

    def all_prometheus_clients(self) -> list[tuple[str, PrometheusClient]]:
        """Return (name, client) pairs for fan-out operations."""
        return [(name, entry.prometheus) for name, entry in self._instances.items()]

    def all_alertmanager_clients(self) -> list[tuple[str, AlertmanagerClient]]:
        """Return (name, client) pairs for AM fan-out. Skips instances without AM."""
        return [
            (name, entry.alertmanager)
            for name, entry in self._instances.items()
            if entry.alertmanager is not None
        ]

    def close_all(self) -> None:
        """Close every HTTP session (called from lifespan shutdown)."""
        for entry in self._instances.values():
            try:
                entry.prometheus.close()
            except Exception:
                pass
            if entry.alertmanager is not None:
                try:
                    entry.alertmanager.close()
                except Exception:
                    pass
```

**Backward compatibility bridge:** When `PROMETHEUS_MCP_CONFIG` is not set, the registry creates a single `"default"` entry using env vars — exactly matching current `get_client()` behavior. `get_client(None)` in legacy mode returns the same `PrometheusClient` as today.

**Per-instance caching:** Each `InstanceEntry` holds its own `TTLCache`. Different Prometheus instances have different metric names. The tools that use caching (`prometheus_list_metrics`) get the per-instance cache via `registry.get_cache(instance)`.

---

### 3. `federation.py` — Fan-out and Merge

**Purpose:** Execute the same query against multiple Prometheus/Alertmanager instances concurrently and merge results.

**Concurrency model: `concurrent.futures.ThreadPoolExecutor`**

Why this fits the existing synchronous model perfectly:
- Tools are `def` (synchronous), running in FastMCP worker threads
- `PrometheusClient` uses `requests` (synchronous, blocking)
- `ThreadPoolExecutor` submits N blocking HTTP calls to N threads
- The calling tool thread blocks on `as_completed()` / `executor.map()`
- No asyncio involvement — thread-level parallelism within the worker thread
- `ThreadPoolExecutor` is stdlib (`concurrent.futures`) — zero new dependencies

```python
# federation.py — key interface
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from prometheus_mcp.registry import InstanceRegistry

_DEFAULT_MAX_WORKERS = 8  # cap concurrent HTTP calls

@dataclass
class InstanceResult:
    """Result from one instance in a fan-out operation."""
    instance: str
    data: Any | None  # parsed JSON response, None on error
    error: str | None  # human-readable error string, None on success

def fan_out_prometheus(
    registry: InstanceRegistry,
    call_fn: Callable[[PrometheusClient], Any],
    *,
    instance: str | None = None,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> list[InstanceResult]:
    """Query one or all Prometheus instances concurrently.

    Args:
        registry: Instance registry
        call_fn: Function that takes a PrometheusClient and returns data.
                 Example: lambda c: c.get("/query", params={"query": "up"})
        instance: None for all instances, specific name for one
        max_workers: ThreadPool size cap
    
    If instance is specified → call just that one (no fan-out, no ThreadPool).
    If instance is None and federation mode → fan out to all.
    If instance is None and legacy mode → call the single default.
    
    Returns list of InstanceResult. Partial failures captured, not raised.
    """
    if instance is not None and instance != "all":
        # Single-instance targeted query — no thread pool needed
        client = registry.get_prometheus_client(instance)
        try:
            data = call_fn(client)
            return [InstanceResult(instance=instance, data=data, error=None)]
        except Exception as exc:
            return [InstanceResult(instance=instance, data=None, error=str(exc))]
    
    clients = registry.all_prometheus_clients()
    if len(clients) == 1:
        # Legacy mode or single configured instance — no thread pool
        name, client = clients[0]
        try:
            data = call_fn(client)
            return [InstanceResult(instance=name, data=data, error=None)]
        except Exception as exc:
            return [InstanceResult(instance=name, data=None, error=str(exc))]
    
    # Multi-instance fan-out with ThreadPoolExecutor
    results: list[InstanceResult] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(clients))) as executor:
        future_to_name = {
            executor.submit(call_fn, client): name
            for name, client in clients
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                data = future.result()
                results.append(InstanceResult(instance=name, data=data, error=None))
            except Exception as exc:
                results.append(InstanceResult(instance=name, data=None, error=str(exc)))
    
    # Sort by instance name for deterministic output
    results.sort(key=lambda r: r.instance)
    return results
```

**Why `call_fn` callback pattern:** The fan-out function doesn't know which endpoint/params the tool needs. The tool passes a lambda: `fan_out_prometheus(registry, lambda c: c.get("/query", params=params))`. This keeps federation.py generic and reusable across all query types.

**Instance label injection:** Fan-out results get `__prometheus_instance__` label injected into every metric/sample:

```python
def inject_instance_label(
    result_data: dict[str, Any],
    instance_name: str,
) -> dict[str, Any]:
    """Add __prometheus_instance__ to all metric labels in a Prometheus response.
    
    Works with instant query results, range query results, and alert data.
    Modifies in place and returns the same dict.
    """
    data = result_data.get("data", {})
    raw_results = data.get("result", [])
    for item in raw_results:
        metric = item.get("metric", {})
        metric["__prometheus_instance__"] = instance_name
    return result_data
```

**Merge strategies by query type:**

| Query Type | Endpoint | Merge Strategy | Key Detail |
|-----------|----------|---------------|------------|
| **Instant query** | `/query` | Concatenate samples, inject `__prometheus_instance__` per sample | Different instances → different series. Union is correct. |
| **Range query** | `/query_range` | Concatenate series, inject instance label, apply global points cap post-merge | Same as instant but with point budget enforcement. |
| **List metrics** | `/label/__name__/values` | Set union across instances, sort, apply cap | Agent wants "what exists anywhere". De-duplicate. |
| **Label values** | `/label/{name}/values` | Set union, sort | Same de-duplication logic. |
| **Metadata** | `/metadata` | Merge dicts; same-metric-name entries concatenated from all instances | Metadata is definitional. Different instances may report different HELP. |
| **Alerts** | `/alerts` | Concatenate, inject `__prometheus_instance__` | Different instances fire different alerts. |
| **Targets** | `/targets` | Concatenate, inject `__prometheus_instance__` | Targets are per-instance by definition. |
| **Rules** | `/rules` | Concatenate rule groups, prefix group name with `[instance_name]` | Same-named groups on different instances may have different rules. |
| **Cardinality** | `/status/tsdb` | Return list of per-instance cardinality objects | TSDB stats are per-database; merging them is meaningless. |
| **Health** | `/-/healthy` | Return list of per-instance health status | Health is per-instance. |
| **Build/Runtime info** | `/status/buildinfo`, `/status/runtimeinfo` | Return per-instance objects | Version/runtime is per-instance. |
| **AM silences** | AM `/silences` | Concatenate, inject `__alertmanager_instance__` | Silences are per-Alertmanager. |
| **AM alerts** | AM `/alerts` | Concatenate, inject `__alertmanager_instance__` | Same pattern. |
| **AM status** | AM `/status` | Per-instance status list | Same as health. |
| **AM alert groups** | AM `/alerts/groups` | Concatenate, inject `__alertmanager_instance__` | Same pattern. |

```python
# Merge functions — concrete examples

def merge_instant_results(
    results: list[InstanceResult],
) -> tuple[list[dict], str, list[str]]:
    """Merge instant query results from multiple instances.
    
    Returns: (merged_raw_results, result_type, error_strings)
    """
    merged: list[dict] = []
    errors: list[str] = []
    result_type = "vector"
    for r in results:
        if r.error:
            errors.append(f"{r.instance}: {r.error}")
            continue
        data = (r.data or {}).get("data", {})
        result_type = data.get("resultType", result_type)
        for item in data.get("result", []):
            metric = item.get("metric", {})
            metric["__prometheus_instance__"] = r.instance
            merged.append(item)
    return merged, result_type, errors


def merge_set_values(
    results: list[InstanceResult],
    data_key: str = "data",
) -> tuple[list[str], list[str]]:
    """Merge list-of-strings results (metric names, label values) via set union.
    
    Returns: (sorted_unique_values, error_strings)
    """
    merged_set: set[str] = set()
    errors: list[str] = []
    for r in results:
        if r.error:
            errors.append(f"{r.instance}: {r.error}")
            continue
        values = (r.data or {}).get(data_key, [])
        merged_set.update(values)
    return sorted(merged_set), errors


def merge_range_results(
    results: list[InstanceResult],
) -> tuple[list[dict], str, list[str]]:
    """Merge range query results. Same as instant but preserves matrix type."""
    merged: list[dict] = []
    errors: list[str] = []
    result_type = "matrix"
    for r in results:
        if r.error:
            errors.append(f"{r.instance}: {r.error}")
            continue
        data = (r.data or {}).get("data", {})
        result_type = data.get("resultType", result_type)
        for item in data.get("result", []):
            metric = item.get("metric", {})
            metric["__prometheus_instance__"] = r.instance
            merged.append(item)
    return merged, result_type, errors
```

---

### 4. `tools_federation.py` — Federation-Specific Tools

**Purpose:** One new tool that only exists in federation mode — instance discovery.

```python
# tools_federation.py

@mcp.tool(
    name="federation_list_instances",
    annotations={
        "title": "List Instances",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def federation_list_instances() -> ListInstancesOutput:
    """List all configured Prometheus/Alertmanager instances.

    Returns instance names, URLs, and whether each has an Alertmanager.
    Use this to discover available instances before targeting queries
    with the 'instance' parameter.

    In single-instance mode (no config file), returns one "default" instance.
    """
    registry = get_registry()
    instances = registry.list_instances()
    ...
    return output.ok(result, md)
```

**Only one new tool.** All other federation behavior is opt-in via the `instance` parameter on existing tools. This keeps the tool surface clean — agents that don't need federation see the same 16 tools plus one discovery tool.

---

## Modified Components

### `_mcp.py` — The Central Wiring Change

This is the most critical modification. It replaces the singleton client pattern with a registry pattern.

**Before (current code, lines 18-73):**
```python
_client: PrometheusClient | None = None
_client_lock = threading.Lock()
_am_client: AlertmanagerClient | None = None
_am_client_lock = threading.Lock()

async def app_lifespan(_app):
    yield {}
    # close _client and _am_client

def get_client() -> PrometheusClient:
    # double-checked locking, lazy init from env vars
    
def get_alertmanager_client() -> AlertmanagerClient:
    # double-checked locking, lazy init from env vars
```

**After:**
```python
_registry: InstanceRegistry | None = None

async def app_lifespan(_app):
    global _registry
    config_path = os.environ.get("PROMETHEUS_MCP_CONFIG", "")
    if config_path:
        config = load_config(config_path)
        _registry = InstanceRegistry(config)
        logger.info("prometheus_mcp: federation — %d instances", len(config.instances))
    else:
        _registry = InstanceRegistry(None)  # legacy single-instance
        logger.debug("prometheus_mcp: single-instance mode")
    try:
        yield {}
    finally:
        if _registry is not None:
            _registry.close_all()
            _registry = None

def get_registry() -> InstanceRegistry:
    if _registry is None:
        raise ConfigError("Registry not initialized — server not started")
    return _registry

def get_client(instance: str | None = None) -> PrometheusClient:
    return get_registry().get_prometheus_client(instance)

def get_alertmanager_client(instance: str | None = None) -> AlertmanagerClient:
    return get_registry().get_alertmanager_client(instance)
```

**What changes:**
- `_client` / `_am_client` globals → replaced by single `_registry` global
- `get_client()` and `get_alertmanager_client()` gain optional `instance` parameter
- Lifespan loads config file and creates registry at startup (eager, not lazy)
- Shutdown iterates all instances to close sessions
- No more double-checked locking — registry is created once in lifespan before any tool runs

**What stays the same:**
- `get_client()` with no arguments returns the default instance's client — **identical behavior**
- `get_alertmanager_client()` with no arguments returns the default AM client — **identical behavior**
- `mcp = FastMCP("prometheus_mcp", lifespan=app_lifespan)` — same FastMCP instance
- Thread-safety: registry is created in lifespan (async, single-threaded), read by tools (multiple threads) — reads are safe on a fully-constructed dict

### Existing Tool Modifications — The `instance` Parameter

Every existing tool gains an optional `instance` parameter. The pattern is identical across all 16 tools:

```python
# Example: prometheus_query in tools.py

@mcp.tool(name="prometheus_query", ...)
def prometheus_query(
    query: Annotated[str, Field(...)],
    time: Annotated[str | None, Field(...)] = None,
    instance: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Target a specific Prometheus instance by name "
                "(use federation_list_instances to discover names). "
                "Leave empty to query the default instance. "
                "Use 'all' to fan out across all instances and merge results."
            ),
        ),
    ] = None,
) -> QueryOutput:
    try:
        if instance == "all":
            # Fan-out path
            registry = get_registry()
            params: dict[str, Any] = {"query": query}
            if time is not None:
                params["time"] = time
            results = fan_out_prometheus(
                registry,
                lambda c: c.get("/query", params=params),
            )
            merged_raw, result_type, errors = merge_instant_results(results)
            # Build samples from merged_raw (existing shaping logic)
            samples = [_shape_instant_sample(item) for item in merged_raw]
            result = QueryOutput(...)
            # Build markdown with instance tags + error notes
            ...
            return output.ok(result, md)
        else:
            # Single-instance path: instance=None → default, instance="name" → specific
            client = get_client(instance)
            # ... existing logic unchanged ...
    except Exception as exc:
        output.fail(exc, ...)
```

**Backward compatibility proof:**
1. `instance` parameter defaults to `None` → callers that don't send it get identical behavior
2. No output schema changes — `QueryOutput` TypedDict is identical
3. When `instance=None` and no config file → `get_client(None)` → registry returns legacy singleton
4. `instance` is always the last parameter with a default → positional callers unaffected
5. `__prometheus_instance__` label lives inside existing `labels: dict[str, str]` — no schema change

### `models.py` Additions

New types for the federation discovery tool and federated per-instance responses:

```python
# models.py — additions (append, don't modify existing)

class InstanceInfoItem(TypedDict):
    name: str
    prometheus_url: str
    has_alertmanager: bool

class ListInstancesOutput(TypedDict):
    instance_count: int
    federation_mode: bool
    instances: list[InstanceInfoItem]
```

**Existing TypedDicts are NOT modified.** The `__prometheus_instance__` label appears inside the already-existing `labels: dict[str, str]` field on `InstantSample`, `AlertItem`, `TargetItem`, etc. No schema change required.

### `errors.py` Additions

```python
# errors.py — add to handle() function

if isinstance(exc, ConfigError) and "not found" in str(exc).lower():
    return (
        f"Error: {exc}. "
        "Call federation_list_instances to see available instance names."
    )
```

### `cache.py` — No Changes Needed

The `TTLCache` class is already instantiable (not a singleton pattern on the class itself — only the `get_metrics_cache()` function is singleton). `InstanceEntry` in `registry.py` creates its own `TTLCache()` instance per registered instance.

The existing `get_metrics_cache()` global function can remain for backward compatibility in test fixtures. The tools will migrate to using `registry.get_cache(instance)` instead.

---

## Data Flow Diagrams

### Single-Instance Query (backward compatible, no change)

```
Agent: prometheus_query(query="up")
  │  instance=None (default)
  ▼
tools.py: instance != "all" → single-instance path
  │
  ▼
get_client(None) → registry.get_prometheus_client(None) → default entry
  │
  ▼
PrometheusClient.get("/query", params={"query": "up"})
  │
  ▼ HTTP GET https://prometheus:9090/api/v1/query?query=up
  │
  ▼
_shape_instant_sample() → QueryOutput → output.ok(result, md)
```

### Targeted Single-Instance Query (new capability)

```
Agent: prometheus_query(query="up", instance="eu-central")
  │
  ▼
tools.py: instance="eu-central" → single-instance path
  │
  ▼
get_client("eu-central") → registry.get_prometheus_client("eu-central")
  │
  ▼
PrometheusClient[eu-central].get("/query", params={"query": "up"})
  │
  ▼ HTTP GET https://prom-eu.corp/api/v1/query?query=up
  │
  ▼
_shape_instant_sample() → QueryOutput → output.ok(result, md)
```

### Fan-Out Query (new capability)

```
Agent: prometheus_query(query="up", instance="all")
  │
  ▼
tools.py: instance="all" → fan-out path
  │
  ▼
fan_out_prometheus(registry, lambda c: c.get("/query", params))
  │
  ├─→ ThreadPoolExecutor(max_workers=min(8, N))
  │     ├─ Thread 1: client[us-west].get("/query") → JSON
  │     ├─ Thread 2: client[eu-central].get("/query") → JSON
  │     └─ Thread 3: client[ap-east].get("/query") → error (timeout)
  │
  ▼ as_completed() collects results
  │
merge_instant_results([ok, ok, err])
  │
  ├─ us-west: 3 samples → inject __prometheus_instance__="us-west"
  ├─ eu-central: 2 samples → inject __prometheus_instance__="eu-central"
  └─ ap-east: error "timed out" → captured in errors list
  │
  ▼
5 merged samples + 1 error in markdown header
  │
  ▼
QueryOutput(result_count=5, data=[...]) → output.ok(result, md)
```

---

## Error Handling: Partial Failures

Fan-out introduces a new error category: **partial failure** — some instances succeed, some fail. This does not exist in the current single-instance model.

**Strategy:** Succeed with available data + report failures.

| Scenario | Behavior |
|----------|----------|
| All instances succeed | Normal output, no error notes |
| Some succeed, some fail | Return merged data + list failures in markdown and structured output |
| All instances fail | Raise `ToolError` with all error messages concatenated |
| Single-instance query fails | Existing behavior (raise ToolError via `output.fail()`) |

```python
# In the tool function after fan-out:
merged, result_type, errors = merge_instant_results(fan_out_results)

if not merged and errors:
    # Total failure — all instances errored
    output.fail(
        ValueError(f"All instances failed: {'; '.join(errors)}"),
        f"querying all instances for {query!r}",
    )

# Partial success — include error note in markdown
md = f"## Query: `{query}` (across {success_count} of {total_count} instances)\n\n"
if errors:
    md += "### Instance Errors\n\n"
    for e in errors:
        md += f"- {e}\n"
    md += "\n"
```

---

## Module Structure Summary

### New Files (4)

| File | Purpose | Est. Lines | Dependencies |
|------|---------|-----------|-------------|
| `config.py` | JSON config parsing, validation, `InstanceConfig`/`FederationConfig` dataclasses | ~100 | stdlib only (`json`, `dataclasses`, `pathlib`) |
| `registry.py` | `InstanceRegistry` managing N client pairs + per-instance caches | ~130 | `config.py`, `client.py`, `alertmanager_client.py`, `cache.py` |
| `federation.py` | `fan_out_prometheus()`, `fan_out_alertmanager()`, merge functions | ~200 | `registry.py`, `concurrent.futures` (stdlib) |
| `tools_federation.py` | `federation_list_instances` tool | ~60 | `_mcp.py`, `models.py`, `output.py` |

### Modified Files (6)

| File | What Changes | Scope |
|------|-------------|-------|
| `_mcp.py` | Replace singleton clients with `InstanceRegistry`; add `get_registry()`; modify lifespan | ~40 lines changed, ~20 added |
| `tools.py` | Add `instance` param to 8 tools; add fan-out routing per tool | ~15 lines per tool × 8 tools = ~120 lines |
| `tools_status.py` | Add `instance` param to 4 tools | ~15 lines per tool × 4 tools = ~60 lines |
| `tools_alertmanager.py` | Add `instance` param to 4 tools | ~15 lines per tool × 4 tools = ~60 lines |
| `models.py` | Add `InstanceInfoItem`, `ListInstancesOutput` | ~15 lines added |
| `errors.py` | Add federation-specific error messages | ~15 lines added |

### Unchanged Files (5)

| File | Why Unchanged |
|------|--------------|
| `client.py` | Already fully parameterized. Federation creates multiple instances of it via constructor args. |
| `alertmanager_client.py` | Same — already parameterized. |
| `output.py` | `ok()` and `fail()` are generic. Work with any dict/exception. |
| `cache.py` | `TTLCache` class is already instantiable. Registry creates per-instance instances. |
| `server.py` | Just adds `import tools_federation` — 1 line, trivial. |

---

## Build Order (Dependency-Driven)

```
Phase 1: config.py ─────────────────────────────────────────────
  Dependencies: none (stdlib only)
  Unlocks: registry.py
  Tests: unit tests for JSON parsing, defaults, validation
  Checkpoint: config parsing works with sample JSON

Phase 2: models.py additions ───────────────────────────────────
  Dependencies: none
  Unlocks: tools_federation.py, tool modifications
  Tests: none (TypedDicts are type-only)
  Checkpoint: types importable

Phase 3: registry.py ───────────────────────────────────────────
  Dependencies: config.py, client.py, alertmanager_client.py, cache.py
  Unlocks: _mcp.py modification, federation.py
  Tests: unit tests for client creation, lookup, error on unknown instance
  Checkpoint: registry creates clients from config + legacy mode works

Phase 4: _mcp.py modification ─────────────────────────────────
  Dependencies: registry.py, config.py
  Unlocks: tool modifications (get_client(instance) now works)
  Tests: ALL EXISTING TESTS MUST PASS (backward compat checkpoint)
  Checkpoint: `pytest` green with no config file (legacy mode)
  CRITICAL: This is the backward-compatibility gate. If existing tests
  fail here, stop and fix before proceeding.

Phase 5: federation.py (fan-out + merge) ───────────────────────
  Dependencies: registry.py
  Unlocks: instance="all" support in tools
  Tests: unit tests for fan_out, merge functions, partial failure handling
  Checkpoint: fan-out works with mock clients

Phase 6: tools_federation.py ───────────────────────────────────
  Dependencies: _mcp.py (get_registry), models.py additions
  Independent of: tool modifications
  Tests: test federation_list_instances tool
  Checkpoint: new tool returns instance list

Phase 7: Existing tool modifications (add instance param) ─────
  Dependencies: _mcp.py modification, federation.py
  Can be parallelized:
    7a: tools.py (8 tools)
    7b: tools_status.py (4 tools)
    7c: tools_alertmanager.py (4 tools)
  Tests: each tool tested with instance=None (backward compat),
         instance="specific_name", instance="all"
  Checkpoint: all 16 tools support federation

Phase 8: server.py + integration tests ─────────────────────────
  Dependencies: all above
  Tests: end-to-end integration with config file
  Checkpoint: full test suite green
```

**Why this order:**

1. **config.py first** — zero dependencies, everything else needs it
2. **models.py early** — TypedDicts are additive, needed by tools but changing them breaks nothing
3. **registry.py before _mcp.py** — the registry must exist before _mcp.py can reference it
4. **_mcp.py is the critical hinge** — after this, `get_client()` routes through registry. **ALL EXISTING TESTS MUST PASS.** This is the backward-compatibility checkpoint. If anything breaks, the registry's legacy mode has a bug.
5. **federation.py after registry** — fan-out needs registry for client lists
6. **tools_federation.py is independent** — doesn't depend on tool modifications
7. **Tool modifications last** — they consume everything above; can be parallelized across modules
8. **Integration tests last** — verify the full system works end-to-end

---

## Patterns to Follow

### Pattern 1: Instance Resolution (every tool)

```python
def prometheus_some_tool(
    ...,  # existing params
    instance: Annotated[str | None, Field(
        default=None,
        description="Target instance name, 'all' for fan-out, empty for default."
    )] = None,
) -> SomeOutput:
    try:
        if instance == "all":
            registry = get_registry()
            results = fan_out_prometheus(registry, lambda c: c.get("/...", params=...))
            merged, errors = merge_some_results(results)
            # Build output from merged + errors
        else:
            client = get_client(instance)
            raw = client.get("/...", params=...)
            # Existing logic unchanged
    except Exception as exc:
        output.fail(exc, "...")
```

### Pattern 2: Merge Function Signature

```python
def merge_X_results(results: list[InstanceResult]) -> tuple[MERGED_TYPE, list[str]]:
    """Returns (merged_data, list_of_error_strings)."""
```

### Pattern 3: Backward-Compatible Parameter

The `instance` parameter is always:
- Last in the parameter list (after all existing params)
- `Annotated[str | None, Field(default=None, ...)]`
- With description: "empty = default, name = specific, 'all' = fan-out"

### Pattern 4: Per-Instance Cache Access

```python
# Before (legacy):
cache = get_metrics_cache()

# After (federation-aware):
registry = get_registry()
cache = registry.get_cache(instance)
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Modifying PrometheusClient to Be "Instance-Aware"
**What:** Adding instance routing logic inside `PrometheusClient` itself.
**Why bad:** `PrometheusClient` is a clean HTTP wrapper. It should not know about federation, registries, or instance names.
**Instead:** Keep `PrometheusClient` unchanged. Create multiple instances via constructor args.

### Anti-Pattern 2: Global Config Object Read by Tools
**What:** A module-level `_config` global that tools read directly.
**Why bad:** Hidden coupling, hard to test. Config should flow through the registry.
**Instead:** `load_config()` → `InstanceRegistry.__init__()` → registry owns the lifecycle.

### Anti-Pattern 3: Async Fan-Out
**What:** Using `asyncio.gather()` for concurrent queries.
**Why bad:** Tools are `def` (synchronous). Introducing `async def` tools breaks the existing model. `requests` is synchronous. The tool's worker thread is already off the event loop. Adding async would require converting tools to `async def` and using `httpx` or `aiohttp`.
**Instead:** `concurrent.futures.ThreadPoolExecutor` for fan-out within the synchronous tool. Threads within a thread — works perfectly, no model change.

### Anti-Pattern 4: Changing Existing Output Schemas
**What:** Adding new required fields to `QueryOutput`, `ListAlertsOutput`, etc.
**Why bad:** Breaks MCP clients that validate structured output against the published schema.
**Instead:** `__prometheus_instance__` label lives in the existing `labels: dict[str, str]` field. No schema change. Fan-out error reporting in markdown text.

### Anti-Pattern 5: Lazy Config Loading
**What:** Loading the JSON config on first tool call instead of at startup.
**Why bad:** First tool invocation becomes unpredictably slow. Config errors surface mid-investigation, not at startup. Thread-safety becomes complex (who loads first? what if two threads race?).
**Instead:** Load in lifespan (eager). Fail fast. Registry is ready before any tool runs.

### Anti-Pattern 6: Separate "Federated" Versions of Every Tool
**What:** Creating `prometheus_federated_query`, `prometheus_federated_query_range`, etc. as new tools alongside existing ones.
**Why bad:** Doubles the tool surface (32 tools instead of 16+1). Agent must learn which tool to use. The tool descriptions diverge and become hard to maintain.
**Instead:** Add `instance` parameter to existing tools. One tool, one purpose, optional federation. `instance="all"` triggers fan-out; otherwise, single-instance query.

---

## Scalability Considerations

| Concern | 2-3 instances | 10 instances | 50+ instances |
|---------|--------------|-------------|--------------|
| Fan-out latency | Bounded by slowest (parallel). <1s typical. | Pool cap (8) batches. 2 rounds. | 7+ rounds. Make pool size configurable. |
| Memory (merged) | Negligible — few KB | Existing caps (500 metrics, 5000 points) apply post-merge. Fine. | Per-instance pre-merge caps may be needed. |
| HTTP sessions | 2-6 sessions | 10-20 sessions | 50-100 sessions. Consider lazy client creation. |
| Config file | Trivial | ~1KB JSON | ~5KB JSON. Not a concern. |
| ThreadPool overhead | Minimal | 8 threads × 2 rounds | 8 threads × 7 rounds. Consider increasing pool. |

**Practical ceiling:** `_DEFAULT_MAX_WORKERS = 8` means at most 8 concurrent HTTP calls. Intentional — corporate Prometheus instances shouldn't be hit with 50 concurrent requests. For most deployments (2-5 instances), every instance is queried in a single parallel round.

---

## Test Strategy

### Backward Compatibility Tests (Critical)

After Phase 4 (_mcp.py modification), **all existing tests must pass unchanged** when `PROMETHEUS_MCP_CONFIG` is not set. This validates the registry's legacy mode.

### New Test Files

| Test File | Covers |
|-----------|--------|
| `test_config.py` | JSON parsing, defaults application, validation errors |
| `test_registry.py` | Instance lookup, legacy mode, unknown instance errors, close_all |
| `test_federation.py` | fan_out with mock clients, merge functions, partial failure |
| `test_tools_federation.py` | `federation_list_instances` tool |

### Test Fixtures (conftest.py changes)

The existing `reset_client_cache` fixture resets `_mcp._client` and `_mcp._am_client`. It needs to reset `_mcp._registry` instead:

```python
def _do_reset() -> None:
    """Reset the registry (closes all clients)."""
    import prometheus_mcp._mcp as _mcp
    if _mcp._registry is not None:
        _mcp._registry.close_all()
    _mcp._registry = None
    get_metrics_cache().clear()
```

---

## Sources

- **Existing codebase** (HIGH confidence): Direct analysis of all 14 files in `src/prometheus_mcp/` + `tests/conftest.py` + `pyproject.toml`
- **Python `concurrent.futures.ThreadPoolExecutor`** (HIGH confidence): stdlib since Python 3.2, well-documented
- **FastMCP threading model** (HIGH confidence): Confirmed via `_mcp.py` lifespan pattern + tool function signatures (all `def`, not `async def`) + docstring in `client.py` lines 12-16
- **Prometheus HTTP API v1** (HIGH confidence): All endpoints in existing tools verified against API docs
- **Alertmanager API v2** (HIGH confidence): Endpoints in `tools_alertmanager.py` verified against API docs
- **MCP protocol** (HIGH confidence): `CallToolResult` with `TextContent` + `structuredContent` pattern in `output.py`
- **`PrometheusClient` parameterization** (HIGH confidence): Constructor at `client.py:97-106` accepts all config via keyword args with env-var fallbacks — no modifications needed for multi-instance
