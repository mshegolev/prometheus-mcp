"""Shared test fixtures for the prometheus-mcp test suite.

Provides the client-cache reset fixture used by both integration tests
and client-cache tests. Centralising this eliminates duplication and
ensures consistent cleanup between test runs.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from prometheus_mcp import _mcp


@pytest.fixture()
def reset_client_cache() -> Generator[None, None, None]:
    """Reset the module-global PrometheusClient cache before and after a test.

    This fixture acquires ``_mcp._client_lock``, closes any existing client,
    and sets ``_mcp._client = None``. It yields, then repeats cleanup after
    the test to prevent leaking state to subsequent tests.

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
    """Close the cached client (if any) and clear the cache."""
    with _mcp._client_lock:
        if _mcp._client is not None:
            try:
                _mcp._client.close()
            except Exception:
                pass
        _mcp._client = None
