# Phase 2: Instance Registry & Client Management - Summary

**Completed:** 2026-06-16
**Status:** ✅ Complete

## What Was Built

Built thread-safe InstanceRegistry that creates and manages N PrometheusClient + AlertmanagerClient pairs with per-instance authentication, per-instance TTL caches, and proper session lifecycle. The registry is consumed by _mcp.py (Phase 3) and federation.py (Phase 4).

### Core Components

1. **Data Structures** (`src/prometheus_mcp/registry.py`):
   - `InstanceEntry`: Internal registry entry holding config, clients, and cache
   - `InstanceInfo`: Public instance metadata for discovery tool
   - `InstanceRegistry`: Thread-safe registry mapping names to client pairs

2. **Key Features**:
   - Thread-safe operations with reentrant locking
   - Lazy client creation in legacy mode for v2.0 compatibility
   - Per-instance authentication (Bearer/Basic per instance)
   - Per-instance TTL caches with configurable TTL
   - Proper session lifecycle management with close_all()
   - Backward compatibility: single "default" entry from env vars

### Implementation Details

- **Thread Safety**: All public methods acquire a reentrant lock before accessing shared state
- **Lazy Initialization**: Registry auto-initializes on first access, safe to call multiple times
- **Legacy Mode**: When no FederationConfig provided, creates single "default" entry that behaves identically to v2.0
- **Client Creation**: Each client gets its own requests.Session (never shared)
- **Per-Instance Overrides**: Config values override defaults for timeout, max_response_bytes, cache_ttl
- **Error Handling**: Actionable ConfigError messages with valid instance names

## Success Criteria Verification

✅ **1. InstanceRegistry creates per-instance PrometheusClient with independent auth (Bearer/Basic) from config**
- Clients created with per-instance authentication parameters from config

✅ **2. Each instance has its own requests.Session (never shared) and per-instance TTLCache**
- Every client gets its own session; every instance gets its own cache

✅ **3. Per-instance config overrides defaults for timeout, max_response_bytes, and cache_ttl**
- Full inheritance system with per-instance override support

✅ **4. Registry provides get_prometheus_client(name), get_alertmanager_client(name), list_instances(), all_prometheus_clients(), close_all()**
- Complete interface implemented with proper error handling

✅ **5. Legacy mode: when no config file, registry creates single "default" entry from env vars — identical to v2.0 behavior**
- Backward compatibility maintained with lazy client creation

## Test Coverage

Comprehensive test suite with 14 test cases covering:
- Legacy mode behavior (single default entry, env var reading, error handling)
- Federation mode (multi-instance configs, minimal configs, mixed types)
- Per-instance cache with correct TTL values
- InstanceInfo metadata for discovery tool
- Client enumeration methods (all_prometheus_clients, all_alertmanager_clients)
- Error handling (unknown instances, missing URLs, initialization safety)
- Session lifecycle management (close_all with exceptions)

**Coverage:** 100% of success criteria verified by tests

## Integration Points

- Consumed by `_mcp.py` (Phase 3) for client routing
- Consumed by `federation.py` (Phase 4) for fan-out queries
- Uses `config.py` data classes (InstanceConfig, FederationConfig)
- Uses existing client modules (client.py, alertmanager_client.py)
- Uses cache module (cache.py) for per-instance TTL caches
- Follows existing error handling patterns (ConfigError)

## Next Steps

Phase 2 complete. Ready for Phase 3: Core Wiring.