"""Federation config loading for multi-instance Prometheus/Alertmanager.

Loads a JSON config file that defines named Prometheus and Alertmanager
instances with shared defaults, schema versioning, and validation.

**Config file format (version 1):**

.. code-block:: json

    {
        "version": 1,
        "instances": {
            "us-west": {
                "prometheus_url": "https://prom-usw.corp.example.com",
                "alertmanager_url": "https://am-usw.corp.example.com"
            }
        },
        "defaults": {
            "timeout": 30,
            "ssl_verify": true
        }
    }

**Backward compatibility:** When no config file is present (no
``PROMETHEUS_MCP_CONFIG`` env var), :func:`load_config` returns ``None``
and the server falls back to single-instance mode using environment
variables directly.

**Threading model:** :class:`FederationConfig` and :class:`InstanceConfig`
are frozen dataclasses — fully immutable and safe to share across threads
without locking.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from prometheus_mcp.errors import ConfigError

logger = logging.getLogger(__name__)

_SUPPORTED_VERSION = 1
_DEFAULT_SSL_VERIFY = True
_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_CACHE_TTL = 300.0

# Fields that can appear in the "defaults" section and be inherited by instances.
_INHERITABLE_FIELDS = frozenset(
    {
        "prometheus_url",
        "prometheus_token",
        "prometheus_username",
        "prometheus_password",
        "alertmanager_url",
        "alertmanager_token",
        "alertmanager_username",
        "alertmanager_password",
        "ssl_verify",
        "timeout",
        "max_response_bytes",
        "cache_ttl",
    }
)


@dataclass(frozen=True)
class InstanceConfig:
    """Configuration for a single named Prometheus/Alertmanager instance.

    All fields are immutable (frozen dataclass). URL fields default to empty
    strings; at least one of ``prometheus_url`` or ``alertmanager_url`` must
    be non-empty after loading.

    Attributes:
        name: Unique instance identifier (e.g. ``"us-west"``).
        prometheus_url: Prometheus server URL (no trailing slash).
        prometheus_token: Bearer token for Prometheus auth.
        prometheus_username: HTTP Basic auth username for Prometheus.
        prometheus_password: HTTP Basic auth password for Prometheus.
        alertmanager_url: Alertmanager server URL (no trailing slash).
        alertmanager_token: Bearer token for Alertmanager auth.
        alertmanager_username: HTTP Basic auth username for Alertmanager.
        alertmanager_password: HTTP Basic auth password for Alertmanager.
        ssl_verify: Whether to verify TLS certificates.
        timeout: HTTP request timeout in seconds.
        max_response_bytes: Maximum response body size in bytes.
        cache_ttl: Cache TTL for metric name lists in seconds.
    """

    name: str = ""
    prometheus_url: str = ""
    prometheus_token: str = ""
    prometheus_username: str = ""
    prometheus_password: str = ""
    alertmanager_url: str = ""
    alertmanager_token: str = ""
    alertmanager_username: str = ""
    alertmanager_password: str = ""
    ssl_verify: bool = _DEFAULT_SSL_VERIFY
    timeout: float = _DEFAULT_TIMEOUT
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES
    cache_ttl: float = _DEFAULT_CACHE_TTL


@dataclass(frozen=True)
class FederationConfig:
    """Top-level federation configuration with named instances.

    Attributes:
        version: Schema version (currently ``1``).
        instances: Mapping of instance name to :class:`InstanceConfig`.
        defaults: Raw defaults dict from the config file, preserved for
            debugging/introspection.
    """

    version: int = _SUPPORTED_VERSION
    instances: dict[str, InstanceConfig] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)


def _build_instance(name: str, raw: dict[str, Any], defaults: dict[str, Any], config_path: str) -> InstanceConfig:
    """Merge defaults into instance raw dict and construct an :class:`InstanceConfig`.

    Instance-level values override defaults. Unknown keys are ignored with a
    warning. Type coercion is applied for ``ssl_verify`` (bool), ``timeout``
    (float), ``max_response_bytes`` (int), and ``cache_ttl`` (float).

    Args:
        name: Instance name (used in error messages).
        raw: Raw instance dict from JSON.
        defaults: Defaults section dict from JSON.
        config_path: File path (used in error messages).

    Returns:
        A validated :class:`InstanceConfig`.

    Raises:
        ConfigError: If required fields are missing or types are invalid.
    """
    # Merge: defaults first, instance overrides
    merged: dict[str, Any] = {}
    for key in _INHERITABLE_FIELDS:
        if key in defaults:
            merged[key] = defaults[key]
    merged.update(raw)

    # Warn about unknown keys
    known_fields = {f.name for f in fields(InstanceConfig)}
    for key in merged:
        if key not in known_fields and key != "name":
            logger.warning(
                "Unknown field %r in instance %r of config file %s — ignoring",
                key,
                name,
                config_path,
            )

    # Type coercion with actionable errors
    try:
        ssl_verify = merged.get("ssl_verify", _DEFAULT_SSL_VERIFY)
        if isinstance(ssl_verify, str):
            ssl_verify = ssl_verify.strip().lower() not in ("false", "0", "no", "off")
        ssl_verify = bool(ssl_verify)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"Instance {name!r} in {config_path}: 'ssl_verify' must be a boolean (got {merged.get('ssl_verify')!r})"
        ) from exc

    try:
        timeout = float(merged.get("timeout", _DEFAULT_TIMEOUT))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"Instance {name!r} in {config_path}: 'timeout' must be a number (got {merged.get('timeout')!r})"
        ) from exc

    try:
        max_response_bytes = int(merged.get("max_response_bytes", _DEFAULT_MAX_RESPONSE_BYTES))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"Instance {name!r} in {config_path}: "
            f"'max_response_bytes' must be an integer (got {merged.get('max_response_bytes')!r})"
        ) from exc

    try:
        cache_ttl = float(merged.get("cache_ttl", _DEFAULT_CACHE_TTL))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"Instance {name!r} in {config_path}: 'cache_ttl' must be a number (got {merged.get('cache_ttl')!r})"
        ) from exc

    instance = InstanceConfig(
        name=name,
        prometheus_url=str(merged.get("prometheus_url", "")).strip().rstrip("/"),
        prometheus_token=str(merged.get("prometheus_token", "")),
        prometheus_username=str(merged.get("prometheus_username", "")),
        prometheus_password=str(merged.get("prometheus_password", "")),
        alertmanager_url=str(merged.get("alertmanager_url", "")).strip().rstrip("/"),
        alertmanager_token=str(merged.get("alertmanager_token", "")),
        alertmanager_username=str(merged.get("alertmanager_username", "")),
        alertmanager_password=str(merged.get("alertmanager_password", "")),
        ssl_verify=ssl_verify,
        timeout=timeout,
        max_response_bytes=max_response_bytes,
        cache_ttl=cache_ttl,
    )

    # Validate: at least one URL must be set
    if not instance.prometheus_url and not instance.alertmanager_url:
        raise ConfigError(
            f"Instance {name!r} in {config_path}: at least one of 'prometheus_url' or 'alertmanager_url' must be set"
        )

    return instance


def load_config(path: str) -> FederationConfig:
    """Load and validate a federation config file.

    Opens the file with ``encoding="utf-8-sig"`` to transparently handle
    UTF-8 BOM markers commonly added by Windows editors.

    Args:
        path: Path to the JSON config file.

    Returns:
        A validated :class:`FederationConfig`.

    Raises:
        ConfigError: If the file is missing, malformed, or fails validation.
            All errors include the file path for actionable diagnostics.
    """
    config_path = str(path)

    # Read file (utf-8-sig handles BOM transparently)
    try:
        text = Path(config_path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {config_path} — check PROMETHEUS_MCP_CONFIG path") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {config_path}: {exc}") from exc

    # Parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Invalid JSON in config file {config_path}: {exc}. Validate the file at https://jsonlint.com"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config file {config_path}: expected a JSON object at top level, got {type(data).__name__}")

    # Validate version
    version = data.get("version")
    if version is None:
        raise ConfigError(
            f"Config file {config_path}: missing required 'version' field. "
            f"Add '\"version\": {_SUPPORTED_VERSION}' to the top level"
        )
    try:
        version_int = int(version)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Config file {config_path}: 'version' must be an integer (got {version!r})") from exc
    if version_int != _SUPPORTED_VERSION:
        raise ConfigError(
            f"Config file {config_path}: unsupported version {version_int}. "
            f"This version of prometheus-mcp supports version {_SUPPORTED_VERSION}"
        )

    # Extract defaults
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ConfigError(f"Config file {config_path}: 'defaults' must be an object (got {type(defaults).__name__})")

    # Validate instances
    raw_instances = data.get("instances")
    if raw_instances is None:
        raise ConfigError(
            f"Config file {config_path}: missing required 'instances' section. Define at least one named instance"
        )
    if not isinstance(raw_instances, dict):
        raise ConfigError(
            f"Config file {config_path}: 'instances' must be an object mapping names to configs "
            f"(got {type(raw_instances).__name__})"
        )
    if not raw_instances:
        raise ConfigError(
            f"Config file {config_path}: 'instances' is empty — define at least one named instance. "
            f'Example: {{"instances": {{"my-prom": {{"prometheus_url": "https://..."}}}}}}'
        )

    # Build instances
    instances: dict[str, InstanceConfig] = {}
    for inst_name, inst_raw in raw_instances.items():
        if not isinstance(inst_raw, dict):
            raise ConfigError(
                f"Config file {config_path}: instance {inst_name!r} must be an object (got {type(inst_raw).__name__})"
            )
        instances[inst_name] = _build_instance(inst_name, inst_raw, defaults, config_path)

    logger.info(
        "Loaded federation config from %s: version=%d, %d instance(s): %s",
        config_path,
        version_int,
        len(instances),
        ", ".join(instances.keys()),
    )

    return FederationConfig(
        version=version_int,
        instances=instances,
        defaults=defaults,
    )
