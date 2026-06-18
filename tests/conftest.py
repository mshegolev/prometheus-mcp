"""Shared test fixtures for the prometheus-mcp test suite.

Provides the client-cache reset fixture used by both integration tests
and client-cache tests. Centralising this eliminates duplication and
ensures consistent cleanup between test runs.
"""

from __future__ import annotations

import threading
from collections.abc import Generator

import pytest

from prometheus_mcp import _mcp
from prometheus_mcp.cache import get_metrics_cache


@pytest.fixture()
def reset_client_cache() -> Generator[None, None, None]:
    """Reset the module-global PrometheusClient cache and metrics cache.

    This fixture closes any existing registry clients,
    sets the global registry to None, and clears the metrics TTL cache.
    It yields, then repeats cleanup after the test.

    Usage:
        Apply via ``@pytest.mark.usefixtures("reset_client_cache")`` on a
        class/module, or include ``reset_client_cache`` in the test function
        signature.  For autouse in a module, define a local fixture that
        delegates::

            @pytest.fixture(autouse=True)
            def _auto_reset(reset_client_cache):
                pass
    """
    _do_reset()
    yield
    _do_reset()


def _do_reset() -> None:
    """Close the cached clients (if any), clear client and metrics caches."""
    # Close any existing registry
    if _mcp._registry is not None:
        try:
            _mcp._registry.close_all()
        except Exception:
            pass

    # Reset global registry to None
    with _mcp._registry_lock:
        _mcp._registry = None

    # Clear the metrics TTL cache to prevent cross-test contamination.
    get_metrics_cache().clear()
