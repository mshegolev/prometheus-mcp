# Feature Landscape: Federation (Multi-Instance Prometheus/Alertmanager)

**Domain:** MCP server federation — multi-instance Prometheus & Alertmanager query proxy
**Researched:** 2026-06-08
**Confidence:** HIGH (based on codebase analysis + Prometheus official docs + Thanos/Grafana ecosystem patterns)

## Table Stakes

Features users expect when a tool claims "multi-instance support." Missing = federation feels broken or unusable.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|-------------|------------|------------|-------|
| **JSON config file for named instances** | Users must be able to declare multiple Prometheus/Alertmanager endpoints with names and per-instance auth | Low | Nothing (foundation) | Convention in ecosystem: named objects with `url`, `token`, `username`, `password`, `ssl_verify`. Grafana datasources, Thanos file-SD endpoints, and promtool all use named JSON/YAML config. File path via `PROMETHEUS_CONFIG_FILE` env var. JSON over YAML because stdlib `json` avoids new deps. |
| **Backward-compatible single-instance mode** | Existing users (env-var config) must not break when upgrading to v3.0 | Low | Config file feature | If no config file is provided, fall back to existing env-var behavior exactly as today. Zero migration cost for existing users. This is an explicit project constraint. |
| **Instance listing tool** | AI agents need to discover which instances are available before targeting queries | Low | Config loading | New tool `prometheus_list_instances` returning `[{name, url, type}]`. Agent calls this first in any multi-instance investigation. Analogous to Grafana's datasource list API or Thanos's `/stores` endpoint. |
| **Targeted instance parameter on existing tools** | Agents must be able to query a specific cluster's Prometheus/Alertmanager | Med | Config loading, client registry | Add optional `instance: str | None` parameter to all 16 existing tools. `None` = use default instance (first configured, or env-var singleton). Must not break existing tool signatures — new param is optional with default `None`. |
| **Per-instance authentication** | Different Prometheus instances typically have different auth credentials (separate teams, separate clusters, separate security domains) | Med | Config loading | Each instance config entry supports `token`, `username`/`password`, `ssl_verify` independently. Bearer > Basic > none priority per instance, same as current single-instance pattern. |
| **Per-instance client caching** | Each named instance needs its own HTTP session, connection pool, and metric name cache | Med | Client registry, cache module | Registry pattern: `Dict[str, PrometheusClient]`, lazy-init, thread-safe. Each client has its own `requests.Session` and `TTLCache` keyed by instance name. Current singleton `_client` becomes the "default" entry. |
| **Alertmanager multi-instance** | Organizations with multiple clusters typically have separate Alertmanager per cluster | Med | Config loading, AM client registry | Named Alertmanager instances in same config file. All 4 AM tools get `instance` parameter. Alertmanager HA clusters should be pointed at a single URL (not load-balanced, per official docs). |
| **Config file validation with actionable errors** | Agents and operators need clear error messages when config is malformed | Low | Config loading | Pydantic model for config schema. Validation at startup with errors like "Instance 'prod' is missing required field 'url'" — same LLM-readable error style as existing `errors.py`. |

## Differentiators

Features that set this MCP server apart from "just querying one Prometheus at a time." Not expected, but highly valued by SRE/DevOps teams managing multiple clusters.

| Feature | Value Proposition | Complexity | Depends On | Notes |
|---------|------------------|------------|------------|-------|
| **Fan-out queries across all instances** | AI agent asks "what's the CPU across ALL clusters?" and gets unified results with instance labels injected | High | Client registry, result merging | Query all Prometheus instances in parallel (ThreadPoolExecutor), inject `__prometheus_instance__: "<name>"` label into each result's labels, merge into single response. This is the killer feature — mirrors what Thanos Query does with its StoreAPI fan-out but at the MCP tool level. |
| **Subset fan-out (query specific instances)** | Agent queries a subset: `instances=["prod-us", "prod-eu"]` for regional comparison | Med | Fan-out infrastructure | `instances: list[str] | None` parameter on fan-out tools. `None` = all instances. Validates names against config. More targeted than "all" — avoids slow/irrelevant instances. |
| **Partial response handling** | If 3/5 instances respond but 2 timeout, return results from the 3 that succeeded + warnings | Med | Fan-out infrastructure | Follow Thanos pattern: return available data with `warnings` field listing failed instances. Agent sees "got data from prod-us, prod-eu, prod-asia; failed: staging-1 (timeout), staging-2 (connection refused)". Never fail the entire query because one instance is down. |
| **Per-instance health in listing** | `prometheus_list_instances` returns connectivity/health status for each instance | Med | Instance listing, health check | Parallel health probe (`/-/healthy`) for all configured instances. Shows which instances are reachable before agent starts querying. Prevents wasted round-trips to dead instances. |
| **Per-instance timeout/limits override** | Different instances may need different timeouts (local = 5s, remote WAN = 60s) | Low | Config loading | Optional `timeout`, `max_response_bytes`, `cache_ttl` in per-instance config, falling back to global defaults. Small config enhancement, big operational value for mixed environments. |
| **Instance name injection as external label** | When fan-out results are merged, the instance name is added as a synthetic label so agents can distinguish sources | Low | Fan-out infrastructure | Use synthetic label `__prometheus_instance__` (double-underscore convention from Prometheus relabeling). Must not collide with existing labels. Injected post-query into the result data, not into the PromQL expression itself. |

## Anti-Features

Features to explicitly NOT build. Each has been considered and rejected for specific reasons.

| Anti-Feature | Why Avoid | What to Do Instead |
|-------------|-----------|-------------------|
| **Cross-instance PromQL evaluation** | PromQL is evaluated server-side by each Prometheus instance. We cannot merge raw time series from different instances and re-evaluate PromQL across them — that requires a full PromQL engine (Thanos/Cortex territory). | Fan-out the same PromQL expression to each instance independently, then merge the labeled results. Agent-side comparison via `__prometheus_instance__` label. |
| **Automatic instance discovery (DNS/SD/Kubernetes)** | Service discovery adds operational complexity (DNS SRV, Kubernetes API, Consul, file_sd_configs). Config file is simpler and fits MCP's static-config philosophy (env vars + config files). | Named instances in JSON config file. Static, explicit, auditable. Users who need dynamic discovery can generate the JSON from their service discovery tooling. |
| **Write operations (silence creation, rule management)** | Read-only constraint is a core architectural decision. Write operations across multiple instances add complexity and risk (partial writes, no rollback, safety hazard of AI agents creating silences). | Continue read-only pattern. Existing tools return info agents need; write operations should be done via Alertmanager UI or curl commands suggested by the agent. |
| **YAML config file format** | Adding PyYAML as a dependency violates "minimal new deps" constraint. JSON is parsed by stdlib `json` module with zero new dependencies. | Use JSON config file. Provide a well-documented `.example` file. JSON works for structured config; Prometheus ecosystem tools use both JSON and YAML, but JSON is more common for MCP server configs (`server.json` already exists in this project). |
| **Deduplication of HA replica results** | Thanos implements complex deduplication for HA Prometheus pairs using replica labels, penalty algorithms, and gap-filling. This is a deep rabbit hole of algorithmic complexity. | If users have Thanos, they should point the MCP server at Thanos Query (which deduplicates natively). For direct multi-Prometheus without Thanos, return all results with instance labels and let the agent reason about overlap. |
| **Dynamic instance addition at runtime** | Hot-reloading config adds complexity for minimal benefit in an MCP stdio server (short-lived process, started per-session). | Restart the MCP server to pick up config changes. Config file is loaded once at startup during lifespan init. |
| **Aggregation/reduction of fan-out results** | Aggregating (sum, avg) across instances in the MCP server would require PromQL-like computation logic. | Return raw results with instance labels. The AI agent can reason about cross-instance patterns from labeled results. If server-side aggregation is needed, suggest Thanos/Cortex. |
| **Config file encryption/vault integration** | Encrypting tokens in the config file adds crypto dependencies and secret management complexity. | Document that config file should have restricted file permissions (0600). Tokens in config files follow the same security model as tokens in environment variables. |
| **Full Prometheus federation endpoint (`/federate`)** | The `/federate` endpoint returns exposition format (not JSON) and is designed for Prometheus-to-Prometheus scraping, not for API clients. Parsing exposition format adds complexity for no MCP benefit. | Use standard `/api/v1/query` on each instance via fan-out. Each Prometheus instance's query API is the right interface for MCP tools. |

## Feature Dependencies

```
                     JSON Config File Loading
                    /           |              \
                   v            v               v
        Config Validation    Backward Compat    Per-Instance Auth
        (Pydantic model)     (env-var fallback)  (per-client creds)
                   \            |              /
                    v           v             v
                  Client Registry (Dict[name -> Client])
                  (PrometheusClient + AlertmanagerClient)
                    /           |              \
                   v            v               v
        Instance Listing   Targeted Queries   Per-Instance Cache
              Tool         (instance param     (TTLCache per
                            on 16 tools)       instance)
                                |
                                v
                         Fan-Out Queries
                        /       |        \
                       v        v         v
               Parallel     Instance    Partial
               Execution    Label       Response
               (ThreadPool) Injection   Handling
                                |
                                v
                         Subset Fan-Out
                         (instances param)
```

### Dependency Chain (build order):

1. **Config file loading + Pydantic validation** — foundation, everything depends on this
2. **Client registry** — maps instance names to `PrometheusClient`/`AlertmanagerClient` objects with lazy init
3. **Instance listing tool + targeted queries** — can be built in parallel once registry exists
4. **Fan-out infrastructure** — requires client registry and parallel execution
5. **Partial response + subset selection** — enhancements layered on top of fan-out

## MVP Recommendation

### Phase 1: Foundation (must-have for any federation)
1. **JSON config file loading** with Pydantic validation
2. **Backward-compatible single-instance mode** — env-var fallback when no config file
3. **Client registry** — `Dict[str, PrometheusClient]` with thread-safe lazy init
4. **Per-instance authentication** — each client gets its own session/auth

### Phase 2: Agent Discovery + Targeted Queries
5. **`prometheus_list_instances` tool** — agent discovers what's available
6. **Optional `instance` parameter on all 16 existing tools** — targeted queries to specific instances
7. **Alertmanager multi-instance** (same registry pattern for `AlertmanagerClient`)

### Phase 3: Fan-Out (killer differentiator)
8. **Fan-out query tools** — parallel execution across instances with ThreadPoolExecutor
9. **Instance label injection** (`__prometheus_instance__` on every sample)
10. **Partial response handling** — return available data + warnings for failed instances
11. **Subset fan-out** (`instances` parameter for targeting specific subsets)

### Defer to post-v3.0:
- Per-instance health probes in listing (adds latency to listing tool; agents can use `prometheus_health_check` with `instance` param instead)
- Per-instance timeout/limits override (small config enhancement, not blocking)

## Detailed Feature Specifications

### Config File Format

The config file is specified via `PROMETHEUS_CONFIG_FILE` env var. If not set, existing env-var behavior applies unchanged (backward compat).

```json
{
  "instances": {
    "prod-us": {
      "type": "prometheus",
      "url": "https://prometheus.us.example.com",
      "token": "Bearer-token-here",
      "ssl_verify": true,
      "timeout": 30,
      "max_response_bytes": 10485760,
      "cache_ttl": 300
    },
    "prod-eu": {
      "type": "prometheus",
      "url": "https://prometheus.eu.example.com",
      "username": "admin",
      "password": "secret",
      "ssl_verify": false
    },
    "alertmanager-global": {
      "type": "alertmanager",
      "url": "https://alertmanager.example.com",
      "token": "am-token"
    }
  },
  "defaults": {
    "timeout": 30,
    "max_response_bytes": 10485760,
    "cache_ttl": 300,
    "ssl_verify": true
  }
}
```

**Design rationale:**
- `instances` is a **dict** (not array) so names are unique keys and lookups are O(1)
- `type` field (`"prometheus"` or `"alertmanager"`) distinguishes instance kind
- `defaults` section reduces repetition for shared settings across instances
- Per-instance fields override `defaults`, which override hardcoded defaults
- No YAML — stdlib `json` only, zero new dependencies
- JSON matches existing `server.json` convention in this project
- The first Prometheus-type instance is the "default" instance when `instance` param is omitted

### Instance Listing Tool Output

```python
class InstanceInfo(TypedDict):
    name: str           # "prod-us"
    type: str           # "prometheus" | "alertmanager"
    url: str            # base URL (no secrets exposed in output)

class ListInstancesOutput(TypedDict):
    total_count: int
    prometheus_count: int
    alertmanager_count: int
    instances: list[InstanceInfo]
```

Agent workflow: call `prometheus_list_instances` → see "prod-us, prod-eu, staging" → call `prometheus_query(query="up", instance="prod-us")`.

### Targeted Query Parameter

All 16 existing tools gain one optional parameter:

```python
instance: Annotated[
    str | None,
    Field(
        default=None,
        max_length=100,
        description=(
            "Target a specific named Prometheus instance from the config file. "
            "Use prometheus_list_instances to discover available instances. "
            "Leave empty to use the default instance."
        ),
    ),
] = None
```

When `instance` is provided:
- Look up the named client from the registry
- Execute the tool against that specific instance
- Return results exactly as today (no label injection, no schema change)
- Raise `ToolError` if instance name not found

When `instance` is `None`:
- Use the default instance (first Prometheus-type in config, or env-var singleton)
- Single-instance behavior, backward compatible

### Fan-Out Query Output Schema

Fan-out is implemented as **new tools** (not modifications to existing), because fan-out changes the output schema. This follows the project's "add new tools, not modify existing" key decision.

```python
class FanOutQueryOutput(TypedDict):
    query: str
    time: str | None
    instances_queried: list[str]     # ["prod-us", "prod-eu", "prod-asia"]
    instances_failed: list[str]      # ["staging-1"]
    warnings: list[str]              # ["staging-1: connection timeout after 30s"]
    result_type: str
    result_count: int
    data: list[InstantSample]        # merged, each sample has __prometheus_instance__ label
```

New fan-out tools:
- `prometheus_federated_query` — fan-out instant query across instances
- `prometheus_federated_query_range` — fan-out range query across instances

### Result Merging Strategy

When fan-out queries return results from multiple instances:

1. **Label injection:** Add `__prometheus_instance__: "<instance_name>"` to every sample's label set before merging
2. **Concatenation:** Concatenate results from all successful instances (no dedup, no aggregation)
3. **Ordering:** Results grouped by instance name, then by existing label order within each instance
4. **Truncation:** Global caps still apply (500 metrics, 5000 range points) across the merged result set
5. **Partial failure:** If some instances fail, return results from successful ones + `warnings` list describing failures. Never fail the entire query because one instance is down — this matches Thanos's partial-response design.

### Parallel Execution Model

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _fan_out_query(query: str, instances: list[str] | None = None) -> FanOutQueryOutput:
    registry = get_client_registry()
    targets = instances or registry.prometheus_names()
    
    results = []
    failed = []
    warnings = []
    
    with ThreadPoolExecutor(max_workers=min(len(targets), 10)) as pool:
        futures = {
            pool.submit(registry.get_prometheus(name).get, "/query", {"query": query}): name
            for name in targets
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                # Inject instance label into each sample
                results.extend(_inject_instance_label(data, name))
            except Exception as exc:
                failed.append(name)
                warnings.append(f"{name}: {errors.handle(exc, f'querying {name}')}")
    
    return {
        "instances_queried": [n for n in targets if n not in failed],
        "instances_failed": failed,
        "warnings": warnings,
        ...
    }
```

Key design choices:
- **ThreadPoolExecutor** (not asyncio) — matches existing synchronous tool model. FastMCP already runs sync tools in worker threads.
- **`as_completed`** — return results as they arrive, don't wait for slowest instance
- **Max 10 workers** — cap concurrent HTTP connections to avoid overwhelming the system
- **Per-instance error isolation** — each instance failure is caught independently

### Config Loading Architecture

```python
# In _mcp.py or new config.py module:

class InstanceConfig(BaseModel):
    type: Literal["prometheus", "alertmanager"]
    url: str
    token: str | None = None
    username: str | None = None
    password: str | None = None
    ssl_verify: bool = True
    timeout: float = 30.0
    max_response_bytes: int = 10_485_760
    cache_ttl: float = 300.0

class FederationConfig(BaseModel):
    instances: dict[str, InstanceConfig]
    defaults: InstanceConfig | None = None

class ClientRegistry:
    """Thread-safe registry of named Prometheus/Alertmanager clients."""
    
    def __init__(self, config: FederationConfig):
        self._config = config
        self._prometheus_clients: dict[str, PrometheusClient] = {}
        self._alertmanager_clients: dict[str, AlertmanagerClient] = {}
        self._lock = threading.Lock()
    
    def get_prometheus(self, name: str) -> PrometheusClient:
        """Lazy-init and return a PrometheusClient for the named instance."""
        ...
    
    def get_alertmanager(self, name: str) -> AlertmanagerClient:
        """Lazy-init and return an AlertmanagerClient for the named instance."""
        ...
    
    def prometheus_names(self) -> list[str]:
        """Return all configured Prometheus instance names."""
        ...
    
    def alertmanager_names(self) -> list[str]:
        """Return all configured Alertmanager instance names."""
        ...
    
    def default_prometheus(self) -> PrometheusClient:
        """Return the first Prometheus client (default for instance=None)."""
        ...
    
    def close_all(self) -> None:
        """Close all HTTP sessions (called from lifespan shutdown)."""
        ...
```

### Backward Compatibility Strategy

The `get_client()` function in `_mcp.py` must continue to work for single-instance mode:

```python
def get_client(instance: str | None = None) -> PrometheusClient:
    """Return a PrometheusClient.
    
    If federation config exists: return named or default instance.
    If no config file: return env-var singleton (existing behavior).
    """
    registry = _get_registry()  # may be None if no config file
    if registry is not None:
        if instance:
            return registry.get_prometheus(instance)
        return registry.default_prometheus()
    # Legacy single-instance mode
    return _get_singleton_client()
```

This means:
- All existing tools that call `get_client()` continue to work unchanged
- Tools that add `instance` parameter call `get_client(instance=instance)`
- Zero breaking changes for users who don't use a config file

## Sources

- Prometheus Federation docs: https://prometheus.io/docs/prometheus/latest/federation/ (HIGH confidence — official docs, verified 2026-06-08)
- Prometheus HTTP API v1: https://prometheus.io/docs/prometheus/latest/querying/api/ (HIGH confidence — official docs)
- Alertmanager HA docs: https://prometheus.io/docs/alerting/latest/high_availability/ (HIGH confidence — official docs)
- Thanos Querier design: https://thanos.io/tip/components/query.md/ (HIGH confidence — authoritative for fan-out/partial-response patterns)
- Thanos file-SD config format: https://thanos.io/tip/components/query.md/#file-sd (HIGH confidence — shows JSON endpoint config with per-endpoint TLS)
- Existing prometheus-mcp codebase: v0.2.0, 12 Python modules, 16 tools, ~2500 LoC (HIGH confidence — direct analysis)
- Grafana multi-datasource provisioning: named datasource objects with per-datasource auth (MEDIUM confidence — training data, pattern verified against Thanos)
