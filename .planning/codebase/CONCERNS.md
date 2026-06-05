# Codebase Concerns

**Analysis Date:** 2026-06-06

## Tech Debt

**`type: ignore[return-value]` on every tool return:**
- Issue: All 5 tool functions in `src/prometheus_mcp/tools.py` (lines 186, 287, 442, 535, 691) use `# type: ignore[return-value]` because the declared return type is a `TypedDict` (e.g. `ListMetricsOutput`) but the actual return is a `CallToolResult` from `output.ok()`. The type signatures lie to the caller.
- Files: `src/prometheus_mcp/tools.py`
- Impact: Type checkers cannot validate tool return values. A future mypy/pyright strict pass will flag every tool. Consumers importing these functions get misleading type hints.
- Fix approach: Define overloaded return types, use `Any` return, or refactor so that `output.ok()` returns the declared TypedDict when called internally while FastMCP wraps it. Alternatively, annotate return as `CallToolResult` and let FastMCP infer the structured schema differently.

**`output.fail()` silently breaks control flow:**
- Issue: In every tool's `except` block, `output.fail(exc, ...)` is called without `return` or `raise` in the tool code. This works because `output.fail()` raises `ToolError` internally (declared as `NoReturn`), but reading the tool code alone, the `except` branch appears to fall through without returning a value. This pattern is fragile — if `fail()` were ever refactored to not raise, all 5 tools would silently return `None`.
- Files: `src/prometheus_mcp/tools.py` (lines 188, 289, 444, 537, 693), `src/prometheus_mcp/output.py` (line 22)
- Impact: Low current risk (the `NoReturn` annotation is correct), but a maintenance footgun for anyone unfamiliar with the codebase.
- Fix approach: Explicitly write `raise` or `return` after `output.fail()` calls for clarity, or restructure as `raise output.fail(exc, action)`.

**Version duplicated in 3 places:**
- Issue: Version `0.1.0` is hardcoded in `pyproject.toml` (line 7), `src/prometheus_mcp/__init__.py` (line 3), and `server.json` (line 9). No single-source-of-version mechanism.
- Files: `pyproject.toml`, `src/prometheus_mcp/__init__.py`, `server.json`
- Impact: Version drift risk on release. The publish CI checks tag vs `pyproject.toml` but not `__init__.py` or `server.json`.
- Fix approach: Use `hatch-vcs` or `importlib.metadata.version()` in `__init__.py` to derive version from the installed package. Update `server.json` programmatically or via a pre-release script.

**Dockerfile installs from PyPI, not local source:**
- Issue: `Dockerfile` (line 6) runs `pip install --no-cache-dir prometheus-mcp` from PyPI. This means the Docker image always uses the published version, not the current working tree. Local development via Docker is impossible without a manual `pip install -e .` step.
- Files: `Dockerfile`
- Impact: Docker builds don't reflect local changes. CI/CD for Docker image builds would lag behind the codebase until the next PyPI publish.
- Fix approach: Add a `COPY . /app` + `pip install .` path for development, or provide a separate `Dockerfile.dev`. Keep the PyPI install for production images if desired.

**No `conftest.py` — test fixtures duplicated:**
- Issue: The client cache reset fixture is duplicated across `tests/test_tools_integration.py` (lines 32-51) and `tests/test_mcp_client_cache.py` (lines 17-26). Both manually acquire `_mcp._client_lock` and reset `_mcp._client`.
- Files: `tests/test_tools_integration.py`, `tests/test_mcp_client_cache.py`
- Impact: Maintenance burden; if the client cache mechanism changes, two fixtures must be updated.
- Fix approach: Extract the shared reset fixture into `tests/conftest.py`.

## Security Considerations

**No PromQL input sanitization:**
- Risk: The `query` parameter in `prometheus_query()` and `prometheus_query_range()` is passed directly to the Prometheus HTTP API without any sanitization (only Pydantic `max_length=2000` validation). While Prometheus itself rejects malformed PromQL, an attacker with access to the MCP server could craft queries that:
  - Enumerate all metric names / label values for reconnaissance
  - Execute expensive queries that DoS the Prometheus server (e.g. `{__name__=~".+"}`)
  - Exploit theoretical future Prometheus HTTP API vulnerabilities
- Files: `src/prometheus_mcp/tools.py` (lines 202-289, 303-444)
- Current mitigation: Prometheus is typically internal-only. The MCP server is read-only (no write endpoints). Pydantic enforces max query length (2000 chars).
- Recommendations: This is acceptable for the current threat model (trusted LLM agents calling a read-only API). If exposed to untrusted inputs, consider adding a PromQL complexity limiter or query cost estimator. Document the trust model explicitly.

**SSL verification can be disabled:**
- Risk: `PROMETHEUS_SSL_VERIFY=false` disables TLS certificate verification and suppresses urllib3 warnings globally via `urllib3.disable_warnings()` at line 124 of `client.py`. This is process-wide and affects all urllib3 users in the same process.
- Files: `src/prometheus_mcp/client.py` (lines 102-124)
- Current mitigation: SSL verify defaults to `true`. The option exists for self-signed certs in internal deployments.
- Recommendations: Instead of global `urllib3.disable_warnings()`, suppress only on the session. Document that this disables verification for the entire process.

**Credentials stored in plain-text env vars:**
- Risk: `PROMETHEUS_TOKEN` and `PROMETHEUS_PASSWORD` are read from environment variables and stored as plain attributes on the `PrometheusClient` instance (`self.token`, `self.password` at lines 98-100 of `client.py`). They persist in memory for the lifetime of the process and could be leaked via debugging, logging, or memory dumps.
- Files: `src/prometheus_mcp/client.py` (lines 98-100)
- Current mitigation: Standard approach for container/serverless deployments. `.env` is in `.gitignore`.
- Recommendations: Consider clearing `self.token`/`self.password` after setting session auth. Use `__repr__` redaction if the client is ever logged.

**No `tests/__init__.py` — test discovery ambiguity:**
- Risk: Missing `tests/__init__.py` means `pytest` relies on `rootdir` detection. Currently works because `pyproject.toml` sets `testpaths = ["tests"]`, but could break with certain `pytest` invocation patterns or if tests import from each other.
- Files: `tests/` directory
- Impact: Minor — pytest handles this fine in practice.
- Fix approach: Add an empty `tests/__init__.py`.

## Performance Risks

**`prometheus_list_metrics` fetches ALL metric names every call:**
- Problem: `prometheus_list_metrics()` calls `GET /api/v1/label/__name__/values` which returns every metric name in Prometheus, then applies the substring filter client-side (line 161 of `tools.py`). Large Prometheus instances can have 100,000+ metric names.
- Files: `src/prometheus_mcp/tools.py` (lines 153-188)
- Cause: Prometheus's label values API has no native substring filtering. The cap at 500 returned metrics (line 167) only limits output, not the data fetched.
- Improvement path: Cache the metric names list with a short TTL (30-60s). Consider using Prometheus's `match[]` parameter on newer API versions. Document the performance characteristic for operators.

**No HTTP response size limits:**
- Problem: `client.get()` calls `response.json()` without any size guard (line 151 of `client.py`). A range query returning massive matrices could consume unbounded memory before the 5000-point cap is applied in `tools.py`.
- Files: `src/prometheus_mcp/client.py` (line 151), `src/prometheus_mcp/tools.py` (line 392)
- Cause: The HTTP response is fully loaded into memory, then the JSON is parsed, then the cap is applied.
- Improvement path: Add `stream=True` and parse incrementally, or set a response size limit via `requests` adapter. In practice, Prometheus itself limits response sizes, but defense-in-depth is warranted for production use.

**Fixed 30-second timeout for all requests:**
- Problem: All HTTP requests use a hardcoded 30-second timeout (line 138 of `client.py`). Range queries over large time windows may legitimately need more time, while simple metadata queries could use a shorter timeout.
- Files: `src/prometheus_mcp/client.py` (line 138)
- Cause: Single timeout value for all endpoint types.
- Improvement path: Make timeout configurable via `PROMETHEUS_TIMEOUT` env var. Consider per-endpoint timeout hints (metadata = 10s, range query = 60s).

**Singleton client cannot be reconfigured:**
- Problem: The `PrometheusClient` is lazily created once and cached forever in `_mcp._client` (line 54 of `_mcp.py`). If environment variables change (e.g., token rotation), the server must be restarted.
- Files: `src/prometheus_mcp/_mcp.py` (lines 42-55)
- Cause: Design choice for simplicity and connection pooling.
- Improvement path: Add a TTL to the client cache, or expose an admin tool to force reconnection. For MCP servers (typically short-lived stdio processes), this is acceptable.

## Reliability Risks

**No retry logic for transient failures:**
- Problem: HTTP requests to Prometheus have no retry mechanism. Transient 5xx errors, connection resets, and timeouts result in immediate failure. The error messages suggest retrying, but the server doesn't do it automatically.
- Files: `src/prometheus_mcp/client.py` (lines 126-140)
- Impact: MCP clients (LLMs) must manually retry, which wastes tokens and latency. A simple 1-retry with backoff would handle most transient issues.
- Fix approach: Add `urllib3.util.Retry` to the `requests.Session` adapter, or use `tenacity` with limited retries for 5xx/timeout.

**Bare `except Exception` in every tool:**
- Problem: Each tool wraps its entire body in `try/except Exception` (tools.py lines 153/187, 250/288, 378/443, 483/536, 589/692). This catches everything including `KeyboardInterrupt` (via `BaseException` subclasses — though `Exception` technically doesn't catch `KeyboardInterrupt`). More importantly, it means programming errors (e.g. `AttributeError`, `KeyError`) in shaping logic are converted to user-facing `ToolError` messages that may be confusing.
- Files: `src/prometheus_mcp/tools.py`
- Impact: Bugs in data shaping code are silently converted to "unexpected RuntimeError" messages instead of producing a traceback for debugging.
- Fix approach: Narrow the `try/except` to wrap only the HTTP call and response parsing, not the entire function body. Let programming errors propagate as unhandled exceptions for proper debugging.

**No health check endpoint:**
- Problem: The MCP server provides no liveness or readiness probe. The only way to verify it works is to call a tool. For containerized deployments, this means no health check for orchestrators (Kubernetes, Docker Compose).
- Files: `src/prometheus_mcp/server.py`, `Dockerfile`
- Impact: Container orchestrators cannot detect if the server is stuck or misconfigured without calling a full tool.
- Fix approach: Implement a lightweight `_ping` or `health` tool, or rely on the MCP `initialize` handshake as the health signal.

## Maintainability Issues

**`tools.py` is a 693-line monolith:**
- Files: `src/prometheus_mcp/tools.py`
- Why concern: All 5 tools, all helper functions, and all markdown formatting logic live in a single file. Each tool function is 80-100 lines mixing HTTP calls, data shaping, markdown generation, and structured output assembly.
- Safe modification: Changes to one tool's markdown format risk merge conflicts with changes to another tool. The file is the most likely conflict point in multi-developer workflows.
- Fix approach: Extract markdown formatting into `src/prometheus_mcp/formatters.py`. Each tool function would call `shape_*()` + `format_*()` separately, keeping `tools.py` as a thin orchestrator.

**Tests directly access private module state:**
- Files: `tests/test_tools_integration.py` (lines 37-51), `tests/test_mcp_client_cache.py` (lines 20-26)
- Why concern: Tests manipulate `_mcp._client` and `_mcp._client_lock` directly. This couples tests to internal implementation details. Any refactoring of the client cache (e.g., moving to a class-based registry) would break all integration tests.
- Fix approach: Expose a `reset_client()` function in `_mcp.py` for testing, or use dependency injection for the client.

**No type checking configured:**
- Files: `pyproject.toml`
- Why concern: No mypy, pyright, or pytype configuration. The 5 `type: ignore[return-value]` suppressions in `tools.py` suggest someone attempted type checking but didn't integrate it into CI.
- Impact: Type errors accumulate silently. The `type: ignore` comments may mask real issues.
- Fix approach: Add `mypy` or `pyright` to `[project.optional-dependencies.dev]` and add a step to `.github/workflows/test.yml`.

## Missing Capabilities

**No metadata / `HELP` / `TYPE` introspection:**
- Problem: The server exposes metric names via `prometheus_list_metrics` but provides no way to retrieve metric `HELP` text or `TYPE` (counter, gauge, histogram, summary). Prometheus exposes this via `GET /api/v1/metadata`.
- Impact: LLM agents must guess what a metric measures and its type, leading to incorrect PromQL (e.g., using `rate()` on a gauge).
- Blocks: Effective autonomous metric exploration without prior domain knowledge.

**No label value discovery:**
- Problem: No tool to list values for a specific label (e.g., "what jobs exist?" or "what instances are in job X?"). Prometheus exposes `GET /api/v1/label/{label_name}/values`.
- Impact: Agents must use `prometheus_query` with `group by` to discover label values, which is slower and less ergonomic.
- Blocks: Efficient label exploration for query building.

**No rule / recording rule inspection:**
- Problem: Prometheus recording rules and alerting rules are not exposed. Prometheus provides `GET /api/v1/rules`.
- Impact: Agents cannot understand the full alerting configuration or see which recording rules exist.

**No configurable request timeout:**
- Problem: The 30-second timeout is hardcoded. No `PROMETHEUS_TIMEOUT` env var.
- Impact: Operators of slow or remote Prometheus instances cannot tune timeout without code changes.

**No pagination / cursor support for large result sets:**
- Problem: `prometheus_list_metrics` caps at 500, `prometheus_list_alerts` and `prometheus_list_targets` return everything. There's no pagination mechanism for any tool.
- Impact: Instances with thousands of alerts or targets will produce large outputs. The markdown truncation at 20 items helps, but structured output still contains the full dataset.

## Dependency Risks

**`mcp>=1.2` — broad version range:**
- Risk: The `mcp` package (FastMCP) is pinned with only a lower bound (`>=1.2`). FastMCP is rapidly evolving; breaking changes in the `mcp` package could silently break the server on `pip install --upgrade`.
- Files: `pyproject.toml` (line 29)
- Impact: Future `mcp` versions may change `CallToolResult`, `ToolError`, or `structured_output` behavior. The `# type: ignore` comments and the `output.ok()` wrapper are already adapting to API quirks.
- Migration plan: Pin to `mcp>=1.2,<2.0` or `~=1.2` once the API stabilizes. Run tests against multiple `mcp` versions in CI.

**`requests` — synchronous HTTP in an async world:**
- Risk: The project uses `requests` (synchronous) instead of `httpx` or `aiohttp`. FastMCP runs sync tools in worker threads, which works but limits concurrency to the thread pool size.
- Files: `src/prometheus_mcp/client.py`, `pyproject.toml` (line 30)
- Impact: Under high concurrent tool calls, the thread pool becomes the bottleneck. Not a concern for typical MCP usage (single agent, sequential calls), but limits future scalability.
- Migration plan: No action needed for current use case. If concurrent tool calls become needed, migrate to `httpx.AsyncClient` with `async def` tools.

**No lockfile committed:**
- Risk: No `requirements.lock`, `uv.lock`, or `pip-compile` output is committed. Dependency resolution is non-deterministic across environments.
- Files: Repository root (missing file)
- Impact: CI and production may get different transitive dependency versions. A transitive dependency update could break the build silently.
- Migration plan: Add `uv lock` or `pip-compile` output for reproducible installs. At minimum, pin transitive deps in CI.

## Test Coverage Gaps

**No tests for concurrent client initialization:**
- What's not tested: The double-checked locking in `_mcp.get_client()` (lines 50-55) is not tested under actual concurrent access. `test_mcp_client_cache.py` only tests sequential calls.
- Files: `src/prometheus_mcp/_mcp.py` (lines 50-55)
- Risk: Race condition bugs in the locking pattern would go undetected.
- Priority: Low — the pattern is standard and correct by inspection.

**No tests for `client._request()` / `client.get()` HTTP behavior:**
- What's not tested: The `PrometheusClient.get()` method (line 142) and `_request()` (line 126) are only tested indirectly through integration tests. No unit tests verify timeout behavior, empty response handling (`response.content` check at line 149), or session reuse.
- Files: `src/prometheus_mcp/client.py` (lines 126-151)
- Risk: Edge cases in HTTP response handling (empty body, non-JSON response, timeout) are not covered.
- Priority: Medium — these are the most likely failure points in production.

**No tests for `app_lifespan` shutdown behavior:**
- What's not tested: The `app_lifespan` async context manager (`_mcp.py` lines 21-36) is never exercised in tests. The `client.close()` call during shutdown is untested.
- Files: `src/prometheus_mcp/_mcp.py` (lines 21-36)
- Risk: Resource leaks if shutdown cleanup fails silently (the bare `except Exception: pass` at line 33 already swallows all errors).
- Priority: Low — cleanup failure has no functional impact for short-lived stdio processes.

**No negative test for `list_targets` with `state='dropped'` or `state='any'`:**
- What's not tested: The `state` parameter branching in `prometheus_list_targets` (lines 606-611) is only tested for `state='active'` (default) and invalid state. The `'dropped'` and `'any'` branches have no coverage.
- Files: `src/prometheus_mcp/tools.py` (lines 606-611), `tests/test_tools_integration.py`
- Risk: Bugs in the `dropped` or `any` filtering paths would go undetected.
- Priority: Medium — these are documented features.

## Recommendations

**Priority 1 (High Impact, Low Effort):**
1. Add `tests/conftest.py` with shared client-reset fixture — removes duplication, 15 min
2. Pin `mcp` upper bound in `pyproject.toml` (`mcp>=1.2,<2.0`) — prevents surprise breakage, 5 min
3. Add tests for `state='dropped'` and `state='any'` in `prometheus_list_targets` — covers untested branches, 30 min

**Priority 2 (High Impact, Medium Effort):**
4. Extract markdown formatters from `tools.py` into `formatters.py` — improves maintainability of the largest file, 1-2 hours
5. Add `urllib3.util.Retry` to `requests.Session` for transient 5xx — improves reliability without adding deps, 30 min
6. Add configurable timeout via `PROMETHEUS_TIMEOUT` env var — operator quality-of-life, 30 min

**Priority 3 (Medium Impact, Medium Effort):**
7. Add a `prometheus_get_metric_metadata` tool wrapping `/api/v1/metadata` — biggest missing capability, 2-3 hours
8. Add a `prometheus_list_label_values` tool wrapping `/api/v1/label/{name}/values` — second biggest gap, 1-2 hours
9. Add mypy/pyright to CI and resolve the `type: ignore` suppressions — improves code quality, 2-3 hours
10. Fix `Dockerfile` to support local builds (`COPY . /app && pip install .`) — enables Docker-based development, 30 min

**Priority 4 (Low Impact, Future Consideration):**
11. Add response size limits or streaming for large Prometheus responses
12. Add metric name caching with TTL for `prometheus_list_metrics`
13. Commit a lockfile (`uv.lock` or `pip-compile` output) for reproducible builds
14. Single-source the version (use `hatch-vcs` or `importlib.metadata`)

---

*Concerns audit: 2026-06-06*
