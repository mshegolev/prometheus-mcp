# Testing Patterns

**Analysis Date:** 2026-06-06

## Test Framework & Tools

**Runner:**
- pytest >= 7
- Config: `pyproject.toml` → `[tool.pytest.ini_options]`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Assertion Library:** pytest built-in `assert` statements (no separate assertion library)

**Mocking / HTTP stubbing:**
- `responses` >= 0.25 — intercepts `requests` HTTP calls with decorator `@responses.activate`
- `pytest.MonkeyPatch` — for environment variable manipulation (`monkeypatch.setenv`, `monkeypatch.delenv`)
- No `unittest.mock` / `pytest-mock` usage; HTTP mocking is handled entirely by `responses`

**Coverage:**
- `pytest-cov` >= 4
- Coverage target: `src/prometheus_mcp` package

**Run Commands:**
```bash
pytest tests/ -v                                          # Run all tests
pytest tests/ -v --cov=src/prometheus_mcp --cov-report=term-missing  # With coverage (CI default)
pytest tests/test_client.py -v                            # Run a specific test file
pytest tests/test_tools_integration.py::test_query_instant_vector -v  # Run a single test
ruff check src tests && ruff format --check src tests     # Lint (runs before tests in CI)
```

## Test File Organization

**Location:** Separate `tests/` directory at project root (not co-located with source)

**Naming:**
- Test files: `test_{module_or_concern}.py`
- Test classes: `Test{Subject}` (e.g., `TestParseBool`, `TestValidateUrl`, `TestPrometheusClientInit`)
- Test functions: `test_{what_it_verifies}` (e.g., `test_truthy_strings`, `test_list_metrics_happy_path`)

**Structure:**
```
tests/
├── test_client.py              # Unit tests for PrometheusClient, _parse_bool, _validate_url
├── test_errors.py              # Unit tests for errors.handle() — HTTP status mapping
├── test_mcp_client_cache.py    # Unit tests for _mcp.get_client() lazy singleton
├── test_protocol.py            # Wire-protocol smoke tests — tool registration, schemas
├── test_tools_helpers.py       # Unit tests for pure shaping helpers (_shape_*, _format_value)
└── test_tools_integration.py   # Integration tests for all 5 MCP tools with mocked HTTP
```

**No `conftest.py`** — all fixtures are defined locally in test modules.

## Test Types & Coverage

### Unit Tests (4 files, ~500 lines)

**`tests/test_client.py` (176 lines):**
- Tests `_parse_bool()` — truthy strings, falsy strings, None/empty default, bool passthrough
- Tests `_validate_url()` — trailing slash stripping, whitespace, valid schemes, missing scheme/host, port, path
- Tests `PrometheusClient.__init__()` — missing URL raises ConfigError, no-auth happy path, bearer auth, basic auth, bearer precedence over basic, constructor overrides vs env, SSL verify default/env, User-Agent, api_url path

**`tests/test_errors.py` (140 lines):**
- Tests `errors.handle()` for every special-cased HTTP status: 401, 403, 404, 400, 422, 429, 5xx
- Tests ConfigError message formatting
- Tests network errors: ConnectionError, Timeout
- Tests fallthrough for unknown exceptions (RuntimeError)
- Tests ValueError surface path
- Uses `_http_error()` helper to generate real `requests.HTTPError` via the `responses` library

**`tests/test_tools_helpers.py` (126 lines):**
- Tests `_format_value()` — None, string, int, float
- Tests `_shape_instant_sample()` — vector item, scalar list, no labels, missing value, label type conversion, non-dict fallback
- Tests `_shape_range_series()` — basic series, empty values, timestamp float conversion, missing metric/values keys
- Tests `_truncation_hint()` — markdown format, correct counts

**`tests/test_mcp_client_cache.py` (60 lines):**
- Tests `get_client()` returns same instance on repeated calls
- Tests missing config raises exception
- Tests cache rebuild after reset
- Tests client builds without auth (unauthenticated allowed)

### Protocol Smoke Tests (1 file, ~197 lines)

**`tests/test_protocol.py` (197 lines):**
- Uses `asyncio.run(mcp.list_tools())` to fetch the tool catalogue
- Verifies all 5 tools are registered
- Parametrized checks for `annotations` (readOnlyHint, destructiveHint, idempotentHint) on each tool
- Parametrized checks for `inputSchema` — required and optional params match expectations
- Verifies `outputSchema` is generated (non-None, object type, has properties) for each tool
- Spot-checks specific fields: query required, time optional, step description, state options, metrics/data/truncated/firing_count/job_summary in output schemas

### Integration Tests (1 file, ~650 lines)

**`tests/test_tools_integration.py` (650 lines):**
- Calls MCP tool functions directly (not via MCP server transport)
- HTTP layer mocked with `@responses.activate` + `responses.add()`
- Covers all 5 tools:
  - `prometheus_list_metrics` — happy path, pattern filter, case-insensitive filter, empty result, truncation at 500, markdown truncation hint, 401 error
  - `prometheus_query` — instant vector, time param forwarding, scalar result, empty vector, 400 error, markdown content, markdown truncation
  - `prometheus_query_range` — happy path, param forwarding, total-points cap (5000), 422 error, empty result, markdown truncation hint
  - `prometheus_list_alerts` — happy path, empty alerts, state summary, annotations preserved, 401 error, markdown content
  - `prometheus_list_targets` — happy path, job summary, invalid state error, last_error captured, scrape duration ms conversion, markdown down targets, 401 error

## Test Patterns

### Environment Setup with `monkeypatch`

Tests that need `PrometheusClient` use `monkeypatch` to control env vars:

```python
def test_happy_path_no_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_URL", "https://prometheus.example.com/")
    monkeypatch.delenv("PROMETHEUS_TOKEN", raising=False)
    monkeypatch.delenv("PROMETHEUS_USERNAME", raising=False)
    monkeypatch.delenv("PROMETHEUS_PASSWORD", raising=False)
    client = PrometheusClient()
    try:
        assert client.url == "https://prometheus.example.com"
        # ...
    finally:
        client.close()
```

**Pattern:** Always `delenv(..., raising=False)` for optional env vars to avoid test pollution. Always `client.close()` in `finally` blocks for clients created in tests.

### Client Cache Reset Fixture

Integration tests that call tool functions must reset the module-global client cache before/after each test:

```python
@pytest.fixture(autouse=True)
def configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_URL", BASE)
    monkeypatch.delenv("PROMETHEUS_TOKEN", raising=False)
    with _mcp._client_lock:
        if _mcp._client is not None:
            try:
                _mcp._client.close()
            except Exception:
                pass
        _mcp._client = None
    yield
    with _mcp._client_lock:
        if _mcp._client is not None:
            try:
                _mcp._client.close()
            except Exception:
                pass
        _mcp._client = None
```

**Why:** The `get_client()` singleton persists across tests. Without this fixture, env var changes in one test leak into the next.

### HTTP Mocking with `responses`

All HTTP-dependent tests use `@responses.activate` decorator + `responses.add()`:

```python
@responses.activate
def test_list_metrics_happy_path() -> None:
    responses.add(
        responses.GET,
        f"{API}/label/__name__/values",
        json={"status": "success", "data": ["http_requests_total", "node_cpu_seconds_total", "up"]},
        status=200,
    )
    result = prometheus_list_metrics()
    data = result.structuredContent
    assert data["returned_count"] == 3
```

**Constants used:** `BASE = "https://prometheus.example.com"` and `API = f"{BASE}/api/v1"` defined at module level in `tests/test_tools_integration.py`.

### Error Path Testing

Tool errors are tested by expecting `ToolError` from `mcp.server.fastmcp.exceptions`:

```python
@responses.activate
def test_list_metrics_401_raises_tool_error() -> None:
    responses.add(responses.GET, f"{API}/label/__name__/values", json={}, status=401)
    with pytest.raises(ToolError, match="401"):
        prometheus_list_metrics()
```

Error message content is tested via `errors.handle()` in `tests/test_errors.py` — checking that specific env var names, status codes, and guidance strings appear.

### Parametrized Tests

Used for repetitive assertion sets:

```python
@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "on", "YES"])
def test_truthy_strings(self, value: str) -> None:
    assert _parse_bool(value, default=False) is True

@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_5xx_flags_transient(self, code: int) -> None:
    msg = handle(_http_error(code), "fetching targets")
    assert str(code) in msg

@pytest.mark.parametrize("tool_name", list(EXPECTED_TOOLS))
def test_tool_annotations(listed_tools: list[Any], tool_name: str) -> None:
    ...
```

### Test Data Helpers

Factory functions create realistic Prometheus API response objects:

```python
# tests/test_tools_integration.py
def _make_alert(name: str, state: str = "firing", severity: str = "critical") -> dict:
    return {
        "labels": {"alertname": name, "severity": severity, "job": "node"},
        "annotations": {"summary": f"{name} is {state}"},
        "state": state,
        "activeAt": "2024-01-15T10:00:00Z",
        "value": "1",
    }

def _make_target(job: str, instance: str, health: str = "up", ...) -> dict:
    return { ... }
```

```python
# tests/test_errors.py
def _http_error(status: int, url: str = "...", body: str | None = None, json_body: dict | None = None) -> requests.HTTPError:
    """Trigger a real requests.HTTPError carrying a response with the given status."""
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, url, json=json_body or {}, status=status)
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
        except requests.HTTPError as e:
            return e
```

### Dual-Channel Result Assertions

Integration tests verify both structured data and markdown content:

```python
# Structured data
result = prometheus_list_metrics()
data = result.structuredContent
assert data["returned_count"] == 3
assert data["metrics"] == sorted(data["metrics"])

# Markdown content
md = result.content[0].text
assert "Showing first 20 of 25" in md
```

### Module-Scoped Fixture

Protocol tests use `scope="module"` to avoid repeated async `list_tools()` calls:

```python
@pytest.fixture(scope="module")
def listed_tools() -> list[Any]:
    return asyncio.run(mcp.list_tools())
```

## CI Integration

**Workflow:** `.github/workflows/test.yml`

```yaml
strategy:
  matrix:
    python-version: ["3.10", "3.11", "3.12"]

steps:
  - name: Lint with ruff
    run: |
      ruff check src tests
      ruff format --check src tests

  - name: Run tests with coverage
    run: |
      pytest tests/ -v --cov=src/prometheus_mcp --cov-report=term-missing
```

**Trigger:** Push to `main` and all pull requests targeting `main`.

**Matrix:** Tests run across Python 3.10, 3.11, and 3.12.

**Order:** Lint runs before tests — formatting/lint failures block test execution.

## Coverage Gaps

### No Coverage Threshold Enforced
There is no `--cov-fail-under` flag in the CI command. Coverage is reported but not gated.

### `server.py` `main()` Not Directly Tested
The `main()` function in `src/prometheus_mcp/server.py` calls `mcp.run()` which starts an stdio transport. This is exercised by the protocol tests (which import the module), but `main()` itself is never invoked in tests.

### Async Lifespan Not Directly Tested
The `app_lifespan()` async context manager in `src/prometheus_mcp/_mcp.py` is tested indirectly via client cache reset, but the startup/shutdown logging paths and the `finally` branch (closing the client on shutdown) are not directly unit-tested.

### No End-to-End MCP Transport Tests
Tests call tool functions directly rather than going through the MCP stdio transport. There are no tests that spin up a real MCP server session and communicate via JSON-RPC. The protocol tests (`test_protocol.py`) call `mcp.list_tools()` directly which partially covers this.

### Dropped Targets Path Lightly Covered
`prometheus_list_targets` with `state="dropped"` is not tested — only `state="active"` (default), `state="invalid"` (error case) are tested. The `state="any"` path is also not tested.

### No Concurrent Access Tests
The double-checked locking in `get_client()` is not tested under actual concurrent thread access. Only single-threaded tests verify the cache behavior.

### `_request()` Method Not Directly Tested
The `PrometheusClient._request()` method is tested indirectly through `get()`, but direct tests for timeout handling, non-JSON responses, or empty body responses at the `_request` level don't exist.

### When Writing New Tests

1. **Place test files in `tests/`** with `test_` prefix
2. **Use `@responses.activate`** for any test that hits the HTTP layer
3. **Use `monkeypatch`** for env var manipulation — never set `os.environ` directly
4. **Reset client cache** with the `configured_env` fixture pattern if calling tool functions
5. **Assert both channels** (structuredContent and markdown text) for tool integration tests
6. **Use `pytest.raises(ToolError, match="...")`** for error path testing
7. **Add parametrize** when testing multiple inputs with the same assertion logic
8. **Type-annotate test functions** with `-> None` return type

---

*Testing analysis: 2026-06-06*
