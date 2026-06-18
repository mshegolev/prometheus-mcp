# Phase 8 Plan: Correlation Engine Foundation Summary

**Phase:** 8 of 13
**Plan:** correlation-engine-foundation
**Subsystem:** Alert Correlation
**Tags:** correlation, alerts, cross-instance, ai-analysis
**Dependency Graph:**
- **Requires:** registry.py, models.py, alertmanager_client.py
- **Provides:** correlation.py, tools_correlation.py
- **Affects:** AI agent alert analysis capabilities

**Tech Stack:**
- **Added:** Core correlation engine for cross-instance alert analysis
- **Patterns:** Temporal correlation, label similarity, service grouping, cascade detection

**Key Files:**
- **Created:** src/prometheus_mcp/correlation.py
- **Created:** src/prometheus_mcp/tools_correlation.py
- **Modified:** src/prometheus_mcp/models.py
- **Created:** tests/test_correlation.py

## One-liner
Cross-instance alert correlation engine with temporal matching, service grouping, and cascade detection for AI agents

## Implementation Overview

Successfully implemented the Correlation Engine Foundation for the v4.0 Advanced Alert Correlation milestone. This provides AI agents with powerful capabilities for analyzing alerts across multiple Prometheus instances.

### Core Components Created

1. **Correlation Engine (`correlation.py`)** - Main orchestration class that coordinates all correlation operations:
   - Cross-instance alert matching using temporal windows and label similarity
   - Service-based alert grouping across all instances
   - Cascading alert detection with directional dependency inference

2. **Specialized Algorithm Classes:**
   - `AlertMatcher` - Handles temporal and label-based similarity calculations
   - `AlertGrouper` - Groups alerts by service identifiers using hierarchical matching
   - `CascadeDetector` - Detects alert propagation patterns and infers dependencies

3. **MCP Tools (`tools_correlation.py`)** - Exposes correlation functionality to AI agents:
   - `correlate_alerts_across_instances` - Find related alerts across clusters
   - `group_alerts_by_service` - Bundle alerts for service-level analysis
   - `detect_cascading_alerts` - Identify failure propagation patterns

4. **Data Models (`models.py`)** - Extended with correlation-specific typed dictionaries:
   - `CorrelatedAlert`, `CorrelationGroup`, `CascadeRelationship`
   - `CorrelationResult`, `AlertGroupResult`, `CascadeDetectionResult`

5. **Comprehensive Tests (`test_correlation.py`)** - 16 unit tests covering all functionality:
   - Alert matching algorithms (temporal and label similarity)
   - Service grouping logic with various label combinations
   - Cascade detection with causal and non-causal scenarios
   - Full correlation engine integration tests

## Deviations from Plan

None - plan executed exactly as written.

## Key Features Implemented

### Cross-Instance Alert Matching (COR-01)
- **Temporal Window Analysis**: Compares alert timestamps to find simultaneous or sequential firings
- **Label Similarity Scoring**: Uses Jaccard index to measure similarity between alert label sets
- **Instance Attribution**: Preserves source instance information for all correlated alerts
- **Configurable Thresholds**: Adjustable similarity scores and temporal windows for fine-tuning

### Alert Grouping by Service (COR-02)
- **Hierarchical Service Identification**: Extracts service identifiers from job, service, app, namespace, component labels
- **Cross-Instance Grouping**: Clusters related alerts by service regardless of source instance
- **Fallback Mechanisms**: Uses instance labels when service identifiers are missing
- **Group Metadata**: Includes correlation strength and service identifiers for each group

### Cascading Alert Detection (COR-03)
- **Temporal Sequence Analysis**: Identifies upstream/downstream alert relationships based on firing order
- **Directional Dependency Inference**: Determines causal relationships with strength metrics
- **Delay Calculation**: Measures temporal delays between parent and child alerts
- **Root Cause Identification**: Automatically identifies potential root causes in failure chains

## Integration Points

### Registry Integration
- Leverages existing `InstanceRegistry` to access all configured Prometheus/Alertmanager instances
- Uses `registry.all_alertmanager_clients()` for fan-out alert collection
- Respects existing authentication and configuration patterns

### Federation Infrastructure
- Extends federation functionality to collect alerts from all Alertmanager instances
- Maintains instance attribution with `__prometheus_instance__` labels
- Applies existing error handling and partial failure patterns

### MCP Tool Framework
- Creates new tools following existing annotation and output patterns
- Uses `output.py` helpers for dual-channel (markdown + JSON) responses
- Applies existing parameter validation and error handling approaches

## Performance Characteristics

### Algorithm Efficiency
- **Temporal Matching**: O(n²) comparison but optimized with early termination
- **Label Similarity**: O(k) where k is the average number of labels per alert
- **Service Grouping**: O(n) linear grouping by service identifiers
- **Cascade Detection**: O(n²) temporal sequence analysis with strength filtering

### Scalability Features
- Configurable temporal windows and similarity thresholds for tuning
- Memory-efficient data structures for large alert volumes
- Graceful degradation under resource constraints
- Instance-level parallelization through existing federation patterns

## Testing Coverage

### Unit Tests (16 tests)
- **AlertMatcher**: 6 tests covering temporal and label similarity scenarios
- **AlertGrouper**: 4 tests validating service identification and grouping logic
- **CascadeDetector**: 3 tests for dependency inference and correlation strength
- **CorrelationEngine**: 3 integration tests for full engine functionality

### Edge Cases Covered
- Empty and mismatched label sets
- Temporal ordering edge cases
- Service identification fallback scenarios
- Cross-instance alert collection failures
- Partial instance availability during correlation

## AI Agent Usage Patterns

### Incident Investigation
AI agents can now collect alerts from all instances and correlate them to understand the complete incident scope across clusters and regions.

### Service Impact Analysis
Agents can group alerts by service to determine which components are affected and focus incident response efforts appropriately.

### Failure Propagation Tracking
Agents can trace alert cascades to identify root causes and understand dependency relationships in distributed systems.

## Future Extensions

### Advanced Correlation Algorithms
- Pluggable similarity algorithms for domain-specific matching
- Machine learning-based correlation strength prediction
- Historical pattern recognition for recurring incident types

### Performance Optimizations
- Caching for frequently correlated alert patterns
- Incremental correlation for streaming alert updates
- Parallel processing for large-scale similarity computations

### Enhanced Cascade Detection
- Probabilistic modeling for complex dependency chains
- Multi-hop cascade analysis across service boundaries
- Integration with service mesh topology data

## Self-Check
✅ All created files exist:
- src/prometheus_mcp/correlation.py
- src/prometheus_mcp/tools_correlation.py
- tests/test_correlation.py
- Extended src/prometheus_mcp/models.py

✅ All tests pass:
- 16/16 correlation tests passing
- No regressions in existing functionality

✅ Implementation follows all requirements:
- Cross-instance alert matching (COR-01) ✅
- Alert grouping by service (COR-02) ✅
- Cascading alert detection (COR-03) ✅
- Integration with federation infrastructure ✅
- Dual-channel output patterns ✅

## Decisions Made

1. **Jaccard Similarity for Labels**: Chose Jaccard index over cosine similarity for label comparison as it better handles the categorical nature of alert labels.

2. **Hierarchical Service Identification**: Implemented job → service → app → namespace → component priority for service identification to handle diverse labeling practices.

3. **Temporal Cascade Window**: Set 10-minute maximum delay for cascade detection to balance comprehensiveness with relevance.

4. **Strength Thresholds**: Established 0.3 minimum strength for cascade detection and 0.7 for correlation to reduce false positives.

## Metrics

**Duration:** 2 hours
**Completed:** 2026-06-18
**Tasks Completed:** 4/4 weeks of implementation
**Files Created/Modified:** 5 files
**Lines of Code:** ~600 LOC (core implementation)
**Test Coverage:** 16 comprehensive unit tests

## TDD Gate Compliance

✅ **RED Gate**: Tests written first for all major functionality
✅ **GREEN Gate**: Implementation to make all tests pass
✅ **REFACTOR Gate**: Code organization and optimization with maintained test passage