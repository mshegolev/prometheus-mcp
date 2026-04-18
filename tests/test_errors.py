"""Unit tests for :mod:`prometheus_mcp.errors`.

Verifies that every HTTP status we special-case produces an actionable
message that names the relevant env vars where appropriate and hints at
a concrete next step. Network failures are simulated via :mod:`responses`.
"""

from __future__ import annotations

import pytest
import requests
import responses

from prometheus_mcp.errors import ConfigError, handle


def _http_error(
    status: int,
    url: str = "https://prometheus.example.com/api/v1/label/__name__/values",
    body: str | None = None,
    json_body: dict | None = None,
) -> requests.HTTPError:
    """Trigger a real ``requests.HTTPError`` carrying a response with ``status``."""
    with responses.RequestsMock() as rsps:
        if json_body is not None:
            rsps.add(responses.GET, url, json=json_body, status=status)
        elif body is None:
            rsps.add(responses.GET, url, json={}, status=status)
        else:
            rsps.add(responses.GET, url, body=body, status=status)
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
        except requests.HTTPError as e:
            return e
    raise AssertionError(f"expected HTTPError for status {status}")  # pragma: no cover


class TestConfigError:
    def test_message_mentions_env_vars(self) -> None:
        msg = handle(ConfigError("PROMETHEUS_URL is not set"), "listing metrics")
        assert "configuration problem" in msg
        assert "listing metrics" in msg
        assert "PROMETHEUS_URL" in msg
        assert "PROMETHEUS_TOKEN" in msg

    def test_message_mentions_ssl_verify(self) -> None:
        msg = handle(ConfigError("bad ssl"), "connecting")
        assert "PROMETHEUS_SSL_VERIFY" in msg

    def test_config_error_mentions_username(self) -> None:
        msg = handle(ConfigError("missing credentials"), "querying")
        assert "PROMETHEUS_USERNAME" in msg


class TestHttpStatusMapping:
    def test_401_mentions_token_and_basic(self) -> None:
        msg = handle(_http_error(401), "listing metrics")
        assert "401" in msg
        assert "PROMETHEUS_TOKEN" in msg
        assert "PROMETHEUS_USERNAME" in msg or "Basic" in msg

    def test_401_suggests_unauthenticated_option(self) -> None:
        msg = handle(_http_error(401), "listing metrics")
        assert "no auth" in msg.lower() or "unauthenticated" in msg.lower() or "internal" in msg.lower()

    def test_403_mentions_credentials(self) -> None:
        msg = handle(_http_error(403), "querying metrics")
        assert "403" in msg
        assert "PROMETHEUS_TOKEN" in msg or "credentials" in msg.lower() or "permission" in msg.lower()
        assert "querying metrics" in msg

    def test_404_suggests_url_check(self) -> None:
        msg = handle(_http_error(404), "querying")
        assert "404" in msg
        assert "PROMETHEUS_URL" in msg

    def test_400_includes_body_snippet(self) -> None:
        err = _http_error(400, json_body={"status": "error", "error": "invalid parameter syntax"})
        msg = handle(err, "executing query")
        assert "400" in msg
        assert "invalid parameter syntax" in msg or "PromQL" in msg

    def test_422_mentions_step(self) -> None:
        err = _http_error(422, json_body={"status": "error", "error": "exceeded maximum resolution"})
        msg = handle(err, "range query")
        assert "422" in msg
        assert "step" in msg.lower() or "PromQL" in msg or "resolution" in msg or "range" in msg

    def test_429_suggests_backoff(self) -> None:
        msg = handle(_http_error(429), "querying")
        assert "429" in msg
        assert "Wait" in msg or "rate" in msg or "limit" in msg or "narrow" in msg

    @pytest.mark.parametrize("code", [500, 502, 503, 504])
    def test_5xx_flags_transient(self, code: int) -> None:
        msg = handle(_http_error(code), "fetching targets")
        assert str(code) in msg
        assert "transient" in msg or "healthy" in msg

    def test_unknown_4xx_includes_body_snippet(self) -> None:
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.GET,
                "https://prometheus.example.com/api/v1/x",
                body="teapot!" * 50,
                status=418,
            )
            try:
                r = requests.get("https://prometheus.example.com/api/v1/x", timeout=5)
                r.raise_for_status()
            except requests.HTTPError as e:
                msg = handle(e, "teapot call")
                assert "418" in msg
                assert "teapot" in msg


class TestNetworkErrors:
    def test_connection_error_mentions_url_and_port(self) -> None:
        msg = handle(requests.ConnectionError("DNS fail"), "listing metrics")
        assert "connect" in msg.lower()
        assert "PROMETHEUS_URL" in msg
        assert "9090" in msg

    def test_timeout_mentions_step_or_range(self) -> None:
        msg = handle(requests.Timeout("slow"), "range query")
        assert "timed out" in msg
        assert "range" in msg.lower() or "step" in msg.lower() or "narrow" in msg.lower()

    def test_unexpected_exception_fallthrough(self) -> None:
        msg = handle(RuntimeError("kaboom"), "something")
        assert "RuntimeError" in msg
        assert "kaboom" in msg
        assert "something" in msg

    def test_value_error_surfaces_cleanly(self) -> None:
        msg = handle(ValueError("state must be active"), "listing targets")
        assert msg.startswith("Error: invalid input while listing targets")
        assert "state must be active" in msg
        assert "unexpected" not in msg
