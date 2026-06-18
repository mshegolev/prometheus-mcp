# Phase 6: Alertmanager Federation - Plan

**Planned:** 2026-06-18
**Status:** Ready for execution

## Goal

Add Alertmanager multi-instance support with fan-out queries, alert deduplication by fingerprint, and __alertmanager_instance__ label injection.

## Success Criteria

1. Config file supports named Alertmanager instances with per-instance auth (same pattern as Prometheus instances)
2. All 4 Alertmanager tools accept optional `instance` parameter for targeted and fan-out queries
3. Alertmanager fan-out queries execute in parallel with partial failure handling
4. Alert deduplication by fingerprint when fan-out returns same alert from multiple HA cluster peers

## Wave 1: Config File Extension

### Task 1.1: Verify Alertmanager Instance Support
- Confirm InstanceConfig already supports alertmanager_url and auth fields
- Validate that existing config loading handles Alertmanager instances
- Test config validation with Alertmanager-only instances
- Verify defaults application for Alertmanager instances

### Task 1.2: Update Documentation and Examples
- Document Alertmanager instance configuration in config file examples
- Update .env.example with PROMETHEUS_MCP_CONFIG reference
- Add Alertmanager instance examples to configuration documentation
- Verify README mentions Alertmanager federation support

## Wave 2: Tool Enhancement

### Task 2.1: Add Fan-Out Support to Alertmanager Tools
- Extend alertmanager_list_silences with fan-out capability
- Extend alertmanager_list_alerts with fan-out capability
- Extend alertmanager_get_status with fan-out capability
- Extend alertmanager_list_alert_groups with fan-out capability
- Add `instances: list[str] | None = None` parameter for subset targeting
- Implement fan-out logic using federation.py infrastructure

### Task 2.2: Implement Alert Deduplication
- Create alert deduplication function based on fingerprint field
- Implement __alertmanager_instance__ label injection for source tracking
- Handle partial failure scenarios with clear error attribution
- Generate merged alert lists with deduplication metadata

### Task 2.3: Update Client Acquisition
- Modify tools to use get_alertmanager_client(instance) with routing
- Implement fan-out trigger logic for instance="all" cases
- Add subset targeting support for instances=[...] parameters
- Maintain backward compatibility with instance=None

## Wave 3: Fan-Out Integration

### Task 3.1: Enhance Federation Infrastructure
- Extend federation.py with Alertmanager-specific fan-out functions
- Add Alertmanager result merging with fingerprint deduplication
- Implement Alertmanager partial failure handling
- Add Alertmanager response size management

### Task 3.2: Implement Alert Deduplication Algorithm
- Create fingerprint-based deduplication for alerts across instances
- Preserve source instance information for deduplicated alerts
- Handle alert state variations across instances
- Generate clear deduplication metadata for client visibility

### Task 3.3: Add Alertmanager Health Probes
- Extend tools_federation.py health probing to Alertmanager endpoints
- Add Alertmanager-specific health status interpretation
- Implement Alertmanager readiness/liveness probe handling
- Generate unified health status for mixed Prometheus/Alertmanager instances

## Wave 4: Alert Deduplication Implementation

### Task 4.1: Implement Fingerprint-Based Deduplication
- Create _deduplicate_alerts_by_fingerprint() function
- Handle identical fingerprints from HA cluster peers
- Preserve source instance information in deduplicated alerts
- Generate deduplication metadata showing consolidation

### Task 4.2: Implement Label Injection
- Add __alertmanager_instance__ label to deduplicated alerts
- Handle label collision detection and resolution
- Maintain consistent labeling across all Alertmanager results
- Preserve original alert structure while adding source information

### Task 4.3: Handle Alert State Variations
- Manage alert state differences across Alertmanager instances
- Handle active/suppressed/unprocessed state conflicts
- Generate clear state reporting for multi-instance alerts
- Preserve silence and inhibition information from all sources

## Wave 5: Integration and Testing

### Task 5.1: Add Unit Tests
- Test Alertmanager instance configuration loading
- Test fan-out execution with Alertmanager instances
- Test alert deduplication with identical fingerprints
- Test partial failure handling for Alertmanager fan-out
- Test label injection and collision resolution
- Target >80% coverage for Alertmanager federation features

### Task 5.2: Add Integration Tests
- Test end-to-end Alertmanager federation workflow
- Test mixed Prometheus/Alertmanager instance configurations
- Test HA cluster alert deduplication scenarios
- Test error aggregation and partial failure handling
- Test health probe extension to Alertmanager endpoints

### Task 5.3: Documentation and Examples
- Document Alertmanager federation capabilities
- Provide examples for multi-cluster Alertmanager setups
- Document alert deduplication behavior and metadata
- Update tool documentation with Alertmanager instance support

## Dependencies

- Phase 4 (federation.py) - depends on fan-out infrastructure
- Phase 5 (tool modification pattern) - follows established patterns
- InstanceRegistry (Phase 2) - depends on Alertmanager client management
- Config loading (Phase 1) - depends on InstanceConfig support

## Acceptance Tests

1. ✅ Config file supports named Alertmanager instances with per-instance auth (same pattern as Prometheus instances)
2. ✅ All 4 Alertmanager tools accept optional `instance` parameter with proper routing
3. ✅ alertmanager_list_silences supports fan-out with instance="all" and instances=[...]
4. ✅ alertmanager_list_alerts supports fan-out with alert deduplication by fingerprint
5. ✅ alertmanager_get_status supports fan-out with unified cluster status reporting
6. ✅ alertmanager_list_alert_groups supports fan-out with group consolidation
7. ✅ Alertmanager fan-out queries execute in parallel using ThreadPoolExecutor
8. ✅ Partial failure handling returns available results with error annotations
9. ✅ Alert deduplication by fingerprint when identical alerts from HA cluster peers
10. ✅ __alertmanager_instance__ label injected for source tracking
11. ✅ Health probes extended to Alertmanager /-/healthy and /-/ready endpoints
12. ✅ Mixed Prometheus/Alertmanager instance configurations work correctly
13. ✅ Backward compatibility maintained with existing Alertmanager tool usage
14. ✅ Response size management applies to Alertmanager fan-out results
15. ✅ Error handling provides clear instance-specific failure information