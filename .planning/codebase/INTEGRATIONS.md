# External Integrations

**Analysis Date:** 2026-06-06

## APIs & External Services

### Prometheus HTTP API v1 (Primary Integration)

The server is a read-only client for the Prometheus HTTP API v1. All API communication happens through `src/prometheus_mcp/client.py` via a `requests.Session`.

**Base URL:** `{PROMETHEUS_URL}/api/v1`

**Endpoints consumed:**

| Endpoint | Method | Tool | File |
|----------|--------|------|------|
| `/api/v1/label/__name__/values` | GET | `prometheus_list_metrics` | `src/prometheus_mcp/tools.py:153-188` |
| `/api/v1/query` | GET | `prometheus_query` | `src/prometheus_mcp/tools.py:250-289` |
| `/api/v1/query_range` | GET | `prometheus_query_range` | `src/prometheus_mcp/tools.py:378-444` |
| `/api/v1/alerts` | GET | `prometheus_list_alerts` | `src/prometheus_mcp/tools.py:483-537` |
| `/api/v1/targets` | GET | `prometheus_list_targets` | `src/prometheus_mcp/tools.py:589-693` |

**Authentication (priority order):**
1. **Bearer token** — `Authorization: Bearer {PROMETHEUS_TOKEN}` header set on session (`src/prometheus_mcp/client.py:118-119`)
2. **HTTP Basic auth** — `(PROMETHEUS_USERNAME, PROMETHEUS_PASSWORD)` tuple set as `session.auth` (`src/prometheus_mcp/client.py:120-121`)
3. **No auth** — Valid for many internal Prometheus deployments

**Request configuration:**
- Timeout: 30 seconds (`src/prometheus_mcp/client.py:138`)
- SSL verify: Configurable via `PROMETHEUS_SSL_VERIFY` env var, default `true` (`src/prometheus_mcp/client.py:102-104`)
- User-Agent: `prometheus-mcp` (`src/prometheus_mcp/client.py:112`)
- Accept: `application/json` (`src/prometheus_mcp/client.py:111`)
- Proxy: Disabled (`session.trust_env = False`) — Prometheus is typically internal (`src/prometheus_mcp/client.py:115`)

**Connection pooling:**
- Single `requests.Session` instance cached as module singleton in `src/prometheus_mcp/_mcp.py`
- Thread-safe lazy initialization with double-checked locking (`src/prometheus_mcp/_mcp.py:42-55`)
- Session closed on server shutdown via `app_lifespan` async context manager (`src/prometheus_mcp/_mcp.py:21-36`)

**Rate limiting:**
- No client-side rate limiting implemented
- HTTP 429 responses from Prometheus are handled with actionable error message suggesting 30-60s backoff (`src/prometheus_mcp/errors.py:68-72`)

**Response caps (client-side):**
- Metrics list: 500 items max (`_METRICS_CAP = 500` in `src/prometheus_mcp/tools.py:40`)
- Range query points: 5000 total across all series (`_RANGE_POINTS_CAP = 5000` in `src/prometheus_mcp/tools.py:41`)
- Markdown display: 20 items per section (`_MD_ITEM_LIMIT = 20` in `src/prometheus_mcp/tools.py:42`)

## Data Sources

**Databases:** None — this server is a stateless proxy to Prometheus.

**File Storage:** None — no local file I/O beyond environment variable reading.

**Caching:**
- HTTP session connection pooling via `requests.Session` (TCP connection reuse)
- Single `PrometheusClient` singleton cached in `src/prometheus_mcp/_mcp.py` (`_client` global)
- No response caching — every tool call makes a fresh HTTP request to Prometheus

## Protocol & Communication

### MCP Protocol (Upstream — to MCP Client)

**Transport:** stdio (standard input/output)
- Server entry point: `src/prometheus_mcp/server.py:main()` → `mcp.run()`
- Registered in `server.json` as `transport.type: "stdio"`

**MCP Server registration:**
- Server name: `prometheus_mcp` (`src/prometheus_mcp/_mcp.py:39`)
- Schema version: `2025-12-11` (`server.json:2`)
- MCP package identifier: `io.github.mshegolev/prometheus-mcp`

**Tool output format (dual-channel):**
Every tool returns a `CallToolResult` with both channels (`src/prometheus_mcp/output.py:14-18`):
1. `content` — Markdown-formatted `TextContent` for human-readable display
2. `structuredContent` — JSON dict matching the TypedDict output schema for programmatic consumption

**Tool annotations (all tools):**
- `readOnlyHint: true` — safe, read-only operations
- `destructiveHint: false` — no modifications to Prometheus
- `idempotentHint: true` — same query returns same results (at a given time)
- `openWorldHint: true` — results depend on external Prometheus state

**Structured output schemas:** Defined as TypedDicts in `src/prometheus_mcp/models.py`. FastMCP auto-generates JSON Schema from these for `outputSchema` in the tool catalogue.

### HTTP (Downstream — to Prometheus)

**Protocol:** HTTP/HTTPS (configurable via `PROMETHEUS_URL` scheme)
- Client: synchronous `requests` library
- All requests are GET (read-only)
- Response format: JSON (`Accept: application/json`)

**Error handling chain:**
1. `requests` raises `HTTPError`, `ConnectionError`, or `Timeout`
2. `src/prometheus_mcp/errors.py:handle()` maps exceptions to actionable LLM-readable strings
3. `src/prometheus_mcp/output.py:fail()` wraps the message in `ToolError` (MCP-level error)

**HTTP status handling** (`src/prometheus_mcp/errors.py`):

| Status | Error Type | Message Includes |
|--------|-----------|-----------------|
| 401 | Auth failure | Token/Basic auth env vars to check |
| 403 | Forbidden | Credential permissions |
| 404 | Not found | URL check, suggests `prometheus_list_metrics` |
| 400/422 | Bad request | PromQL syntax, step/range advice, Prometheus error body |
| 429 | Rate limited | Backoff suggestion (30-60s) |
| 5xx | Server error | Transient, retry, health check URL |
| Connection error | Network | URL, default port 9090 |
| Timeout | Network | Narrow range/increase step |

## Configuration & Secrets

**Environment variables (all runtime config):**

| Variable | Required | Default | Secret | Source |
|----------|----------|---------|--------|--------|
| `PROMETHEUS_URL` | Yes | — | No | `src/prometheus_mcp/client.py:94` |
| `PROMETHEUS_TOKEN` | No | `""` | Yes | `src/prometheus_mcp/client.py:98` |
| `PROMETHEUS_USERNAME` | No | `""` | No | `src/prometheus_mcp/client.py:99` |
| `PROMETHEUS_PASSWORD` | No | `""` | Yes | `src/prometheus_mcp/client.py:100` |
| `PROMETHEUS_SSL_VERIFY` | No | `true` | No | `src/prometheus_mcp/client.py:102-103` |

**Secrets management:**
- Secrets passed via env vars — no vault/KMS integration
- `.env` file is gitignored (`.gitignore:30`)
- `.env.example` provides template with commented-out secrets
- MCP client config (`server.json`) documents which vars are `isSecret: true`
- PyPI publish uses OIDC Trusted Publisher — no API tokens stored in repo

**Config validation:**
- `PROMETHEUS_URL` validated on client construction: must have `http://` or `https://` scheme with a host (`src/prometheus_mcp/client.py:43-59`)
- Raises `ConfigError` (subclass of `ValueError`) with actionable message if missing/malformed
- Boolean parsing for `PROMETHEUS_SSL_VERIFY`: accepts `true/false/1/0/yes/no/on/off` case-insensitively (`src/prometheus_mcp/client.py:30-40`)

## Third-Party SDKs

**MCP SDK:**
- Package: `mcp` (PyPI) version `>=1.2`
- Used classes/modules:
  - `mcp.server.fastmcp.FastMCP` — server instance creation (`src/prometheus_mcp/_mcp.py:11`)
  - `mcp.server.fastmcp.exceptions.ToolError` — error signaling (`src/prometheus_mcp/output.py:8`)
  - `mcp.types.CallToolResult` — tool return wrapper (`src/prometheus_mcp/output.py:9`)
  - `mcp.types.TextContent` — markdown content block (`src/prometheus_mcp/output.py:9`)

**HTTP client:**
- Package: `requests` version `>=2.31`
- Used for all Prometheus HTTP API communication
- Single `Session` instance with connection pooling
- No async HTTP client (deliberate — threading model handles concurrency)

**Pydantic:**
- Package: `pydantic` version `>=2.0`
- Used for `Field()` annotations on tool parameters (`src/prometheus_mcp/tools.py`)
- FastMCP uses Pydantic internally for input/output schema generation from TypedDicts

**No wrappers:** The codebase does not use any Prometheus-specific Python SDK (e.g., `prometheus-api-client`). All Prometheus API interaction is via direct HTTP GET requests through the custom `PrometheusClient` class in `src/prometheus_mcp/client.py`.

## Webhooks & Callbacks

**Incoming:** None — the server only responds to MCP tool calls via stdio.

**Outgoing:** None — the server does not send webhooks or callbacks.

## Glama.ai Registry

The project includes `glama.json` for the [Glama MCP registry](https://glama.ai/mcp):
- Schema: `https://glama.ai/mcp/schemas/server.json`
- Maintainer: `mshegolev`

---

*Integration audit: 2026-06-06*
