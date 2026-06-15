"""Unit tests for federation config loading and validation.

Tests cover:
- Happy path with multi-instance config
- Defaults application and instance overrides
- Schema version validation (missing, wrong, non-integer)
- Empty/missing instances rejection
- Instance URL validation
- Malformed JSON handling with file path context
- File-not-found errors
- UTF-8 BOM handling
- Minimal config (single instance, just prometheus_url)
- Frozen dataclass immutability
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prometheus_mcp.config import (
    _DEFAULT_CACHE_TTL,
    _DEFAULT_MAX_RESPONSE_BYTES,
    _DEFAULT_SSL_VERIFY,
    _DEFAULT_TIMEOUT,
    FederationConfig,
    load_config,
)
from prometheus_mcp.errors import ConfigError


def _write_config(tmp_path: Path, data: dict | str, *, filename: str = "config.json") -> str:
    """Write JSON config to a temp file and return its path as a string."""
    p = tmp_path / filename
    if isinstance(data, str):
        p.write_text(data, encoding="utf-8")
    else:
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(p)


# ── Happy path ───────────────────────────────────────────────────────────────


class TestHappyPath:
    """Valid configs load correctly and produce expected dataclasses."""

    def test_two_instances(self, tmp_path: Path) -> None:
        """Multi-instance config with 2 named instances loads correctly."""
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
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        assert isinstance(cfg, FederationConfig)
        assert cfg.version == 1
        assert len(cfg.instances) == 2

        usw = cfg.instances["us-west"]
        assert usw.name == "us-west"
        assert usw.prometheus_url == "https://prom-usw.example.com"
        assert usw.alertmanager_url == "https://am-usw.example.com"
        assert usw.prometheus_token == "tok-usw"
        assert usw.timeout == 60.0

        eu = cfg.instances["eu-central"]
        assert eu.name == "eu-central"
        assert eu.prometheus_url == "https://prom-eu.example.com"
        assert eu.prometheus_username == "admin"
        assert eu.prometheus_password == "secret"
        assert eu.ssl_verify is False

    def test_minimal_config(self, tmp_path: Path) -> None:
        """Single instance with just prometheus_url loads with all defaults."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {
                    "prometheus_url": "https://prom.example.com",
                },
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        assert len(cfg.instances) == 1
        prod = cfg.instances["prod"]
        assert prod.name == "prod"
        assert prod.prometheus_url == "https://prom.example.com"
        assert prod.alertmanager_url == ""
        assert prod.prometheus_token == ""
        assert prod.ssl_verify is _DEFAULT_SSL_VERIFY
        assert prod.timeout == _DEFAULT_TIMEOUT
        assert prod.max_response_bytes == _DEFAULT_MAX_RESPONSE_BYTES
        assert prod.cache_ttl == _DEFAULT_CACHE_TTL

    def test_alertmanager_only_instance(self, tmp_path: Path) -> None:
        """Instance with only alertmanager_url is valid."""
        config_data = {
            "version": 1,
            "instances": {
                "am-only": {
                    "alertmanager_url": "https://am.example.com",
                },
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        am = cfg.instances["am-only"]
        assert am.alertmanager_url == "https://am.example.com"
        assert am.prometheus_url == ""

    def test_trailing_slash_stripped(self, tmp_path: Path) -> None:
        """URLs have trailing slashes stripped."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {
                    "prometheus_url": "https://prom.example.com/",
                    "alertmanager_url": "https://am.example.com///",
                },
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        prod = cfg.instances["prod"]
        assert prod.prometheus_url == "https://prom.example.com"
        assert prod.alertmanager_url == "https://am.example.com"


# ── Defaults inheritance ─────────────────────────────────────────────────────


class TestDefaults:
    """Defaults section values are inherited by instances."""

    def test_instance_inherits_defaults(self, tmp_path: Path) -> None:
        """Instance inherits timeout and ssl_verify from defaults section."""
        config_data = {
            "version": 1,
            "defaults": {
                "timeout": 120,
                "ssl_verify": False,
                "cache_ttl": 600,
            },
            "instances": {
                "prod": {
                    "prometheus_url": "https://prom.example.com",
                },
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        prod = cfg.instances["prod"]
        assert prod.timeout == 120.0
        assert prod.ssl_verify is False
        assert prod.cache_ttl == 600.0

    def test_instance_overrides_defaults(self, tmp_path: Path) -> None:
        """Instance-level value takes precedence over defaults."""
        config_data = {
            "version": 1,
            "defaults": {
                "timeout": 120,
                "ssl_verify": False,
            },
            "instances": {
                "prod": {
                    "prometheus_url": "https://prom.example.com",
                    "timeout": 10,
                    "ssl_verify": True,
                },
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        prod = cfg.instances["prod"]
        assert prod.timeout == 10.0
        assert prod.ssl_verify is True

    def test_defaults_url_inherited(self, tmp_path: Path) -> None:
        """URL from defaults can satisfy the 'at least one URL' requirement."""
        config_data = {
            "version": 1,
            "defaults": {
                "alertmanager_url": "https://am-shared.example.com",
            },
            "instances": {
                "prod": {
                    "prometheus_url": "https://prom.example.com",
                },
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        prod = cfg.instances["prod"]
        assert prod.prometheus_url == "https://prom.example.com"
        assert prod.alertmanager_url == "https://am-shared.example.com"

    def test_no_defaults_section_ok(self, tmp_path: Path) -> None:
        """Config without 'defaults' section is valid (uses built-in defaults)."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {
                    "prometheus_url": "https://prom.example.com",
                },
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)
        assert cfg.defaults == {}
        assert cfg.instances["prod"].timeout == _DEFAULT_TIMEOUT


# ── Version validation ───────────────────────────────────────────────────────


class TestVersionValidation:
    """Schema version field is validated strictly."""

    def test_missing_version_rejected(self, tmp_path: Path) -> None:
        """Config without 'version' field is rejected with actionable error."""
        config_data = {
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com"},
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="missing required 'version' field"):
            load_config(path)

    def test_wrong_version_rejected(self, tmp_path: Path) -> None:
        """Unsupported version number is rejected with current supported version."""
        config_data = {
            "version": 99,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com"},
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="unsupported version 99.*supports version 1"):
            load_config(path)

    def test_string_version_rejected(self, tmp_path: Path) -> None:
        """Non-numeric version is rejected."""
        config_data = {
            "version": "one",
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com"},
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="'version' must be an integer"):
            load_config(path)

    def test_version_zero_rejected(self, tmp_path: Path) -> None:
        """Version 0 is rejected (only version 1 supported)."""
        config_data = {
            "version": 0,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com"},
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="unsupported version 0"):
            load_config(path)


# ── Instances validation ─────────────────────────────────────────────────────


class TestInstancesValidation:
    """Instance section validation catches all structural errors."""

    def test_empty_instances_rejected(self, tmp_path: Path) -> None:
        """Empty instances dict is rejected with example."""
        config_data = {
            "version": 1,
            "instances": {},
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="'instances' is empty"):
            load_config(path)

    def test_missing_instances_rejected(self, tmp_path: Path) -> None:
        """Missing instances key is rejected."""
        config_data = {"version": 1}
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="missing required 'instances' section"):
            load_config(path)

    def test_instance_missing_all_urls_rejected(self, tmp_path: Path) -> None:
        """Instance with no prometheus_url or alertmanager_url is rejected."""
        config_data = {
            "version": 1,
            "instances": {
                "no-url": {
                    "timeout": 30,
                },
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="'no-url'.*at least one of.*'prometheus_url'.*'alertmanager_url'"):
            load_config(path)

    def test_instance_not_object_rejected(self, tmp_path: Path) -> None:
        """Instance value that isn't a dict is rejected."""
        config_data = {
            "version": 1,
            "instances": {
                "bad": "not-a-dict",
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="instance 'bad' must be an object"):
            load_config(path)

    def test_instances_array_rejected(self, tmp_path: Path) -> None:
        """Instances as array (not object) is rejected."""
        config_data = {
            "version": 1,
            "instances": [{"prometheus_url": "https://prom.example.com"}],
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="'instances' must be an object"):
            load_config(path)


# ── JSON / file errors ───────────────────────────────────────────────────────


class TestFileErrors:
    """File-level errors include path context for actionable diagnostics."""

    def test_malformed_json(self, tmp_path: Path) -> None:
        """Malformed JSON produces error with file path."""
        path = _write_config(tmp_path, "{bad json", filename="broken.json")

        with pytest.raises(ConfigError, match="Invalid JSON.*broken.json"):
            load_config(path)

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Missing file produces error with path."""
        missing = str(tmp_path / "does-not-exist.json")

        with pytest.raises(ConfigError, match="Config file not found.*does-not-exist.json"):
            load_config(missing)

    def test_non_object_top_level(self, tmp_path: Path) -> None:
        """JSON array at top level is rejected."""
        path = _write_config(tmp_path, "[]")

        with pytest.raises(ConfigError, match="expected a JSON object at top level"):
            load_config(path)

    def test_error_includes_file_path(self, tmp_path: Path) -> None:
        """Error messages include the full file path for debugging."""
        config_data = {"version": 99, "instances": {"x": {"prometheus_url": "https://x.com"}}}
        path = _write_config(tmp_path, config_data, filename="my-config.json")

        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert "my-config.json" in str(exc_info.value)


# ── BOM handling ─────────────────────────────────────────────────────────────


class TestBOMHandling:
    """UTF-8 BOM (byte order mark) is handled transparently."""

    def test_utf8_bom_parsed(self, tmp_path: Path) -> None:
        """File with UTF-8 BOM is parsed correctly."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {
                    "prometheus_url": "https://prom.example.com",
                },
            },
        }
        p = tmp_path / "bom-config.json"
        # Write BOM + JSON content
        content = json.dumps(config_data, indent=2)
        p.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

        cfg = load_config(str(p))
        assert cfg.instances["prod"].prometheus_url == "https://prom.example.com"


# ── Type coercion errors ────────────────────────────────────────────────────


class TestTypeCoercion:
    """Type coercion for numeric/boolean fields with error messages."""

    def test_ssl_verify_string_true(self, tmp_path: Path) -> None:
        """String 'true' is coerced to bool True."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com", "ssl_verify": "true"},
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)
        assert cfg.instances["prod"].ssl_verify is True

    def test_ssl_verify_string_false(self, tmp_path: Path) -> None:
        """String 'false' is coerced to bool False."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com", "ssl_verify": "false"},
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)
        assert cfg.instances["prod"].ssl_verify is False

    def test_invalid_timeout_rejected(self, tmp_path: Path) -> None:
        """Non-numeric timeout is rejected."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com", "timeout": "slow"},
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="'timeout' must be a number"):
            load_config(path)

    def test_invalid_max_response_bytes_rejected(self, tmp_path: Path) -> None:
        """Non-integer max_response_bytes is rejected."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com", "max_response_bytes": "big"},
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="'max_response_bytes' must be an integer"):
            load_config(path)

    def test_invalid_cache_ttl_rejected(self, tmp_path: Path) -> None:
        """Non-numeric cache_ttl is rejected."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com", "cache_ttl": "long"},
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="'cache_ttl' must be a number"):
            load_config(path)


# ── Frozen dataclass immutability ────────────────────────────────────────────


class TestImmutability:
    """Config dataclasses are frozen and cannot be mutated."""

    def test_instance_config_frozen(self, tmp_path: Path) -> None:
        """InstanceConfig fields cannot be reassigned."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com"},
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        with pytest.raises(AttributeError):
            cfg.instances["prod"].timeout = 999  # type: ignore[misc]

    def test_federation_config_frozen(self, tmp_path: Path) -> None:
        """FederationConfig fields cannot be reassigned."""
        config_data = {
            "version": 1,
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com"},
            },
        }
        path = _write_config(tmp_path, config_data)
        cfg = load_config(path)

        with pytest.raises(AttributeError):
            cfg.version = 2  # type: ignore[misc]


# ── Defaults section validation ──────────────────────────────────────────────


class TestDefaultsValidation:
    """Defaults section must be an object if present."""

    def test_defaults_not_object_rejected(self, tmp_path: Path) -> None:
        """Defaults as array is rejected."""
        config_data = {
            "version": 1,
            "defaults": [1, 2, 3],
            "instances": {
                "prod": {"prometheus_url": "https://prom.example.com"},
            },
        }
        path = _write_config(tmp_path, config_data)

        with pytest.raises(ConfigError, match="'defaults' must be an object"):
            load_config(path)
