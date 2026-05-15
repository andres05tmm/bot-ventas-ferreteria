# Coding Conventions

**Analysis Date:** 2026-03-28

## Naming Patterns

**Files:**
- `snake_case.py` for modules and scripts
- `handlers/` subdirectory contains handler files (`comandos.py`, `mensajes.py`, `callbacks.py`, etc.)
- `routers/` subdirectory contains FastAPI route modules (`ventas.py`, `catalogo.py`, `caja.py`, etc.)
- Migration files prefixed with `migrate_` (e.g., `migrate_ventas.py`, `migrate_memoria.py`)

**Functions:**
- `snake_case` for all functions, both public and private
- Private/internal functions prefixed with single underscore: `_normalizar()`, `_leer_catalogo_postgres()`, `_reconectar()`
- Handler functions: `comando_*` for command handlers, `manejar_*` for action handlers (e.g., `comando_inicio()`, `manejar_audio()`)
- Async functions use `async def` and typically have clear names indicating their async nature

**Variables:**
- `snake_case` for all variables
- Dictionary keys use `snake_case` (camelCase discouraged)
- Constants use `UPPER_SNAKE_CASE` (e.g., `COLOMBIA_TZ`, `MAX_STANDBY`, `_TIMEOUT_PENDIENTE`, `DB_DISPONIBLE`)
- Protected module-level state variables prefixed with underscore: `_pool`, `_cache`, `_cache_ts`, `_estado_lock`
- Type hints use lowercase except for custom types (e.g., `dict[int, str]`, not `Dict[int, str]`)

**Types:**
- Use modern union syntax: `dict | None` instead of `Optional[dict]` or `Union[dict, None]`
- Use lowercase built-in types for hints: `list[dict]`, `dict[str, int]`, `tuple[str, str]`

## Code Style

**Formatting:**
- No linter/formatter explicitly configured (check for `.flake8`, `.pylintrc`, `.black` — none found)
- Line length appears to follow Python conventions (~79-100 char soft limit based on code observed)
- Indentation: 4 spaces consistently

**Linting:**
- No explicit linting config found
- Imports follow PEP 8 conventions but organized with custom headers (see Import Organization below)

## Import Organization

**Order:**
1. Module docstring (if present)
2. Standard library (`# -- stdlib --` header comment)
3. Third-party packages (`# -- terceros --` header comment)
4. Local/project imports (`# -- propios --` header comment)

**Pattern example from `handlers/mensajes.py`:**
```python
"""
Handlers de mensajes: texto, audio (voz) y documentos Excel.
"""

# -- stdlib --
import base64
import json
import logging
import asyncio
import os
import re
import tempfile
import traceback
from datetime import datetime

# -- terceros --
import openpyxl
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# -- propios --
import config
from ai import procesar_con_claude, procesar_acciones, procesar_acciones_async, editar_excel_con_claude
from ventas_state import agregar_al_historial, get_historial
from handlers.callbacks import _enviar_botones_pago as _botones_central
```

**Lazy imports:**
- Used inside functions to avoid circular imports: `import db as _db` and `import psycopg2` appear in function bodies
- Example in `db.py`: `from psycopg2.pool import ThreadedConnectionPool` imported inside `init_db()` function

**Path aliases:**
- No path aliases observed (no `jsconfig.json` or `tsconfig` for paths)
- Imports use relative module names: `from memoria import ...`, `import config`, `import db as _db`

## Error Handling

**Patterns:**
- **Broad except**: `except Exception as e:` is intentional throughout codebase (documented in `CLAUDE.md` as stabilizing pattern)
  - Example in `ai.py` (lines 103-108): Upload function catches ImportError separately, then generic Exception
  - Example in `db.py` (lines 119-150): Connection retry logic handles specific `_BROKEN` exceptions separately, then generic Exception
- **Graceful fallbacks**: Functions return sensible defaults instead of raising
  - `query_one()` returns `dict | None`
  - `parsear_precio()` returns `0.0` on parse failure
  - `convertir_fraccion_a_decimal()` returns `0.0` on conversion failure
- **Logging errors**: Most exception handlers log the error but don't always re-raise (see Logging below)
- **Resource cleanup**: Context managers (`with` statements) used for DB connections and file handles
- **Retry logic**: `_get_conn()` in `db.py` automatically reconnects pool if connection broken, retries once

**Critical error checking:**
- `_check_db()` in `db.py` raises `RuntimeError` if database unavailable (used at start of all public DB functions)
- Environment variable validation in `config.py`: missing TELEGRAM_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY causes `SystemExit(1)` at import

## Logging

**Framework:** Standard library `logging` module

**Logger creation pattern:**
- Module-level logger created at top of each file after imports
- Pattern: `logger = logging.getLogger("ferrebot.<module>")`
- Examples:
  - `config.py`: `logger = logging.getLogger("ferrebot")`
  - `db.py`: `logger = logging.getLogger("ferrebot.db")`
  - `handlers/mensajes.py`: `logger = logging.getLogger("ferrebot.mensajes")`
  - `routers/ventas.py`: `logger = logging.getLogger("ferrebot.api")`
  - `api.py`: `_req_logger = logging.getLogger("ferrebot.request")`

**Usage patterns:**
- `logger.info()` for normal operations (pool created, DB connected, schema verified)
- `logger.warning()` for degraded states (DB offline, DB reconnection needed, missing config)
- Lazy logging for initialization: examples in `db.py` lines 64, 87, 100
- No explicit log levels enforced; application uses INFO and WARNING at minimum

## Comments

**When to comment:**
- Docstrings (in Spanish) required for all public functions and modules
- Inline comments used sparingly, mostly for:
  - Explaining business logic (e.g., fractions in thinner, price thresholds for tornillos)
  - Noting intentional quirks or workarounds (e.g., "Bug fix: L vs XL matching" in test_suite.py)
  - Code sections marked with visual dividers: `# ────────────────────────────────────────`

**Docstring style:**
- Docstrings in Spanish for business logic modules (e.g., `db.py`, `memoria.py`, `ai.py`)
- Docstring includes purpose and sometimes parameter/return documentation
- Example from `db.py` line 35-39:
  ```python
  def init_db() -> bool:
      """
      Inicializa el pool de conexiones.
      Llamar desde start.py ANTES de _restaurar_memoria().
      Retorna True si la conexion fue exitosa.
      """
  ```

**JSDoc/TSDoc:**
- Not applicable (Python project)

## Function Design

**Size:**
- No enforced line limit observed
- Functions range from 10 lines (simple getters) to 300+ lines (complex handlers)
- Complex functions like `procesar_con_claude()` and `procesar_acciones()` in `ai.py` break logic into smaller internal helper functions

**Parameters:**
- Use descriptive parameter names
- Type hints used throughout (modern syntax: `dict`, `list`, not `Dict`, `List`)
- Default parameters documented in docstrings when complex
- Example from `handlers/comandos.py` line 46-50:
  ```python
  async def upload_foto_cloudinary(
      foto_bytes: bytes,
      public_id: str,
      carpeta: str = "ferreteria",
  ) -> dict:
  ```

**Return values:**
- Explicit return type hints: `-> dict`, `-> list[dict]`, `-> dict | None`, `-> int`
- Nullable returns documented: functions returning `None` on failure use `-> dict | None` syntax
- Dictionary returns use consistent key naming across related functions

## Module Design

**Exports:**
- No explicit `__all__` lists found
- Public functions are those without leading underscore
- Import style is selective: `from module import specific_function` (not `from module import *`)
- Example from `handlers/mensajes.py`: explicit imports with internal names preserved: `from handlers.callbacks import _enviar_botones_pago as _botones_central`

**Barrel files:**
- `handlers/__init__.py` and `routers/__init__.py` exist but appear empty (checked via file listings)
- No re-exports through barrel files observed

## Threading & Concurrency

**Synchronization:**
- `threading.Lock()` used for all shared state access in multi-threaded contexts
- Pattern: `with _estado_lock:` wraps reads/writes to shared dicts
- Examples:
  - `ventas_state.py` line 20: `_estado_lock = threading.Lock()`
  - `ventas_state.py` lines 67-70: Lock guards `ventas_pendientes` dictionary
  - `db.py` line 26: `_pool_lock = threading.Lock()` protects pool connection management
  - `db.py` lines 114-150: Lock-protected getconn() in context manager

**Async patterns:**
- Handlers use `async def` and `await` with python-telegram-bot's `ContextTypes`
- Non-blocking DB access: `asyncio.to_thread()` delegates sync DB operations to thread pool
- Example from `db.py` lines 523-540: async wrapper functions use `await _asyncio.to_thread(sync_func, args)`

## State Management

**Global module state:**
- Protected by locks and timestamps for expiration
- Examples:
  - `_cache` and `_cache_ts` in `memoria.py` with `_CACHE_TTL` (600 sec)
  - `_precios_recientes` in `ai.py` with `_PRECIO_TTL` (300 sec)
  - Database connection pool `_pool` in `db.py` with reconnection logic

**State cleanup:**
- Explicit cleanup functions: `limpiar_pendientes_expirados()` in `ventas_state.py`
- Timestamp-based expiration: `_TIMEOUT_PENDIENTE = 300` (5 minutes in ventas_state.py)
- Background reloading: `_reload_cache_background()` in `memoria.py` uses daemon threads

---

*Convention analysis: 2026-03-28*
