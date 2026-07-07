"""Smoke test: every implemented tool is actually registered on the server.

This guards against the class of bug where a fully-written, fully-unit-tested
tool module is never imported by ``server.py`` and therefore contributes zero
tools at runtime (``@mcp.tool`` only fires as an import side effect).

It imports the real console-script entry point (``prometheus_mcp.server``) and
asserts the tool set the server actually exposes -- not what the modules define
in isolation.
"""

from __future__ import annotations

import asyncio

# Tools we expect the server to expose. ``federation_analyze_alerts`` is
# intentionally excluded: its implementation references APIs that do not exist
# and must be rewritten before it can be registered (see CHANGELOG / review).
EXPECTED_TOOLS = {
    # Core query / discovery (tools.py)
    "prometheus_query",
    "prometheus_query_range",
    "prometheus_list_metrics",
    "prometheus_list_label_values",
    "prometheus_list_alerts",
    "prometheus_list_rules",
    "prometheus_list_targets",
    "prometheus_get_metric_metadata",
    # Status (tools_status.py)
    "prometheus_health_check",
    "prometheus_get_build_info",
    "prometheus_get_runtime_info",
    "prometheus_get_cardinality",
    # Alertmanager (tools_alertmanager.py)
    "alertmanager_list_alerts",
    "alertmanager_list_alert_groups",
    "alertmanager_list_silences",
    "alertmanager_get_status",
    # Correlation (tools_correlation.py)
    "correlate_alerts_across_instances",
    "group_alerts_by_service",
    "detect_cascading_alerts",
    # Federation (tools_federation.py)
    "federation_list_instances",
}


def _registered_tool_names() -> set[str]:
    from prometheus_mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    return {t.name for t in tools}


def test_all_expected_tools_registered() -> None:
    """The server exposes exactly the expected tool set."""
    registered = _registered_tool_names()

    missing = EXPECTED_TOOLS - registered
    assert not missing, f"Expected tools not registered by server.py: {sorted(missing)}"


def test_no_unexpected_tools_registered() -> None:
    """Catch tools that get added without updating this guard."""
    registered = _registered_tool_names()

    unexpected = registered - EXPECTED_TOOLS
    assert not unexpected, (
        f"Server registers tools missing from EXPECTED_TOOLS: {sorted(unexpected)}. "
        "If intentional, add them to EXPECTED_TOOLS."
    )
