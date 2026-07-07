"""FastMCP server entry point for Prometheus MCP."""

from __future__ import annotations

# Importing the tools module attaches @mcp.tool decorators to the shared
# FastMCP instance.
from prometheus_mcp import tools as _tools  # noqa: F401
from prometheus_mcp import tools_alertmanager as _tools_am  # noqa: F401
from prometheus_mcp import tools_correlation as _tools_corr  # noqa: F401
from prometheus_mcp import tools_federation as _tools_fed  # noqa: F401
from prometheus_mcp import tools_status as _tools_status  # noqa: F401
from prometheus_mcp._mcp import app_lifespan, mcp

# NOTE: ``tools_federation_v4`` (``federation_analyze_alerts``) is intentionally
# NOT imported. Its implementation references APIs that do not exist
# (e.g. ``PrometheusClient.list_alerts``/``query``, ``output.warn``,
# ``registry.get_all_clients``) and crashes on first call. It must be rewritten
# against the real engine/client APIs before being registered. See CHANGELOG.


def main() -> None:
    """Entry point for the ``prometheus-mcp`` console script (stdio)."""
    mcp.run()


__all__ = ["mcp", "app_lifespan", "main"]


if __name__ == "__main__":
    main()
