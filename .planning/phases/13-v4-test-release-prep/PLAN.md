# Phase 13 Plan: v4.0 Test & Release Prep

## Objective
Comprehensive testing of all v4.0 features, version bump, and documentation updates to prepare for release.

## Approach
1. Create integration tests for the full v4.0 workflow
2. Implement performance tests for scalability validation
3. Verify unit test coverage for all new modules
4. Update version information and CHANGELOG.md
5. Enhance documentation with v4.0 features and examples

## Implementation Steps

### Step 1: Create integration tests
- Develop tests covering the full correlation workflow: alert matching → grouping → RCA → dependency analysis
- Test cross-instance functionality with multiple simulated Prometheus instances
- Validate trend analysis integration with correlation and RCA features
- Test the new federation_analyze_alerts tool with various scenarios

### Step 2: Implement performance tests
- Create test environment with 10+ simulated Prometheus instances
- Generate test data with 1000+ alerts across instances
- Measure performance of correlation, grouping, and analysis operations
- Validate scalability and resource usage patterns

### Step 3: Verify unit test coverage
- Audit code coverage for correlation.py module (target >80%)
- Audit code coverage for rca.py module (target >80%)
- Audit code coverage for dependency.py module (target >80%)
- Audit code coverage for trend_analysis.py module (target >80%)
- Add missing tests to meet coverage requirements

### Step 4: Update version information
- Bump version to 0.4.0 in pyproject.toml
- Update version in src/prometheus_mcp/__init__.py
- Update CHANGELOG.md with comprehensive v4.0 feature list
- Add release date and upgrade notes

### Step 5: Enhance documentation
- Update README.md with v4.0 features and usage examples
- Add migration guide from v3.0 to v4.0
- Document new federation_analyze_alerts tool
- Update configuration examples for new features
- Add troubleshooting section for common v4.0 issues

## Files to Create/Modify
1. tests/test_v4_integration.py (new) - Integration tests
2. tests/test_v4_performance.py (new) - Performance tests
3. Various existing test files (enhance for coverage)
4. pyproject.toml (modify) - Version bump
5. src/prometheus_mcp/__init__.py (modify) - Version bump
6. CHANGELOG.md (modify) - Release notes
7. README.md (modify) - Documentation updates

## Success Metrics
- Integration tests covering full v4.0 workflow passing
- Performance tests validating scalability with 10+ instances and 1000+ alerts
- All new modules achieving >80% code coverage
- Version correctly bumped to 0.4.0 with updated changelog
- Documentation comprehensively updated with v4.0 features and examples