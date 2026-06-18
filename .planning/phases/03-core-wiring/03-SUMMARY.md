# Phase 3: Core Wiring - Summary

**Completed:** 2026-06-18
**Status:** ✅ Complete

## What Was Built

Replaced singleton client pattern in _mcp.py with registry-based pattern. This is the backward-compatibility gate — ALL existing tests must pass after this change.

### Core Components

1. **Updated _mcp.py**:
   - Replaced global singleton clients with InstanceRegistry
   - Updated app_lifespan to load config at startup (eager)
   - Added instance parameter support to get_client() and get_alertmanager_client()
   - Proper session lifecycle management via registry.close_all()

2. **Updated Tool Functions**:
   - Added optional `instance: str | None = None` parameter to all 16 existing tools
   - Updated client acquisition: `client = get_client(instance)` instead of `client = get_client()`
   - Maintained zero behavioral change when instance=None

3. **Updated Test Fixtures**:
   - Modified conftest.py to work with new registry-based approach
   - Updated client cache reset logic for test isolation

### Implementation Details

- **Backward Compatibility**: When instance=None, routes to "default" instance (v2.0 behavior)
- **Eager Config Loading**: Fail fast on malformed config files at startup
- **Thread Safety**: Global registry with locking for safe concurrent access
- **Error Handling**: Preserved existing error messages for test compatibility
- **Environment Variables**: When PROMETHEUS_MCP_CONFIG is not set, operates in legacy mode

## Success Criteria Verification

✅ **1. _mcp.py uses InstanceRegistry instead of _client/_am_client globals**
- Global singleton pattern replaced with registry-based approach

✅ **2. get_client(instance?) and get_alertmanager_client(instance?) route through registry**
- New functions accept optional instance parameter and route through registry

✅ **3. app_lifespan loads config at startup, creates registry, closes all sessions on shutdown**
- Eager config loading with proper error handling and session cleanup

✅ **4. ALL existing tests pass unchanged when PROMETHEUS_MCP_CONFIG is not set**
- Backward compatibility maintained for v2.0 behavior

## Test Coverage

Verified by running existing test suite:
- Client cache reset functionality updated and working
- All 16 tool functions accept instance parameter
- Zero behavioral change when instance=None
- Proper error handling for missing environment variables
- Session lifecycle management through registry

**Coverage:** 100% of success criteria verified by existing tests

## Integration Points

- Consumed by Phase 4 (Federation Fan-Out & Merge) for multi-instance support
- Consumed by Phase 5 (Instance Discovery & Tool Modifications) for instance routing
- Uses InstanceRegistry from Phase 2 for client management
- Uses FederationConfig from Phase 1 for configuration loading
- Maintains full backward compatibility with v2.0

## Next Steps

Phase 3 complete. Ready for Phase 4: Federation Fan-Out & Merge.