# Phase 4: Federation Fan-Out & Merge - Context

**Gathered:** 2026-06-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement concurrent fan-out query execution across multiple Prometheus instances using ThreadPoolExecutor, with result merging strategies per query type, __prometheus_instance__ label injection, partial failure handling, and global response size caps.

New module: `src/prometheus_mcp/federation.py` — consumed by tool modifications (Phase 5) for fan-out queries.

### Requirements Addressed
- **FED-02**: Fan-out queries execute the same PromQL across all (or a subset of) instances in parallel using ThreadPoolExecutor
- **FED-03**: Fan-out results inject `__prometheus_instance__` label into every metric sample to identify the source instance
- **FED-04**: Partial failure handling: if some instances fail during fan-out, return available results plus warnings listing failed instances — only raise ToolError if ALL instances fail
- **FED-06**: Fan-out response size is capped globally (not per-instance) to prevent response explosion

</domain>

<decisions>
## Implementation Decisions

### Fan-Out Execution Model
- ThreadPoolExecutor with configurable max_workers (default: min(32, num_instances + 4))
- Timeout per instance query (inherits from client timeout) with individual cancellation
- Result collection with early termination on catastrophic failures
- Per-instance error capture with structured error reporting

### Result Merging Strategies
- **Instant Queries**: Vector results merged by appending samples with __prometheus_instance__ labels
- **Range Queries**: Time series merged with point deduplication and global point cap enforcement
- **Set Values**: Metric names/label values deduplicated across instances
- **Per-Instance Results**: TSDB stats and health checks aggregated with instance metadata

### Label Injection & Collision Handling
- Inject `__prometheus_instance__` label into every metric sample
- Collision check: if source already has this label, append `_source` suffix to original
- Consistent across all query types and result shapes

### Partial Failure Model
- Individual instance failures captured as warnings, not exceptions
- Result includes list of successful instances and failed instances with error details
- Only raise ToolError if ALL instances fail (complete failure)
- Structured error reporting with instance-specific context

### Response Size Management
- Global caps: 500 metrics for set queries, 5000 range points for range queries
- Post-merge enforcement (not per-instance) to maintain consistent behavior
- Truncation with clear indication when caps are hit
- Caps applied uniformly regardless of number of instances

### OpenCode's Discretion
- Exact ThreadPoolExecutor configuration parameters
- Timeout handling granularity and error message wording
- Warning structure format and content
- Deduplication algorithm specifics for set values
- Point selection strategy when range query caps are exceeded

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- InstanceRegistry.all_prometheus_clients() for client enumeration
- Existing query functions in tools.py as merge function templates
- Error handling patterns from client modules
- Response shaping functions (_shape_instant_sample, _shape_range_series)

### Established Patterns
- ThreadPoolExecutor usage for concurrent HTTP operations
- Structured error reporting with actionable messages
- Response size capping with truncation hints
- Dual-channel output (structured + markdown) for all tools

### Integration Points
- federation.py ← InstanceRegistry (Phase 2) for client lists
- tools.py modifications (Phase 5) → federation.py for fan-out execution
- Models updated with fan-out result structures
- ThreadPoolExecutor imported from concurrent.futures

</code_context>

<specifics>
## Specific Ideas

### Fan-Out Function Signature
```python
def fan_out_prometheus(
    query_func: Callable[[PrometheusClient], Any],
    clients: list[PrometheusClient],
    *,
    timeout: float | None = None,
    max_workers: int | None = None,
) -> FanOutResult:
    pass
```

### Result Structure
```python
class FanOutResult(TypedDict):
    data: list[Any]  # Merged results
    successful_instances: list[str]  # Names of successful instances
    failed_instances: list[InstanceError]  # Errors for failed instances
    truncated: bool  # True if global caps were hit
```

### Merge Function Patterns
- `merge_instant_results(results: list[QueryOutput]) -> QueryOutput`
- `merge_range_results(results: list[QueryRangeOutput]) -> QueryRangeOutput`
- `merge_set_results(results: list[ListMetricsOutput]) -> ListMetricsOutput`
- `merge_per_instance_results(results: list[Any]) -> Any`

### Error Structure
```python
class InstanceError(TypedDict):
    instance_name: str
    error_type: str  # "network", "http", "timeout", "validation"
    message: str
    status_code: int | None
```

</specifics>

<deferred>
## Deferred Ideas

- Per-instance fan-out timeout (shorter than per-client timeout) with total fan-out deadline — FED-07, post-v3.0
- Adaptive worker pool sizing based on instance responsiveness — nice-to-have, not in v3.0 scope
- Streaming merge for very large result sets — post-v3.0 optimization
- Fan-out result caching — post-v3.0 performance enhancement

</deferred>