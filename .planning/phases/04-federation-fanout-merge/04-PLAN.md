# Phase 4: Federation Fan-Out & Merge - Plan

**Planned:** 2026-06-18
**Status:** Ready for execution

## Goal

Implement concurrent fan-out query execution across multiple Prometheus instances using ThreadPoolExecutor, with result merging strategies per query type, __prometheus_instance__ label injection, partial failure handling, and global response size caps.

## Success Criteria

1. New `federation.py` module with fan_out_prometheus() using ThreadPoolExecutor for concurrent queries
2. Merge functions for instant queries, range queries, set values (metrics/labels), and per-instance results (TSDB, health)
3. __prometheus_instance__ label injected into every metric sample during merging (with collision check)
4. Partial failure: return available results + error annotations for failed instances; only raise ToolError if ALL instances fail
5. Global response size caps apply post-merge (not per-instance) — 500 metrics, 5000 range points across all instances

## Wave 1: Core Data Structures

### Task 1.1: Define Result and Error Structures
- Create `FanOutResult` TypedDict for unified fan-out response structure
- Create `InstanceError` TypedDict for structured error reporting
- Create `InstanceResult` TypedDict for individual instance results
- Add proper type hints and documentation strings

### Task 1.2: Define Constants and Configuration
- Define global response size caps (500 metrics, 5000 range points)
- Define default ThreadPoolExecutor parameters
- Define timeout handling constants
- Define error type categories (network, http, timeout, validation)

## Wave 2: Fan-Out Execution Engine

### Task 2.1: Implement Core Fan-Out Function
- Create `fan_out_prometheus()` function with ThreadPoolExecutor
- Implement per-instance timeout handling with individual cancellation
- Add result collection with early termination logic
- Implement structured error capture for each instance

### Task 2.2: Implement Worker Function
- Create `_execute_query_on_instance()` worker function
- Handle individual instance timeouts and cancellations
- Capture and structure instance-specific errors
- Return consistent result format for successful queries

### Task 2.3: Implement Error Classification
- Create `_classify_error()` function to categorize error types
- Map HTTP status codes to error categories
- Handle network errors, timeouts, and validation errors
- Generate actionable error messages with instance context

## Wave 3: Result Merging Strategies

### Task 3.1: Implement Instant Query Merging
- Create `merge_instant_results()` function for vector results
- Inject `__prometheus_instance__` label into every sample
- Handle label collision detection and resolution
- Maintain sample ordering and deduplication

### Task 3.2: Implement Range Query Merging
- Create `merge_range_results()` function for time series data
- Implement point deduplication across instances
- Enforce global range point cap (5000 points)
- Handle timestamp alignment and interpolation

### Task 3.3: Implement Set Value Merging
- Create `merge_set_results()` function for metric names/label values
- Implement cross-instance deduplication
- Enforce global metric cap (500 items)
- Maintain sorted output for consistency

### Task 3.4: Implement Per-Instance Result Merging
- Create `merge_per_instance_results()` function for TSDB/stats
- Aggregate numerical values across instances
- Preserve instance metadata for attribution
- Handle heterogeneous result types

## Wave 4: Label Injection and Collision Handling

### Task 4.1: Implement Label Injection Logic
- Create `_inject_instance_label()` utility function
- Handle label collision detection with existing `__prometheus_instance__` labels
- Implement collision resolution by appending `_source` suffix
- Ensure consistent behavior across all result types

### Task 4.2: Implement Collision Detection
- Create `_detect_label_collision()` function
- Check for existing `__prometheus_instance__` labels in samples
- Generate appropriate collision resolution strategy
- Log warnings for collision occurrences

## Wave 5: Partial Failure Handling

### Task 5.1: Implement Partial Success Logic
- Create `_handle_partial_failure()` function
- Determine when to return partial results vs. raise ToolError
- Generate structured error reports for failed instances
- Maintain list of successful instances for client feedback

### Task 5.2: Implement Complete Failure Handling
- Detect when ALL instances fail during fan-out
- Raise appropriate ToolError with aggregated failure information
- Generate actionable error messages for complete failures
- Preserve individual error details for debugging

## Wave 6: Response Size Management

### Task 6.1: Implement Global Cap Enforcement
- Create `_enforce_global_caps()` function for post-merge capping
- Implement metric cap enforcement (500 items)
- Implement range point cap enforcement (5000 points)
- Generate truncation indicators when caps are hit

### Task 6.2: Implement Truncation Logic
- Create `_truncate_results()` function for cap enforcement
- Maintain representative samples when truncating
- Generate clear truncation hints for user awareness
- Preserve instance attribution in truncated results

## Wave 7: Integration and Testing

### Task 7.1: Add Unit Tests
- Test fan-out execution with successful instances
- Test partial failure scenarios with mixed results
- Test complete failure with all instances failing
- Test timeout handling and cancellation
- Test label injection and collision resolution
- Test result merging for all query types
- Test global cap enforcement and truncation
- Target >80% coverage for federation module

### Task 7.2: Add Integration Tests
- Test end-to-end fan-out with multiple instances
- Test error aggregation and reporting
- Test resource cleanup and session management
- Test edge cases (empty results, large responses)
- Verify backward compatibility with single instance

### Task 7.3: Documentation and Examples
- Document module interface and usage patterns
- Provide examples for each query type
- Document error handling and failure modes
- Update README with federation capabilities

## Dependencies

- Phase 2 (registry.py) - depends on InstanceRegistry for client lists
- Existing tools.py functions - used as templates for merge functions

## Acceptance Tests

1. ✅ New `federation.py` module with fan_out_prometheus() using ThreadPoolExecutor
2. ✅ Merge functions for instant queries with __prometheus_instance__ label injection
3. ✅ Merge functions for range queries with point deduplication and global caps
4. ✅ Merge functions for set values with cross-instance deduplication
5. ✅ Merge functions for per-instance results with proper aggregation
6. ✅ __prometheus_instance__ label injected into every metric sample with collision check
7. ✅ Partial failure returns available results + error annotations for failed instances
8. ✅ ToolError raised only when ALL instances fail
9. ✅ Global response size caps applied post-merge (500 metrics, 5000 range points)
10. ✅ ThreadPoolExecutor properly configured with timeout handling
11. ✅ Structured error reporting with instance-specific context
12. ✅ Resource cleanup with proper session management