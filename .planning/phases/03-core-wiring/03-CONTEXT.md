# Phase 3: Core Wiring - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace singleton client pattern in _mcp.py with registry-based pattern. This is the backward-compatibility gate — ALL existing tests must pass after this change.

The registry is consumed from InstanceRegistry (Phase 2). Migration involves:
1. Modifying _mcp.py to use registry instead of _client/_am_client globals
2. Updating app_lifespan to load config at startup, create registry, close all sessions on shutdown
3. Updating all tool functions to route through registry with instance parameter support
4. Ensuring zero behavioral change when PROMETHEUS_MCP_CONFIG is not set

### Requirements Addressed
None (internal refactoring)

</domain>

<decisions>
## Implementation Decisions

### Core Wiring Approach
- Modify _mcp.py to store InstanceRegistry in app state instead of global clients
- Update get_client(instance?) and get_alertmanager_client(instance?) to route through registry
- Default instance parameter to None (backwards compatible) → maps to "default" in registry
- When instance="all", return special marker for fan-out coordination (Phase 4)

### App Lifespan Changes
- Eager config loading at startup (fail fast on malformed config)
- Registry creation from config (None for legacy mode)
- Registry storage in app state for tool access
- Proper session cleanup on shutdown via registry.close_all()

### Tool Function Migration
- All 16 existing tools get optional `instance: str | None = None` parameter
- Tools call get_client(instance) instead of get_client()
- get_client(None) routes to "default" instance (maintains backward compatibility)
- Zero code changes required in tool bodies beyond client acquisition

### OpenCode's Discretion
- Exact parameter naming and placement in tool functions
- Error message wording for unknown instances
- Registry initialization timing and error handling
- App state key naming conventions

</decisions>

<code_context>
## Existing Code Insights

### Current Singleton Pattern
- `_mcp.py:get_client()` and `get_alertmanager_client()` return cached global clients
- Tools call these functions directly: `client = get_client()`
- App lifespan closes global clients manually on shutdown

### Tool Function Signatures
- 8 Prometheus tools in tools.py
- 4 status tools in tools_status.py  
- 4 Alertmanager tools in tools_alertmanager.py
- All use `get_client()` or `get_alertmanager_client()` directly

### Integration Points
- InstanceRegistry provides get_prometheus_client(name), get_alertmanager_client(name)
- FederationConfig loaded via config.load_config(path) when PROMETHEUS_MCP_CONFIG set
- Legacy mode: when no config, registry creates single "default" entry from env vars

</code_context>

<specifics>
## Specific Ideas

### Parameter Naming Convention
```python
def prometheus_query(
    query: str,
    *,
    instance: Annotated[str | None, Field(description="Target instance name (omit for default)")] = None,
) -> QueryOutput:
```

### Client Acquisition Pattern
```python
# In _mcp.py
def get_client(instance: str | None = None) -> PrometheusClient:
    registry = mcp.state["registry"]
    if instance is None:
        return registry.get_prometheus_client("default")
    elif instance == "all":
        # Special marker for fan-out (Phase 4)
        return registry.all_prometheus_clients()  # Or return special sentinel
    else:
        return registry.get_prometheus_client(instance)
```

### App Lifespan Flow
1. Check PROMETHEUS_MCP_CONFIG env var
2. If set: load_config() → create registry with config
3. If unset: create registry with None (legacy mode)
4. Store registry in mcp.state
5. On shutdown: registry.close_all()

### Error Handling
- ConfigError during startup for malformed config files
- ConfigError during tool execution for unknown instance names
- Preserve existing error messages when instance=None (backward compatibility)

</specifics>

<deferred>
## Deferred Ideas

- Instance parameter validation at tool registration time (post-v3.0)
- Dynamic tool registration based on config instances (post-v3.0)
- Instance-aware tool grouping in MCP protocol (post-v3.0)

</deferred>