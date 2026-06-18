# Phase 7: v3.0 Test & Release Prep - Context

**Gathered:** 2026-06-18
**Status:** Ready for planning

<domain>
## Phase Boundary

End-to-end integration tests covering full federation workflow, version bump, CHANGELOG update, and release documentation.

Quality assurance phase ensuring v3.0 Federation features work correctly in concert and are ready for release.

### Requirements Addressed
None (quality phase)

</domain>

<decisions>
## Implementation Decisions

### Integration Test Scope
- Multi-instance config file with Prometheus and Alertmanager instances
- Fan-out query execution across mixed instance types
- Partial failure simulation with one unhealthy instance
- Result verification including instance labels and merged data correctness
- Health probe validation showing reachability status

### Protocol Test Updates
- Add federation_list_instances to EXPECTED_TOOLS list
- Update schema validation to include new tool signatures
- Verify all tool annotations and structured output declarations
- Test backward compatibility with v2.0 tool signatures

### Coverage Targets
- config.py: 100% coverage for dataclass validation and loading
- registry.py: 100% coverage for client creation and lifecycle
- federation.py: 100% coverage for fan-out execution and merging
- tools_federation.py: 100% coverage for discovery and health probes
- All modified tool functions: >80% coverage for new parameters

### Release Preparation
- Version bump to 0.3.0 following semantic versioning
- Comprehensive CHANGELOG.md with all v3.0 features organized by phase
- .env.example documentation for PROMETHEUS_MCP_CONFIG with examples
- README updates highlighting federation capabilities and migration path

### OpenCode's Discretion
- Exact integration test scenario composition and edge cases
- Coverage measurement methodology and tool selection
- CHANGELOG entry formatting and feature organization
- Release documentation structure and content emphasis

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing integration test patterns and fixtures
- Unit test coverage baselines from v2.0
- Test configuration files and mock data
- Release automation scripts and checklists

### Established Patterns
- pytest-based testing with fixture reuse
- Coverage reporting with threshold enforcement
- CHANGELOG formatting with feature grouping
- Semantic versioning with minor version bump for new features

### Integration Points
- All v3.0 modules (config, registry, federation, tools_federation)
- All 21 tool functions with new instance parameter support
- Mixed Prometheus/Alertmanager instance configurations
- Legacy mode backward compatibility with v2.0 behavior

</code_context>

<specifics>
## Specific Ideas

### Integration Test Scenario
```python
def test_full_federation_workflow():
    # 1. Config with 2 Prometheus + 1 Alertmanager instances
    # 2. One Prometheus instance unreachable (partial failure)
    # 3. Fan-out query to all instances
    # 4. Verify merged results with __prometheus_instance__ labels
    # 5. Verify error reporting for failed instance
    # 6. Verify health probe shows correct reachability status
    pass
```

### Coverage Measurement
- Use pytest-cov for coverage reporting
- Measure statement and branch coverage
- Enforce minimum thresholds per module
- Generate HTML coverage reports for review

### CHANGELOG Structure
```markdown
## [0.3.0] - 2026-06-18

### Added
- Federation support for multi-instance Prometheus queries
- Alertmanager multi-instance support with fan-out queries
- Instance discovery and health monitoring tool
- Per-instance authentication and configuration
```

### Version Bump Locations
- pyproject.toml: version = "0.3.0"
- src/prometheus_mcp/__init__.py: __version__ = "0.3.0"
- Dockerfile: LABEL version="0.3.0"

</specifics>

<deferred>
## Deferred Ideas

- Performance benchmarking against v2.0 baseline — post-release optimization
- Stress testing with large instance counts (>10 instances) — nice-to-have, not blocking v3.0
- Cross-platform compatibility testing — assumed covered by existing CI
- Long-running stability tests — post-release monitoring

</deferred>