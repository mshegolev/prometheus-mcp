# Phase 7: v3.0 Test & Release Prep - Plan

**Planned:** 2026-06-18
**Status:** Ready for execution

## Goal

End-to-end integration tests covering full federation workflow, version bump, CHANGELOG update, and release documentation.

## Success Criteria

1. Integration test: config file with 2+ instances, fan-out query, partial failure, verify merged results with instance labels
2. Protocol test updated: federation_list_instances in EXPECTED_TOOLS, schema validation passes
3. All new modules (config, registry, federation, tools_federation) have unit tests with >80% coverage
4. Version bumped to 0.3.0 in pyproject.toml, __init__.py; CHANGELOG updated with v3.0 features; .env.example documents PROMETHEUS_MCP_CONFIG

## Wave 1: Integration Testing

### Task 1.1: Create Multi-Instance Integration Test
- Create test config file with 2+ Prometheus instances and 1+ Alertmanager instances
- Implement fan-out query test across mixed instance types
- Simulate partial failure with one unhealthy instance
- Verify merged results include __prometheus_instance__ and __alertmanager_instance__ labels
- Validate error reporting for failed instances

### Task 1.2: Implement Health Probe Validation
- Test federation_list_instances with mixed reachable/unreachable instances
- Verify health probe shows correct reachability status for each instance
- Validate response time measurements and error details
- Test federation mode detection with multiple instances

### Task 1.3: Test Backward Compatibility
- Verify legacy mode (no PROMETHEUS_MCP_CONFIG) maintains v2.0 behavior
- Test mixed usage: some tools with instance parameter, others without
- Validate error handling for unknown instance names
- Confirm zero behavioral change for existing tool usage

## Wave 2: Protocol Testing

### Task 2.1: Update EXPECTED_TOOLS List
- Add federation_list_instances to protocol test EXPECTED_TOOLS
- Update tool signature validation to include new instance parameters
- Verify all 21 tools (16 Prometheus + 4 Alertmanager + 1 federation) are registered
- Test structured output annotations for all new tools

### Task 2.2: Validate Schema Compliance
- Run schema validation on all tool signatures with new parameters
- Verify parameter descriptions and types match expectations
- Test annotation consistency across all tools
- Confirm backward compatibility with v2.0 tool schemas

### Task 2.3: Test Tool Discovery
- Verify federation_list_instances appears in tool discovery
- Test tool filtering by instance parameter support
- Validate health status reporting in discovery results
- Confirm federation mode flag detection

## Wave 3: Unit Test Coverage

### Task 3.1: Achieve 100% Coverage for Core Modules
- config.py: Test all validation scenarios and loading edge cases
- registry.py: Test client creation, lifecycle, and error handling
- federation.py: Test fan-out execution, merging, and failure scenarios
- tools_federation.py: Test discovery, health probes, and error reporting

### Task 3.2: Test New Tool Parameter Support
- Verify instance parameter works for all 16 Prometheus tools
- Test instances parameter for subset fan-out targeting
- Validate Alertmanager tool enhancements with fan-out support
- Test error handling for invalid instance names and parameters

### Task 3.3: Coverage Reporting and Thresholds
- Configure pytest-cov for coverage measurement
- Set minimum coverage thresholds (80% for existing, 100% for new)
- Generate HTML coverage reports for review
- Verify no coverage regressions from v2.0

## Wave 4: Release Preparation

### Task 4.1: Version Bumping
- Update pyproject.toml to version 0.3.0
- Update src/prometheus_mcp/__init__.py to __version__ = "0.3.0"
- Update Dockerfile LABEL version="0.3.0"
- Verify version consistency across all files

### Task 4.2: CHANGELOG Update
- Document all v3.0 features organized by phase
- Include breaking changes and migration notes
- Add configuration examples and tool usage examples
- Update release date to 2026-06-18

### Task 4.3: Documentation Updates
- Update .env.example to document PROMETHEUS_MCP_CONFIG
- Add federation configuration examples with mixed instances
- Document new tool parameters and fan-out capabilities
- Update README with federation features and migration guide

## Wave 5: Final Verification

### Task 5.1: End-to-End Workflow Test
- Full integration test from config file to tool execution
- Test mixed Prometheus/Alertmanager instance scenarios
- Verify fan-out queries with alert deduplication
- Validate health monitoring and error reporting

### Task 5.2: Performance and Stability
- Run stress tests with multiple concurrent fan-out queries
- Verify resource cleanup and session management
- Test timeout handling and cancellation scenarios
- Confirm stability under normal and error conditions

### Task 5.3: Release Readiness Check
- Final version consistency verification
- CHANGELOG completeness and accuracy check
- Documentation review and example validation
- License and attribution review

## Dependencies

- Phase 1-6 - depends on all v3.0 features being implemented
- Existing test infrastructure - relies on pytest and coverage tools
- Release automation - follows established versioning and documentation patterns

## Acceptance Tests

1. ✅ Integration test passes: config with 2+ instances, fan-out query, partial failure, merged results with instance labels
2. ✅ Protocol test updated: federation_list_instances in EXPECTED_TOOLS, schema validation passes
3. ✅ Unit test coverage: config.py (100%), registry.py (100%), federation.py (100%), tools_federation.py (100%)
4. ✅ Tool coverage: all 16 Prometheus + 4 Alertmanager + 1 federation tools have >80% coverage
5. ✅ Version bumped to 0.3.0 in pyproject.toml, __init__.py, Dockerfile
6. ✅ CHANGELOG.md updated with v3.0 features organized by phase
7. ✅ .env.example documents PROMETHEUS_MCP_CONFIG with federation examples
8. ✅ Backward compatibility maintained: legacy mode works identically to v2.0
9. ✅ Health probe validation shows correct reachability status for instances
10. ✅ Tool discovery includes federation_list_instances with proper annotations
11. ✅ Schema validation passes for all 21 tool signatures with new parameters
12. ✅ Error handling provides clear messages for unknown instances and invalid parameters
13. ✅ Fan-out execution handles partial failures and returns available results
14. ✅ Alert deduplication works correctly for identical alerts from HA cluster peers
15. ✅ Documentation is complete, accurate, and includes migration guidance