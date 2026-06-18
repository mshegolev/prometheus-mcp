"""Thread-safe registry for managing multiple Prometheus/Alertmanager instances.

Maintains a mapping from instance names to client pairs with per-instance
authentication, TTL caches, and session lifecycle management. Used by _mcp.py
(Phase 3) and federation.py (Phase 4).

**Legacy mode:** When no FederationConfig is provided, creates a single
"default" entry from environment variables — identical behavior to v2.0.

**Threading model:** Fully thread-safe. All public methods acquire a lock
before accessing shared state. Individual clients and caches are safe to
share across threads (they manage their own internal state).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prometheus_mcp.alertmanager_client import AlertmanagerClient
from prometheus_mcp.cache import TTLCache
from prometheus_mcp.client import PrometheusClient
from prometheus_mcp.errors import ConfigError

if TYPE_CHECKING:
    from prometheus_mcp.config import FederationConfig, InstanceConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstanceInfo:
    """Public instance metadata for the discovery tool.

    Attributes:
        name: Instance name from config (e.g. "us-west").
        prometheus_url: Prometheus endpoint URL ("" if not configured).
        alertmanager_url: Alertmanager endpoint URL ("" if not configured).
        has_prometheus_auth: True if Prometheus client has auth configured.
        has_alertmanager_auth: True if Alertmanager client has auth configured.
    """

    name: str
    prometheus_url: str = ""
    alertmanager_url: str = ""
    has_prometheus_auth: bool = False
    has_alertmanager_auth: bool = False


@dataclass(frozen=True)
class InstanceEntry:
    """Internal registry entry holding a complete client set for one instance.

    Attributes:
        config: Source InstanceConfig from FederationConfig.
        prometheus_client: Prometheus client (None if no prometheus_url).
        alertmanager_client: Alertmanager client (None if no alertmanager_url).
        cache: Per-instance TTL cache for expensive lookups.
    """

    config: InstanceConfig
    prometheus_client: PrometheusClient | None
    alertmanager_client: AlertmanagerClient | None
    cache: TTLCache


class InstanceRegistry:
    """Thread-safe registry mapping instance names to client pairs.

    The registry is the central coordinator for multi-instance support.
    It owns the lifecycle of all HTTP sessions and ensures proper cleanup.

    Args:
        config: Federation configuration (None for legacy mode).
    """

    def __init__(self, config: FederationConfig | None) -> None:
        self._config = config
        self._entries: dict[str, InstanceEntry] = {}
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the registry by building all instance entries.

        In legacy mode (no config), creates a single "default" entry from
        environment variables. Otherwise builds entries from config instances.

        Safe to call multiple times — subsequent calls are no-ops.
        """
        with self._lock:
            if self._initialized:
                return

            if self._config is None:
                # Legacy mode: single "default" entry from env vars
                self._build_legacy_entry()
            else:
                # Federation mode: build entry for each configured instance
                for name, instance_config in self._config.instances.items():
                    self._entries[name] = self._build_entry(instance_config)

            self._initialized = True
            logger.info(
                "Initialized registry with %d instance(s): %s",
                len(self._entries),
                ", ".join(self._entries.keys()),
            )

    def _build_entry(self, config: InstanceConfig) -> InstanceEntry:
        """Build an InstanceEntry from an InstanceConfig."""
        # Create Prometheus client if URL is configured
        prometheus_client = None
        if config.prometheus_url:
            prometheus_client = PrometheusClient(
                url=config.prometheus_url,
                token=config.prometheus_token,
                username=config.prometheus_username,
                password=config.prometheus_password,
                ssl_verify=config.ssl_verify,
                timeout=config.timeout,
                max_response_bytes=config.max_response_bytes,
            )
        elif config.name == "default" and not config.prometheus_url:
            # Legacy mode: pass None to let client read from env vars
            prometheus_client = PrometheusClient(
                url=None,  # Will read from PROMETHEUS_URL env var
                token=None,  # Will read from PROMETHEUS_TOKEN env var
                username=None,  # Will read from PROMETHEUS_USERNAME env var
                password=None,  # Will read from PROMETHEUS_PASSWORD env var
                ssl_verify=None,  # Will read from PROMETHEUS_SSL_VERIFY env var
                timeout=None,  # Will read from PROMETHEUS_TIMEOUT env var
                max_response_bytes=None,  # Will read from PROMETHEUS_MAX_RESPONSE_BYTES env var
            )

        # Create Alertmanager client if URL is configured
        alertmanager_client = None
        if config.alertmanager_url:
            alertmanager_client = AlertmanagerClient(
                url=config.alertmanager_url,
                token=config.alertmanager_token,
                username=config.alertmanager_username,
                password=config.alertmanager_password,
                ssl_verify=config.ssl_verify,
            )
        elif config.name == "default" and not config.alertmanager_url:
            # Legacy mode: pass None to let client read from env vars
            alertmanager_client = AlertmanagerClient(
                url=None,  # Will read from ALERTMANAGER_URL env var
                token=None,  # Will read from ALERTMANAGER_TOKEN env var
                username=None,  # Will read from ALERTMANAGER_USERNAME env var
                password=None,  # Will read from ALERTMANAGER_PASSWORD env var
                ssl_verify=None,  # Will read from ALERTMANAGER_SSL_VERIFY env var
            )

        # Create per-instance cache with configured TTL
        cache = TTLCache(ttl=config.cache_ttl)

        return InstanceEntry(
            config=config,
            prometheus_client=prometheus_client,
            alertmanager_client=alertmanager_client,
            cache=cache,
        )

    def _build_legacy_entry(self) -> None:
        """Build single "default" entry from environment variables (v2.0 compat)."""
        # Import here to avoid circular imports
        from prometheus_mcp.config import InstanceConfig

        # Create minimal config matching v2.0 behavior
        # In legacy mode, we don't create any clients by default
        # They will be created on-demand when requested, reading from env vars
        legacy_config = InstanceConfig(name="default")

        # For legacy mode, we create entries with None clients
        # The clients will be lazily created when first accessed
        entry = InstanceEntry(
            config=legacy_config,
            prometheus_client=None,  # Will be created on first access
            alertmanager_client=None,  # Will be created on first access
            cache=TTLCache(),  # Use default cache TTL
        )
        self._entries["default"] = entry

    def get_prometheus_client(self, name: str) -> PrometheusClient:
        """Retrieve a Prometheus client by instance name.

        Args:
            name: Instance name (e.g. "us-west").

        Returns:
            The Prometheus client for the named instance.

        Raises:
            ConfigError: If the instance name is unknown or the instance
                has no Prometheus URL configured.
        """
        self.initialize()  # Auto-initialize if needed
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                valid_names = ", ".join(sorted(self._entries.keys()))
                raise ConfigError(f"Unknown Prometheus instance {name!r} — valid names: {valid_names}")

            # For legacy mode, create client on-demand
            if entry.prometheus_client is None and name == "default":
                # In legacy mode, create client that reads from env vars
                client = PrometheusClient()  # All params None, reads from env vars
                # Update the entry with the created client
                object.__setattr__(entry, "prometheus_client", client)
                return client
            elif entry.prometheus_client is None:
                raise ConfigError(f"Instance {name!r} has no Prometheus URL configured")
            return entry.prometheus_client

    def get_alertmanager_client(self, name: str) -> AlertmanagerClient:
        """Retrieve an Alertmanager client by instance name.

        Args:
            name: Instance name (e.g. "us-west").

        Returns:
            The Alertmanager client for the named instance.

        Raises:
            ConfigError: If the instance name is unknown or the instance
                has no Alertmanager URL configured.
        """
        self.initialize()  # Auto-initialize if needed
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                valid_names = ", ".join(sorted(self._entries.keys()))
                raise ConfigError(f"Unknown Alertmanager instance {name!r} — valid names: {valid_names}")

            # For legacy mode, create client on-demand
            if entry.alertmanager_client is None and name == "default":
                # In legacy mode, try to create client that reads from env vars
                try:
                    client = AlertmanagerClient()  # All params None, reads from env vars
                    # Update the entry with the created client
                    object.__setattr__(entry, "alertmanager_client", client)
                    return client
                except ConfigError:
                    # If Alertmanager URL is not configured, raise the appropriate error
                    raise ConfigError(f"Instance {name!r} has no Alertmanager URL configured")
            elif entry.alertmanager_client is None:
                raise ConfigError(f"Instance {name!r} has no Alertmanager URL configured")
            return entry.alertmanager_client

    def get_cache(self, name: str) -> TTLCache:
        """Retrieve the TTL cache for an instance.

        Args:
            name: Instance name (e.g. "us-west").

        Returns:
            The TTL cache for the named instance.

        Raises:
            ConfigError: If the instance name is unknown.
        """
        self.initialize()  # Auto-initialize if needed
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                valid_names = ", ".join(sorted(self._entries.keys()))
                raise ConfigError(f"Unknown instance {name!r} — valid names: {valid_names}")
            return entry.cache

    def get_instance_info(self, name: str) -> InstanceInfo:
        """Retrieve public metadata for an instance (for discovery tool).

        Args:
            name: Instance name (e.g. "us-west").

        Returns:
            Public instance metadata.

        Raises:
            ConfigError: If the instance name is unknown.
        """
        self.initialize()  # Auto-initialize if needed
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                valid_names = ", ".join(sorted(self._entries.keys()))
                raise ConfigError(f"Unknown instance {name!r} — valid names: {valid_names}")

            config = entry.config
            return InstanceInfo(
                name=config.name,
                prometheus_url=config.prometheus_url,
                alertmanager_url=config.alertmanager_url,
                has_prometheus_auth=bool(
                    config.prometheus_token or (config.prometheus_username and config.prometheus_password)
                ),
                has_alertmanager_auth=bool(
                    config.alertmanager_token or (config.alertmanager_username and config.alertmanager_password)
                ),
            )

    def list_instances(self) -> list[str]:
        """Return a list of all configured instance names."""
        self.initialize()  # Auto-initialize if needed
        with self._lock:
            return list(self._entries.keys())

    def all_prometheus_clients(self) -> list[PrometheusClient]:
        """Return all Prometheus clients (for fan-out queries)."""
        self.initialize()  # Auto-initialize if needed
        with self._lock:
            return [entry.prometheus_client for entry in self._entries.values() if entry.prometheus_client is not None]

    def all_alertmanager_clients(self) -> list[AlertmanagerClient]:
        """Return all Alertmanager clients (for fan-out queries)."""
        self.initialize()  # Auto-initialize if needed
        with self._lock:
            return [
                entry.alertmanager_client for entry in self._entries.values() if entry.alertmanager_client is not None
            ]

    def close_all(self) -> None:
        """Close all HTTP sessions and clean up resources.

        Should be called at application shutdown to ensure graceful cleanup
        of all network connections. Safe to call multiple times.
        """
        with self._lock:
            closed = 0
            for entry in self._entries.values():
                # Close Prometheus session if client exists
                if entry.prometheus_client is not None:
                    try:
                        entry.prometheus_client.session.close()
                        closed += 1
                    except Exception:
                        logger.warning(
                            "Failed to close Prometheus session for instance %s",
                            entry.config.name,
                            exc_info=True,
                        )

                # Close Alertmanager session if client exists
                if entry.alertmanager_client is not None:
                    try:
                        entry.alertmanager_client.session.close()
                        closed += 1
                    except Exception:
                        logger.warning(
                            "Failed to close Alertmanager session for instance %s",
                            entry.config.name,
                            exc_info=True,
                        )

            logger.info("Closed %d HTTP sessions", closed)
