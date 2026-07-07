"""Unit tests for the instance registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from prometheus_mcp.config import load_config
from prometheus_mcp.errors import ConfigError
from prometheus_mcp.registry import InstanceRegistry


def _write_config(tmp_path: Path, data: dict[str, Any]) -> str:
    """Write JSON config to a temp file and return its path."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(p)


class TestLegacyMode:
    """Tests for v2.0-compatible legacy mode (no config file)."""

    def test_single_default_entry(self) -> None:
        """Legacy mode creates single 'default' entry."""
        registry = InstanceRegistry(config=None)
        registry.initialize()

        instances = registry.list_instances()
        assert instances == ["default"]

    def test_prometheus_client_from_env(self) -> None:
        """Prometheus client in legacy mode reads from env vars."""
        with patch.dict(
            "os.environ",
            {
                "PROMETHEUS_URL": "https://prom.example.com",
                "PROMETHEUS_TOKEN": "test-token",
            },
        ):
            registry = InstanceRegistry(config=None)
            registry.initialize()

            client = registry.get_prometheus_client("default")
            assert client.url == "https://prom.example.com"
            assert client.token == "test-token"

    def test_alertmanager_client_raises_without_url(self) -> None:
        """Alertmanager client raises ConfigError when no URL in env."""
        with patch.dict("os.environ", {}, clear=True):
            registry = InstanceRegistry(config=None)
            registry.initialize()

            with pytest.raises(ConfigError, match="no Alertmanager URL configured"):
                registry.get_alertmanager_client("default")


class TestFederationMode:
    """Tests for federation mode with config file."""

    def test_two_instances(self, tmp_path: Path) -> None:
        """Registry loads two instances from config."""
        config_data = {
            "version": 1,
            "instances": {
                "us-west": {
                    "prometheus_url": "https://prom-usw.example.com",
                    "alertmanager_url": "https://am-usw.example.com",
                    "prometheus_token": "tok-usw",
                    "timeout": 60,
                },
                "eu-central": {
                    "prometheus_url": "https://prom-eu.example.com",
                    "prometheus_username": "admin",
                    "prometheus_password": "secret",
                    "ssl_verify": False,
                },
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        instances = registry.list_instances()
        assert sorted(instances) == ["eu-central", "us-west"]

        # Check us-west instance
        usw_prom = registry.get_prometheus_client("us-west")
        assert usw_prom.url == "https://prom-usw.example.com"
        assert usw_prom.token == "tok-usw"
        assert usw_prom.timeout == 60.0

        usw_am = registry.get_alertmanager_client("us-west")
        assert usw_am.url == "https://am-usw.example.com"

        # Check eu-central instance
        eu_prom = registry.get_prometheus_client("eu-central")
        assert eu_prom.url == "https://prom-eu.example.com"
        assert eu_prom.username == "admin"
        assert eu_prom.password == "secret"
        assert eu_prom.ssl_verify is False

        # eu-central has no Alertmanager
        with pytest.raises(ConfigError, match="no Alertmanager URL configured"):
            registry.get_alertmanager_client("eu-central")

    def test_minimal_config(self, tmp_path: Path) -> None:
        """Single instance with minimal config works."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com"},
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        instances = registry.list_instances()
        assert instances == ["prod"]

        client = registry.get_prometheus_client("prod")
        assert client.url == "https://prom.example.com"

    def test_per_instance_cache(self, tmp_path: Path) -> None:
        """Each instance gets its own cache with correct TTL."""
        config_data = {
            "version": 1,
            "instances": {
                "fast": {
                    "prometheus_url": "https://prom.example.com",
                    "cache_ttl": 60,
                },
                "slow": {
                    "prometheus_url": "https://prom2.example.com",
                    "cache_ttl": 600,
                },
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        fast_cache = registry.get_cache("fast")
        slow_cache = registry.get_cache("slow")

        assert fast_cache.ttl == 60.0
        assert slow_cache.ttl == 600.0

    def test_instance_info(self, tmp_path: Path) -> None:
        """InstanceInfo provides correct public metadata."""
        config_data = {
            "version": 1,
            "instances": {
                "auth": {
                    "prometheus_url": "https://prom.example.com",
                    "prometheus_token": "token",
                    "alertmanager_url": "https://am.example.com",
                },
                "no-auth": {
                    "prometheus_url": "https://prom2.example.com",
                },
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        # Check authenticated instance
        auth_info = registry.get_instance_info("auth")
        assert auth_info.name == "auth"
        assert auth_info.prometheus_url == "https://prom.example.com"
        assert auth_info.alertmanager_url == "https://am.example.com"
        assert auth_info.has_prometheus_auth is True
        assert auth_info.has_alertmanager_auth is False  # No AM auth configured

        # Check non-authenticated instance
        no_auth_info = registry.get_instance_info("no-auth")
        assert no_auth_info.name == "no-auth"
        assert no_auth_info.prometheus_url == "https://prom2.example.com"
        assert no_auth_info.alertmanager_url == ""
        assert no_auth_info.has_prometheus_auth is False

    def test_all_clients(self, tmp_path: Path) -> None:
        """all_prometheus_clients() and all_alertmanager_clients() work."""
        config_data = {
            "version": 1,
            "instances": {
                "both": {
                    "prometheus_url": "https://prom1.example.com",
                    "alertmanager_url": "https://am1.example.com",
                },
                "prom-only": {
                    "prometheus_url": "https://prom2.example.com",
                },
                "am-only": {
                    "alertmanager_url": "https://am2.example.com",
                },
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        prom_clients = registry.all_prometheus_clients()
        am_clients = registry.all_alertmanager_clients()

        assert len(prom_clients) == 2  # both + prom-only
        assert len(am_clients) == 2  # both + am-only

        # Check URLs are correct
        prom_urls = {client.url for client in prom_clients}
        am_urls = {client.url for client in am_clients}

        assert prom_urls == {
            "https://prom1.example.com",
            "https://prom2.example.com",
        }
        assert am_urls == {
            "https://am1.example.com",
            "https://am2.example.com",
        }


class TestErrorHandling:
    """Tests for error conditions and edge cases."""

    def test_unknown_instance(self, tmp_path: Path) -> None:
        """Unknown instance name raises ConfigError with valid names."""
        config_data = {
            "version": 1,
            "instances": {"prod": {"prometheus_url": "https://prom.example.com"}},
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        with pytest.raises(ConfigError, match="Unknown Prometheus instance.*valid names.*prod"):
            registry.get_prometheus_client("staging")

    def test_no_prometheus_url(self, tmp_path: Path) -> None:
        """Instance without prometheus_url raises when accessed."""
        config_data = {
            "version": 1,
            "instances": {"am-only": {"alertmanager_url": "https://am.example.com"}},
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        with pytest.raises(ConfigError, match="no Prometheus URL configured"):
            registry.get_prometheus_client("am-only")

    def test_no_alertmanager_url(self, tmp_path: Path) -> None:
        """Instance without alertmanager_url raises when accessed."""
        config_data = {
            "version": 1,
            "instances": {"prom-only": {"prometheus_url": "https://prom.example.com"}},
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        with pytest.raises(ConfigError, match="no Alertmanager URL configured"):
            registry.get_alertmanager_client("prom-only")

    def test_initialize_multiple_times_safe(self, tmp_path: Path) -> None:
        """Calling initialize() multiple times is safe."""
        config_data = {
            "version": 1,
            "instances": {"prod": {"prometheus_url": "https://prom.example.com"}},
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)

        # First call
        registry.initialize()
        instances_first = registry.list_instances()

        # Second call
        registry.initialize()
        instances_second = registry.list_instances()

        assert instances_first == instances_second == ["prod"]


class TestSessionLifecycle:
    """Tests for session lifecycle management."""

    def test_close_all_closes_sessions(self, tmp_path: Path) -> None:
        """close_all() closes all HTTP sessions."""
        config_data = {
            "version": 1,
            "instances": {
                "both": {
                    "prometheus_url": "https://prom.example.com",
                    "alertmanager_url": "https://am.example.com",
                }
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        # Get clients to create sessions
        prom_client = registry.get_prometheus_client("both")
        am_client = registry.get_alertmanager_client("both")

        # Mock session.close() to verify it's called
        prom_client.session.close = Mock()
        am_client.session.close = Mock()

        # Close all sessions
        registry.close_all()

        # Verify close() was called on both sessions
        prom_client.session.close.assert_called_once()
        am_client.session.close.assert_called_once()

    def test_close_all_with_exceptions(self, tmp_path: Path) -> None:
        """close_all() handles exceptions gracefully."""
        config_data = {
            "version": 1,
            "instances": {
                "both": {
                    "prometheus_url": "https://prom.example.com",
                    "alertmanager_url": "https://am.example.com",
                }
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        registry = InstanceRegistry(config)
        registry.initialize()

        # Get clients to create sessions
        prom_client = registry.get_prometheus_client("both")
        am_client = registry.get_alertmanager_client("both")

        # Mock session.close() to raise an exception
        prom_client.session.close = Mock(side_effect=RuntimeError("close failed"))
        am_client.session.close = Mock()

        # Should not raise - exceptions are logged and ignored
        registry.close_all()

        # Verify close() was still attempted on both sessions
        prom_client.session.close.assert_called_once()
        am_client.session.close.assert_called_once()
