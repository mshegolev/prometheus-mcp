# Milestone Completed: v3.0 Federation

**Completed:** 2026-06-18
**Status:** ✅ All phases complete

## Overview

The prometheus-mcp v3.0 Federation milestone has been successfully completed. This major release adds multi-instance support for both Prometheus and Alertmanager, enabling federated querying across distributed monitoring setups.

## Key Features Delivered

### 🌐 Federation Support
- **Multi-Instance Config**: JSON configuration file defining named Prometheus instances with per-instance authentication
- **Fan-Out Queries**: Execute PromQL queries across all instances in parallel with `instance="all"`
- **Targeted Queries**: Query specific instances using `instance="name"` parameter
- **Subset Targeting**: Query groups of instances with `instances=["a", "b"]` parameter
- **Result Merging**: Automatic merging of results with `__prometheus_instance__` source labels
- **Partial Failure Handling**: Continue returning available results when some instances fail

### 🚨 Alertmanager Federation
- **Multi-Instance Support**: Configure named Alertmanager instances alongside Prometheus
- **Alert Deduplication**: Automatically deduplicate alerts by fingerprint from HA cluster peers
- **Source Attribution**: Track alert origins with `__alertmanager_instance__` labels
- **Fan-Out Operations**: Execute Alertmanager API calls across all configured instances

### 🔍 Instance Discovery
- **New Tool**: `federation_list_instances` for discovering configured instances
- **Health Monitoring**: Parallel health probing with reachability status and response times
- **Mixed Instance Support**: Unified view of Prometheus and Alertmanager instances
- **Federation Detection**: Automatic detection of multi-instance mode

### ⚙️ Core Infrastructure
- **Instance Registry**: Thread-safe management of N PrometheusClient + AlertmanagerClient pairs
- **Per-Instance Caching**: Independent TTL caches for each instance with configurable TTL
- **Session Lifecycle**: Proper HTTP session management with graceful cleanup
- **Backward Compatibility**: Zero behavioral change when no config file is present

## Implementation Statistics

| Category | Count |
|----------|-------|
| Phases Completed | 7/7 |
| New Modules | 4 (config, registry, federation, tools_federation) |
| Enhanced Tools | 21 (16 Prometheus + 4 Alertmanager + 1 discovery) |
| New Tool Parameters | 42 (instance + instances for all tools) |
| Unit Tests | 297 total (existing + new coverage) |
| Lines of Code | ~1,200 additions across all modules |

## Backward Compatibility

The v3.0 release maintains **100% backward compatibility**:
- When `PROMETHEUS_MCP_CONFIG` is not set, operates identically to v2.0
- All existing tool signatures and behavior preserved
- Environment variable fallback for seamless migration
- Zero code changes required for existing integrations

## Getting Started

### Upgrade from v2.0
```bash
# No changes needed for existing single-instance usage
export PROMETHEUS_URL=https://prometheus.example.com
export PROMETHEUS_TOKEN=your-token
prometheus-mcp

# Enable federation by setting config file path
export PROMETHEUS_MCP_CONFIG=prometheus-mcp.json
```

### Federation Config Example
```json
{
  "version": 1,
  "instances": {
    "prod-us": {
      "prometheus_url": "https://prom-us.prod.example.com",
      "prometheus_token": "prod-token",
      "alertmanager_url": "https://am-us.prod.example.com"
    },
    "prod-eu": {
      "prometheus_url": "https://prom-eu.prod.example.com",
      "prometheus_token": "prod-token",
      "alertmanager_url": "https://am-eu.prod.example.com"
    }
  }
}
```

### New Tool Usage
```python
# Query specific instance
prometheus_query(query="up", instance="prod-us")

# Fan-out to all instances
prometheus_query(query="up", instance="all")

# Target subset of instances
prometheus_query(query="up", instances=["prod-us", "prod-eu"])

# Discover configured instances
federation_list_instances()
```

## Next Steps

The v3.0 Federation release is ready for production use. Future enhancements will focus on:
- Advanced alert correlation across instance pairs
- Alertmanager clustering awareness for intelligent routing
- Performance optimizations for large instance counts
- Cross-cluster alert dependency analysis

---
*Release date: 2026-06-18*
*Version: 0.3.0*