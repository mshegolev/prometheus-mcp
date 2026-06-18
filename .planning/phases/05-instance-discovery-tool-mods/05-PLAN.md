# Phase 5: Instance Discovery & Tool Modifications - Plan

**Planned:** 2026-06-18
**Status:** Ready for execution

## Goal

Add federation_list_instances discovery tool and optional `instance` parameter to all 16 existing tools for targeted and fan-out queries.

## Success Criteria

1. New `tools_federation.py` with federation_list_instances tool returning instance names, URLs, health status, and federation mode flag
2. Instance listing performs parallel health probes (/-/healthy) to show reachability
3. All 8 Prometheus tools in tools.py accept optional `instance` parameter (None=default, name=specific, "all"=fan-out)
4. All 4 status tools in tools_status.py accept optional `instance` parameter
5. Fan-out supports subset targeting via `instances` parameter (list of instance names)

## Wave 1: Instance Discovery Tool

### Task 1.1: Define Data Models
- Create `InstanceHealth` TypedDict for health probe results
- Create `InstanceInfo` TypedDict for discovery tool output
- Create `ListInstancesOutput` for structured tool response
- Add proper type hints and documentation strings

### Task 1.2: Implement Health Probing
- Create `_probe_instance_health()` function for individual health checks
- Implement parallel health probing using ThreadPoolExecutor
- Add timeout handling and error classification
- Measure response times and capture error details

### Task 1.3: Implement Discovery Tool
- Create `federation_list_instances()` tool function
- Use InstanceRegistry to enumerate configured instances
- Perform parallel health probes for all instances
- Generate structured and markdown output with health status

## Wave 2: Tool Parameter Extensions

### Task 2.1: Add Instance Parameters to Prometheus Tools
- Add `instance: str | None = None` parameter to all 8 Prometheus tools in tools.py
- Add `instances: list[str] | None = None` parameter for subset fan-out
- Update client acquisition to route through registry with instance parameter
- Implement fan-out logic for instance="all" and instances=[...] cases

### Task 2.2: Add Instance Parameters to Status Tools
- Add `instance: str | None = None` parameter to all 4 status tools in tools_status.py
- Update client acquisition pattern
- Maintain backward compatibility with instance=None

### Task 2.3: Add Instance Parameters to Alertmanager Tools
- Add `instance: str | None = None` parameter to all 4 Alertmanager tools in tools_alertmanager.py
- Update client acquisition to use get_alertmanager_client(instance)
- Maintain backward compatibility

## Wave 3: Fan-Out Integration

### Task 3.1: Implement Fan-Out Logic
- Create `_handle_fan_out()` function for "all" instance queries
- Create `_handle_subset_fan_out()` function for instances=[...] queries
- Integrate with federation.py merge functions
- Handle partial failure scenarios with error aggregation

### Task 3.2: Implement Instance Validation
- Create `_validate_instance_names()` function for parameter validation
- Generate actionable error messages with valid instance names
- Handle special "all" value appropriately
- Validate subset instance lists before fan-out execution

### Task 3.3: Implement Result Aggregation
- Update merge functions to handle fan-out results properly
- Add instance attribution to all merged results
- Implement truncation handling for large fan-out responses
- Generate clear error annotations for failed instances

## Wave 4: Health Probe Implementation

### Task 4.1: Implement Parallel Health Probes
- Create `_probe_all_instances_health()` function
- Use ThreadPoolExecutor for concurrent health checks
- Implement timeout handling per probe
- Aggregate probe results into structured format

### Task 4.2: Implement Health Status Logic
- Create `_determine_health_status()` function
- Classify instances as reachable/unreachable
- Calculate response times and error rates
- Generate actionable health status messages

### Task 4.3: Implement Error Handling
- Create `_handle_probe_error()` function for error classification
- Map HTTP status codes to health status categories
- Capture network errors and timeout conditions
- Generate user-friendly error descriptions

## Wave 5: Integration and Testing

### Task 5.1: Add Unit Tests
- Test discovery tool with various instance configurations
- Test health probing with reachable and unreachable instances
- Test instance parameter validation and error handling
- Test fan-out execution with successful and failed instances
- Test subset targeting with valid and invalid instance lists
- Target >80% coverage for tools_federation module

### Task 5.2: Add Integration Tests
- Test end-to-end discovery tool functionality
- Test fan-out queries with multiple instances
- Test error aggregation and partial failure handling
- Test backward compatibility with instance=None
- Test health probe timeout and error scenarios

### Task 5.3: Documentation and Examples
- Document new federation_list_instances tool
- Update tool documentation with instance parameter descriptions
- Provide examples for single instance, fan-out, and subset queries
- Document health status meanings and troubleshooting

## Dependencies

- Phase 3 (_mcp.py wiring) - depends on get_client(instance) routing
- Phase 4 (federation.py for fan-out) - depends on fan-out execution functions
- InstanceRegistry (Phase 2) - depends on instance enumeration and client access

## Acceptance Tests

1. ✅ New `tools_federation.py` with federation_list_instances tool returning instance info and health status
2. ✅ Instance listing performs parallel health probes (/-/healthy) showing reachability
3. ✅ All 8 Prometheus tools accept optional `instance` parameter with proper routing
4. ✅ All 4 status tools accept optional `instance` parameter with proper routing
5. ✅ All 4 Alertmanager tools accept optional `instance` parameter with proper routing
6. ✅ instance=None maintains backward compatibility with v2.0 behavior
7. ✅ instance="instance-name" routes to specific named instance
8. ✅ instance="all" triggers fan-out to all configured instances
9. ✅ instances=["a", "b"] supports subset targeting for fan-out
10. ✅ Fan-out returns merged results with __prometheus_instance__ labels
11. ✅ Partial failure returns available results + error annotations
12. ✅ Health probes complete within reasonable timeout
13. ✅ Unknown instance names raise actionable ConfigError
14. ✅ Invalid instance lists raise ValidationError with details
15. ✅ No secrets exposed in returned URLs or health status