# AGENTS.md - MonoRelay

## Project Overview

Configurable LLM API relay server built with **Python 3.12 + FastAPI**. Supports OpenRouter, NVIDIA NIM, OpenAI, Anthropic, DeepSeek, Groq, and ChatGPT web reverse proxy.

## Commands

### Development
```bash
# Create virtual environment and install deps
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Run server (default port 8787)
python -m backend.main
python -m backend.main --config /path/to/config.yml --port 9000

# One-click start (auto-creates venv, installs deps, starts server)
./start.sh          # Linux/macOS
.\start.ps1         # Windows
```

### Docker
```bash
docker compose up -d
docker compose logs -f
```

### Packaging (single executable)
```bash
bash scripts/build.sh       # Linux/macOS
.\scripts\build.ps1         # Windows
```

### Testing
**No test framework is currently configured.** There are no test files in the repository. If adding tests, use `pytest` (not yet a dependency). To run a single test file once added:
```bash
.venv/bin/pytest tests/test_file.py -v
.venv/bin/pytest tests/test_file.py::test_function -v
```

### Linting / Formatting
**No linter or formatter is configured.** The codebase has no ruff, black, mypy, flake8, or similar tooling. Follow the existing style manually (see below).

## Code Style

### Imports
- `from __future__ import annotations` at the top of every `.py` file
- Standard library imports first, then third-party, then relative imports (`..module`)
- Group imports with a blank line between each group
- Use relative imports within the `backend` package (e.g., `from ..models import AppConfig`)

### Formatting
- 4-space indentation (no tabs)
- Max line length ~120 chars (not strictly enforced, no formatter configured)
- Blank lines: 2 between top-level classes/functions, 1 between methods in a class
- Trailing commas on multi-line structures when it improves readability

### Type Hints
- **Always use type hints** on function signatures and class attributes
- Use `Optional[T]` for nullable values (not `T | None` in function signatures, though `str | list[str]` is used in Pydantic model fields)
- Use `dict[str, Any]` for untyped dicts
- Return type annotations required: `-> dict`, `-> StreamingResponse | dict`, `-> AsyncGenerator[bytes, None]`

### Naming Conventions
- **Modules/files**: `snake_case.py` (e.g., `key_manager.py`, `openai_format.py`)
- **Classes**: `PascalCase` (e.g., `KeyManager`, `ModelRouter`, `ProviderConfig`)
- **Functions/methods**: `snake_case` (e.g., `resolve_model`, `select_key`, `record_request`)
- **Variables**: `snake_case` (e.g., `provider_name`, `resolved_model`, `is_stream`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MODEL_COSTS`, `GIST_DESCRIPTION`)
- **Private attributes**: leading underscore (e.g., `_entries`, `_config`, `_callbacks`)

### Pydantic Models
- All config/data models inherit from `pydantic.BaseModel`
- Use `Field(default_factory=...)` for mutable defaults (lists, dicts)
- Use `Field(default_factory=lambda: {...})` for complex dict defaults
- Optional fields use `Optional[T] = None` or `T = default_value`

### Error Handling
- Use `try/except` with specific exception types where possible, bare `except Exception` as fallback
- Log errors with `logger.error()` or `logger.warning()` before returning error responses
- API errors return `{"error": {"message": str, "type": str}}` dicts
- Use `HTTPException` from FastAPI for management API errors (400, 404, 409, 500)
- Never expose raw stack traces to clients

### Logging
- Logger naming convention: `prisma.<module_name>` (e.g., `prisma.openai_proxy`, `prisma.key_manager`)
- Get logger via `logging.getLogger("prisma.xxx")` at module level
- Use Chinese in log messages for user-facing output (e.g., `f"模型={resolved_model} | 提供商={provider_name}"`)
- Key info logged: model, provider, URL, latency, token counts, error messages

### Async Patterns
- All I/O-bound code is async (`async def`)
- Use `httpx.AsyncClient` for HTTP requests (never `requests`)
- Use `aiosqlite` for database operations (never synchronous sqlite3)
- Streaming uses `AsyncGenerator[bytes, None]` with `StreamingResponse`
- Background tasks via `asyncio.create_task()`

### Architecture
```
backend/
  main.py           # FastAPI app, routes, lifespan, auth middleware
  config.py         # ConfigManager - YAML loading, hot-reload via watchfiles
  models.py         # All Pydantic data models (AppConfig, ProviderConfig, etc.)
  key_manager.py    # KeyEntry + KeyManager - rotation, cooldown, selection
  router.py         # ModelRouter - alias resolution, provider matching
  logger.py         # RequestLogger - async SQLite request logging
  stats.py          # StatsTracker - in-memory + JSON-persisted statistics
  sync.py           # GistSync - GitHub Gist push/pull
  sync_storage.py   # SyncStorage - local token persistence
  proxy/            # OpenAI/Anthropic format proxy handlers
  web_reverse/      # ChatGPT web reverse proxy module
```

### Docstrings
- Module-level: triple-quoted single-line description (e.g., `"""API Key manager with round-robin..."""`)
- Function docstrings: optional, but use Google-style if present
- Chinese comments are acceptable and common throughout the codebase
