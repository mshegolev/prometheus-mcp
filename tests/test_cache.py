"""Tests for the TTL cache in :mod:`prometheus_mcp.cache`."""

from __future__ import annotations

import time

from prometheus_mcp.cache import TTLCache


class TestTTLCache:
    def test_set_and_get(self) -> None:
        cache = TTLCache(ttl=60.0)
        cache.set("key1", ["a", "b", "c"])
        assert cache.get("key1") == ["a", "b", "c"]

    def test_get_missing_returns_none(self) -> None:
        cache = TTLCache(ttl=60.0)
        assert cache.get("nonexistent") is None

    def test_expired_returns_none(self) -> None:
        cache = TTLCache(ttl=0.01)  # 10ms TTL
        cache.set("key1", "value")
        time.sleep(0.02)
        assert cache.get("key1") is None

    def test_ttl_zero_disables_cache(self) -> None:
        cache = TTLCache(ttl=0)
        cache.set("key1", "value")
        assert cache.get("key1") is None

    def test_negative_ttl_disables_cache(self) -> None:
        cache = TTLCache(ttl=-1)
        cache.set("key1", "value")
        assert cache.get("key1") is None

    def test_clear_removes_all(self) -> None:
        cache = TTLCache(ttl=60.0)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        assert cache.get("k1") is None
        assert cache.get("k2") is None

    def test_overwrite_key(self) -> None:
        cache = TTLCache(ttl=60.0)
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"

    def test_ttl_property(self) -> None:
        cache = TTLCache(ttl=42.0)
        assert cache.ttl == 42.0
