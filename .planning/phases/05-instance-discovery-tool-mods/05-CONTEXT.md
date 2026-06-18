# Phase 5: Instance Discovery & Tool Modifications - Context

**Gathered:** 2026-06-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Add federation_list_instances discovery tool and optional `instance` parameter to all 16 existing tools for targeted and fan-out queries.

New module: `src/prometheus_mcp/tools_federation.py` — discovery tool for agent instance awareness.
Modified modules: `tools.py`, `tools_status.py`, `tools_alertmanager.py` — instance parameter support.

### Requirements Addressed
- **INST-02**: `federation_list_instances` tool returns all configured instances with names, URLs (no secrets), type (prometheus/alertmanager), and health status
- **INST-04**: Instance listing tool performs parallel health probes (/-/healthy) to show reachability
- **FED-01**: All existing Prometheus tools accept an optional `instance` parameter to target a specific named instance
- **FED-05**: Fan-out supports subset targeting via an `instances` parameter (list of instance names to query)

</domain>

<decisions>
## Implementation Decisions

### Discovery Tool Design
- New module `tools_federation.py` with `federation_list_instances` tool
- Parallel health probing using ThreadPoolExecutor for concurrency
- Health status includes reachability, response time, and error details
- Federation mode flag indicates multi-instance capability
- No secrets exposed in URLs (tokens/redacted)

### Tool Parameter Strategy
- All 16 existing tools get optional `instance: str | None = None` parameter
- Special "all" value triggers fan-out execution via federation.py
- Instance validation with actionable error messages for unknown names
- Backward compatibility: None/default maintains v2.0 behavior

### Fan-Out Extension
- Optional `instances: list[str] | None = None` parameter for subset targeting
- Validates all instance names before execution
- Uses federation.py fan-out functions for parallel execution
- Aggregates results with instance attribution

### Health Probe Implementation
- Parallel GET /-/healthy requests to all instances
- Configurable timeout per probe (default: 5 seconds)
- Structured error reporting with failure reasons
- Response time measurement for performance insights

### OpenCode's Discretion
- Exact health probe timeout values and retry logic
- Response time formatting and threshold definitions
- Error message wording for validation failures
- Tool annotation details and descriptions
- Health status categorization (healthy/degraded/unreachable)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- InstanceRegistry for instance enumeration and client access
- federation.py for fan-out execution and result merging
- _mcp.py get_client/get_alertmanager_client for client routing
- Existing tool patterns and response shaping functions

### Established Patterns
- Tool registration with @mcp.tool decorator
- Dual-channel output (structured + markdown)
- Actionable error messages with context
- Response size capping with truncation hints

### Integration Points
- tools_federation.py → InstanceRegistry (Phase 2) for instance listing
- tools_federation.py → PrometheusClient for health probes
- All tool modules → federation.py (Phase 4) for fan-out execution
- All tool modules → _mcp.py (Phase 3) for client routing

</code_context>

<specifics>
## Specific Ideas

### Discovery Tool Signature
```python
def federation_list_instances() -> ListInstancesOutput:
    pass
```

### Instance Parameter Extensions
```python
def prometheus_query(
    query: str,
    *,
    instance: Annotated[str | None, Field(description="Target instance (omit for default, 'all' for fan-out)")] = None,
    instances: Annotated[list[str] | None, Field(description="Specific instances for fan-out subset")] = None,
) -> QueryOutput:
    pass
```

### Health Probe Result Structure
```python
class InstanceHealth(TypedDict):
    name: str
    url: str
    type: Literal["prometheus", "alertmanager"]
    reachable: bool
    response_time_ms: float | None
    error: str | None
```

### Fan-Out Trigger Logic
- `instance=None` → single default instance query (v2.0 compatibility)
- `instance="instance-name"` → single specific instance query
- `instance="all"` → fan-out to all configured instances
- `instances=["a", "b"]` → fan-out to specific subset

### Error Handling Patterns
- Unknown instance name: ConfigError with valid names list
- Health probe failures: Logged but don't fail the discovery tool
- Fan-out partial failures: Return partial results + error annotations
- Invalid instance list: ValidationError with specific details

</specifics>

<deferred>
## Deferred Ideas

- Health probe caching for improved discovery tool performance — post-v3.0 optimization
- Advanced health metrics (memory usage, scrape stats) — nice-to-have, not in v3.0 scope
- Dynamic tool registration based on configured instances — post-v3.0 feature
- Instance grouping/tags for organized querying — post-v3.0 capability

</deferred>