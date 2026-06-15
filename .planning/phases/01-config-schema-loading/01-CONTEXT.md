# Phase 1: Config Schema & Loading - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement JSON config file parsing for named Prometheus/Alertmanager instances with Pydantic-free validation (frozen dataclasses), defaults inheritance, schema versioning (version: 1), and fully backward-compatible single-instance mode when no config file is present.

New module: `src/prometheus_mcp/config.py` — loaded by lifespan at startup, consumed by registry (Phase 2) and _mcp.py (Phase 3).

### Requirements Addressed
- **CFG-01**: JSON config file loaded via PROMETHEUS_MCP_CONFIG env var
- **CFG-02**: Config has `version: 1` with clear errors on missing/unknown
- **CFG-04**: `defaults` section for shared settings inherited by instances
- **CFG-06**: Actionable validation errors referencing config file path and instance name
- **CFG-07**: No config file = single-instance mode via existing env vars (unchanged)

</domain>

<decisions>
## Implementation Decisions

### Config File Schema Design
- Flat dict structure: instances keyed by name, each with optional `prometheus_url` and `alertmanager_url` fields (type inferred from which URLs are present)
- Frozen dataclasses for config types (`InstanceConfig`, `FederationConfig`) — config is loaded once, never mutated, no Pydantic overhead
- Auth fields use flat naming mirroring env vars (lowercased): `prometheus_token`, `prometheus_username`, `prometheus_password`, `alertmanager_token`, etc.
- Env var substitution in config values (`${VAR}`) deferred to post-v3.0 (requirement CFG-08 is in Future)

### Backward Compatibility Strategy
- When both config file AND env vars are set, config file takes precedence; env vars are ignored with an INFO log message
- Config env var name: `PROMETHEUS_MCP_CONFIG` (follows existing naming convention)
- When config path is set but file doesn't exist: fail fast at startup with ConfigError referencing the missing path

### Validation UX & Error Messages
- Custom ConfigError wrapping catches all parsing/validation errors and rewrites them with config file path and instance name context
- Config with zero instances: rejected with actionable error ("Add at least one instance with a prometheus_url")
- Each instance requires at least one URL (prometheus_url or alertmanager_url) — instances with neither are rejected

### OpenCode's Discretion
- Internal code organization within config.py (helper functions, constants)
- Exact error message wording (must be actionable and reference file path/instance name)
- UTF-8 BOM handling approach (use `encoding="utf-8-sig"` per PITFALLS.md)
- JSON parsing error messages (reference line numbers where possible)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `errors.py:ConfigError(ValueError)` — existing config error class, reuse for config file errors
- `client.py:_parse_bool()` — boolean parsing helper for ssl_verify
- `client.py:PrometheusClient.__init__()` constructor accepts all config via kwargs with env-var fallbacks — already parameterized for multi-instance

### Established Patterns
- Environment configuration: `os.environ.get("VAR", default)` with explicit parameter override
- Error messages: actionable, mentioning specific env var names and suggesting fixes
- Module docstrings explain threading model and purpose
- `from __future__ import annotations` in every module
- Line length 120, target Python 3.10

### Integration Points
- `config.py` → consumed by `registry.py` (Phase 2) to create client pairs
- `config.py` → consumed by `_mcp.py` lifespan (Phase 3) at startup
- `PROMETHEUS_MCP_CONFIG` env var → documented in `.env.example`, `server.json`, README
- `.gitignore` → needs config file pattern added (Pitfall 16)

</code_context>

<specifics>
## Specific Ideas

### Config File Format (from ARCHITECTURE.md)
```json
{
  "version": 1,
  "instances": {
    "us-west": {
      "prometheus_url": "https://prom-usw.corp.example.com",
      "prometheus_token": "...",
      "alertmanager_url": "https://am-usw.corp.example.com",
      "alertmanager_token": "...",
      "ssl_verify": true,
      "timeout": 30,
      "max_response_bytes": 10485760,
      "cache_ttl": 300
    },
    "eu-central": {
      "prometheus_url": "https://prom-eu.corp.example.com",
      "prometheus_username": "reader",
      "prometheus_password": "...",
      "ssl_verify": false
    }
  },
  "defaults": {
    "timeout": 30,
    "ssl_verify": true,
    "max_response_bytes": 10485760,
    "cache_ttl": 300
  }
}
```

### Dataclass Types (from ARCHITECTURE.md)
```python
@dataclass(frozen=True)
class InstanceConfig:
    name: str
    prometheus_url: str = ""
    prometheus_token: str = ""
    prometheus_username: str = ""
    prometheus_password: str = ""
    alertmanager_url: str = ""
    alertmanager_token: str = ""
    alertmanager_username: str = ""
    alertmanager_password: str = ""
    ssl_verify: bool = True
    timeout: float = 30.0
    max_response_bytes: int = 10 * 1024 * 1024
    cache_ttl: float = 300.0

@dataclass(frozen=True)
class FederationConfig:
    instances: dict[str, InstanceConfig]
    defaults: dict[str, Any] = field(default_factory=dict)
```

</specifics>

<deferred>
## Deferred Ideas

- Env var substitution in config values (`${VAR}` syntax) — CFG-08, deferred to post-v3.0
- Config hot-reload via SIGHUP — CFG-09, deferred to post-v3.0
- JSON Schema file for editor validation — nice-to-have, not in v3.0 scope

</deferred>
