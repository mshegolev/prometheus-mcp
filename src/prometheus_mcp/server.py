"""FastMCP server entry point for Prometheus MCP."""

from __future__ import annotations

# Importing the tools module attaches @mcp.tool decorators to the shared
# FastMCP instance.
from prometheus_mcp import tools as _tools  # noqa: F401
from prometheus_mcp import tools_alertmanager as _tools_am  # noqa: F401
from prometheus_mcp import tools_status as _tools_status  # noqa: F401
from prometheus_mcp._mcp import app_lifespan, mcp


def main() -> None:
    """Entry point for the ``prometheus-mcp`` console script (stdio)."""
    mcp.run()


__all__ = ["mcp", "app_lifespan", "main"]


if __name__ == "__main__":
    main()
