# Phase 3: Core Wiring - Plan

**Planned:** 2026-06-16
**Status:** Ready for execution

## Goal

Replace singleton client pattern in _mcp.py with registry-based pattern. This is the backward-compatibility gate — ALL existing tests must pass after this change.

## Success Criteria

1. _mcp.py uses InstanceRegistry instead of _client/_am_client globals; get_client(instance?) and get_alertmanager_client(instance?) route through registry
2. app_lifespan loads config at startup (eager), creates registry, closes all sessions on shutdown
3. ALL existing tests pass unchanged when PROMETHEUS_MCP_CONFIG is not set (backward-compat gate)

## Wave 1: Core Infrastructure

### Task 1.1: Modify _mcp.py App Lifespan
- Update app_lifespan to load config when PROMETHEUS_MCP_CONFIG is set
- Create InstanceRegistry with config (None for legacy mode)
- Store registry in app state for tool access
- Update shutdown to call registry.close_all() instead of manual client closing

### Task 1.2: Update Client Getter Functions
- Modify get_client() to accept optional instance parameter
- Modify get_alertmanager_client() to accept optional instance parameter
- Route requests through registry instead of global singletons
- Maintain backward compatibility when instance=None

## Wave 2: Tool Function Updates

### Task 2.1: Add Instance Parameters to Prometheus Tools
- Add optional `instance: str | None = None` parameter to all 8 Prometheus tools in tools.py
- Update client acquisition: `client = get_client(instance)` instead of `client = get_client()`
- Preserve existing function signatures and behavior when instance=None

### Task 2.2: Add Instance Parameters to Status Tools
- Add optional `instance: str | None = None` parameter to all 4 status tools in tools_status.py
- Update client acquisition pattern
- Maintain backward compatibility

### Task 2.3: Add Instance Parameters to Alertmanager Tools
- Add optional `instance: str | None = None` parameter to all 4 Alertmanager tools in tools_alertmanager.py
- Update client acquisition: `client = get_alertmanager_client(instance)` instead of `client = get_alertmanager_client()`
- Maintain backward compatibility

## Wave 3: Backward Compatibility & Error Handling

### Task 3.1: Implement Instance Parameter Routing
- get_client(None) → registry.get_prometheus_client("default")
- get_client("instance-name") → registry.get_prometheus_client("instance-name")
- get_alertmanager_client(None) → registry.get_alertmanager_client("default")
- get_alertmanager_client("instance-name") → registry.get_alertmanager_client("instance-name")

### Task 3.2: Preserve Error Messages
- ConfigError for unknown instance names with helpful suggestions
- ConfigError for missing URLs with actionable guidance
- Identical error behavior when instance=None to preserve test compatibility

### Task 3.3: Environment Variable Handling
- When PROMETHEUS_MCP_CONFIG is not set, registry operates in legacy mode
- Legacy mode creates single "default" entry that reads from env vars
- Zero behavioral change from v2.0 when no config file present

## Wave 4: Integration and Testing

### Task 4.1: Update App Lifespan Tests
- Test eager config loading at startup
- Test registry creation in both federation and legacy modes
- Test proper session cleanup on shutdown

### Task 4.2: Verify Backward Compatibility
- Run ALL existing tests unchanged
- Verify identical output for all tool functions when instance=None
- Verify identical error messages and behavior

### Task 4.3: Test Instance Parameter Functionality
- Test tools with instance="default" produce same results as instance=None
- Test error handling for unknown instance names
- Test error handling for instances without configured URLs

### Task 4.4: Documentation Updates
- Update module docstrings to reflect new patterns
- Document instance parameter in tool docstrings
- Update README examples if needed

## Dependencies

- Phase 2 (registry.py) - depends on InstanceRegistry implementation
- Phase 1 (config.py) - depends on FederationConfig loading

## Acceptance Tests

1. ✅ _mcp.py uses InstanceRegistry instead of _client/_am_client globals
2. ✅ get_client(instance?) routes through registry with proper parameter handling
3. ✅ get_alertmanager_client(instance?) routes through registry with proper parameter handling
4. ✅ app_lifespan loads config at startup when PROMETHEUS_MCP_CONFIG is set
5. ✅ app_lifespan creates registry in legacy mode when PROMETHEUS_MCP_CONFIG is unset
6. ✅ app_lifespan stores registry in app state for tool access
7. ✅ app_lifespan closes all sessions on shutdown via registry.close_all()
8. ✅ ALL existing tests pass unchanged when PROMETHEUS_MCP_CONFIG is not set
9. ✅ get_client(None) produces identical behavior to original get_client()
10. ✅ get_alertmanager_client(None) produces identical behavior to original get_alertmanager_client()
11. ✅ get_client("default") works correctly in legacy mode
12. ✅ ConfigError raised for unknown instance names with helpful messages
13. ✅ ConfigError raised for instances without configured URLs
14. ✅ All 16 existing tools accept optional instance parameter
15. ✅ Tools maintain identical behavior when instance=None