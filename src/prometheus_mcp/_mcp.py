"""Shared FastMCP instance and client cache."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from prometheus_mcp.alertmanager_client import AlertmanagerClient
from prometheus_mcp.client import PrometheusClient

logger = logging.getLogger(__name__)

_client: PrometheusClient | None = None
_client_lock = threading.Lock()

_am_client: AlertmanagerClient | None = None
_am_client_lock = threading.Lock()


@asynccontextmanager
async def app_lifespan(_app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Server lifespan: close HTTP sessions on shutdown."""
    logger.debug("prometheus_mcp: startup")
    try:
        yield {}
    finally:
        global _client, _am_client
        with _client_lock:
            if _client is not None:
                try:
                    _client.close()
                except Exception:
                    pass
                _client = None
        with _am_client_lock:
            if _am_client is not None:
                try:
                    _am_client.close()
                except Exception:
                    pass
                _am_client = None
        logger.debug("prometheus_mcp: shutdown — HTTP sessions closed")


mcp = FastMCP("prometheus_mcp", lifespan=app_lifespan)


def get_client() -> PrometheusClient:
    """Return a cached :class:`PrometheusClient` (thread-safe lazy-init)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = PrometheusClient()
    return _client


def get_alertmanager_client() -> AlertmanagerClient:
    """Return a cached :class:`AlertmanagerClient` (thread-safe lazy-init).

    Raises :class:`ConfigError` if ``ALERTMANAGER_URL`` is not set.
    """
    global _am_client
    if _am_client is None:
        with _am_client_lock:
            if _am_client is None:
                _am_client = AlertmanagerClient()
    return _am_client
