# Domain Pitfalls

**Domain:** MCP server for Prometheus — v2.0 feature additions
**Researched:** 2026-06-08
**Focus:** Mistakes when adding Alertmanager, cardinality, federation, health checks, caching, and response limits to an existing MCP server

## Critical Pitfalls

Mistakes that cause rewrites, break existing functionality, or create production incidents.

### Pitfall 1: Alertmanager API Is Not Prometheus API

**What goes wrong:** Developers assume Alertmanager uses the same API conventions as Prometheus (`/api/v1/` prefix, same JSON envelope `{"status":"success","data":...}`). The Alertmanager API v2 uses `/api/v2/` prefix, returns raw JSON arrays (not wrapped in a `data` envelope), and has different error response shapes (plain strings for 400/500, not `{"errorType":"...","error":"..."}`).

**Why it happens:** The existing `PrometheusClient.get()` calls `self.api_url` (hardcoded as `{url}/api/v1`) and expects `response.json().get("data")`. Reusing this client for Alertmanager will silently return `None` for every call because Alertmanager responses have no `"data"` wrapper — `GET /api/v2/silences` returns a raw JSON array `[{...}, ...]`.

**Consequences:** All Alertmanager tools return empty results with no error. This is invisible to the AI agent — it sees "0 silences" when there are actually 100. Debugging is extremely difficult because there's no error thrown.

**Prevention:**
- Create a dedicated `AlertmanagerClient` class (or at minimum a separate `get_raw()` method) that does NOT strip responses through the `data` key
- Use `/api/v2/` base path for all Alertmanager endpoints
- Parse Alertmanager error responses as plain strings, not JSON `{"error":"..."}` objects
- Test with actual Alertmanager response fixtures (not Prometheus-shaped mocks)

**Detection:** Integration tests that assert non-empty results against realistic Alertmanager response fixtures. If `GET /api/v2/silences` returns `[]` when the fixture contains silences, the parsing is wrong.

**Phase assignment:** Must be addressed in the Alertmanager phase. Design the client separation before writing any tools.

---

### Pitfall 2: Singleton Client Cannot Handle Multiple Endpoints

**What goes wrong:** The current architecture uses a module-global singleton `_client` in `_mcp.py` created from `PROMETHEUS_URL`. Adding Alertmanager (different URL) and federation (multiple Prometheus URLs) breaks this singleton model. Developers try to add `_alertmanager_client` and `_federation_clients` as additional globals, leading to initialization ordering bugs, missing cleanup in lifespan, and untestable code.

**Why it happens:** The singleton pattern in `_mcp.py` with `get_client()` and double-checked locking was designed for exactly one Prometheus instance. The lifespan cleanup only closes `_client`. Each new global needs its own lock, its own cleanup, and its own lazy-init — tripling the boilerplate and bug surface.

**Consequences:** Resource leaks (unclosed HTTP sessions), race conditions on federation client initialization, test pollution between test modules because `reset_client_cache` fixture only resets the Prometheus client.

**Prevention:**
- Refactor to a `ClientRegistry` (or `ClientManager`) that holds named clients: `{"prometheus": PrometheusClient, "alertmanager": AlertmanagerClient, "fed_dc1": PrometheusClient, ...}`
- Single lock, single lifespan cleanup loop, single `reset_all()` for tests
- Each client type has its own env-var prefix: `ALERTMANAGER_URL`, `PROMETHEUS_FEDERATION_URLS`
- Introduce the registry in a foundational phase BEFORE adding Alertmanager or federation tools

**Detection:** Test that creates an Alertmanager client and a federation client, then verifies lifespan shutdown closes ALL sessions. Test that `reset_client_cache` (renamed to `reset_all_clients`) actually clears everything.

**Phase assignment:** Must be the first phase of v2.0 — client infrastructure refactoring before any new tools.

---

### Pitfall 3: Federation Config Explosion

**What goes wrong:** Federation requires connecting to N Prometheus instances. Developers expose this as a single env var like `PROMETHEUS_FEDERATION_URLS=http://prom1:9090,http://prom2:9090,http://prom3:9090`. But each instance may need different auth (one uses Bearer, another uses Basic), different timeouts, different SSL settings. A single comma-separated URL string cannot express this.

**Why it happens:** Following the pattern of `PROMETHEUS_URL` (one env var per setting) seems natural but doesn't scale to N instances with heterogeneous auth.

**Consequences:** Users with mixed-auth federation deployments (common in large enterprises — DC1 uses OIDC, DC2 uses mTLS, DC3 uses Basic auth) cannot use the federation feature at all. They file bugs, and the fix requires breaking config format changes.

**Prevention:**
- Use structured config via JSON env var or config file: `PROMETHEUS_FEDERATION_CONFIG='[{"name":"dc1","url":"...","token":"..."},{"name":"dc2","url":"...","username":"...","password":"..."}]'`
- Alternatively, use env-var naming convention: `PROMETHEUS_FED_DC1_URL`, `PROMETHEUS_FED_DC1_TOKEN`, etc.
- Start with the simpler approach (comma-separated URLs, shared auth) but design the internal model to support per-instance config from day one — so upgrading is additive, not breaking
- Document clearly what's supported in v2.0 vs what's planned

**Detection:** Config validation tests that reject `PROMETHEUS_FEDERATION_URLS` when instances need different auth. Integration test with two mock Prometheus instances using different auth methods.

**Phase assignment:** Federation phase. Must be designed before implementation, not discovered during testing.

---

### Pitfall 4: Caching Metric Names Hides Newly Deployed Services

**What goes wrong:** Metric name caching with TTL means that when a new service is deployed and starts exporting metrics, agents won't see those metrics until the cache expires. For `prometheus_list_metrics` (the discovery tool agents call first), this means the agent literally cannot discover new metrics during the cache window.

**Why it happens:** The obvious caching approach is: cache the full metric names list, serve from cache for TTL seconds. This is correct for performance but wrong for discovery workflows where agents need to find metrics from a just-deployed service during incident investigation.

**Consequences:** Agent investigating a deployment issue calls `prometheus_list_metrics(pattern="new_service")` and gets "0 metrics found." The agent concludes the service isn't instrumented and investigates the wrong direction. The human wastes 30 minutes before realizing the cache was stale.

**Prevention:**
- Make cache bypass easy: add `cache: bool = True` parameter to `prometheus_list_metrics` so agents can force a fresh fetch
- Use short default TTL (60-120s, not 5-10 minutes) — the cache is for reducing load on Prometheus during rapid-fire agent queries, not for long-term memoization
- Only cache the unfiltered full list; when `pattern` is provided, apply the filter to the cached list but allow a force-refresh
- Log cache hits/misses at DEBUG level so operators can diagnose stale-data issues
- Document the caching behavior in the tool's docstring so the AI agent knows it can force-refresh

**Detection:** Test: populate cache, "deploy new metric" (update mock), call with `cache=False`, verify new metric appears. Test: verify cache expires after TTL.

**Phase assignment:** Caching phase. Design cache invalidation strategy before implementing the cache.

---

### Pitfall 5: Response Size Limits Silently Truncate Valid Query Results

**What goes wrong:** Adding HTTP response size limits (e.g., "reject responses > 10MB") causes `prometheus_query_range` and `prometheus_list_metrics` to fail on legitimate queries in large Prometheus deployments. Developers implement this as a hard cut on `response.content` length, which truncates JSON mid-stream — the truncated JSON fails to parse, and the agent sees "Error: unexpected JSONDecodeError."

**Why it happens:** The defense-in-depth intention is correct (protect the MCP server from OOM on unbounded Prometheus responses), but the implementation cuts at the HTTP layer without understanding the JSON structure.

**Consequences:** Queries that worked in v1.0 start failing in v2.0 with cryptic JSON parse errors. This is a backward compatibility violation. Worse, the error message doesn't tell the agent WHY parsing failed, so it retries the same query in an infinite loop.

**Prevention:**
- Implement size limits as a pre-check on `Content-Length` header (when available) BEFORE reading the body — reject early with a clear error message
- For chunked responses (no Content-Length), use `response.iter_content()` with a byte counter and abort with a clear error if exceeded
- The error message must be actionable: "Response size (15.2 MB) exceeds the 10 MB limit. Try narrowing the time range, increasing the step, or adding label matchers to reduce the result set."
- Set a generous default (50MB or even 100MB) — this is defense-in-depth against runaway responses, not a tight budget
- Make it configurable via `PROMETHEUS_MAX_RESPONSE_SIZE` env var
- Never truncate and try to parse — either accept the full response or reject it entirely

**Detection:** Test with a mock response body slightly over the limit. Verify the error message is clear and actionable. Test that responses under the limit still work. Test with chunked transfer encoding.

**Phase assignment:** Response limits phase. Can be implemented independently but must not break existing tool behavior.

---

## Moderate Pitfalls

### Pitfall 6: Health Check Tool Creates Circular Dependency

**What goes wrong:** The health check tool (`prometheus_health_check`) calls Prometheus's `/-/healthy` endpoint. If the MCP server is deployed as a sidecar to Prometheus and Kubernetes uses the MCP server's health endpoint for liveness probes, you get a circular dependency: Prometheus must be healthy for MCP to report healthy, and if MCP reports unhealthy, Kubernetes may restart the pod, killing Prometheus too.

**Prevention:**
- Health check should report the MCP server's own health, not Prometheus's health
- Separate concerns: `prometheus_health_check` is a TOOL (agent calls it to check Prometheus), not the MCP server's own liveness endpoint
- If an MCP-level health endpoint is needed (for Kubernetes), implement it as an HTTP endpoint on the MCP server itself (not as an MCP tool) that returns 200 if the process is alive — independent of Prometheus connectivity
- Document clearly: "This tool checks Prometheus health for investigation purposes. It is NOT the MCP server's own health endpoint."

**Detection:** Architecture review. Test that the health check tool can return "Prometheus unreachable" without the MCP server itself crashing or becoming unhealthy.

**Phase assignment:** Health check phase. Design decision must be made upfront.

---

### Pitfall 7: Alertmanager Auth Is Independently Configured

**What goes wrong:** Developers reuse `PROMETHEUS_TOKEN` for Alertmanager calls. In many deployments, Alertmanager is a different service with different credentials, different network path, and potentially different TLS settings. Using Prometheus credentials for Alertmanager silently fails with 401/403, and the error message says "Check PROMETHEUS_TOKEN" — confusing because the token IS correct for Prometheus.

**Prevention:**
- Dedicated env vars: `ALERTMANAGER_URL`, `ALERTMANAGER_TOKEN`, `ALERTMANAGER_USERNAME`, `ALERTMANAGER_PASSWORD`, `ALERTMANAGER_SSL_VERIFY`
- Update `errors.py` to produce Alertmanager-specific error messages: "Check ALERTMANAGER_TOKEN" not "Check PROMETHEUS_TOKEN"
- Make Alertmanager entirely optional — if `ALERTMANAGER_URL` is not set, Alertmanager tools should return a clear message: "Alertmanager not configured. Set ALERTMANAGER_URL to enable."
- Document in `.env.example` and `server.json`

**Detection:** Test calling an Alertmanager tool without `ALERTMANAGER_URL` set — should get a helpful ConfigError, not a crash. Test with wrong Alertmanager credentials — should get Alertmanager-specific error message.

**Phase assignment:** Alertmanager phase. Must update errors.py and .env.example.

---

### Pitfall 8: Cardinality Stats API Not Available on All Prometheus Versions

**What goes wrong:** The `/api/v1/status/tsdb` endpoint is used for cardinality statistics. Developers assume it exists on all Prometheus versions. Older Prometheus versions (pre-2.14 for basic TSDB stats, and the detailed fields evolved over time) may not support all fields. Remote-storage or Thanos/Cortex/Mimir frontends may not implement this endpoint at all.

**Prevention:**
- Handle 404 on `/api/v1/status/tsdb` gracefully: "Cardinality statistics are not available on this Prometheus instance. This endpoint requires Prometheus 2.14+ and is not supported by all Prometheus-compatible backends (e.g., Thanos Query, Cortex, Mimir)."
- Parse response defensively — treat every field as optional with sensible defaults
- Don't make cardinality tools a dependency for other tools — they should be purely additive

**Detection:** Test with a mock 404 response for `/api/v1/status/tsdb`. Test with a partial response (only `headStats`, no `seriesCountByMetricName`).

**Phase assignment:** Cardinality phase.

---

### Pitfall 9: Federation Tool Naming Collision with Existing Tools

**What goes wrong:** Federation adds the ability to query multiple Prometheus instances. Developers create `prometheus_query` overloads or add an `instance` parameter to existing tools. This breaks backward compatibility — existing agents that call `prometheus_query(query="up")` now need to specify which instance to target.

**Prevention:**
- Federation tools must be NEW tools with distinct names: `prometheus_federation_query`, `prometheus_federation_list_instances`
- Existing tools (`prometheus_query`, `prometheus_list_metrics`, etc.) must continue targeting the primary Prometheus instance exactly as before
- Federation is an ADDITIONAL capability, not a replacement
- The `prometheus_federation_query` tool should accept an `instance` parameter (name from federation config) to target a specific remote Prometheus

**Detection:** Protocol test (`test_protocol.py`) must continue to validate all 8 existing tool names unchanged. New federation tools are added to `EXPECTED_TOOLS` separately.

**Phase assignment:** Federation phase. Naming convention must be decided in the design phase.

---

### Pitfall 10: Thread Safety of In-Memory Cache

**What goes wrong:** Metric name caching adds a module-global dict/list for cached metric names plus a timestamp. Multiple worker threads (FastMCP runs tools in threads) can read and write this cache concurrently. Without synchronization, you get torn reads (partial cache state), duplicate refresh calls (thundering herd on cache expiry), or corrupted state.

**Prevention:**
- Use `threading.Lock` to protect cache read/write (the existing pattern from `_mcp.py` with `_client_lock` is the right model)
- Consider using `functools.lru_cache` with a wrapper that checks TTL — simpler than hand-rolled cache
- For thundering herd: use a "single-flight" pattern where the first thread to find an expired cache starts the refresh, and other threads serve the stale-but-valid cached value while the refresh is in progress
- Keep the cache simple — a single `(timestamp, list[str])` tuple protected by a lock is sufficient for metric names

**Detection:** Concurrent test: launch 10 threads calling `prometheus_list_metrics` simultaneously with an expired cache. Verify exactly one HTTP call is made to Prometheus (no thundering herd). Verify all threads get a valid result.

**Phase assignment:** Caching phase.

---

### Pitfall 11: Alertmanager Silences Require Write-API Awareness Even for Read-Only

**What goes wrong:** The Alertmanager API v2 mixes read and write operations on the same paths. `GET /api/v2/silences` lists silences (read), but `POST /api/v2/silences` creates silences (write). Developers implementing the read-only tool accidentally expose the wrong HTTP method, or the tool description misleads agents into thinking they can create silences.

**Prevention:**
- Explicitly use `GET` only in the Alertmanager client — never `POST`, `PUT`, or `DELETE`
- Tool descriptions must clearly state: "Lists active and expired silences. This tool cannot create, modify, or delete silences."
- Tool annotations must include `readOnlyHint: True`, `destructiveHint: False` (existing pattern from v1.0 tools)
- Code review checklist: verify all Alertmanager client methods use `session.get()`, never `session.post()`

**Detection:** Code review. Grep for `session.post`, `session.put`, `session.delete` in Alertmanager client code — should find zero matches.

**Phase assignment:** Alertmanager phase.

---

## Minor Pitfalls

### Pitfall 12: Cache Invalidation on Config Reload

**What goes wrong:** If `PROMETHEUS_URL` changes (container restart with different env vars), the cached metric names are from the old Prometheus instance. This is rare in production but common during development and testing.

**Prevention:** Tie cache validity to the Prometheus URL. Store `(url, timestamp, data)` not just `(timestamp, data)`. On client recreation, invalidate the cache.

**Phase assignment:** Caching phase.

---

### Pitfall 13: Federation Timeout Multiplication

**What goes wrong:** A federated query fans out to N Prometheus instances. If the timeout is 30s and 3 instances are queried sequentially, the worst case is 90s — far beyond what an MCP client expects.

**Prevention:**
- Query federation instances concurrently (use `concurrent.futures.ThreadPoolExecutor`)
- Apply per-instance timeout, not total timeout
- Set a lower per-instance timeout for federation (e.g., 10s) with a configurable total timeout
- Return partial results when some instances fail: `{"dc1": {...}, "dc2": "error: timeout", "dc3": {...}}`

**Phase assignment:** Federation phase.

---

### Pitfall 14: Response Size Limit Default Too Low

**What goes wrong:** Developers set a conservative default (e.g., 1MB) based on typical responses. But `prometheus_list_metrics` on a large Prometheus instance with 50K+ metrics returns 2-3MB of JSON. Users upgrade to v2.0 and their previously-working metric listing breaks immediately.

**Prevention:**
- Default to a high limit (50MB) — this is defense against pathological cases, not a typical budget
- Document the env var prominently in upgrade notes
- Test with realistic large-deployment response sizes

**Phase assignment:** Response limits phase.

---

### Pitfall 15: Missing env var documentation for new config

**What goes wrong:** New features add env vars (`ALERTMANAGER_URL`, `PROMETHEUS_FEDERATION_URLS`, `PROMETHEUS_MAX_RESPONSE_SIZE`, `PROMETHEUS_CACHE_TTL`) but developers forget to update `.env.example`, `server.json`, `README.md`, and the `errors.py` config error messages.

**Prevention:**
- Checklist for every phase that adds an env var: `.env.example`, `server.json`, `README.md`, `Dockerfile`, `errors.py` config message
- CI lint that extracts `os.environ.get(...)` calls and verifies each key appears in `.env.example`

**Phase assignment:** Every phase. Add to definition-of-done for each phase.

---

### Pitfall 16: TypedDict Output Schemas Grow Inconsistently

**What goes wrong:** New tools define output schemas in `models.py` but don't follow the existing naming conventions (`ListXOutput`, `XItem`, `XSummary`). Alertmanager outputs might use different patterns than Prometheus outputs, making the codebase harder to navigate.

**Prevention:**
- Follow existing conventions: `ListAlertmanagerSilencesOutput`, `SilenceItem`, `AlertmanagerAlertItem`
- Prefix Alertmanager models to distinguish from Prometheus models (there's already `AlertItem` in Prometheus — Alertmanager needs `AlertmanagerAlertItem` or `AmAlertItem`)
- Review `models.py` for naming collisions before adding new TypedDicts

**Phase assignment:** Every phase that adds tools.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Severity | Mitigation |
|-------------|---------------|----------|------------|
| Client refactoring | Breaking existing `get_client()` callers | Critical | Keep `get_client()` as a backward-compatible wrapper that returns the primary Prometheus client |
| Alertmanager | Reusing PrometheusClient for Alertmanager API v2 | Critical | Separate client class or separate `get_raw()` method; different base path, different response parsing |
| Alertmanager | Auth confusion (Prometheus creds ≠ Alertmanager creds) | Moderate | Dedicated `ALERTMANAGER_*` env vars, Alertmanager-specific error messages |
| Alertmanager | Model naming collision (`AlertItem` already exists) | Minor | Prefix with `Alertmanager` or `Am` |
| Cardinality | TSDB stats endpoint not available on all backends | Moderate | Graceful 404 handling with clear message |
| Federation | Config format doesn't support per-instance auth | Critical | Design structured config from day one |
| Federation | Sequential queries multiply timeouts | Moderate | Concurrent fan-out with per-instance timeout |
| Federation | Tool naming breaks backward compatibility | Moderate | New tool names, never modify existing tools |
| Health check | Circular dependency with Kubernetes liveness | Moderate | MCP health ≠ Prometheus health; separate concerns |
| Caching | Stale metric names hide new services | Critical | Short TTL + `cache=False` bypass parameter |
| Caching | Thread-safety of in-memory cache | Moderate | `threading.Lock`, single-flight refresh pattern |
| Response limits | Truncating JSON mid-stream | Critical | Pre-check Content-Length or streaming byte count; never truncate-and-parse |
| Response limits | Default too low breaks existing queries | Moderate | High default (50MB), configurable, documented |
| All phases | Missing env var documentation | Minor | Per-phase checklist: `.env.example`, `server.json`, `README.md`, `errors.py` |

## Recommended Phase Ordering Based on Pitfall Risk

1. **Client infrastructure** (Pitfall 2) — refactor singleton to registry. Everything else depends on this.
2. **Response size limits** (Pitfalls 5, 14) — pure HTTP layer, no new tools, low risk, high value.
3. **Caching** (Pitfalls 4, 10, 12) — pure infrastructure, no new tools, enables faster iteration on later phases.
4. **Health check** (Pitfall 6) — small scope, validates the new client infrastructure works.
5. **Cardinality stats** (Pitfall 8) — first new tool using existing Prometheus client via the new registry.
6. **Alertmanager** (Pitfalls 1, 7, 11, 16) — highest integration risk, benefits from all infrastructure being in place.
7. **Federation** (Pitfalls 3, 9, 13) — highest complexity, should be last so all patterns are proven.

## Sources

- Prometheus HTTP API documentation: https://prometheus.io/docs/prometheus/latest/querying/api/
- Alertmanager API v2 OpenAPI spec: https://github.com/prometheus/alertmanager/blob/main/api/v2/openapi.yaml
- Prometheus Federation documentation: https://prometheus.io/docs/prometheus/latest/federation/
- Existing codebase analysis: `src/prometheus_mcp/client.py`, `_mcp.py`, `tools.py`, `models.py`, `errors.py`
- Existing test fixtures: `tests/conftest.py`
- Confidence: HIGH for all pitfalls — based on official API specs and direct codebase analysis
