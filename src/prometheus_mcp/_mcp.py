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


def _ensure_registry() -> InstanceRegistry:
    """Return the process-global registry, lazily building it on first use.

    In production the registry is created eagerly by :func:`app_lifespan`.
    When tool functions are invoked directly — in tests, or before the server
    lifespan has run — ``_registry`` is still ``None``; we build it here using
    the same rules as startup: load ``PROMETHEUS_MCP_CONFIG`` if set
    (federation mode), otherwise ``None`` for v2.0 legacy mode, where clients
    read their endpoint/auth from ``PROMETHEUS_*`` / ``ALERTMANAGER_*`` env
    vars on first access.

    This restores the pre-v3.0 ``get_client`` contract (thread-safe lazy-init
    from the environment) that the federation refactor accidentally dropped.

    Thread-safe via double-checked locking on ``_registry_lock``.
    """
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                config_path = os.environ.get("PROMETHEUS_MCP_CONFIG")
                config = load_config(config_path) if config_path else None
                _registry = InstanceRegistry(config)
    return _registry


def get_registry() -> InstanceRegistry:
    """Return the live :class:`InstanceRegistry`.

    Tools MUST call this at request time rather than importing the
    module-global ``_registry`` by value: ``_registry`` is ``None`` at import
    and only assigned during :func:`app_lifespan` startup, so a captured
    ``from _mcp import _registry`` binding stays frozen at ``None`` forever.

    Unlike :func:`get_client`, this does NOT lazily build a registry: the
    federation/correlation tools that use it require a genuinely initialized
    multi-instance registry (from ``app_lifespan`` or an explicit test mock),
    not a best-effort legacy default synthesized from env vars.

    Raises:
        RuntimeError: If the registry has not been initialized (app not started).
    """
    if _registry is None:
        raise RuntimeError("Registry not initialized - app not started")
    return _registry


def get_client(instance: str | None = None) -> PrometheusClient:
    """Return a :class:`PrometheusClient` for the specified instance.

    Args:
        instance: Instance name, or None for default instance (v2.0 compatibility).

    Returns:
        Prometheus client for the specified instance.

    Raises:
        ConfigError: If instance name is unknown or has no Prometheus URL.
    """
    registry = _ensure_registry()
    return registry.get_prometheus_client("default" if instance is None else instance)


def get_alertmanager_client(instance: str | None = None) -> AlertmanagerClient:
    """Return an :class:`AlertmanagerClient` for the specified instance.

    Args:
        instance: Instance name, or None for default instance (v2.0 compatibility).

    Returns:
        Alertmanager client for the specified instance.

    Raises:
        ConfigError: If instance name is unknown or has no Alertmanager URL.
    """
    registry = _ensure_registry()
    return registry.get_alertmanager_client("default" if instance is None else instance)
