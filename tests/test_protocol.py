"""Wire-protocol smoke-test (substitute for MCP Inspector).

FastMCP exposes ``mcp.list_tools()`` as the in-process equivalent of the
``tools/list`` MCP request. Running it confirms that:

- The shared ``FastMCP`` instance actually has tools registered.
- Each tool carries the expected ``annotations`` (readOnlyHint, etc.).
- The ``outputSchema`` is generated from the TypedDict return annotation.
- The ``inputSchema`` contains the right param names, constraints, and
  required markers — what an MCP client would use to build tool-call arguments.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

# Importing tools attaches @mcp.tool decorators.
import prometheus_mcp.tools  # noqa: F401
import prometheus_mcp.tools_alertmanager  # noqa: F401
import prometheus_mcp.tools_status  # noqa: F401
from prometheus_mcp._mcp import mcp

EXPECTED_TOOLS: dict[str, dict[str, Any]] = {
    "prometheus_list_metrics": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": {"pattern"},
    },
    "prometheus_query": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": {"query"},
        "optional_params": {"time"},
    },
    "prometheus_query_range": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": {"query", "start", "end", "step"},
        "optional_params": set(),
    },
    "prometheus_list_alerts": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
    "prometheus_list_targets": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": {"state"},
    },
    "prometheus_get_metric_metadata": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": {"metric"},
    },
    "prometheus_list_label_values": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": {"label"},
        "optional_params": {"match"},
    },
    "prometheus_list_rules": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": {"type"},
    },
    "prometheus_health_check": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
    "prometheus_get_cardinality": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
    "prometheus_get_runtime_info": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
    "prometheus_get_build_info": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
    "alertmanager_list_silences": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
    "alertmanager_list_alerts": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
    "alertmanager_get_status": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
    "alertmanager_list_alert_groups": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "required_params": set(),
        "optional_params": set(),
    },
}


@pytest.fixture(scope="module")
def listed_tools() -> list[Any]:
    """One-shot handshake equivalent: fetch the tool catalogue FastMCP exposes."""
    return asyncio.run(mcp.list_tools())


def test_all_sixteen_tools_registered(listed_tools: list[Any]) -> None:
    names = {t.name for t in listed_tools}
    assert names == set(EXPECTED_TOOLS), (
        f"tool list mismatch.\n  registered: {sorted(names)}\n  expected:   {sorted(EXPECTED_TOOLS)}"
    )


@pytest.mark.parametrize("tool_name", list(EXPECTED_TOOLS))
def test_tool_annotations(listed_tools: list[Any], tool_name: str) -> None:
    """Every tool must carry readOnly/destructive/idempotent hints matching our design."""
    tool = next(t for t in listed_tools if t.name == tool_name)
    ann = tool.annotations
    expected = EXPECTED_TOOLS[tool_name]
    assert ann.readOnlyHint is expected["readOnlyHint"], f"{tool_name}.readOnlyHint"
    assert ann.destructiveHint is expected["destructiveHint"], f"{tool_name}.destructiveHint"
    assert ann.idempotentHint is expected["idempotentHint"], f"{tool_name}.idempotentHint"


@pytest.mark.parametrize("tool_name", list(EXPECTED_TOOLS))
def test_input_schema_shape(listed_tools: list[Any], tool_name: str) -> None:
    """Required + optional parameter sets must match the tool signatures."""
    tool = next(t for t in listed_tools if t.name == tool_name)
    schema = tool.inputSchema
    assert schema["type"] == "object"
    properties = set(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))

    expected = EXPECTED_TOOLS[tool_name]
    assert required == expected["required_params"], (
        f"{tool_name}.required: got {required}, expected {expected['required_params']}"
    )
    expected_all = expected["required_params"] | expected["optional_params"]
    assert expected_all.issubset(properties), f"{tool_name}: missing properties {expected_all - properties}"


@pytest.mark.parametrize("tool_name", list(EXPECTED_TOOLS))
def test_output_schema_is_generated(listed_tools: list[Any], tool_name: str) -> None:
    """structured_output=True must produce an outputSchema for every tool."""
    tool = next(t for t in listed_tools if t.name == tool_name)
    assert tool.outputSchema is not None, f"{tool_name} has no outputSchema"
    assert tool.outputSchema.get("type") == "object", f"{tool_name} outputSchema not an object"
    assert tool.outputSchema.get("properties"), f"{tool_name} outputSchema has no properties"


def test_query_has_query_as_required(listed_tools: list[Any]) -> None:
    tool = next(t for t in listed_tools if t.name == "prometheus_query")
    schema = tool.inputSchema
    assert "query" in schema.get("required", [])


def test_query_range_all_four_params_required(listed_tools: list[Any]) -> None:
    tool = next(t for t in listed_tools if t.name == "prometheus_query_range")
    schema = tool.inputSchema
    required = set(schema.get("required", []))
    assert required == {"query", "start", "end", "step"}


def test_list_metrics_pattern_description_explains_filter(listed_tools: list[Any]) -> None:
    """The pattern param description should explain substring filtering."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_metrics")
    props = tool.inputSchema.get("properties", {})
    pattern_desc = props.get("pattern", {}).get("description", "")
    assert "substring" in pattern_desc or "filter" in pattern_desc


def test_query_range_step_description_mentions_format(listed_tools: list[Any]) -> None:
    """The step param must document valid formats."""
    tool = next(t for t in listed_tools if t.name == "prometheus_query_range")
    step_desc = tool.inputSchema["properties"]["step"].get("description", "")
    assert "15s" in step_desc or "1m" in step_desc or "Duration" in step_desc


def test_list_targets_state_description_lists_options(listed_tools: list[Any]) -> None:
    """The state param must list the valid options."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_targets")
    state_desc = tool.inputSchema["properties"]["state"].get("description", "")
    assert "active" in state_desc
    assert "dropped" in state_desc
    assert "any" in state_desc


def test_query_time_param_is_optional(listed_tools: list[Any]) -> None:
    """time param in prometheus_query must not be in required list."""
    tool = next(t for t in listed_tools if t.name == "prometheus_query")
    schema = tool.inputSchema
    assert "time" not in schema.get("required", [])


def test_list_alerts_has_no_required_params(listed_tools: list[Any]) -> None:
    """prometheus_list_alerts takes no parameters."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_alerts")
    schema = tool.inputSchema
    assert schema.get("required", []) == [] or "required" not in schema


def test_list_metrics_output_schema_has_metrics_field(listed_tools: list[Any]) -> None:
    """Output schema for list_metrics must include 'metrics' field."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_metrics")
    props = tool.outputSchema.get("properties", {})
    assert "metrics" in props


def test_query_output_schema_has_data_field(listed_tools: list[Any]) -> None:
    """Output schema for query must include 'data' and 'result_type'."""
    tool = next(t for t in listed_tools if t.name == "prometheus_query")
    props = tool.outputSchema.get("properties", {})
    assert "data" in props
    assert "result_type" in props


def test_query_range_output_schema_has_truncated_field(listed_tools: list[Any]) -> None:
    """Output schema for query_range must include 'truncated' for the 5000-point cap."""
    tool = next(t for t in listed_tools if t.name == "prometheus_query_range")
    props = tool.outputSchema.get("properties", {})
    assert "truncated" in props


def test_list_alerts_output_schema_has_firing_count(listed_tools: list[Any]) -> None:
    """Output schema for list_alerts must include 'firing_count'."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_alerts")
    props = tool.outputSchema.get("properties", {})
    assert "firing_count" in props


def test_list_targets_output_schema_has_job_summary(listed_tools: list[Any]) -> None:
    """Output schema for list_targets must include 'job_summary'."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_targets")
    props = tool.outputSchema.get("properties", {})
    assert "job_summary" in props


# ── New investigation tool schema tests ───────────────────────────────────────


def test_metadata_output_schema_has_metadata_field(listed_tools: list[Any]) -> None:
    """Output schema for get_metric_metadata must include 'metadata' field."""
    tool = next(t for t in listed_tools if t.name == "prometheus_get_metric_metadata")
    props = tool.outputSchema.get("properties", {})
    assert "metadata" in props


def test_label_values_output_schema_has_values_field(listed_tools: list[Any]) -> None:
    """Output schema for list_label_values must include 'values' field."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_label_values")
    props = tool.outputSchema.get("properties", {})
    assert "values" in props


def test_label_values_label_is_required(listed_tools: list[Any]) -> None:
    """label param in prometheus_list_label_values must be required."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_label_values")
    schema = tool.inputSchema
    assert "label" in schema.get("required", [])


def test_rules_output_schema_has_groups_field(listed_tools: list[Any]) -> None:
    """Output schema for list_rules must include 'groups' field."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_rules")
    props = tool.outputSchema.get("properties", {})
    assert "groups" in props


def test_rules_type_param_is_optional(listed_tools: list[Any]) -> None:
    """type param in prometheus_list_rules must not be required."""
    tool = next(t for t in listed_tools if t.name == "prometheus_list_rules")
    schema = tool.inputSchema
    assert "type" not in schema.get("required", [])
