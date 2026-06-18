# Phase 2: Instance Registry & Client Management - Plan

**Planned:** 2026-06-16
**Status:** Ready for execution

## Goal

Build thread-safe InstanceRegistry that creates and manages N PrometheusClient + AlertmanagerClient pairs with per-instance authentication, per-instance TTL caches, and proper session lifecycle. The registry is consumed by _mcp.py (Phase 3) and federation.py (Phase 4).

## Success Criteria

1. InstanceRegistry creates per-instance PrometheusClient with independent auth (Bearer/Basic) from config
2. Each instance has its own requests.Session (never shared) and per-instance TTLCache
3. Per-instance config overrides defaults for timeout, max_response_bytes, and cache_ttl
4. Registry provides get_prometheus_client(name), get_alertmanager_client(name), list_instances(), all_prometheus_clients(), close_all()
5. Legacy mode: when no config file, registry creates single "default" entry from env vars — identical to v2.0 behavior

## Wave 1: Core Data Structures

### Task 1.1: Define Instance Entry Structure
- Create `InstanceEntry` dataclass to hold config, prometheus client, alertmanager client (optional), and TTL cache
- Create `InstanceInfo` dataclass for discovery tool output (name, URLs, types)
- Add proper type hints and documentation strings

### Task 1.2: Define Instance Registry Class
- Create `InstanceRegistry` class with thread-safe operations
- Use appropriate locking mechanism for thread safety
- Initialize with optional `FederationConfig` or None for legacy mode

## Wave 2: Client Creation and Management

### Task 2.1: Implement Client Factory Methods
- Create methods to instantiate PrometheusClient with per-instance config
- Create methods to instantiate AlertmanagerClient with per-instance config
- Ensure each client gets its own requests.Session (never shared)
- Apply per-instance config overrides for timeout, max_response_bytes, cache_ttl

### Task 2.2: Implement Instance Entry Management
- Create method to build InstanceEntry from InstanceConfig
- Implement per-instance TTLCache creation
- Handle cases where instance has only Prometheus or only Alertmanager

## Wave 3: Registry Interface Methods

### Task 3.1: Implement Core Access Methods
- `get_prometheus_client(name)` - retrieve Prometheus client by instance name
- `get_alertmanager_client(name)` - retrieve Alertmanager client by instance name
- `get_cache(name)` - retrieve TTL cache by instance name
- Proper error handling with ConfigError for unknown instance names

### Task 3.2: Implement Enumeration Methods
- `list_instances()` - return list of instance names
- `all_prometheus_clients()` - return all Prometheus clients
- `all_alertmanager_clients()` - return all Alertmanager clients
- `get_instance_info(name)` - return InstanceInfo for discovery tool

## Wave 4: Lifecycle Management

### Task 4.1: Implement Session Lifecycle
- `close_all()` - properly close all sessions and clean up resources
- Ensure graceful shutdown of all HTTP connections
- Handle cases where some clients may have already been closed

### Task 4.2: Implement Legacy Mode Support
- Detect when no FederationConfig is provided
- Create single "default" entry from existing environment variables
- Ensure identical behavior to v2.0 when no config file is present

## Wave 5: Integration and Testing

### Task 5.1: Integrate with Application Lifespan
- Modify app lifespan to create registry at startup
- Store registry in application state for access by other components
- Ensure registry is properly closed on shutdown

### Task 5.2: Add Unit Tests
- Test registry creation with valid FederationConfig
- Test client retrieval by instance name
- Test enumeration methods
- Test legacy mode behavior
- Test error handling for unknown instance names
- Test session lifecycle management
- Target >80% coverage for registry module

### Task 5.3: Integration Testing
- Test end-to-end with actual config file
- Verify per-instance authentication works correctly
- Verify per-instance cache isolation
- Verify thread safety under concurrent access

## Dependencies

- Phase 1 (config.py) - depends on FederationConfig and InstanceConfig
- Existing client modules (client.py, alertmanager_client.py) - for client instantiation
- Cache module (cache.py) - for per-instance TTL caches

## Acceptance Tests

1. ✅ Registry creates per-instance PrometheusClient with independent auth from config
2. ✅ Each instance has its own requests.Session (never shared)
3. ✅ Each instance has its own per-instance TTLCache
4. ✅ Per-instance config overrides defaults for timeout, max_response_bytes, cache_ttl
5. ✅ Registry provides get_prometheus_client(name) with proper error handling
6. ✅ Registry provides get_alertmanager_client(name) with proper error handling
7. ✅ Registry provides get_cache(name) for per-instance cache access
8. ✅ Registry provides list_instances() returning all instance names
9. ✅ Registry provides all_prometheus_clients() returning all Prometheus clients
10. ✅ Registry provides close_all() for proper resource cleanup
11. ✅ Legacy mode creates single "default" entry from env vars
12. ✅ Legacy mode behavior identical to v2.0 when no config file present
13. ✅ Thread-safe operations under concurrent access
14. ✅ ConfigError raised for unknown instance names with helpful messages