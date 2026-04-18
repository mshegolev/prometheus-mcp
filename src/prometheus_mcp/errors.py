"""Actionable error messages for Prometheus HTTP errors."""

from __future__ import annotations

import requests


class ConfigError(ValueError):
    """Raised when required environment variables are missing or malformed.

    Subclass of :class:`ValueError` so callers can continue to use
    ``isinstance(..., ValueError)``, but narrow enough that :func:`handle`
    can distinguish config errors from Pydantic validation errors bubbling
    up from tool input.
    """


def handle(exc: Exception, action: str) -> str:
    """Convert an exception raised while performing ``action`` into an
    LLM-readable string with a suggested next step.

    The goal is that the agent sees *why* the call failed and *what it could
    do about it* without needing to inspect a Python traceback.
    """
    if isinstance(exc, ConfigError):
        return (
            f"Error: configuration problem while {action} — {exc}. "
            "Check PROMETHEUS_URL, PROMETHEUS_TOKEN, PROMETHEUS_USERNAME, PROMETHEUS_PASSWORD, "
            "PROMETHEUS_SSL_VERIFY environment variables."
        )

    if isinstance(exc, requests.HTTPError):
        code = exc.response.status_code if exc.response is not None else None
        if code == 401:
            return (
                f"Error: authentication failed (HTTP 401) while {action}. "
                "Verify PROMETHEUS_TOKEN (Bearer) or PROMETHEUS_USERNAME/PROMETHEUS_PASSWORD (Basic auth) "
                "are set correctly. Many internal Prometheus instances require no auth — "
                "try unsetting those env vars if this is an internal deployment."
            )
        if code == 403:
            return (
                f"Error: forbidden (HTTP 403) while {action}. "
                "The provided credentials lack permission for this Prometheus resource. "
                "Check PROMETHEUS_TOKEN or PROMETHEUS_USERNAME/PROMETHEUS_PASSWORD and "
                "Prometheus's auth configuration."
            )
        if code == 404:
            return (
                f"Error: resource not found (HTTP 404) while {action}. "
                "Check PROMETHEUS_URL points to a valid Prometheus instance. "
                "Use prometheus_list_metrics to discover valid metric names."
            )
        if code in (400, 422):
            body = ""
            if exc.response is not None:
                try:
                    data = exc.response.json()
                    body = data.get("error", exc.response.text[:300])
                except Exception:
                    body = exc.response.text[:300]
            return (
                f"Error: bad request (HTTP {code}) while {action}. "
                "Prometheus rejected the parameters — check your PromQL expression syntax, "
                "time range, or step value. "
                f"Prometheus error: {body}"
            )
        if code == 429:
            return (
                f"Error: rate-limited (HTTP 429) while {action}. "
                "Wait 30-60s before retrying; narrow the time range or reduce the step resolution."
            )
        if code is not None and 500 <= code < 600:
            return (
                f"Error: Prometheus server error (HTTP {code}) while {action}. "
                "This is usually transient — retry in a few seconds; "
                "check Prometheus health at PROMETHEUS_URL/-/healthy."
            )
        body = ""
        if exc.response is not None:
            try:
                body = exc.response.text[:200]
            except Exception:
                pass
        return f"Error: HTTP {code} while {action}. Response: {body}"

    if isinstance(exc, requests.ConnectionError):
        return (
            f"Error: could not connect to Prometheus while {action}. "
            "Check PROMETHEUS_URL is set and reachable (e.g. https://prometheus.example.com). "
            "Prometheus HTTP API runs on port 9090 by default."
        )

    if isinstance(exc, requests.Timeout):
        return (
            f"Error: request timed out while {action}. "
            "Check network latency and retry; narrow the time range or increase the step for range queries."
        )

    if isinstance(exc, ValueError):
        return f"Error: invalid input while {action} — {exc}"

    return f"Error: unexpected {type(exc).__name__} while {action}: {exc}"
