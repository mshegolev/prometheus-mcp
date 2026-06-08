"""Thread-safe TTL cache for expensive Prometheus lookups.

Currently caches metric name lists (``GET /api/v1/label/__name__/values``),
which are expensive on large Prometheus instances (500K+ metrics) and change
slowly. Query results are **never** cached — time-varying data must always
be fresh.

The TTL is controlled by ``PROMETHEUS_CACHE_TTL`` (default 300 seconds).
Set to ``0`` to disable caching entirely.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

_DEFAULT_CACHE_TTL = 300  # seconds


def _get_cache_ttl() -> float:
    """Read cache TTL from environment, defaulting to 300s."""
    env_ttl = os.environ.get("PROMETHEUS_CACHE_TTL", "")
    if env_ttl:
        try:
            return float(env_ttl)
        except ValueError:
            return float(_DEFAULT_CACHE_TTL)
    return float(_DEFAULT_CACHE_TTL)


class TTLCache:
    """Simple thread-safe TTL cache.

    Stores a single cached value per key with a monotonic expiry timestamp.
    Thread safety is provided by a :class:`threading.Lock`.
    """

    def __init__(self, ttl: float | None = None) -> None:
        self._ttl = ttl if ttl is not None else _get_cache_ttl()
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    @property
    def ttl(self) -> float:
        return self._ttl

    def get(self, key: str) -> Any | None:
        """Return cached value if still valid, else ``None``."""
        if self._ttl <= 0:
            return None
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        """Store a value with TTL-based expiry."""
        if self._ttl <= 0:
            return
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._store.clear()


# Module-level singleton used by tools.
_metrics_cache: TTLCache | None = None
_cache_lock = threading.Lock()


def get_metrics_cache() -> TTLCache:
    """Return the module-level metrics cache (lazy-init, thread-safe)."""
    global _metrics_cache
    if _metrics_cache is None:
        with _cache_lock:
            if _metrics_cache is None:
                _metrics_cache = TTLCache()
    return _metrics_cache
