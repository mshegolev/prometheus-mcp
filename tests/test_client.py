"""Unit tests for pure helpers in :mod:`prometheus_mcp.client`.

These tests avoid the network entirely — they cover env-var parsing, URL
validation, :class:`PrometheusClient` construction (which raises
:class:`ConfigError` when PROMETHEUS_URL is missing), and auth selection.
"""

from __future__ import annotations

import pytest

from prometheus_mcp.client import PrometheusClient, _parse_bool, _validate_url
from prometheus_mcp.errors import ConfigError


class TestParseBool:
    @pytest.mark.parametrize("value", ["true", "True", "1", "yes", "on", "YES"])
    def test_truthy_strings(self, value: str) -> None:
        assert _parse_bool(value, default=False) is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "off", "OFF"])
    def test_falsy_strings(self, value: str) -> None:
        assert _parse_bool(value, default=True) is False

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_returns_default(self, value: str | None) -> None:
        assert _parse_bool(value, default=True) is True
        assert _parse_bool(value, default=False) is False

    def test_bool_passthrough(self) -> None:
        assert _parse_bool(True, default=False) is True
        assert _parse_bool(False, default=True) is False


class TestValidateUrl:
    def test_strips_trailing_slash(self) -> None:
        assert _validate_url("https://prometheus.example.com/") == "https://prometheus.example.com"

    def test_strips_whitespace(self) -> None:
        assert _validate_url("  https://prometheus.example.com  ") == "https://prometheus.example.com"

    def test_preserves_no_trailing_slash(self) -> None:
        assert _validate_url("https://prometheus.example.com") == "https://prometheus.example.com"

    def test_http_scheme_allowed(self) -> None:
        assert _validate_url("http://prometheus.local:9090") == "http://prometheus.local:9090"

    def test_empty_raises(self) -> None:
        with pytest.raises(ConfigError, match="PROMETHEUS_URL is not set"):
            _validate_url("")

    def test_missing_scheme_raises(self) -> None:
        with pytest.raises(ConfigError, match="http:// or https://"):
            _validate_url("prometheus.example.com")

    def test_wrong_scheme_raises(self) -> None:
        with pytest.raises(ConfigError, match="http:// or https://"):
            _validate_url("ftp://prometheus.example.com")

    def test_missing_host_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing host"):
            _validate_url("https://")

    def test_url_with_port(self) -> None:
        assert _validate_url("http://localhost:9090") == "http://localhost:9090"

    def test_url_with_path(self) -> None:
        result = _validate_url("https://prometheus.example.com/path/")
        assert result == "https://prometheus.example.com/path"


class TestPrometheusClientInit:
    def test_missing_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PROMETHEUS_URL", raising=False)
        with pytest.raises(ConfigError, match="PROMETHEUS_URL"):
            PrometheusClient()

    def test_happy_path_no_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com/")
        monkeypatch.delenv("PROMETHEUS_TOKEN", raising=False)
        monkeypatch.delenv("PROMETHEUS_USERNAME", raising=False)
        monkeypatch.delenv("PROMETHEUS_PASSWORD", raising=False)
        client = PrometheusClient()
        try:
            assert client.url == "https://prometheus.example.com"
            assert client.api_url == "https://prometheus.example.com/api/v1"
            assert client.ssl_verify is True
            assert client.session.trust_env is False
            assert "Authorization" not in client.session.headers
            assert client.session.auth is None
        finally:
            client.close()

    def test_bearer_auth_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
        monkeypatch.setenv("PROMETHEUS_TOKEN", "mytoken123")  # pragma: allowlist secret
        client = PrometheusClient()
        try:
            assert client.session.headers["Authorization"] == "Bearer mytoken123"
            assert client.session.auth is None
        finally:
            client.close()

    def test_basic_auth_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
        monkeypatch.delenv("PROMETHEUS_TOKEN", raising=False)
        monkeypatch.setenv("PROMETHEUS_USERNAME", "admin")
        monkeypatch.setenv("PROMETHEUS_PASSWORD", "secret")  # pragma: allowlist secret
        client = PrometheusClient()
        try:
            assert "Authorization" not in client.session.headers
            assert client.session.auth == ("admin", "secret")
        finally:
            client.close()

    def test_bearer_takes_precedence_over_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
        monkeypatch.setenv("PROMETHEUS_TOKEN", "bearer-wins")  # pragma: allowlist secret
        monkeypatch.setenv("PROMETHEUS_USERNAME", "admin")
        monkeypatch.setenv("PROMETHEUS_PASSWORD", "secret")  # pragma: allowlist secret
        client = PrometheusClient()
        try:
            assert client.session.headers["Authorization"] == "Bearer bearer-wins"
            assert client.session.auth is None
        finally:
            client.close()

    def test_overrides_take_precedence_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://env.example.com")
        monkeypatch.setenv("PROMETHEUS_TOKEN", "env-token")  # pragma: allowlist secret
        client = PrometheusClient(
            url="https://explicit.example.com",
            token="explicit-token",  # pragma: allowlist secret
            ssl_verify=True,
        )
        try:
            assert client.url == "https://explicit.example.com"
            assert client.token == "explicit-token"  # pragma: allowlist secret
            assert client.ssl_verify is True
        finally:
            client.close()

    def test_ssl_verify_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
        monkeypatch.delenv("PROMETHEUS_SSL_VERIFY", raising=False)
        client = PrometheusClient()
        try:
            assert client.ssl_verify is True
        finally:
            client.close()

    def test_ssl_verify_false_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
        monkeypatch.setenv("PROMETHEUS_SSL_VERIFY", "false")
        client = PrometheusClient()
        try:
            assert client.ssl_verify is False
            assert client.session.verify is False
        finally:
            client.close()

    def test_user_agent_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
        client = PrometheusClient()
        try:
            assert client.session.headers["User-Agent"] == "prometheus-mcp"
        finally:
            client.close()

    def test_api_url_has_v1_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com")
        client = PrometheusClient()
        try:
            assert client.api_url.endswith("/api/v1")
        finally:
            client.close()
