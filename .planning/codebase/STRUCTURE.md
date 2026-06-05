# Codebase Structure

**Analysis Date:** 2026-06-06

## Directory Layout

```
prometheus-mcp/
├── src/
│   └── prometheus_mcp/          # Main Python package (all source code)
│       ├── __init__.py           # Package init — __version__ only
│       ├── _mcp.py               # Shared FastMCP instance + client cache
│       ├── server.py             # Entry point — console script main()
│       ├── tools.py              # 5 MCP tool functions + shaping helpers
│       ├── models.py             # TypedDict output schemas for all tools
│       ├── output.py             # Dual-channel result helpers (ok/fail)
│       ├── client.py             # PrometheusClient HTTP wrapper
│       └── errors.py             # Exception → actionable message mapper
├── tests/                        # All test files (flat, no subdirs)
│   ├── test_tools_integration.py # End-to-end tool tests (mocked HTTP)
│   ├── test_tools_helpers.py     # Unit tests for pure shaping functions
│   ├── test_protocol.py          # Wire-protocol / MCP schema smoke tests
│   ├── test_client.py            # PrometheusClient construction + config
│   ├── test_errors.py            # Error handler → message mapping
│   └── test_mcp_client_cache.py  # Singleton cache get_client() tests
├── .github/
│   └── workflows/
│       ├── test.yml              # CI: lint + test on Python 3.10/3.11/3.12
│       └── publish.yml           # CD: build + publish to PyPI on tag push
├── .planning/
│   └── codebase/                 # GSD codebase analysis documents
├── pyproject.toml                # Build config, deps, scripts, tool config
├── Dockerfile                    # Minimal image — pip install + entrypoint
├── server.json                   # MCP server manifest (schema, env vars)
├── glama.json                    # Glama.ai MCP registry metadata
├── .env.example                  # Example env var template
├── .gitignore                    # Standard Python .gitignore
├── README.md                     # User-facing documentation
├── CHANGELOG.md                  # Release history
├── EVALUATION.md                 # MCP evaluation criteria / rubric
├── evaluation.xml                # Machine-readable evaluation data
└── LICENSE                       # MIT license
```

## Directory Purposes

**`src/prometheus_mcp/`:**
- Purpose: All production source code — the installable Python package
- Contains: 7 Python modules + `__init__.py`
- Key files: `tools.py` (693 lines, largest file — contains all business logic), `client.py` (155 lines — HTTP layer), `models.py` (125 lines — output schemas)

**`tests/`:**
- Purpose: All test code — flat directory, no subdirectories
- Contains: 6 test files, ~1350 lines total
- Key files: `test_tools_integration.py` (650 lines — comprehensive integration tests), `test_protocol.py` (197 lines — MCP schema validation)

**`.github/workflows/`:**
- Purpose: CI/CD automation
- Contains: 2 workflow files
- `test.yml` runs on push/PR to main: ruff lint + pytest with coverage across Python 3.10/3.11/3.12
- `publish.yml` runs on tag push (`v*`): builds sdist+wheel, verifies tag matches version, publishes to PyPI via trusted publisher OIDC

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis documents (this file lives here)
- Generated: Partially — created by GSD mapper agents
- Committed: Yes

## Key File Locations

**Entry Points:**
- `src/prometheus_mcp/server.py`: Console script entry point — `main()` calls `mcp.run()` to start stdio loop
- `Dockerfile`: Docker entry — `ENTRYPOINT ["prometheus-mcp"]` runs the console script

**Configuration:**
- `pyproject.toml`: Build system (hatchling), dependencies, console scripts, ruff/pytest config
- `server.json`: MCP server manifest — declares package, transport (stdio), required/optional env vars
- `.env.example`: Template showing all 5 environment variables
- `glama.json`: Glama.ai registry metadata (maintainer only)

**Core Logic:**
- `src/prometheus_mcp/tools.py`: All 5 tool implementations + data shaping helpers (largest file)
- `src/prometheus_mcp/client.py`: `PrometheusClient` class — HTTP communication with Prometheus
- `src/prometheus_mcp/_mcp.py`: Shared `FastMCP` instance, `get_client()` singleton cache, `app_lifespan`

**Type Definitions:**
- `src/prometheus_mcp/models.py`: 10 TypedDict classes defining all tool output schemas

**Error Handling:**
- `src/prometheus_mcp/errors.py`: `ConfigError` class + `handle()` function for exception → message mapping
- `src/prometheus_mcp/output.py`: `ok()` / `fail()` functions wrapping results into `CallToolResult`

**Testing:**
- `tests/test_tools_integration.py`: Integration tests for all 5 tools (mocked HTTP via `responses`)
- `tests/test_tools_helpers.py`: Unit tests for pure helper functions
- `tests/test_protocol.py`: MCP wire-protocol validation — annotations, input/output schemas
- `tests/test_client.py`: Client construction, URL validation, auth selection, env-var parsing
- `tests/test_errors.py`: HTTP status → error message mapping
- `tests/test_mcp_client_cache.py`: Singleton cache behavior

## Module Organization

The package `prometheus_mcp` uses a flat module structure (no sub-packages). Every module has a single clear responsibility:

| Module | Lines | Responsibility |
|--------|-------|----------------|
| `tools.py` | 693 | Tool functions + data shaping helpers — the "application layer" |
| `client.py` | 155 | HTTP client for Prometheus API v1 |
| `models.py` | 125 | TypedDict output schemas |
| `errors.py` | 103 | Exception mapping to actionable messages |
| `_mcp.py` | 55 | Shared FastMCP instance + client singleton cache |
| `output.py` | 28 | Dual-channel result construction |
| `server.py` | 20 | Entry point — imports tools, starts MCP loop |
| `__init__.py` | 3 | Package metadata (`__version__`) |

**Import convention:** The `_mcp.py` module is prefixed with `_` to signal it's internal. All other modules are regular public modules.

**No `__all__` exports** except `server.py` which exports `["mcp", "app_lifespan", "main"]`.

## Entry Points

**Console script (`prometheus-mcp`):**
- Defined in: `pyproject.toml` line 45: `prometheus-mcp = "prometheus_mcp.server:main"`
- Implementation: `src/prometheus_mcp/server.py:11` → `mcp.run()` (stdio transport)
- The import of `prometheus_mcp.tools` at the top of `server.py` triggers `@mcp.tool` decorator registration

**Direct Python execution:**
- `python -m prometheus_mcp.server` works via `if __name__ == "__main__": main()`

**Docker:**
- `Dockerfile:8` → `ENTRYPOINT ["prometheus-mcp"]`

**No CLI arguments.** All configuration is via environment variables.

## Naming Conventions

**Files:**
- Source modules: `snake_case.py` (e.g., `tools.py`, `client.py`, `models.py`)
- Internal modules: `_snake_case.py` (e.g., `_mcp.py`)
- Test files: `test_<module_or_feature>.py` (e.g., `test_client.py`, `test_tools_integration.py`)

**Directories:**
- Package: `snake_case` (e.g., `prometheus_mcp`)
- Config: dotfile directories (e.g., `.github`, `.planning`)

**Functions:**
- Tool functions: `prometheus_<action>` (e.g., `prometheus_list_metrics`, `prometheus_query`)
- Internal helpers: `_snake_case` (e.g., `_shape_instant_sample`, `_format_value`, `_parse_bool`)
- Public helpers: `snake_case` (e.g., `get_client`, `handle`, `ok`, `fail`)

**Constants:**
- `_UPPER_SNAKE_CASE` for module-level caps: `_METRICS_CAP = 500`, `_RANGE_POINTS_CAP = 5000`, `_MD_ITEM_LIMIT = 20`

**Classes:**
- `PascalCase`: `PrometheusClient`, `ConfigError`
- TypedDicts: `PascalCase` matching output semantics: `ListMetricsOutput`, `InstantSample`, `RangeSeries`, etc.

## Where to Add New Code

**New MCP tool:**
1. Add TypedDict output schema(s) to `src/prometheus_mcp/models.py`
2. Add the tool function to `src/prometheus_mcp/tools.py` with `@mcp.tool(...)` decorator
3. Follow the existing pattern: get client → call API → shape response → return `output.ok(result, md)`
4. Add integration tests to `tests/test_tools_integration.py`
5. If the tool has pure helpers, add unit tests to `tests/test_tools_helpers.py`
6. Update `tests/test_protocol.py` `EXPECTED_TOOLS` dict with the new tool's annotations and params

**New Prometheus API endpoint support:**
1. No changes to `client.py` needed — use `client.get(endpoint, params)` directly
2. Add tool + models as described above

**New error handling for a specific HTTP status:**
1. Add a new `if code == NNN:` branch in `src/prometheus_mcp/errors.py:handle()`
2. Add test in `tests/test_errors.py`

**New authentication method:**
1. Extend `PrometheusClient.__init__()` in `src/prometheus_mcp/client.py`
2. Add new env var to: `server.json`, `.env.example`, `errors.py` config error message
3. Add tests in `tests/test_client.py`

## Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Build system (hatchling), package metadata, dependencies, console scripts, ruff config, pytest config |
| `server.json` | MCP server manifest — declares package identifier, transport type (stdio), env var schema for MCP clients |
| `glama.json` | Glama.ai MCP registry — maintainer metadata |
| `.env.example` | Template for required/optional environment variables (not loaded at runtime) |
| `.gitignore` | Standard Python gitignore (pycache, venv, dist, coverage, IDE files) |
| `Dockerfile` | Minimal Python 3.12-slim image — `pip install prometheus-mcp` + `ENTRYPOINT` |

**No runtime config files.** The application reads only environment variables:
- `PROMETHEUS_URL` (required)
- `PROMETHEUS_TOKEN` (optional — Bearer auth)
- `PROMETHEUS_USERNAME` (optional — Basic auth)
- `PROMETHEUS_PASSWORD` (optional — Basic auth)
- `PROMETHEUS_SSL_VERIFY` (optional — defaults to `true`)

## Generated vs Authored Files

**Authored (hand-written):**
- All files in `src/prometheus_mcp/` — production code
- All files in `tests/` — test code
- `pyproject.toml`, `server.json`, `glama.json`, `.env.example`, `Dockerfile`
- `README.md`, `CHANGELOG.md`, `EVALUATION.md`, `LICENSE`
- `.github/workflows/*.yml`
- `.gitignore`

**Generated:**
- `evaluation.xml` — machine-readable evaluation data (likely generated from EVALUATION.md or CI)
- `.planning/codebase/*.md` — generated by GSD codebase mapper agents
- Build artifacts (not committed): `dist/`, `*.egg-info/`, `__pycache__/`

**No code generation, no ORM migrations, no protobuf/gRPC stubs.** The codebase is 100% hand-authored production code.

## Special Directories

**`.planning/`:**
- Purpose: GSD workflow planning and analysis documents
- Generated: Yes (by GSD agents)
- Committed: Yes

**`.github/workflows/`:**
- Purpose: GitHub Actions CI/CD pipelines
- Generated: No (hand-authored)
- Committed: Yes

---

*Structure analysis: 2026-06-06*
