"""Tests for the module-level client cache in :mod:`prometheus_mcp._mcp`.

``get_client`` lazily instantiates a single :class:`PrometheusClient`
protected by a lock (double-checked locking). This test covers the happy
path — repeated calls return the *same* instance, and wiping the global
cache rebuilds the client.
"""

from __future__ import annotations

import pytest

from prometheus_mcp import _mcp
from prometheus_mcp.client import PrometheusClient


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    """Clear the module-global client between tests to avoid test-order coupling."""
    with _mcp._client_lock:
        if _mcp._client is not None:
            try:
                _mcp._client.close()
            except Exception:
                pass
        _mcp._client = None


def test_get_client_returns_same_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
    first = _mcp.get_client()
    second = _mcp.get_client()
    assert first is second
    assert isinstance(first, PrometheusClient)


def test_get_client_raises_on_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    with pytest.raises(Exception, match="PROMETHEUS_URL"):
        _mcp.get_client()


def test_cache_rebuilds_after_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
    first = _mcp.get_client()
    with _mcp._client_lock:
        _mcp._client = None
    second = _mcp.get_client()
    assert first is not second


def test_get_client_no_auth_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prometheus allows unauthenticated access — client should build without token."""
    monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.internal")
    monkeypatch.delenv("PROMETHEUS_TOKEN", raising=False)
    monkeypatch.delenv("PROMETHEUS_USERNAME", raising=False)
    monkeypatch.delenv("PROMETHEUS_PASSWORD", raising=False)
    client = _mcp.get_client()
    assert isinstance(client, PrometheusClient)
    assert client.token == ""
