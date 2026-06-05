# Coding Conventions

**Analysis Date:** 2026-06-06

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `client.py`, `tools.py`, `output.py`, `errors.py`, `models.py`
- Private/internal modules prefixed with underscore: `_mcp.py`
- Test files prefixed with `test_`: `test_client.py`, `test_errors.py`, `test_tools_integration.py`

**Functions:**
- Use `snake_case` for all functions and methods
- Private helper functions prefixed with underscore: `_parse_bool()`, `_validate_url()`, `_shape_instant_sample()`, `_format_value()`, `_truncation_hint()`, `_request()`
- MCP tool functions use `prometheus_` prefix: `prometheus_list_metrics()`, `prometheus_query()`, `prometheus_query_range()`, `prometheus_list_alerts()`, `prometheus_list_targets()`

**Variables:**
- Use `snake_case` for local variables: `raw_url`, `pat_lower`, `total_count`, `result_type`
- Module-level constants use `UPPER_SNAKE_CASE`: `_METRICS_CAP = 500`, `_RANGE_POINTS_CAP = 5000`, `_MD_ITEM_LIMIT = 20`, `BASE`, `API`
- Private module-level constants prefixed with underscore: `_METRICS_CAP`, `_RANGE_POINTS_CAP`, `_MD_ITEM_LIMIT`
- Module-level mutable globals prefixed with underscore: `_client`, `_client_lock` in `src/prometheus_mcp/_mcp.py`

**Classes:**
- Use `PascalCase`: `PrometheusClient`, `ConfigError`
- TypedDict output schemas use `PascalCase` with descriptive suffixes: `ListMetricsOutput`, `QueryOutput`, `QueryRangeOutput`, `InstantSample`, `RangeSeries`, `AlertItem`, `AlertStateSummary`, `TargetItem`, `TargetJobSummary`

**Types:**
- TypedDict for all structured output schemas — never Pydantic BaseModel for outputs
- `Annotated[type, Field(...)]` for MCP tool parameter validation

## Code Style & Formatting

**Formatter:** Ruff (format)
**Linter:** Ruff (lint)
**Config location:** `pyproject.toml`

```toml
[tool.ruff]
line-length = 120
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]
```

**Enabled rule sets:**
- `E` — pycodestyle errors
- `F` — pyflakes
- `W` — pycodestyle warnings
- `I` — isort (import sorting)
- `B` — flake8-bugbear
- `UP` — pyupgrade (modern Python idioms)

**CI enforcement:** Both `ruff check` and `ruff format --check` run in `.github/workflows/test.yml` before tests.

**Key style rules:**
- Line length: 120 characters
- Target Python 3.10 minimum
- Use `from __future__ import annotations` in every source module (PEP 604 union syntax `str | None` works at runtime on Python 3.10+ this way)
- Use `str | None` union syntax instead of `Optional[str]`

## Import Organization

**Order (enforced by ruff `I` rule):**
1. `__future__` imports (`from __future__ import annotations`)
2. Standard library (`os`, `sys`, `logging`, `threading`, `collections`, `typing`)
3. Third-party packages (`requests`, `urllib3`, `pydantic`, `mcp`, `responses`, `pytest`)
4. Local application imports (`from prometheus_mcp.errors import ConfigError`)

**Path Aliases:** None. All imports are relative to the installed package `prometheus_mcp`.

**Import style:**
- Prefer `from X import Y` over `import X`
- Use `# noqa: F401` for imports that exist only for side-effects (e.g., `from prometheus_mcp import tools as _tools  # noqa: F401` in `src/prometheus_mcp/server.py`)
- Group related imports on multiple lines from the same module:

```python
from prometheus_mcp.models import (
    AlertItem,
    AlertStateSummary,
    InstantSample,
    ListAlertsOutput,
    ...
)
```

## Error Handling Patterns

**Custom exception hierarchy:**
- `ConfigError(ValueError)` in `src/prometheus_mcp/errors.py` — raised for missing/malformed env vars
- Inherits from `ValueError` so existing `isinstance(..., ValueError)` checks still work

**Error handler function:** `errors.handle(exc, action) -> str` in `src/prometheus_mcp/errors.py`
- Converts any exception into an LLM-readable string with actionable next steps
- `action` parameter provides context: `"listing Prometheus metrics"`, `"executing instant query 'up'"`, etc.
- Maps specific HTTP status codes to advice:
  - 401 → mentions `PROMETHEUS_TOKEN`, `PROMETHEUS_USERNAME`, Basic auth
  - 403 → mentions credentials and permissions
  - 404 → suggests checking `PROMETHEUS_URL`
  - 400/422 → extracts Prometheus error body, suggests PromQL syntax check
  - 429 → advises waiting 30-60s, narrowing time range
  - 5xx → flags as transient, suggests retry
- Also handles `requests.ConnectionError`, `requests.Timeout`, generic `ValueError`, and catch-all `Exception`

**Tool error flow (every tool follows this pattern):**

```python
# In src/prometheus_mcp/tools.py — every tool function body
try:
    client = get_client()
    # ... business logic ...
    return output.ok(result, md)
except Exception as exc:
    output.fail(exc, "listing Prometheus metrics")
```

**`output.fail()` in `src/prometheus_mcp/output.py`:**
- Calls `errors.handle(exc, action)` to get actionable message
- Raises `ToolError(message)` from `mcp.server.fastmcp.exceptions`
- Annotated `-> NoReturn` so type-checkers understand the control flow

**`output.ok()` in `src/prometheus_mcp/output.py`:**
- Wraps structured data + markdown into `CallToolResult` with both `content` (TextContent) and `structuredContent`

**Validation errors:**
- Input validation uses `pydantic.Field` constraints (`min_length`, `max_length`) via `Annotated` types on tool parameters
- Business-logic validation raises `ValueError` directly (e.g., invalid `state` parameter in `prometheus_list_targets`)

**Pattern summary:** Errors never leak Python tracebacks to the LLM. Every error becomes an actionable message naming specific env vars or API parameters to check.

## Logging & Observability

**Framework:** Python `logging` standard library

**Logger creation:**
```python
# src/prometheus_mcp/_mcp.py
logger = logging.getLogger(__name__)
```

**Usage:** Minimal — only two `logger.debug()` calls exist:
- `"prometheus_mcp: startup"` in the lifespan context manager
- `"prometheus_mcp: shutdown — HTTP session closed"` on shutdown

**Log levels used:** `DEBUG` only. No `INFO`, `WARNING`, or `ERROR` log calls exist in the codebase.

**Observability approach:** The MCP tool response itself is the primary observability channel:
- Structured data (`structuredContent`) carries machine-readable results
- Markdown rendering (`content`) carries human-readable summaries
- Error messages are self-contained and actionable (no need to correlate with logs)

**Pattern:** When adding new logging, use `logging.getLogger(__name__)` and prefer `DEBUG` for internal operations. Tool errors are communicated via `ToolError`, not logs.

## Documentation Patterns

**Module docstrings:**
- Every `.py` file has a module-level docstring explaining its purpose
- Module docstrings include threading model notes where relevant:
  ```python
  """HTTP client for the Prometheus HTTP API v1.
  ...
  **Threading model.** The client uses ``requests`` (synchronous). FastMCP
  runs synchronous ``@mcp.tool`` in a worker thread...
  """
  ```
- Module docstrings in `src/prometheus_mcp/models.py` include compatibility notes about Pydantic/TypedDict behavior

**Function/method docstrings:**
- Use reStructuredText-style references: `:class:`PrometheusClient``, `:mod:`prometheus_mcp.errors``, `:func:`handle``
- Include `Args:`, `Returns:`, `Raises:` sections where appropriate
- Tool function docstrings are extensive (20-30 lines) because FastMCP exposes them as the tool `description` to MCP clients. They include:
  - What the tool wraps (API endpoint)
  - What it returns (data structure overview)
  - Usage examples with "Use when:" and "Don't use when:" guidance
  - Caveats (e.g., truncation at 500 metrics, 5000-point cap)

**Inline comments:**
- Used sparingly for non-obvious logic (e.g., `# Auth priority: Bearer > Basic > none.`)
- Section separators use Unicode box-drawing characters:
  ```python
  # ── Helpers ────────────────────────────────────────────────────────────────
  # ── Tools ──────────────────────────────────────────────────────────────────
  ```
- Section separators in `models.py`:
  ```python
  # ── Metrics list ──────────────────────────────────────────────────────────────
  # ── Instant query ─────────────────────────────────────────────────────────────
  ```

**Type annotations:**
- Full type annotations on all function signatures including return types
- Use `-> None` for functions with no return value
- Use `-> NoReturn` for functions that always raise (e.g., `output.fail`)
- Type ignore comments used sparingly with explanation: `# type: ignore[return-value]`

**Test docstrings:**
- Every test module has a module docstring explaining what it covers and the testing approach
- Test class names are descriptive: `TestParseBool`, `TestValidateUrl`, `TestPrometheusClientInit`

## Common Patterns

### Dual-Channel Output

Every MCP tool returns both structured data and markdown text via `output.ok()`:

```python
# src/prometheus_mcp/output.py
def ok(data: Mapping[str, Any], markdown: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=markdown)],
        structuredContent=dict(data),
    )
```

All tools construct a `TypedDict` result and a markdown string, then call `output.ok(result, md)`.

### Markdown Truncation

When displaying lists in markdown, cap at `_MD_ITEM_LIMIT = 20` items and append a truncation hint:

```python
md_metrics = metrics[:_MD_ITEM_LIMIT]
md += "\n".join(f"- `{m}`" for m in md_metrics)
if len(metrics) > _MD_ITEM_LIMIT:
    md += _truncation_hint(len(metrics), _MD_ITEM_LIMIT, "metrics")
```

### Thread-Safe Lazy Singleton

The `PrometheusClient` is lazily instantiated with double-checked locking in `src/prometheus_mcp/_mcp.py`:

```python
_client: PrometheusClient | None = None
_client_lock = threading.Lock()

def get_client() -> PrometheusClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # double-checked locking
                _client = PrometheusClient()
    return _client
```

### Environment Configuration

Configuration is read from environment variables with explicit override parameters on the constructor. Pattern in `src/prometheus_mcp/client.py`:

```python
raw_url = url if url is not None else os.environ.get("PROMETHEUS_URL", "")
```

Boolean env vars parsed via `_parse_bool()` accepting `true/false/1/0/yes/no/on/off`.

### Shaping Functions

Raw Prometheus API responses are transformed into typed output schemas via `_shape_*` helper functions in `src/prometheus_mcp/tools.py`:
- `_shape_instant_sample(item) -> InstantSample`
- `_shape_range_series(item) -> RangeSeries`

These handle missing keys gracefully with `.get()` and fallback defaults.

### Tool Registration

Tools are registered via `@mcp.tool()` decorator with explicit metadata:

```python
@mcp.tool(
    name="prometheus_list_metrics",
    annotations={
        "title": "List Metrics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
```

All tools are read-only, non-destructive, and idempotent. The `structured_output=True` flag triggers JSON Schema generation from the TypedDict return annotation.

### `from __future__ import annotations`

Present in every source file. Enables PEP 604 `X | Y` union syntax at annotation time on Python 3.10. **Always add this import when creating new modules.**

---

*Convention analysis: 2026-06-06*
