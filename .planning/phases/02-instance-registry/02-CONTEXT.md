# Phase 2: Instance Registry & Client Management - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning
**Mode:** Infrastructure phase — discuss skipped

<domain>
## Phase Boundary

Build thread-safe InstanceRegistry that creates and manages N PrometheusClient + AlertmanagerClient pairs with per-instance authentication, per-instance TTL caches, and proper session lifecycle. The registry is consumed by _mcp.py (Phase 3) and federation.py (Phase 4).

### Requirements Addressed
- **CFG-03**: Per-instance authentication (Bearer/Basic per instance)
- **CFG-05**: Per-instance config overrides defaults for timeout, max_response_bytes, cache_ttl
- **INST-01**: Thread-safe client registry mapping instance names to client pairs
- **INST-03**: Per-instance metric name TTL cache, isolated from other instances

</domain>

<decisions>
## Implementation Decisions

### OpenCode's Discretion
All implementation choices are at OpenCode's discretion — pure infrastructure phase. Follow ARCHITECTURE.md design:
- InstanceRegistry class with InstanceEntry dataclass holding config, prometheus client, alertmanager client (optional), TTL cache
- Each client gets its own requests.Session (never shared — Pitfall 4)
- Legacy mode: single "default" entry from env vars when no config
- get_prometheus_client(name), get_alertmanager_client(name), get_cache(name), list_instances(), all_prometheus_clients(), all_alertmanager_clients(), close_all()
- InstanceInfo dataclass for discovery tool output
- ConfigError on unknown instance name with list of valid names

</decisions>

<code_context>
## Existing Code Insights

- `client.py:PrometheusClient` already parameterized — accepts url, token, username, password, ssl_verify, timeout, max_response_bytes via kwargs
- `alertmanager_client.py:AlertmanagerClient` same pattern
- `cache.py:TTLCache` is instantiable per-instance (not a singleton class)
- `config.py:InstanceConfig` and `FederationConfig` just created in Phase 1
- `errors.py:ConfigError` for error handling

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Follow ARCHITECTURE.md registry design.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
