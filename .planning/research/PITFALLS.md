# Domain Pitfalls — v3.0 Federation

**Domain:** Adding multi-instance Prometheus/Alertmanager federation to an existing single-instance MCP server
**Researched:** 2026-06-08
**Focus:** Specific mistakes when adding fan-out queries, per-instance config/auth, and result merging to the existing prometheus-mcp codebase
**Confidence:** HIGH — based on direct codebase analysis, API specs, and Python runtime verification

---

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, security incidents, or break existing users.

---

### Pitfall 1: Config File Breaks Existing Env Var Users on Upgrade

**What goes wrong:** Federation introduces a JSON config file for named instances. Developers make the config file the *primary* config mechanism and treat env vars as legacy. On v3.0 upgrade, users who set `PROMETHEUS_URL` + `PROMETHEUS_TOKEN` in their MCP client config find that their setup silently stops working — either because the code now requires a config file, or because the config file takes precedence and has no instances defined, resulting in "no instances configured" errors.

**Why it happens:** The natural implementation is: "if config file exists, use it; ignore env vars." This breaks the contract from v0.2.0 through v2.0 where env vars are THE config mechanism. The existing `.env.example` has 11 env vars, the `README.md` documents them, and every user has them in their MCP client config (`server.json`, `claude_desktop_config.json`, etc.).

**Consequences:**
- Every existing user's setup breaks on upgrade — this is the worst kind of regression
- Users file bugs: "prometheus-mcp stopped working after update"
- The fix requires a second breaking change or complex migration logic
- PyPI users who `pip install --upgrade prometheus-mcp` get silently broken

**Prevention:**
1. **Env vars remain the primary config for single-instance mode.** If `PROMETHEUS_URL` is set and no config file is specified, behavior is identical to v2.0 — zero changes required
2. **Config file is opt-in via explicit env var:** `PROMETHEUS_MCP_CONFIG=/path/to/config.json`. Only loaded when explicitly pointed to
3. **When config file is present, the "default" instance is the env-var instance.** The config file ADDS instances; it doesn't replace the env-var instance. The env-var instance becomes the unnamed/default instance with name `"default"` or the value of `PROMETHEUS_URL`
4. **Never make the config file mandatory.** Single-instance users should never need to create a config file
5. **Startup validation:** If both config file and env vars are set, log a clear message: "Using config file /path/to/config.json. Environment variables PROMETHEUS_URL/PROMETHEUS_TOKEN are also set — the env-var instance is registered as 'default'."

**Detection:** Test matrix: (a) env vars only, no config file → works as before; (b) config file only → works; (c) both → env-var instance becomes default, config instances are added; (d) neither → clear ConfigError

**Phase assignment:** Must be the FIRST design decision in federation — config loading strategy determines everything else. Address in Phase 1 (config schema/loading).

---

### Pitfall 2: Config File Schema Has No Version Field — Impossible to Evolve

**What goes wrong:** The v3.0 config file is defined as a JSON structure like `{"instances": [...]}`. No `version` or `schema_version` field. In v3.1, a new field is needed (e.g., `tls_client_cert` for mTLS). There's no way to distinguish a v3.0 config from a v3.1 config, so the parser must handle all possible shapes with heuristics, leading to fragile parsing and confusing error messages.

**Why it happens:** Schema versioning feels like over-engineering for a v1 config file. Developers assume the format won't change.

**Consequences:**
- Every config format change becomes a backward-compatibility puzzle
- Users get cryptic Pydantic validation errors when their config is "almost right" for the new version
- No migration tooling possible — can't auto-upgrade configs without knowing which version they are

**Prevention:**
1. **Add `version: 1` as a required top-level field** from day one
2. **Pydantic model with strict validation:** Use `model_validator` to check version and dispatch to the correct schema
3. **Clear error on unknown version:** "Config file version 2 is not supported by this version of prometheus-mcp. Upgrade to v3.2+ or edit the config."
4. **Clear error on missing version:** "Config file is missing 'version' field. Add `\"version\": 1` to the top level."

**Example schema:**
```json
{
  "version": 1,
  "instances": [
    {
      "name": "dc1-prometheus",
      "type": "prometheus",
      "url": "https://prometheus-dc1.example.com",
      "auth": {"type": "bearer", "token": "..."}
    }
  ]
}
```

**Detection:** Test: config without `version` → helpful error. Test: config with `version: 999` → helpful error. Test: config with `version: 1` → accepted.

**Phase assignment:** Phase 1 (config schema). Must be locked in before any config parsing code is written.

---

### Pitfall 3: Pydantic Validation Errors Are Unreadable for Config Files

**What goes wrong:** Using Pydantic models for config validation (the obvious choice given the existing stack) produces error messages like:
```
1 validation error for FederationConfig
instances -> 0 -> auth -> token
  field required (type=value_error.missing)
```
This is a developer error message, not a user error message. The user sees this when they make a typo in their config JSON and has no idea what to fix.

**Why it happens:** Pydantic's default validation errors are designed for API input validation, not config file validation. They're technically correct but not actionable for a human editing a JSON file.

**Consequences:** Users struggle to write valid config files. Support burden increases. Users copy-paste broken configs from each other.

**Prevention:**
1. **Wrap Pydantic validation in a config-specific error handler** that rewrites errors to reference the config file:
   ```
   Error in /path/to/config.json: instance "dc1-prometheus" is missing 'auth.token'.
   Bearer auth requires a token. Example:
     {"type": "bearer", "token": "your-token-here"}
   ```
2. **Validate early at startup** — not on first tool call. Fail fast with the full list of errors
3. **Provide a JSON Schema file** that editors (VS Code) can use for autocompletion and inline validation
4. **Document example configs** for each auth type in README and as separate example files

**Detection:** Test: feed 5 different malformed configs → verify each error message is actionable and mentions the config file path. Test: verify error mentions which instance has the problem (by name).

**Phase assignment:** Phase 1 (config schema). Config validation UX is part of the schema design, not an afterthought.

---

### Pitfall 4: Credential Leaking Between Instances via Shared Session

**What goes wrong:** The current `PrometheusClient` stores auth in `self.session.headers["Authorization"]` or `self.session.auth`. When creating multiple client instances for federation, developers reuse a session pool or accidentally share a `requests.Session` between clients with different credentials. Instance A's Bearer token leaks to Instance B's requests, sending credentials to the wrong server.

**Why it happens:** The current code pattern:
```python
self.session = requests.Session()
if self.token:
    self.session.headers["Authorization"] = f"Bearer {self.token}"
```
This sets auth at the session level. If anyone creates a "connection pool" or "session factory" that shares sessions across instances, the auth from one instance contaminates another. This is especially likely if a developer tries to "optimize" by pooling connections.

**Consequences:**
- **Security incident:** Credentials sent to the wrong Prometheus instance. If Instance A is internal (no auth) and Instance B is external (Bearer token), the token is sent to the internal instance's reverse proxy logs
- **Silent auth failures:** Instance B gets Instance A's (weaker or missing) credentials and returns 401, but the error message says "check your token" — the token IS correct, it's just being sent to the wrong place
- **Cross-tenant data exposure** in multi-tenant setups where different instances serve different teams

**Prevention:**
1. **Each `PrometheusClient` MUST own its own `requests.Session`.** This is already the pattern in the current code — preserve it
2. **Never share sessions between client instances.** Add a code comment and test asserting `client_a.session is not client_b.session`
3. **Never create a "session pool" or "connection manager" that shares sessions across instances**
4. **In the `ClientRegistry`, store fully-constructed client objects, not (url, auth) tuples that get lazily assembled with shared resources**
5. **Log which instance a request is being sent to** (at DEBUG level) so credential routing can be audited

**Detection:** Test: create two clients with different tokens, make a request on each, verify the correct token was sent to the correct URL. Test: verify `client_a.session is not client_b.session`.

**Phase assignment:** Phase 2 (client registry). Must be a design constraint from the start, not a security fix later.

---

### Pitfall 5: Fan-Out Timeout Amplification — Sequential Queries × N Instances

**What goes wrong:** A fan-out query across 5 Prometheus instances is implemented as:
```python
results = []
for instance in instances:
    results.append(instance.client.get("/query", params=params))
```
With a 30-second per-instance timeout and 5 instances, the worst case is **150 seconds** for a single tool call. The MCP client (Claude) will likely time out the entire MCP session long before that. Even with 3 instances and a healthy median response of 2 seconds, one slow instance makes the entire fan-out take 32 seconds.

**Why it happens:** Sequential is the simplest implementation. The existing code is synchronous (tools are `def`, not `async def`), so developers may not think to add concurrency. The existing retry logic (1 retry with 1s backoff) means worst case per instance is actually `30s timeout + 1s backoff + 30s retry = 61s`.

**Consequences:**
- MCP client times out → agent loses the tool call result → agent retries → amplification cascades
- Users think the MCP server is broken when it's actually waiting for one slow Prometheus instance
- No partial results — if Instance 5 fails after 30s, the results from Instances 1-4 are lost

**Prevention:**
1. **Use `concurrent.futures.ThreadPoolExecutor` for fan-out** — this works within the existing synchronous tool model because FastMCP already runs tools in a worker thread
2. **Set a lower per-instance timeout for federation queries** — 10s default instead of 30s, configurable per-instance in the config file
3. **Set a total fan-out timeout** — e.g., 15s total. Use `executor.map(fn, instances, timeout=total_timeout)` or `as_completed()` with a deadline
4. **Return partial results on timeout/error:** `{"dc1": {results}, "dc2": {results}, "dc3": {"error": "timeout after 10s"}}` — never throw away successful results because one instance failed
5. **Disable retry logic for fan-out queries** — retries double the worst-case latency. A single attempt with partial-result tolerance is better than retrying each instance
6. **Log fan-out timing:** `"Fan-out to 5 instances: dc1=0.3s dc2=0.5s dc3=timeout dc4=0.2s dc5=0.4s — total 10.1s"`

**Detection:** Test: mock 3 instances, one with 5s delay. Verify total response time is ~5s (concurrent), not ~15s (sequential). Test: mock one instance as unreachable, verify partial results returned for other instances.

**Phase assignment:** Phase 3 (fan-out queries). Must be designed as concurrent from the start — retrofitting concurrency is much harder.

---

### Pitfall 6: `requests.Session` Is NOT Thread-Safe — Concurrent Fan-Out Corrupts Sessions

**What goes wrong:** The fan-out implementation uses `ThreadPoolExecutor` to query instances concurrently (as recommended in Pitfall 5). Each thread calls `client.get()` which uses `self.session.request()`. If multiple threads share the same `requests.Session` object (e.g., through a shared client), request state gets corrupted: headers are modified mid-request, connection pool state is inconsistent, responses are mixed between requests.

**Why it happens:** `requests.Session` is [documented as NOT thread-safe](https://requests.readthedocs.io/en/latest/user/advanced/#session-objects) — while connection pooling via urllib3 is somewhat thread-safe, the session-level header/auth/cookie state is not synchronized. Verified by inspection: `Session.send()` contains no locking (the `clock()` match is `preferred_clock()`, not a lock).

**Consequences:**
- Intermittent, hard-to-reproduce errors: "Connection reset", garbled responses, auth headers from wrong instance
- Data integrity violation: results from Instance A appear in Instance B's response
- Security: auth tokens from one instance sent to another

**Prevention:**
1. **Each instance MUST have its own `PrometheusClient` with its own `requests.Session`.** This is already the pattern — federation must preserve it
2. **Fan-out code MUST use different client objects per thread** — never share a single client across threads in the executor:
   ```python
   # CORRECT: each instance has its own client
   def query_instance(instance):
       return instance.client.get("/query", params=params)
   
   with ThreadPoolExecutor(max_workers=len(instances)) as pool:
       futures = {pool.submit(query_instance, inst): inst for inst in instances}
   ```
3. **Never use a single client with concurrent requests** — even if the same Prometheus URL is targeted, each concurrent request needs its own session OR the requests must be serialized
4. **Test concurrent access:** Submit 10 concurrent requests through the same client and verify no data corruption (this test should fail to prove the problem, then pass after the fix)

**Detection:** Stress test: 10 concurrent fan-out queries to verify no session corruption. Test: `assert client_a.session is not client_b.session` for all instance pairs.

**Phase assignment:** Phase 3 (fan-out queries). This is a design constraint, not a bug to fix later.

---

### Pitfall 7: Result Merging — Metric Name Collisions Across Instances

**What goes wrong:** A fan-out `prometheus_query(query="up")` returns results from multiple Prometheus instances. Each instance has metrics with identical label sets (e.g., `{job="node-exporter", instance="server1:9100"}`). When merging results, the agent can't tell which Prometheus instance a result came from — was `server1:9100` up on `dc1-prometheus` or `dc2-prometheus`?

**Why it happens:** Prometheus labels identify the target within one Prometheus instance. Across instances, the same `{job, instance}` tuple can exist independently. A naive merge (`all_results = dc1_results + dc2_results`) creates duplicate entries with no way to distinguish origin.

**Consequences:**
- Agent sees duplicate results and makes wrong conclusions (e.g., "server1 is reporting twice — must be a scraping bug")
- Alert correlation fails — the agent can't map an alert from Alertmanager-DC1 to the metric on Prometheus-DC1
- Range queries become impossible to graph — two time series with identical labels produce garbage when merged

**Prevention:**
1. **Inject `__prometheus_instance__` label into every result during merging:**
   ```python
   for sample in instance_results:
       sample["labels"]["__prometheus_instance__"] = instance.name
   ```
2. **Use double-underscore prefix** (`__prometheus_instance__`) to follow the Prometheus convention that `__`-prefixed labels are internal/synthetic. This avoids collision with real user labels
3. **Never inject into the raw Prometheus response** — inject during result shaping in the MCP tool layer, after parsing and before returning to the agent
4. **Document the label in the tool docstring** so the agent knows to expect it and can filter by it
5. **For tools that return non-metric data** (targets, rules, alerts), add an `instance` field to the structured output at the top level, not as a label injection

**Detection:** Test: fan-out query returns results from 2 instances with identical label sets. Verify each result has `__prometheus_instance__` label. Verify the agent can filter by instance name.

**Phase assignment:** Phase 3 (fan-out queries). Label injection strategy must be decided before implementing any merging logic.

---

### Pitfall 8: `__prometheus_instance__` Label Conflicts with User Labels

**What goes wrong:** The injected `__prometheus_instance__` label collides with a label that already exists on the metric from Prometheus. Some Prometheus setups use `external_labels` to add an `__prometheus_instance__` or `prometheus_instance` label to all metrics (this is a common pattern in Prometheus federation/Thanos setups). The injected label overwrites the original, destroying information.

**Why it happens:** The double-underscore convention is not guaranteed to be unused — Prometheus itself uses `__address__`, `__metrics_path__`, etc. as internal labels, but users CAN create custom `__`-prefixed labels via relabeling.

**Consequences:**
- Silent data corruption: the original label value is lost
- Agents that rely on the original label for correlation get wrong results
- Users with Thanos/Cortex federation that already add instance-identifying labels get confused by the duplicate

**Prevention:**
1. **Check if the label already exists** before injecting. If it does, use the existing value (don't overwrite) and inject the MCP instance name as a different label (e.g., `__mcp_instance__`)
2. **Or — cleaner — use `__mcp_source__`** as the label name from the start. This is unique to the MCP layer and won't collide with Prometheus conventions
3. **Document the label name and collision behavior** in the tool docstring
4. **Make the label name configurable** in the config file as a federation-level setting (not per-instance)

**Detection:** Test: mock a Prometheus response that already has `__prometheus_instance__` in its labels. Verify the MCP server does not overwrite it. Verify both the original and the MCP-injected label are present.

**Phase assignment:** Phase 3 (fan-out queries). Design the label name before implementing merging.

---

### Pitfall 9: Fan-Out Response Size Explodes Beyond MCP/LLM Token Limits

**What goes wrong:** A single-instance `prometheus_query_range` might return 5,000 data points (already capped by the existing `_RANGE_POINTS_CAP = 5000`). A fan-out across 5 instances returns up to 25,000 data points. The MCP response is a single JSON-RPC message over stdio — there's no streaming, no pagination. The serialized JSON can be several megabytes. The LLM context window cannot process this volume of structured data.

**Why it happens:** The existing per-tool caps (`_METRICS_CAP = 500`, `_RANGE_POINTS_CAP = 5000`) were designed for single-instance. Multiplying by N instances without adjusting the cap defeats the purpose of the cap.

**Consequences:**
- MCP client may reject oversized responses (implementation-dependent, but Claude's MCP client has practical limits)
- Even if accepted, the LLM context window is wasted on thousands of data points it can't meaningfully process
- The markdown channel (which agents actually read) becomes unusably long
- The `PROMETHEUS_MAX_RESPONSE_BYTES` limit may reject valid fan-out results

**Prevention:**
1. **Apply caps PER FAN-OUT, not per instance.** Total results across all instances should respect the same caps as single-instance: 500 metrics, 5000 points, etc.
2. **For fan-out range queries:** divide the cap by the number of instances (5000 / 5 = 1000 points per instance). Truncate per-instance results proportionally
3. **Add a `limit` parameter to fan-out tools** so the agent can control how many results to return
4. **Include a summary in the markdown channel:** "Queried 5 instances. Total: 15,342 data points across 47 series. Showing top 20 series by instance (capped at 5,000 total points)."
5. **Consider making fan-out range queries opt-in** — default fan-out for instant queries (small results), but require explicit `fan_out=True` for range queries

**Detection:** Test: fan-out range query across 5 instances. Verify total response size is within `PROMETHEUS_MAX_RESPONSE_BYTES`. Verify the markdown channel doesn't exceed ~20 items. Verify the structured content respects the global cap.

**Phase assignment:** Phase 3 (fan-out queries). Cap strategy must be designed before implementing fan-out.

---

### Pitfall 10: Error Aggregation — One Failed Instance Kills the Whole Query

**What goes wrong:** Fan-out query to 5 instances: 4 succeed, 1 returns HTTP 500. The implementation raises an exception, discarding the 4 successful results. The agent retries, gets the same 500 from the bad instance, and enters a retry loop.

**Why it happens:** The existing error handling pattern is:
```python
try:
    result = client.get(...)
except Exception as exc:
    output.fail(exc, "...")  # raises ToolError, aborts the tool
```
In a fan-out, this pattern means any single failure aborts the entire fan-out.

**Consequences:**
- One unhealthy Prometheus instance makes ALL federation queries fail — the opposite of federation's purpose (resilience through redundancy)
- The error message mentions the failing instance but doesn't tell the agent that 4 other instances succeeded
- The agent cannot investigate cross-cluster issues if one cluster's Prometheus is down

**Prevention:**
1. **Catch exceptions per-instance in the fan-out, not at the tool level:**
   ```python
   per_instance_results = {}
   for instance, future in futures.items():
       try:
           per_instance_results[instance.name] = future.result()
       except Exception as exc:
           per_instance_results[instance.name] = {"error": errors.handle(exc, f"querying {instance.name}")}
   ```
2. **Return partial results with error annotations:** The structured output includes both successful results AND error descriptions for failed instances
3. **The markdown channel should clearly show which instances succeeded and which failed:**
   ```
   ## Fan-out Query: `up` (5 instances, 4 succeeded, 1 failed)
   
   ✓ dc1-prometheus: 12 results
   ✓ dc2-prometheus: 15 results
   ✗ dc3-prometheus: timeout after 10s
   ✓ dc4-prometheus: 11 results
   ✓ dc5-prometheus: 13 results
   ```
4. **Only raise `ToolError` if ALL instances fail** — partial success is still useful

**Detection:** Test: 3 instances, one returns 500, two succeed. Verify tool returns successfully with partial results and error annotation for the failed instance.

**Phase assignment:** Phase 3 (fan-out queries). Error handling strategy is part of the fan-out design.

---

## Moderate Pitfalls

---

### Pitfall 11: Per-Instance Auth Inheritance — Unclear Default Behavior

**What goes wrong:** The config file defines 5 instances. Three have explicit auth, two don't. Do the two without auth inherit from the env-var default? From a global auth section in the config? Or are they unauthenticated? The behavior is ambiguous, and different users expect different things.

**Prevention:**
1. **Explicit is better than implicit.** Each instance in the config MUST specify its own auth (or explicitly `"auth": {"type": "none"}`)
2. **No inheritance from env vars.** The env-var auth applies ONLY to the env-var default instance. Config-file instances are self-contained
3. **Validation: reject config with missing auth** — don't silently default to no-auth:
   ```
   Error in config.json: instance "dc2-prometheus" is missing 'auth' field.
   Specify auth explicitly: {"type": "bearer", "token": "..."} or {"type": "none"}
   ```
4. **Optional: support a `defaults` section** in the config file for common settings (timeout, ssl_verify) — but NEVER for credentials

**Detection:** Test: config with one instance missing auth → clear validation error. Test: config with explicit `"auth": {"type": "none"}` → accepted.

**Phase assignment:** Phase 1 (config schema).

---

### Pitfall 12: Connection Lifecycle — Too Many Persistent Sessions

**What goes wrong:** Each `PrometheusClient` maintains a `requests.Session` with a connection pool (default: 10 connections per host, urllib3). With 20 federation instances, that's 20 sessions × 10 connections = 200 potential connections. For long-running MCP servers, these connections consume file descriptors and may hit OS limits (`ulimit -n`), especially in containers with low `nofile` limits.

**Why it happens:** The current pattern creates a session on first use and keeps it alive until shutdown. This is correct for single-instance but doesn't scale to N instances.

**Consequences:**
- File descriptor exhaustion → "Too many open files" errors on tool calls to later instances
- Connection leaks if instances are removed from config but their clients aren't cleaned up
- Idle connections consume kernel resources (TCP keepalive, socket buffers)

**Prevention:**
1. **Limit connection pool size per instance:** `session.mount("https://", HTTPAdapter(pool_maxsize=2))` — federation instances don't need 10 concurrent connections each since the MCP server processes one tool call at a time
2. **Lazy client creation:** Don't create all 20 clients at startup. Create on first use, like the current `get_client()` pattern
3. **Consider a maximum instance limit** in the config validation (e.g., 50 instances max) with a clear error message
4. **Lifespan cleanup must close ALL federation clients:** The current `app_lifespan` closes `_client` and `_am_client`. The registry pattern must iterate and close all clients
5. **Test: verify cleanup closes all sessions.** After lifespan shutdown, assert all sessions are closed

**Detection:** Test: create 20 clients, verify all sessions are closed on lifespan exit. Test: verify session pool size is limited (inspect the adapter config).

**Phase assignment:** Phase 2 (client registry). Connection lifecycle is part of registry design.

---

### Pitfall 13: Adding `instance` Parameter to Existing Tools Breaks Output Schema

**What goes wrong:** The natural way to add federation to existing tools is adding an optional `instance` parameter:
```python
def prometheus_query(query: str, time: str | None = None, instance: str | None = None) -> QueryOutput:
```
But this changes the tool's input schema (new parameter in JSON Schema), and — worse — if the output changes when `instance` is specified (e.g., adding `__prometheus_instance__` labels), the output schema changes too. Agents that have cached the tool's schema from v2.0 send requests without `instance` and expect v2.0 output.

**Why it happens:** Adding optional parameters seems backward-compatible ("old calls still work"), but the schema itself is a contract. MCP clients that validate tool inputs against the schema may reject calls with unexpected parameters, or may not show the new parameter in their UI.

**Consequences:**
- MCP clients with cached tool schemas don't see the new `instance` parameter
- Output format differences between single-instance and fan-out modes create two code paths with different bugs
- The `structuredContent` schema changes, breaking typed consumers

**Prevention:**
1. **Do NOT modify existing tool signatures.** Per PROJECT.md constraint: "Existing 8 tools must not change their API signatures or output schemas"
2. **Create new federation-specific tools:** `prometheus_federation_query`, `prometheus_federation_list_instances`, etc.
3. **The existing tools ALWAYS target the default instance** — identical behavior to v2.0
4. **If a tool MUST support optional instance targeting** (e.g., for convenience), create a SEPARATE tool with a different name that wraps the original logic plus instance selection
5. **Test: protocol test (`test_protocol.py`) must still pass** with all original tool names and schemas unchanged

**Detection:** Protocol test: verify all 16 existing tools have unchanged input/output schemas. New tools are validated separately.

**Phase assignment:** Phase 3 (fan-out queries). Tool naming convention decided in design, enforced by protocol tests.

---

### Pitfall 14: Alertmanager Federation — Different Instance Mapping Than Prometheus

**What goes wrong:** Developers assume Alertmanager instances map 1:1 to Prometheus instances (dc1-prometheus ↔ dc1-alertmanager). In reality, the mapping is often different: one Alertmanager cluster handles alerts from multiple Prometheus instances, or multiple Alertmanager instances are in a gossip cluster sharing state. A `prometheus_federation_list_alerts` that queries N Alertmanagers duplicates results because the gossip cluster means all instances have the same alerts.

**Why it happens:** Prometheus is typically deployed per-cluster/per-datacenter, but Alertmanager is often deployed as a single HA cluster with gossip between peers. The 1:1 assumption is wrong in most production setups.

**Consequences:**
- Duplicate alerts: the same alert appears 3 times (once per Alertmanager peer) with different `__prometheus_instance__` labels
- Silence and inhibition data is duplicated
- Agent thinks there are 3× more alerts than actually exist

**Prevention:**
1. **Alertmanager instances in the config are independent clusters, NOT peers in the same cluster.** Document this clearly
2. **Deduplication by fingerprint:** Alertmanager alerts have a `fingerprint` field. If two Alertmanager instances return the same alert (same fingerprint), deduplicate in the merge layer
3. **Config file should express the mapping explicitly:**
   ```json
   {
     "alertmanagers": [
       {"name": "am-us", "url": "...", "prometheus_instances": ["dc1-prometheus", "dc2-prometheus"]},
       {"name": "am-eu", "url": "...", "prometheus_instances": ["dc3-prometheus"]}
     ]
   }
   ```
4. **Consider making Alertmanager federation a separate phase** from Prometheus federation — the semantics are different enough to warrant separate design

**Detection:** Test: two Alertmanager instances return the same alert (same fingerprint, same labels). Verify the fan-out returns it once, not twice.

**Phase assignment:** Phase 5 (Alertmanager federation). Must be designed separately from Prometheus fan-out.

---

### Pitfall 15: Testing N Instances × M Endpoints With `responses` Library

**What goes wrong:** Testing a fan-out query across 3 instances requires mocking 3 different Prometheus URLs × multiple endpoints. The `responses` library setup becomes:
```python
@responses.activate
def test_fanout_query():
    # 3 instances × 1 endpoint = 3 mocks
    responses.add(GET, "https://prom1:9090/api/v1/query", json={...})
    responses.add(GET, "https://prom2:9090/api/v1/query", json={...})
    responses.add(GET, "https://prom3:9090/api/v1/query", json={...})
    # Plus auth headers, error cases, timeout simulation...
```
This explodes combinatorially. Testing error scenarios (1 of 3 fails, 2 of 3 fail, all fail, timeout on 1, etc.) requires dozens of mock configurations. Test setup dominates test logic, making tests unreadable and unmaintainable.

**Why it happens:** The existing test suite mocks one URL at a time (one Prometheus, one Alertmanager). Federation multiplies every test by N instances.

**Consequences:**
- Tests are so complex they have bugs themselves
- Developers skip edge cases (partial failure, mixed auth) because the setup is too painful
- Test suite becomes slow — each `@responses.activate` adds overhead, and N×M mocks compound it

**Prevention:**
1. **Create test helper fixtures for federation:**
   ```python
   @pytest.fixture
   def federation_config(tmp_path):
       """Generate a config file with N instances and register mock responses."""
       def _make(instances: list[dict], responses_map: dict[str, Any]):
           # Write config file, register all responses.add() calls
           ...
       return _make
   ```
2. **Use a fixture factory pattern** — one function creates N instances with their mock responses
3. **Separate unit tests from integration tests:**
   - Unit: test the merge logic with pre-shaped results (no HTTP mocking needed)
   - Unit: test per-instance error handling with a single mock
   - Integration: test full fan-out with 2-3 instances (minimal, covers the wiring)
4. **Test the fan-out orchestration with mock clients, not mock HTTP:**
   ```python
   # Instead of mocking HTTP, mock the client.get() method
   mock_client_1 = MagicMock()
   mock_client_1.get.return_value = {"data": {"result": [...]}}
   ```
5. **Create response fixture files** (JSON) in `tests/fixtures/` for realistic multi-instance responses

**Detection:** Review: no test function should have more than 5 `responses.add()` calls. If it does, the test should be split or use a helper.

**Phase assignment:** Phase 2 (client registry) — test infrastructure for federation should be built alongside the registry, before fan-out tools need it.

---

### Pitfall 16: Config File Contains Secrets — Accidental Commit to Git

**What goes wrong:** The federation config file contains plaintext tokens and passwords:
```json
{"instances": [{"name": "dc1", "auth": {"type": "bearer", "token": "eyJhbGci..."}}]}
```
Developers testing locally create `prometheus-federation.json` in the project root and commit it to git.

**Why it happens:** The `.env` pattern has `.env` in `.gitignore`. But a new config file path isn't in `.gitignore`, and it's not a well-known secrets file that git hooks catch.

**Consequences:**
- Production credentials leaked to version control
- Even after removing from git, credentials remain in git history

**Prevention:**
1. **Default config file name should be `prometheus-mcp.json`** — add it to `.gitignore`
2. **Also add common variations** to `.gitignore`: `prometheus-mcp.json`, `prometheus-mcp.*.json`, `*.mcp-config.json`
3. **Support env-var references in the config file** so credentials don't need to be in the file:
   ```json
   {"auth": {"type": "bearer", "token": "${PROM_DC1_TOKEN}"}}
   ```
4. **Validate: warn if config file is inside a git repo** and the file contains credentials (check at startup)
5. **Document: "Never commit the config file. Use environment variable references for credentials."**

**Detection:** Test: verify `.gitignore` includes the default config file name. Test: verify env-var substitution works in config file.

**Phase assignment:** Phase 1 (config schema). `.gitignore` update and env-var substitution design happen upfront.

---

### Pitfall 17: Tool Parameter Validation — Instance Name Must Be Validated

**What goes wrong:** The new `prometheus_federation_query(query="up", instance="dc1")` tool accepts an `instance` parameter. If the user (agent) passes an instance name that doesn't exist in the config, the error is either a Python `KeyError` traceback or a generic "instance not found." The agent doesn't know which instances are valid and enters a guess-and-retry loop.

**Prevention:**
1. **Validate instance name against the registry** with a clear error listing valid names:
   ```
   Error: instance "dc1" not found. Available instances: dc1-prometheus, dc2-prometheus, dc3-prometheus.
   Use prometheus_federation_list_instances to discover available instances.
   ```
2. **Create `prometheus_federation_list_instances` as the FIRST federation tool** — agents call this to discover what's available
3. **Use `Literal` type or `enum` in Pydantic if the instance list is static** (probably not — it's config-driven, so validation is runtime)
4. **Allow special values:** `instance="*"` for fan-out to all, `instance=None` for default instance

**Detection:** Test: call with non-existent instance name → error message lists valid instances. Test: call with `*` → fan-out to all.

**Phase assignment:** Phase 3 (fan-out queries). Instance validation is part of tool implementation.

---

## Minor Pitfalls

---

### Pitfall 18: Metrics Cache Is Not Per-Instance — Stale Cross-Instance Data

**What goes wrong:** The existing `TTLCache` in `cache.py` is a module-level singleton with a single cache key for metric names. With federation, `prometheus_list_metrics` on Instance A caches the metric list. A subsequent call for Instance B returns Instance A's cached metrics because the cache key doesn't include the instance identifier.

**Prevention:**
1. **Cache key MUST include the instance identifier:** `cache_key = f"{instance.name}:__name__values"` not just `"__name__values"`
2. **Or: each `PrometheusClient` has its own cache instance** (cleaner separation, simpler invalidation)
3. **Test: list metrics on Instance A, then Instance B → different results** (not A's cached result)

**Phase assignment:** Phase 3 (fan-out tools) or Phase 2 (client registry) if cache is moved into the client.

---

### Pitfall 19: Config File Encoding — Non-UTF-8 Paths and Values

**What goes wrong:** Config file path contains non-ASCII characters (common on macOS: `/Users/José/config.json`). Or the config file itself uses BOM-prefixed UTF-8. Python's `json.load()` handles UTF-8 but may choke on BOM or non-UTF-8 encodings.

**Prevention:**
1. **Open config file with `encoding="utf-8-sig"`** (handles BOM) or strip BOM explicitly
2. **Use `pathlib.Path` for file paths** — handles Unicode paths correctly on all platforms
3. **Clear error message on encoding issues:** "Config file is not valid UTF-8 JSON. Please save as UTF-8 without BOM."

**Phase assignment:** Phase 1 (config loading). Minor but easy to prevent.

---

### Pitfall 20: Missing `type` Field in Config — Prometheus vs Alertmanager Confusion

**What goes wrong:** The config file has an `instances` array. Each entry has `name`, `url`, `auth`. But is instance "dc1-monitoring" a Prometheus or an Alertmanager? Without a `type` field, the code has to guess from the URL or require separate arrays.

**Prevention:**
1. **Require `"type": "prometheus"` or `"type": "alertmanager"` on each instance**
2. **Or: use separate top-level arrays:** `"prometheus_instances": [...]` and `"alertmanager_instances": [...]`
3. **Validate: reject instance without type** with a clear error message

**Phase assignment:** Phase 1 (config schema).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Severity | Mitigation |
|-------------|---------------|----------|------------|
| Config schema & loading | Breaking env-var users on upgrade | Critical | Env vars remain primary for single-instance; config file is opt-in (Pitfall 1) |
| Config schema & loading | No schema version field | Critical | Add `version: 1` from day one (Pitfall 2) |
| Config schema & loading | Unreadable Pydantic validation errors | Moderate | Wrap validation with config-specific error messages (Pitfall 3) |
| Config schema & loading | Config file committed to git with secrets | Moderate | `.gitignore`, env-var references in config (Pitfall 16) |
| Config schema & loading | No type field for Prometheus vs Alertmanager | Minor | Require `type` field or use separate arrays (Pitfall 20) |
| Client registry | Credential leaking between instances | Critical | Each client owns its own session, never share (Pitfall 4) |
| Client registry | Too many persistent sessions | Moderate | Limit pool size per instance, lazy creation (Pitfall 12) |
| Client registry | Testing infrastructure not built early | Moderate | Build federation test fixtures alongside registry (Pitfall 15) |
| Fan-out queries | Sequential timeout amplification | Critical | ThreadPoolExecutor with per-instance + total timeout (Pitfall 5) |
| Fan-out queries | `requests.Session` not thread-safe | Critical | Each instance has its own session, never shared (Pitfall 6) |
| Fan-out queries | Metric name collisions across instances | Critical | Inject `__mcp_source__` label (Pitfall 7) |
| Fan-out queries | Injected label collides with user labels | Moderate | Check before injecting, use `__mcp_source__` (Pitfall 8) |
| Fan-out queries | Response size explosion | Critical | Global caps, not per-instance caps (Pitfall 9) |
| Fan-out queries | One failed instance kills whole query | Critical | Partial results with error annotations (Pitfall 10) |
| Fan-out queries | Modifying existing tool signatures | Moderate | New tools only, never modify existing (Pitfall 13) |
| Fan-out queries | Instance name not validated | Moderate | Validate against registry, list valid names (Pitfall 17) |
| Fan-out queries | Cache not per-instance | Minor | Include instance name in cache key (Pitfall 18) |
| Alertmanager federation | 1:1 Prometheus mapping assumption | Moderate | Separate mapping, deduplicate by fingerprint (Pitfall 14) |
| Per-instance auth | Auth inheritance ambiguity | Moderate | Explicit auth per instance, no inheritance (Pitfall 11) |

## Recommended Phase Ordering Based on Pitfall Risk

1. **Config schema & loading** (Pitfalls 1, 2, 3, 16, 19, 20) — everything depends on config. Get the schema right first. Backward compatibility with env vars is the #1 priority.

2. **Client registry** (Pitfalls 4, 6, 12, 15) — multi-client lifecycle management. Build test infrastructure here. Security constraint: each client owns its own session.

3. **Instance listing tool** (Pitfall 17) — `prometheus_federation_list_instances` is a small tool that validates the config is loaded correctly and gives agents discovery capability.

4. **Fan-out queries** (Pitfalls 5, 7, 8, 9, 10, 13, 18) — the highest-complexity phase. Requires concurrent execution, partial failure handling, result merging, label injection, and response size management.

5. **Per-instance targeting** (Pitfall 11) — optional `instance` parameter for new tools, targeting a specific instance without fan-out.

6. **Alertmanager federation** (Pitfall 14) — separate from Prometheus federation due to different semantics (gossip clusters, fingerprint deduplication).

## Sources

- **Codebase analysis (HIGH confidence):** Direct inspection of `client.py`, `_mcp.py`, `tools.py`, `models.py`, `errors.py`, `cache.py`, `output.py`, `conftest.py`, `test_client.py`
- **MCP SDK (HIGH confidence):** Installed `mcp==1.27.2`, inspected `CallToolResult`, `FastMCP.tool()`, stdio transport — no built-in response size limits in the transport layer
- **`requests` library thread safety (HIGH confidence):** Verified by source inspection — `Session.send()` contains no synchronization primitives. [requests docs](https://requests.readthedocs.io/en/latest/user/advanced/#session-objects) confirm Session is not thread-safe
- **Prometheus HTTP API (HIGH confidence):** Official docs https://prometheus.io/docs/prometheus/latest/querying/api/
- **Alertmanager API v2 (HIGH confidence):** OpenAPI spec https://github.com/prometheus/alertmanager/blob/main/api/v2/openapi.yaml — alerts have `fingerprint` field for deduplication
- **Pydantic v2 validation (HIGH confidence):** Verified Pydantic 2 discriminated union support and error message format via runtime test
- **`responses` library (HIGH confidence):** Inspected API surface — supports multiple URL patterns, no built-in federation helper
