# Architecture

<!-- refreshed: 2026-06-06 -->
**Analysis Date:** 2026-06-06

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                       MCP Client (Claude, etc.)                     │
│                   stdio JSON-RPC (tools/list, tools/call)           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastMCP Runtime                              │
│               `src/prometheus_mcp/server.py`  (entry point)          │
│               `src/prometheus_mcp/_mcp.py`    (shared instance)      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    5 Read-Only Tools                            │  │
│  │               `src/prometheus_mcp/tools.py`                    │  │
│  │                                                                │  │
│  │  prometheus_list_metrics   prometheus_query                    │  │
│  │  prometheus_query_range    prometheus_list_alerts              │  │
│  │  prometheus_list_targets                                       │  │
│  └──────────┬──────────────────────────────┬─────────────────────┘  │
│             │                              │                         │
│             ▼                              ▼                         │
│  ┌─────────────────────┐      ┌───────────────────────────────┐     │
│  │   Output Helpers     │      │    TypedDict Models           │     │
│  │  `output.py`         │      │   `models.py`                 │     │
│  │  ok() / fail()       │      │   ListMetricsOutput, etc.     │     │
│  └─────────────────────┘      └───────────────────────────────┘     │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PrometheusClient (HTTP)                            │
│                `src/prometheus_mcp/client.py`                         │
│                                                                      │
│  requests.Session ──► Prometheus HTTP API v1                         │
│  Bearer/Basic/None    GET /api/v1/{query,query_range,alerts,...}     │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Error Handler                                     │
│              `src/prometheus_mcp/errors.py`                           │
│                                                                      │
│  HTTP status → actionable LLM-readable message                       │
│  ConfigError / HTTPError / ConnectionError / Timeout / ValueError    │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Server entry point | Create FastMCP instance, register tools, run stdio loop | `src/prometheus_mcp/server.py` |
| MCP instance + cache | Shared `FastMCP` singleton; lazy-init thread-safe `PrometheusClient` cache | `src/prometheus_mcp/_mcp.py` |
| Tools | 5 MCP tool functions: list metrics, instant query, range query, list alerts, list targets | `src/prometheus_mcp/tools.py` |
| Models | TypedDict output schemas consumed by FastMCP for JSON-Schema generation | `src/prometheus_mcp/models.py` |
| Output helpers | Dual-channel result construction (markdown `content` + structured `structuredContent`) | `src/prometheus_mcp/output.py` |
| HTTP client | Thin `requests.Session` wrapper for Prometheus API v1; env-var config; auth selection | `src/prometheus_mcp/client.py` |
| Error handler | Maps exceptions to actionable, LLM-readable error strings with next-step hints | `src/prometheus_mcp/errors.py` |
| Package init | Version string (`__version__`) | `src/prometheus_mcp/__init__.py` |

## Pattern Overview

**Overall:** Single-process MCP server using the FastMCP framework, communicating over stdio with JSON-RPC. All tools are synchronous and read-only.

**Key Characteristics:**
- **Read-only design** — every tool carries `readOnlyHint: True` and `destructiveHint: False` annotations. No write operations to Prometheus.
- **Dual-channel output** — every tool returns both a markdown string (for text-only MCP clients) and a typed dict (for structured-output clients via `structuredContent`).
- **Synchronous tools, async runtime** — tool functions are plain `def` (not `async def`). FastMCP runs them in worker threads via `anyio.to_thread.run_sync`, so blocking HTTP calls don't block the asyncio event loop.
- **Singleton HTTP client** — a single `PrometheusClient` (wrapping `requests.Session`) is lazily created on first tool call, cached globally, and reused for connection pooling. Thread-safe via double-checked locking.
- **LLM-first error design** — every exception is caught at the tool boundary and translated into an actionable error message naming specific env vars and suggesting a fix.

## Layers

**Transport Layer (FastMCP + stdio):**
- Purpose: MCP protocol handling — tool registration, JSON-RPC over stdio, input validation via Pydantic
- Location: external `mcp` package; wired in `src/prometheus_mcp/server.py` and `src/prometheus_mcp/_mcp.py`
- Contains: `FastMCP` instance, `app_lifespan` context manager
- Depends on: `mcp>=1.2` package
- Used by: all tool functions (registered via `@mcp.tool` decorator)

**Tool Layer:**
- Purpose: Business logic — translate MCP tool calls into Prometheus API requests, shape responses, produce dual-channel output
- Location: `src/prometheus_mcp/tools.py`
- Contains: 5 tool functions + helper functions (`_shape_instant_sample`, `_shape_range_series`, `_truncation_hint`, `_format_value`)
- Depends on: `_mcp.get_client()`, `output.ok()`/`output.fail()`, `models.*` TypedDicts
- Used by: FastMCP runtime (invoked on `tools/call` JSON-RPC messages)

**Model Layer:**
- Purpose: Define typed output schemas for JSON-Schema generation and structured responses
- Location: `src/prometheus_mcp/models.py`
- Contains: 10 TypedDict classes covering all 5 tool outputs
- Depends on: `typing` / `typing_extensions`
- Used by: `tools.py` (type annotations on return values and intermediate data), FastMCP (schema generation)

**HTTP Client Layer:**
- Purpose: Communicate with Prometheus HTTP API v1 over HTTP(S)
- Location: `src/prometheus_mcp/client.py`
- Contains: `PrometheusClient` class, `_validate_url()`, `_parse_bool()` helpers
- Depends on: `requests`, `urllib3`, `errors.ConfigError`
- Used by: `_mcp.get_client()`, tool functions (via `client.get()`)

**Error Handling Layer:**
- Purpose: Map raw exceptions to actionable, LLM-readable error messages
- Location: `src/prometheus_mcp/errors.py`
- Contains: `ConfigError` exception class, `handle()` function
- Depends on: `requests` (for type checking `HTTPError`, `ConnectionError`, `Timeout`)
- Used by: `output.fail()` → tools catch-all `except Exception` blocks

**Output Layer:**
- Purpose: Construct dual-channel `CallToolResult` objects with both markdown and structured data
- Location: `src/prometheus_mcp/output.py`
- Contains: `ok()` and `fail()` functions
- Depends on: `mcp.types.CallToolResult`, `mcp.types.TextContent`, `errors.handle()`
- Used by: every tool function's return path

## Data Flow

### Primary Request Path (e.g., `prometheus_query`)

1. **MCP client sends** `tools/call` JSON-RPC message via stdio
2. **FastMCP runtime** validates input against Pydantic-generated schema, dispatches to `prometheus_query()` in a worker thread (`src/prometheus_mcp/tools.py:202`)
3. **Tool function** calls `get_client()` to obtain the cached `PrometheusClient` (`src/prometheus_mcp/_mcp.py:42`)
4. **`PrometheusClient.get()`** sends `GET /api/v1/query?query=...` via `requests.Session` (`src/prometheus_mcp/client.py:142`)
5. **Prometheus API** returns JSON response
6. **Tool function** shapes raw JSON into `list[InstantSample]` using `_shape_instant_sample()` (`src/prometheus_mcp/tools.py:60`)
7. **Tool function** builds a `QueryOutput` TypedDict + markdown string
8. **`output.ok()`** wraps both into a `CallToolResult` with `content` (markdown) and `structuredContent` (dict) (`src/prometheus_mcp/output.py:14`)
9. **FastMCP runtime** serializes the result back to the MCP client via stdio

### Error Path

1. Any exception in steps 3–7 is caught by the tool's `except Exception as exc` block
2. **`output.fail()`** calls `errors.handle(exc, action)` to produce an LLM-readable message (`src/prometheus_mcp/output.py:22`)
3. **`errors.handle()`** inspects exception type and HTTP status code, returns actionable string with env-var names and fix suggestions (`src/prometheus_mcp/errors.py:18`)
4. **`output.fail()`** raises `ToolError(message)`, which FastMCP transmits as an MCP error response

### Client Lifecycle

1. **Startup:** `app_lifespan` context manager yields an empty dict; no client created yet (`src/prometheus_mcp/_mcp.py:22`)
2. **First tool call:** `get_client()` acquires lock, creates `PrometheusClient` from env vars, caches it globally (`src/prometheus_mcp/_mcp.py:42`)
3. **Subsequent calls:** `get_client()` returns cached instance without lock (fast path)
4. **Shutdown:** `app_lifespan` finally-block closes the HTTP session and clears the cache (`src/prometheus_mcp/_mcp.py:28`)

**State Management:**
- Module-level global `_client: PrometheusClient | None` in `_mcp.py`, protected by `_client_lock: threading.Lock`
- No other mutable global state; tools are stateless pure functions (given the client)

## Key Abstractions

**`PrometheusClient`:**
- Purpose: Encapsulate HTTP communication with a Prometheus instance
- Location: `src/prometheus_mcp/client.py:62`
- Pattern: Thin wrapper around `requests.Session` with env-var-driven config
- API: `get(endpoint, params)` → parsed JSON; `close()` → cleanup

**TypedDict output schemas:**
- Purpose: Define the exact shape of structured tool output; FastMCP generates JSON-Schema from these for `outputSchema` in `tools/list`
- Examples: `ListMetricsOutput`, `QueryOutput`, `QueryRangeOutput`, `ListAlertsOutput`, `ListTargetsOutput` in `src/prometheus_mcp/models.py`
- Pattern: Each tool has a top-level TypedDict and zero or more nested TypedDicts (e.g., `InstantSample`, `RangeSeries`, `AlertItem`, `TargetItem`)

**Dual-channel output (`output.ok` / `output.fail`):**
- Purpose: Every tool returns *both* human-readable markdown (`content`) and machine-parseable structured data (`structuredContent`)
- Location: `src/prometheus_mcp/output.py`
- Pattern: `ok(data, markdown)` wraps into `CallToolResult`; `fail(exc, action)` raises `ToolError` with actionable message

**`@mcp.tool` decorator:**
- Purpose: Register synchronous functions as MCP tools with annotations (readOnly, destructive, idempotent, openWorld) and structured output
- Pattern: Decorator applied at module level in `tools.py`; tools module imported by `server.py` to trigger registration

## Entry Points

**Console script (`prometheus-mcp`):**
- Location: `src/prometheus_mcp/server.py:11` → `main()` → `mcp.run()`
- Triggers: Defined in `pyproject.toml` `[project.scripts]`: `prometheus-mcp = "prometheus_mcp.server:main"`
- Responsibilities: Import tools (triggers `@mcp.tool` registration), then start the FastMCP stdio event loop

**Direct execution:**
- `python -m prometheus_mcp.server` — same as console script (`if __name__ == "__main__": main()`)
- `python -c "from prometheus_mcp.server import mcp; mcp.run()"` — programmatic

**Docker:**
- `Dockerfile` installs from PyPI and runs `ENTRYPOINT ["prometheus-mcp"]`

## Dependency Graph

```text
server.py
  ├── tools.py (import triggers @mcp.tool registration)
  │     ├── _mcp.py (get_client, mcp instance)
  │     │     └── client.py (PrometheusClient)
  │     │           └── errors.py (ConfigError)
  │     ├── output.py (ok, fail)
  │     │     └── errors.py (handle)
  │     └── models.py (TypedDict schemas)
  └── _mcp.py (mcp, app_lifespan)
        └── client.py
```

**No circular imports.** The dependency DAG is strictly layered:
- `errors.py` → (no internal deps)
- `models.py` → (no internal deps)
- `client.py` → `errors.py`
- `output.py` → `errors.py`
- `_mcp.py` → `client.py`
- `tools.py` → `_mcp.py`, `output.py`, `models.py`
- `server.py` → `tools.py`, `_mcp.py`

## Architectural Constraints

- **Threading:** Asyncio event loop (FastMCP) with synchronous tools dispatched to worker threads via `anyio.to_thread.run_sync`. The `PrometheusClient` uses `requests` (blocking I/O). Concurrent tool calls race through the `_client_lock` only on first access.
- **Global state:** Single mutable global: `_mcp._client` (the cached `PrometheusClient`). Protected by `_mcp._client_lock` (threading.Lock). Cleared on shutdown via `app_lifespan`.
- **Circular imports:** None. Strict DAG as shown above.
- **Read-only:** All 5 tools are read-only GET requests to Prometheus API v1. No mutations, no state changes on the Prometheus side.
- **Output caps:** Metrics capped at 500 (`_METRICS_CAP`), range points capped at 5000 (`_RANGE_POINTS_CAP`), markdown items capped at 20 (`_MD_ITEM_LIMIT`). These are hardcoded constants in `tools.py`.
- **Python compat:** Requires Python ≥3.10. Uses `typing_extensions.TypedDict` on Python <3.12 for Pydantic compat.

## Anti-Patterns

### None Identified

The codebase is small (~1100 lines of source) and well-structured. No significant anti-patterns detected. The layering is clean, the error handling is consistent, and the separation of concerns is clear.

## Error Handling

**Strategy:** Catch-all at tool boundary, translate to actionable LLM messages.

**Patterns:**
- Every tool function wraps its body in `try: ... except Exception as exc: output.fail(exc, "action description")`
- `output.fail()` calls `errors.handle()` which dispatches on exception type:
  - `ConfigError` → mentions all 5 env vars
  - `HTTPError` → dispatches on status code (401, 403, 404, 400/422, 429, 5xx)
  - `ConnectionError` → mentions PROMETHEUS_URL and default port 9090
  - `Timeout` → suggests narrowing range/increasing step
  - `ValueError` → surfaces the message directly (input validation)
  - Anything else → generic fallback with class name and message
- `output.fail()` raises `ToolError` (from `mcp.server.fastmcp.exceptions`) which FastMCP serializes as an error response

## Cross-Cutting Concerns

**Logging:** Python stdlib `logging` module. Only used in `_mcp.py` for startup/shutdown debug messages. Tools do not log — errors are surfaced via `ToolError`.

**Validation:**
- Input: Pydantic `Field` annotations with `min_length`, `max_length`, `default`, `description` on tool parameters. FastMCP generates JSON-Schema for MCP clients.
- URL: `_validate_url()` in `client.py` checks scheme and host.
- State param: Manual validation in `prometheus_list_targets()` before HTTP call.

**Authentication:** Configured via env vars, resolved at `PrometheusClient` construction:
- `PROMETHEUS_TOKEN` → Bearer auth (highest priority)
- `PROMETHEUS_USERNAME` + `PROMETHEUS_PASSWORD` → HTTP Basic auth
- Neither → unauthenticated (valid for internal Prometheus)

**Configuration:** All config via environment variables — no config files, no CLI args, no database. 5 env vars: `PROMETHEUS_URL` (required), `PROMETHEUS_TOKEN`, `PROMETHEUS_USERNAME`, `PROMETHEUS_PASSWORD`, `PROMETHEUS_SSL_VERIFY` (all optional).

---

*Architecture analysis: 2026-06-06*
