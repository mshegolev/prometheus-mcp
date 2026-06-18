"""Shared FastMCP instance and client registry.

Replaced singleton client pattern with InstanceRegistry for multi-instance support.
Backward compatible: when no PROMETHEUS_MCP_CONFIG, operates in v2.0 mode.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from prometheus_mcp.alertmanager_client import AlertmanagerClient
from prometheus_mcp.client import PrometheusClient
from prometheus_mcp.config import load_config
from prometheus_mcp.registry import InstanceRegistry

logger = logging.getLogger(__name__)

# Global registry instance (set during app startup)
_registry: InstanceRegistry | None = None
_registry_lock = threading.Lock()


@asynccontextmanager
async def app_lifespan(_app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Server lifespan: load config, create registry, close sessions on shutdown."""
    global _registry
    logger.debug("prometheus_mcp: startup")

    # Load config if PROMETHEUS_MCP_CONFIG is set, else None for legacy mode
    config_path = os.environ.get("PROMETHEUS_MCP_CONFIG")
    config = None
    if config_path:
        try:
            config = load_config(config_path)
        except Exception as exc:
            logger.error("Failed to load config file %s: %s", config_path, exc)
            raise

    # Create registry (None config = legacy mode)
    with _registry_lock:
        _registry = InstanceRegistry(config)
        registry = _registry

    try:
        yield {}
    finally:
        # Close all HTTP sessions
        try:
            registry.close_all()
        except Exception:
            logger.warning("Error closing HTTP sessions", exc_info=True)
        logger.debug("prometheus_mcp: shutdown — HTTP sessions closed")


mcp = FastMCP("prometheus_mcp", lifespan=app_lifespan)


def get_client(instance: str | None = None) -> PrometheusClient:
    """Return a :class:`PrometheusClient` for the specified instance.

    Args:
        instance: Instance name, or None for default instance (v2.0 compatibility).

    Returns:
        Prometheus client for the specified instance.

    Raises:
        ConfigError: If instance name is unknown or has no Prometheus URL.
    """
    global _registry
    if _registry is None:
        raise RuntimeError("Registry not initialized - app not started")

    if instance is None:
        return _registry.get_prometheus_client("default")
    else:
        return _registry.get_prometheus_client(instance)


def get_alertmanager_client(instance: str | None = None) -> AlertmanagerClient:
    """Return an :class:`AlertmanagerClient` for the specified instance.

    Args:
        instance: Instance name, or None for default instance (v2.0 compatibility).

    Returns:
        Alertmanager client for the specified instance.

    Raises:
        ConfigError: If instance name is unknown or has no Alertmanager URL.
    """
    global _registry
    if _registry is None:
        raise RuntimeError("Registry not initialized - app not started")

    if instance is None:
        return _registry.get_alertmanager_client("default")
    else:
        return _registry.get_alertmanager_client(instance)
