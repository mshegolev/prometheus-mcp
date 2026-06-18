# OpenAPI Specification for Prometheus MCP

This directory contains the OpenAPI specification for the Prometheus MCP server.

## Files

- `openapi.yaml` - The main OpenAPI 3.0 specification document
- `validate_spec.py` - Script to validate the specification

## Overview

The OpenAPI specification documents all MCP tools exposed by the Prometheus MCP server:

1. `prometheus_list_metrics` - List metric names with optional filtering
2. `prometheus_query` - Execute instant PromQL queries
3. `prometheus_query_range` - Execute range PromQL queries
4. `prometheus_list_alerts` - List active and pending alerts
5. `prometheus_list_targets` - List scrape targets by health and job
6. `prometheus_get_metric_metadata` - Retrieve metric metadata
7. `prometheus_list_label_values` - List values for a specific label
8. `prometheus_list_rules` - Inspect recording and alerting rules

## Validation

To validate the specification:

```bash
python3 specs/validate_spec.py
```

## Usage

The specification can be used with any OpenAPI-compatible tooling for:

- Documentation generation
- Client SDK generation
- API testing
- Mock server creation

## License

MIT - see [LICENSE](../LICENSE) in the parent directory.