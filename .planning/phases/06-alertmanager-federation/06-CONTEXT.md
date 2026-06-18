# Phase 6: Alertmanager Federation - Context

**Gathered:** 2026-06-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Add Alertmanager multi-instance support with fan-out queries, alert deduplication by fingerprint, and __alertmanager_instance__ label injection.

Extends existing federation infrastructure to include Alertmanager instances alongside Prometheus instances, enabling unified multi-cluster alert investigation.

### Requirements Addressed
- **AMF-01**: Config file supports named Alertmanager instances with per-instance auth, same pattern as Prometheus instances
- **AMF-02**: All 4 Alertmanager tools accept optional `instance` parameter for targeted and fan-out queries
- **AMF-03**: Alertmanager fan-out queries execute in parallel with partial failure handling
- **AMF-04**: Alert deduplication by fingerprint when fan-out returns same alert from multiple HA cluster peers

</domain>

<decisions>
## Implementation Decisions

### Config File Extension
- Alertmanager instances use identical schema to Prometheus instances
- Shared `instances` section with type inference from URL presence
- Per-instance auth (token/username/password) with SSL/timeout overrides
- Alertmanager-specific defaults for health probe paths

### Tool Enhancement Approach
- Extend existing 4 Alertmanager tools with fan-out support
- Leverage federation.py fan-out infrastructure from Phase 4
- Add `instance="all"` and `instances=[...]` parameter support
- Maintain backward compatibility with existing tool signatures

### Alert Deduplication Strategy
- Deduplicate alerts by `fingerprint` field when identical across instances
- Preserve source instance information via __alertmanager_instance__ labels
- Handle partial failure scenarios with clear error attribution
- Generate merged alert lists with deduplication metadata

### Fan-Out Execution Model
- Parallel execution using existing ThreadPoolExecutor infrastructure
- Per-instance timeout with individual cancellation
- Structured error handling with instance-specific context
- Result merging with fingerprint-based deduplication

### OpenCode's Discretion
- Exact deduplication algorithm implementation details
- Error message wording and failure scenario handling
- Health probe configuration for Alertmanager instances
- Response size management and truncation strategies

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- federation.py fan-out infrastructure and merge functions
- InstanceRegistry for Alertmanager client management
- Existing Alertmanager tool patterns and response structures
- Health probe implementation from tools_federation.py

### Established Patterns
- Parallel execution with ThreadPoolExecutor and timeout handling
- Partial failure handling with error aggregation
- Structured output with dual-channel (markdown + JSON) support
- Actionable error messages with context and suggestions

### Integration Points
- config.py — extend InstanceConfig to support Alertmanager instances
- federation.py — reuse fan-out execution and result merging
- tools_federation.py — extend health probing to Alertmanager endpoints
- tools_alertmanager.py — enhance existing tools with fan-out support
- registry.py — leverage existing Alertmanager client management

</code_context>

<specifics>
## Specific Ideas

### Config File Structure
```json
{
  "version": 1,
  "instances": {
    "am-primary": {
      "alertmanager_url": "https://am-primary.example.com",
      "alertmanager_token": "secret-token"
    },
    "am-secondary": {
      "alertmanager_url": "https://am-secondary.example.com",
      "alertmanager_username": "readonly",
      "alertmanager_password": "password"
    }
  }
}
```

### Alert Deduplication Algorithm
- Group alerts by fingerprint across all instances
- For duplicate fingerprints, preserve first occurrence with source annotation
- Inject __alertmanager_instance__ label indicating source instances
- Generate deduplication metadata showing consolidation details

### Fan-Out Tool Extensions
```python
def alertmanager_list_alerts(
    *,
    instance: Annotated[str | None, Field(description="Target instance or 'all' for fan-out")] = None,
    instances: Annotated[list[str] | None, Field(description="Specific instances for subset fan-out")] = None,
) -> ListAMAlertsOutput:
    pass
```

### Merged Alert Structure
```python
class MergedAMAlertItem(TypedDict):
    fingerprint: str
    labels: dict[str, str]
    annotations: dict[str, str]
    state: str
    activeAt: str
    value: str
    source_instances: list[str]  # List of Alertmanager instances that reported this alert
```

</specifics>

<deferred>
## Deferred Ideas

- Alert correlation across Prometheus-Alertmanager instance pairs — post-v3.0 feature
- Alertmanager clustering awareness for intelligent routing — nice-to-have, not in v3.0 scope
- Alert history federation across multiple Alertmanager clusters — post-v3.0 enhancement
- Cross-cluster alert dependency analysis — advanced feature for future consideration

</deferred>