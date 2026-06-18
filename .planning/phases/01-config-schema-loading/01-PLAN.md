# Phase 1: Config Schema & Loading - Plan

**Planned:** 2026-06-16
**Status:** Ready for execution

## Goal

Implement JSON config file parsing for named Prometheus/Alertmanager instances with frozen dataclass validation (no Pydantic), defaults inheritance, schema versioning (version: 1), and fully backward-compatible single-instance mode when no config file is present.

New module: `src/prometheus_mcp/config.py` — loaded by lifespan at startup, consumed by registry (Phase 2) and _mcp.py (Phase 3).

## Success Criteria

1. New `config.py` module loads JSON config file specified by PROMETHEUS_MCP_CONFIG env var with frozen dataclass validation
2. Config schema has `version: 1` field; missing/unknown versions produce actionable error messages referencing config file path
3. `defaults` section in config provides shared settings (timeout, ssl_verify, max_response_bytes, cache_ttl) inherited by instances
4. When PROMETHEUS_MCP_CONFIG is unset, server operates in single-instance mode using existing env vars — zero behavioral change from v2.0
5. Config validation errors are actionable, referencing file path and instance name (not raw validation errors)

## Wave 1: Core Data Structures

### Task 1.1: Define Configuration Data Classes
- Create `InstanceConfig` frozen dataclass with all configuration fields for a single instance
- Create `FederationConfig` frozen dataclass to hold instances dict and defaults
- Add proper type hints and documentation strings
- Place in `src/prometheus_mcp/config.py`

### Task 1.2: Implement Config Loading Function
- Create `load_config(config_path: str) -> FederationConfig` function
- Handle file reading with proper encoding (`utf-8-sig` to handle BOM)
- Parse JSON with error handling for malformed files
- Validate schema version field
- Validate that at least one instance exists
- Validate that each instance has at least one URL (prometheus_url or alertmanager_url)

## Wave 2: Validation and Error Handling

### Task 2.1: Implement Config Validation
- Add validation for URL formats (basic validation)
- Validate numeric ranges for timeout, max_response_bytes, cache_ttl
- Validate boolean values for ssl_verify
- Validate authentication combinations (token vs username/password)

### Task 2.2: Implement Error Handling
- Create `ConfigError` class inheriting from `ValueError` (reuse existing)
- Wrap all parsing/validation errors with actionable messages
- Include config file path and instance name in error messages
- Handle file not found errors gracefully

## Wave 3: Defaults and Inheritance

### Task 3.1: Implement Defaults Application
- Apply defaults from `defaults` section to each instance
- Allow per-instance config to override defaults
- Handle type conversion for defaults (strings to appropriate types)

### Task 3.2: Implement Backward Compatibility Mode
- Detect when PROMETHEUS_MCP_CONFIG is not set
- Create legacy mode FederationConfig from existing environment variables
- Ensure identical behavior to v2.0 when no config file is present

## Wave 4: Integration and Testing

### Task 4.1: Integrate with Application Lifespan
- Modify app lifespan to load config at startup
- Store config in application state for access by other components
- Ensure config is loaded eagerly (fail fast on startup)

### Task 4.2: Add Unit Tests
- Test config loading with valid JSON files
- Test error handling with invalid files (malformed JSON, missing fields)
- Test defaults application and inheritance
- Test backward compatibility mode
- Target >80% coverage for config.py

### Task 4.3: Documentation Updates
- Update `.env.example` to document PROMETHEUS_MCP_CONFIG
- Update README to mention config file option
- Document config file format in comments/docstrings

## Dependencies

- None (foundation phase)

## Acceptance Tests

1. ✅ Config file loads correctly with valid structure
2. ✅ Config validation rejects missing version field
3. ✅ Config validation rejects unknown version numbers
4. ✅ Config validation rejects configs with zero instances
5. ✅ Config validation rejects instances with no URLs
6. ✅ Config with defaults applies values to instances
7. ✅ Config with per-instance overrides defaults appropriately
8. ✅ Missing config file enables legacy mode with env vars
9. ✅ Malformed JSON produces actionable error messages
10. ✅ Invalid field values produce actionable error messages