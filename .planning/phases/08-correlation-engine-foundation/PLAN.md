# Plan: Phase 8 - Correlation Engine Foundation

**Phase:** 8 of 13
**Milestone:** v4.0 Advanced Alert Correlation
**Approach:** Create core correlation infrastructure for cross-instance alert analysis

## Goal

Build the core infrastructure for cross-instance alert analysis, enabling AI agents to identify related alerts across clusters and group them for holistic incident analysis.

## Requirements Addressed

- **COR-01**: Cross-instance alert matching to identify related alerts that fire simultaneously or in sequence across different Prometheus instances
- **COR-02**: Alert grouping by service to bundle related alerts into service-level incident analysis
- **COR-03**: Cascading alert detection to identify alert propagation patterns indicating dependency failures

## Success Criteria

1. New `correlation.py` module with cross-instance alert matching using temporal windows and label similarity scoring
2. Alert grouping algorithm that clusters related alerts by service identifiers across all instances
3. Cascading alert detection with directional dependency inference and correlation strength metrics
4. Integration with existing federation infrastructure to access alerts from all configured instances
5. Dual-channel output (markdown + structured JSON) following existing patterns with instance attribution

## Implementation

### Module Structure

#### Primary Module
- **File**: `src/prometheus_mcp/correlation.py`
- **Purpose**: Core correlation engine with cross-instance alert matching, grouping, and cascading detection

#### Supporting Modules
- **File**: `src/prometheus_mcp/tools_correlation.py`
- **Purpose**: MCP tools exposing correlation functionality to AI agents

#### Test Files
- **File**: `tests/test_correlation.py`
- **Purpose**: Unit tests for correlation algorithms and logic

#### Data Models
- **File**: `src/prometheus_mcp/models.py` (existing, with additions)
- **Purpose**: Extend with correlation-specific data structures

### Core Classes

#### 1. `CorrelationEngine`
Main class for cross-instance alert correlation operations.

```python
class CorrelationEngine:
    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize correlation engine with instance registry."""
    
    def correlate_alerts_across_instances(
        self, 
        temporal_window: int = 300,
        similarity_threshold: float = 0.7
    ) -> CorrelationResult:
        """Match alerts across instances using temporal windows and label similarity."""
        
    def group_alerts_by_service(self, alerts: list[AMAlertItem]) -> AlertGroupResult:
        """Cluster related alerts by service identifiers across all instances."""
        
    def detect_cascading_alerts(
        self, 
        alerts: list[AMAlertItem], 
        temporal_window: int = 300
    ) -> CascadeDetectionResult:
        """Detect cascading alert patterns with directional dependency inference."""
```

#### 2. `AlertMatcher`
Handles temporal and similarity-based alert matching.

```python
class AlertMatcher:
    def calculate_temporal_similarity(
        self, 
        alert1: AMAlertItem, 
        alert2: AMAlertItem, 
        window_seconds: int
    ) -> bool:
        """Check if two alerts occurred within the temporal window."""
        
    def calculate_label_similarity(
        self, 
        labels1: dict[str, str], 
        labels2: dict[str, str]
    ) -> float:
        """Calculate similarity score between alert label sets."""
```

#### 3. `AlertGrouper`
Groups alerts by service identifiers and relationship patterns.

```python
class AlertGrouper:
    def identify_service_identifier(self, labels: dict[str, str]) -> str:
        """Extract service identifier from alert labels."""
        
    def group_related_alerts(
        self, 
        alerts: list[AMAlertItem]
    ) -> dict[str, list[AMAlertItem]]:
        """Group alerts by service identifiers across instances."""
```

#### 4. `CascadeDetector`
Detects cascading alert patterns and infers dependencies.

```python
class CascadeDetector:
    def infer_dependency_direction(
        self, 
        parent_alert: AMAlertItem, 
        child_alert: AMAlertItem
    ) -> tuple[bool, float]:
        """Infer if parent alert caused child alert and calculate strength."""
        
    def calculate_correlation_strength(
        self, 
        alert1: AMAlertItem, 
        alert2: AMAlertItem
    ) -> float:
        """Calculate correlation strength between two alerts."""
```

### Data Models (Additions to `models.py`)

```python
class CorrelatedAlert(TypedDict):
    alert: AMAlertItem
    instance: str
    correlation_score: float

class CorrelationGroup(TypedDict):
    group_id: str
    alerts: list[CorrelatedAlert]
    service_identifier: str
    correlation_strength: float

class CascadeRelationship(TypedDict):
    parent: CorrelatedAlert
    child: CorrelatedAlert
    dependency_strength: float
    temporal_delay: float

class CorrelationResult(TypedDict):
    total_correlations: int
    correlated_alerts: list[CorrelatedAlert]
    groups: list[CorrelationGroup]
    cascades: list[CascadeRelationship]
    instance_attribution: dict[str, int]

class AlertGroupResult(TypedDict):
    total_groups: int
    groups: dict[str, list[AMAlertItem]]
    ungrouped_count: int

class CascadeDetectionResult(TypedDict):
    total_cascades: int
    cascades: list[CascadeRelationship]
    root_causes: list[CorrelatedAlert]
```

## Integration Points

### 1. Registry Integration
- Leverage existing `InstanceRegistry` to access all configured Prometheus/Alertmanager instances
- Use `registry.all_alertmanager_clients()` for fan-out alert collection
- Use `registry.list_instances()` for instance attribution

### 2. Federation Infrastructure
- Extend `federation.py` fan-out functionality to collect alerts from all instances
- Utilize existing label injection (`__prometheus_instance__`) for source attribution
- Apply existing error handling and partial failure patterns

### 3. MCP Tool Framework
- Create new tools in `tools_correlation.py` following existing patterns
- Use `output.py` helpers for dual-channel (markdown + JSON) responses
- Apply existing parameter patterns (instance selection, filtering)

### 4. Configuration
- Respect existing federation configuration for instance discovery
- Use existing timeout and authentication mechanisms
- Maintain backward compatibility with legacy mode

## Implementation Steps

### Week 1: Core Engine Development

#### Task 1.1: Alert Matching Implementation
- Implement `AlertMatcher.calculate_temporal_similarity()` to compare alert timestamps
- Implement `AlertMatcher.calculate_label_similarity()` using Jaccard similarity or cosine similarity
- Create `CorrelationEngine.correlate_alerts_across_instances()` method
- Add temporal window parameter (default 5 minutes) for correlation timeframe

#### Task 1.2: Alert Grouping Implementation
- Implement `AlertGrouper.identify_service_identifier()` to extract service names from common labels
- Implement `AlertGrouper.group_related_alerts()` to cluster alerts by service
- Create `CorrelationEngine.group_alerts_by_service()` method
- Handle cross-instance grouping with instance attribution

#### Task 1.3: Cascade Detection Implementation
- Implement `CascadeDetector.infer_dependency_direction()` to determine causal relationships
- Implement `CascadeDetector.calculate_correlation_strength()` for metric-based correlation
- Create `CorrelationEngine.detect_cascading_alerts()` method
- Add directional dependency inference based on temporal sequencing

### Week 2: Federation Integration

#### Task 2.1: Cross-Instance Alert Collection
- Extend federation functionality to collect alerts from all Alertmanager instances
- Implement parallel alert fetching using existing `fan_out_prometheus()` patterns
- Handle partial failures gracefully with warning aggregation
- Ensure proper instance attribution with `__prometheus_instance__` labels

#### Task 2.2: Data Model Extensions
- Add new correlation-specific data structures to `models.py`
- Define `CorrelationResult`, `CorrelationGroup`, and `CascadeRelationship` types
- Ensure compatibility with existing MCP structured output requirements

#### Task 2.3: Error Handling and Validation
- Implement robust error handling for network failures
- Add validation for temporal windows and similarity thresholds
- Create meaningful error messages for edge cases

### Week 3: MCP Tools Implementation

#### Task 3.1: Core Correlation Tool
- Create `correlate_alerts_across_instances` tool in `tools_correlation.py`
- Implement parameter validation and default values
- Generate dual-channel output (markdown + structured JSON)
- Follow existing tool annotation patterns

#### Task 3.2: Alert Grouping Tool
- Create `group_alerts_by_service` tool for service-level clustering
- Implement filtering options for service identifiers
- Generate human-readable markdown summaries
- Ensure structured output compatibility

#### Task 3.3: Cascade Detection Tool
- Create `detect_cascading_alerts` tool for dependency analysis
- Implement strength-based filtering for results
- Generate dependency chain visualizations in markdown
- Provide detailed cascade relationship data

### Week 4: Testing and Documentation

#### Task 4.1: Unit Tests for Core Logic
- Create `test_correlation.py` with comprehensive unit tests
- Test alert matching with various temporal scenarios
- Validate label similarity calculations with edge cases
- Verify service grouping accuracy with complex label sets

#### Task 4.2: Integration Tests
- Test cross-instance correlation with mocked federation responses
- Validate error handling with simulated network failures
- Test partial failure scenarios with mixed success/failure responses
- Verify instance attribution accuracy

#### Task 4.3: Performance Tests
- Benchmark correlation algorithms with large alert datasets
- Test memory usage with 1000+ alerts across multiple instances
- Validate response time under various load conditions
- Optimize algorithms for scalability

## Dependencies

- Phase 2: Instance Registry & Client Management (`registry.py`)
- Phase 4: Federation Fan-Out & Merge (`federation.py`)

## Acceptance Criteria

- [ ] New `correlation.py` module implements all core correlation functionality
- [ ] Alert grouping algorithm successfully clusters related alerts by service
- [ ] Cascading alert detection identifies dependency relationships with strength metrics
- [ ] Integration with federation infrastructure enables cross-instance alert collection
- [ ] All new functionality follows existing dual-channel output patterns
- [ ] Unit test coverage exceeds 80% for new modules
- [ ] Integration tests validate cross-instance scenarios
- [ ] Documentation includes usage examples and API reference

---
*Plan created: 2026-06-18*
*Phase 8: Correlation Engine Foundation*