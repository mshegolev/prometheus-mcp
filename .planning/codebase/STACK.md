# Technology Stack

**Analysis Date:** 2026-06-06

## Languages

**Primary:**
- Python >=3.10 — All source code (`src/prometheus_mcp/`), tests (`tests/`), build config (`pyproject.toml`)

**Supported versions (CI-tested):**
- Python 3.10
- Python 3.11
- Python 3.12

**Version-conditional code:** `src/prometheus_mcp/models.py` uses `typing.TypedDict` on Python 3.12+ and falls back to `typing_extensions.TypedDict` on 3.10/3.11 to avoid a Pydantic 2.13+ runtime schema generation bug with `Required`/`NotRequired` qualifiers.

## Runtime

**Environment:**
- CPython 3.10+ (tested on 3.10, 3.11, 3.12 in CI)
- Docker base image: `python:3.12-slim` (`Dockerfile`)

**Package Manager:**
- pip (no lockfile — dependencies specified via `pyproject.toml` version ranges)
- Lockfile: **missing** — no `requirements.txt`, `poetry.lock`, or `uv.lock` present

**Alternative installation:**
- `uvx prometheus-mcp` — zero-install execution via uv's `uvx` runner

## Frameworks

**Core:**
- **FastMCP** (from `mcp>=1.2`) — MCP server framework. Creates the server instance in `src/prometheus_mcp/_mcp.py` via `FastMCP("prometheus_mcp", lifespan=app_lifespan)`. Tools are registered with `@mcp.tool()` decorators in `src/prometheus_mcp/tools.py`.
- **Pydantic** `>=2.0` — Used for tool parameter validation via `Annotated[..., Field(...)]` annotations and TypedDict-based `outputSchema` generation (`structured_output=True`).

**Testing:**
- **pytest** `>=7` — Test runner, configured in `pyproject.toml` `[tool.pytest.ini_options]` with `testpaths = ["tests"]`
- **responses** `>=0.25` — HTTP request mocking library for simulating Prometheus API responses
- **pytest-cov** `>=4` — Coverage reporting via `--cov=src/prometheus_mcp --cov-report=term-missing`

**Build/Dev:**
- **Hatchling** `>=1.24` — PEP 517 build backend (`[build-system]` in `pyproject.toml`)
- **Ruff** `>=0.5` — Linter and formatter (replaces flake8/black/isort)

## Key Dependencies

**Critical (runtime):**

| Package | Version | Purpose | Used in |
|---------|---------|---------|---------|
| `mcp` | `>=1.2` | MCP protocol server (FastMCP), tool registration, `CallToolResult`, `TextContent`, `ToolError` | `src/prometheus_mcp/_mcp.py`, `src/prometheus_mcp/tools.py`, `src/prometheus_mcp/output.py` |
| `requests` | `>=2.31` | Synchronous HTTP client for Prometheus API v1 | `src/prometheus_mcp/client.py` |
| `urllib3` | `>=2.0` | SSL warning suppression when `PROMETHEUS_SSL_VERIFY=false` | `src/prometheus_mcp/client.py` |
| `pydantic` | `>=2.0` | Parameter validation (`Field`), JSON schema generation from TypedDicts | `src/prometheus_mcp/tools.py`, `src/prometheus_mcp/models.py` |
| `typing-extensions` | `>=4.5` | `TypedDict` backport for Python < 3.12 | `src/prometheus_mcp/models.py` |

**Infrastructure (dev-only):**

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | `>=7` | Test runner |
| `responses` | `>=0.25` | HTTP mocking for Prometheus API |
| `pytest-cov` | `>=4` | Coverage measurement |
| `ruff` | `>=0.5` | Lint + format |

## Build System

**Build backend:** Hatchling `>=1.24`
- Config: `pyproject.toml` `[build-system]`
- Wheel package mapping: `[tool.hatch.build.targets.wheel] packages = ["src/prometheus_mcp"]`
- Build command: `python -m build` (used in CI publish workflow)

**Console script entry point:**
```
prometheus-mcp = "prometheus_mcp.server:main"
```
Defined in `pyproject.toml` `[project.scripts]`. The `main()` function in `src/prometheus_mcp/server.py` calls `mcp.run()`.

**Distribution:**
- Published to PyPI as `prometheus-mcp` version `0.1.0`
- PyPI Trusted Publisher (OIDC) — no API token stored; publish via `.github/workflows/publish.yml`
- Triggered on git tags matching `v*`
- Tag-version consistency check: CI verifies git tag matches `pyproject.toml` version before publishing

## Configuration

**Environment:**
- All runtime config via environment variables (no config files read)
- `.env.example` documents required/optional vars
- `.env` is gitignored

**Required env vars:**
- `PROMETHEUS_URL` — Prometheus server base URL (e.g. `https://prometheus.example.com`)

**Optional env vars:**
- `PROMETHEUS_TOKEN` — Bearer token (takes priority over Basic auth)
- `PROMETHEUS_USERNAME` — HTTP Basic auth username
- `PROMETHEUS_PASSWORD` — HTTP Basic auth password
- `PROMETHEUS_SSL_VERIFY` — `true`/`false` (default: `true`)

**Ruff config** (`pyproject.toml`):
- `line-length = 120`
- `target-version = "py310"`
- Lint rules: `["E", "F", "W", "I", "B", "UP"]` (pycodestyle, pyflakes, warnings, isort, bugbear, pyupgrade)

## CI/CD

**Test workflow:** `.github/workflows/test.yml`
- Trigger: push/PR to `main`
- Matrix: Python 3.10, 3.11, 3.12 on `ubuntu-latest`
- Steps: install (`pip install -e '.[dev]'`), lint (`ruff check` + `ruff format --check`), test (`pytest -v --cov`)

**Publish workflow:** `.github/workflows/publish.yml`
- Trigger: tag push `v*`
- Steps: build (`python -m build`), verify tag == version, publish to PyPI (Trusted Publisher OIDC)

## Platform Requirements

**Development:**
- Python 3.10+ with pip
- No OS-specific dependencies (pure Python)
- Install: `pip install -e '.[dev]'`

**Production:**
- Python 3.10+ runtime
- Network access to Prometheus HTTP API
- Environment variables configured
- MCP client (Claude Desktop, Claude Code, Cursor, or any MCP-compatible client)

**Docker:**
- `Dockerfile` uses `python:3.12-slim`
- Installs from PyPI: `pip install --no-cache-dir prometheus-mcp`
- Entry point: `ENTRYPOINT ["prometheus-mcp"]`

## Threading Model

FastMCP runs an asyncio event loop. All 5 tools in `src/prometheus_mcp/tools.py` are synchronous `def` functions. FastMCP dispatches them to worker threads via `anyio.to_thread.run_sync`, so blocking `requests` HTTP calls do not block the event loop. The `PrometheusClient` singleton in `src/prometheus_mcp/_mcp.py` is protected by a `threading.Lock` with double-checked locking for thread-safe lazy initialization.

## Version Constraints & Compatibility

**Deprecation risks:**
- `typing-extensions` dependency is conditional (`python_version < '3.12'`) — will become unnecessary once Python 3.10/3.11 reach EOL
- `mcp>=1.2` is a very recent package — API may evolve rapidly; pin more tightly before production use

**Upgrade paths:**
- Python 3.13+: Should work (no known blockers; TypedDict from stdlib)
- Pydantic 3.x: May require schema generation changes in `models.py`
- `requests` → `httpx`: Would enable native async, eliminating the thread-dispatch pattern; significant refactor of `client.py`

---

*Stack analysis: 2026-06-06*
