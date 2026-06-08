"""HTTP client for the Alertmanager API v2.

Same pattern as :class:`PrometheusClient` — reads config from env vars,
supports Bearer/Basic auth, SSL-verify toggling. Uses ``/api/v2`` base path
(Alertmanager API v2).

The Alertmanager is a separate service from Prometheus with its own URL.
Configuration uses ``ALERTMANAGER_URL`` (and optionally ``ALERTMANAGER_TOKEN``,
``ALERTMANAGER_USERNAME``, ``ALERTMANAGER_PASSWORD``, ``ALERTMANAGER_SSL_VERIFY``).
If ``ALERTMANAGER_URL`` is not set, Alertmanager tools will raise a
:class:`ConfigError`.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
import urllib3

from prometheus_mcp.client import _MAX_RETRIES, _RETRY_BACKOFF, _parse_bool, _validate_url
from prometheus_mcp.errors import ConfigError

logger = logging.getLogger(__name__)


class AlertmanagerClient:
    """Minimal Alertmanager API v2 client.

    Reads ``ALERTMANAGER_URL``, ``ALERTMANAGER_TOKEN``, etc. from the
    environment. Same auth priority as PrometheusClient:
    Bearer > Basic > none.

    Args:
        url: Override ``ALERTMANAGER_URL``. If ``None``, read from env.
        token: Override ``ALERTMANAGER_TOKEN``. If ``None``, read from env.
        username: Override ``ALERTMANAGER_USERNAME``. If ``None``, read from env.
        password: Override ``ALERTMANAGER_PASSWORD``. If ``None``, read from env.
        ssl_verify: Override ``ALERTMANAGER_SSL_VERIFY``. If ``None``, read from env.

    Raises:
        ConfigError: If ALERTMANAGER_URL is missing or malformed.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        ssl_verify: bool | None = None,
    ) -> None:
        raw_url = url if url is not None else os.environ.get("ALERTMANAGER_URL", "")
        if not raw_url:
            raise ConfigError(
                "ALERTMANAGER_URL is not set — configure the env var "
                "(e.g. https://alertmanager.example.com). "
                "Alertmanager tools require a separate URL from Prometheus."
            )
        self.url = _validate_url(raw_url)
        self.api_url = f"{self.url}/api/v2"

        self.token = token if token is not None else os.environ.get("ALERTMANAGER_TOKEN", "")
        self.username = username if username is not None else os.environ.get("ALERTMANAGER_USERNAME", "")
        self.password = password if password is not None else os.environ.get("ALERTMANAGER_PASSWORD", "")

        if ssl_verify is None:
            ssl_verify = _parse_bool(os.environ.get("ALERTMANAGER_SSL_VERIFY"), default=True)
        self.ssl_verify = ssl_verify

        self.session = requests.Session()
        self.session.verify = self.ssl_verify
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "prometheus-mcp",
            }
        )
        self.session.trust_env = False

        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"
        elif self.username and self.password:
            self.session.auth = (self.username, self.password)

        if not self.ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Return ``True`` for transient failures."""
        if isinstance(exc, requests.ConnectionError):
            return True
        if isinstance(exc, requests.Timeout):
            return True
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return exc.response.status_code >= 500
        return False

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``{api_url}{endpoint}`` and return parsed JSON."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self.session.request(
                    method="GET",
                    url=f"{self.api_url}{endpoint}",
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                if not response.content:
                    return None
                return response.json()
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES and self._is_retryable(exc):
                    logger.debug(
                        "prometheus_mcp: retrying AM GET %s after %s",
                        endpoint,
                        type(exc).__name__,
                    )
                    time.sleep(_RETRY_BACKOFF)
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()
