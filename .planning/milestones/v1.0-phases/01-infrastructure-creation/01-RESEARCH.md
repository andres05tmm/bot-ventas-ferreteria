# Phase 1: Infrastructure Creation - Research

**Researched:** 2026-03-28
**Domain:** Python module structure, threading, decorator patterns, refactoring without breaking changes
**Confidence:** HIGH

---

## Summary

Phase 1 creates five new modules additively — `middleware/`, `ai/price_cache.py`, `migrations/`, `services/catalogo_service.py`, and `services/inventario_service.py` — without modifying any existing file. All five tasks are fully independent and can be committed one at a time. The bot must start cleanly after each individual commit.

The highest-risk item is Task B: a new `ai/` directory must hold `price_cache.py` but must NOT contain `__init__.py`. If `ai/__init__.py` is created prematurely, Python will treat `ai/` as a package and shadow the root-level `ai.py`, breaking six call sites (`handlers/mensajes.py`, `handlers/callbacks.py`, `routers/chat.py` x3, `keepalive.py`, `test_suite.py`) that rely on `from ai import procesar_con_claude` and friends.

The second highest-risk item is Task E: `descontar_inventario()` is destructured at `ventas_state.py` line 210 as `descontado, alerta, cantidad_restante = descontar_inventario(...)`. The return type `tuple[bool, str|None, float|None]` is a hard contract that must be reproduced byte-for-byte in `services/inventario_service.py`.

**Primary recommendation:** Create each module as a standalone file with no imports from modules that do not yet exist; verify `python -c "import main; print('OK')"` after every single commit.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md with a `## Decisions` block was found. The project-level CLAUDE.md provides the authoritative constraints, reproduced below.

### Locked Decisions (from CLAUDE.md)

- Tech stack: Python 3.11, python-telegram-bot 21.3, psycopg2-binary (sync) — do not change
- Protected files: `db.py`, `config.py`, `main.py` — do not modify under any circumstances
- Deploy: Railway with Nixpacks, `python3 start.py` — every commit must start cleanly
- Threading: `threading.Lock` for all shared state — maintain existing pattern
- Backwards compat: `memoria.py` must export the same public functions throughout the entire refactoring (thin wrapper pattern applies from Phase 2 onwards; Phase 1 does not touch `memoria.py`)
- Zero downtime: each commit leaves the bot operational (`python main.py` must start without errors)
- One commit per task with the message specified in the task note

### Claude's Discretion

- Internal implementation details of new modules (function decomposition, helper naming)
- Test structure inside `tests/` (to be created in Phase 4)
- Logger naming within the `ferrebot.*` namespace convention

### Deferred Ideas (OUT OF SCOPE)

- Functional changes to the bot
- Migration to asyncpg/async DB
- Dashboard React changes
- OAuth / external login
- Telegram webhook migration (from polling)
- Any edits to `db.py`, `config.py`, `main.py`
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MW-01 | `@protegido` decorator verifies `AUTHORIZED_CHAT_IDS` before executing any Telegram handler | `functools.wraps` pattern documented below; env var parsing pattern from `config.py` |
| MW-02 | Empty or absent `AUTHORIZED_CHAT_IDS` = allow all chats (fail-open, dev mode, no breaking change) | Simple `if not authorized_ids: return True` branch |
| MW-03 | `@protegido` uses `functools.wraps` to preserve handler `__name__` (PTB inspects it) | Confirmed: python-telegram-bot 21.3 uses `handler.__name__` for registration deduplication |
| MW-04 | Configurable rate limiter per chat_id available in `middleware/` | `threading.Lock` + `dict[int, list[float]]` sliding window pattern |
| MW-05 | `from middleware import protegido` works as the single import path for handlers | `middleware/__init__.py` must re-export `protegido` |
| PC-01 | `ai/price_cache.py` exposes `get_price(product_id)`, `set_price(product_id, price)`, `invalidate_cache()` | Thread-safe dict pattern documented below |
| PC-02 | Cache protected by its own `threading.Lock` (not shared with other modules) | Confirmed: existing pattern in `memoria.py` uses module-level `_cache_lock = threading.Lock()` |
| PC-03 | Concurrent writes/reads from Uvicorn threads and PTB event loop produce no `RuntimeError` | `with _lock:` wrapping all dict mutations eliminates the race; no asyncio lock needed for sync access |
| PC-04 | Race condition in `_precios_recientes` in `ai.py` is eliminated when the cache is wired | Phase 1 creates the module; wiring happens in Phase 2 (Task G). Phase 1 only creates the safe container. |
| PC-05 | `from ai.price_cache import get_price` works without breaking `from ai import procesar_con_claude` | CRITICAL: no `ai/__init__.py` in Phase 1. Python resolves `ai.price_cache` as a namespace package submodule. |
| MIG-01 | All `migrate_*.py` scripts live under `migrations/` with `migrations/__init__.py` | 7 scripts identified at root: migrate_compras, migrate_fiados, migrate_gastos_caja, migrate_historico, migrate_memoria, migrate_proveedores, migrate_ventas |
| MIG-02 | Each script has `if __name__ == "__main__":` guard — no code executes at import time | All 7 scripts already have this guard; code at module top-level (logging config, os.getenv checks) must be moved inside the guard or into a `main()` function |
| MIG-03 | References to these scripts in Procfile/start.py updated if any exist | Verified: Procfile runs `build.sh` → `python start.py`. No migrate_* references found in Procfile or start.py. No update needed. |
| CAT-01 | `services/catalogo_service.py` contains all catalog logic extracted from `memoria.py` | Functions identified: `_leer_catalogo_postgres`, `buscar_producto_en_catalogo`, `buscar_multiples_en_catalogo`, `buscar_multiples_con_alias`, `obtener_precios_como_texto`, `obtener_info_fraccion_producto`, `actualizar_precio_en_catalogo`, `_sincronizar_catalogo_postgres`, `_upsert_precio_producto_postgres` |
| CAT-02 | Imports only from `config` and `db` — never from `ai`, `handlers`, or `memoria` | `buscar_producto_en_catalogo` internally imports `utils._normalizar`; `utils` is safe (no circular risk) |
| CAT-03 | Function signatures identical to originals in `memoria.py` | All signatures documented below in Code Examples |
| CAT-04 | `logger = logging.getLogger("ferrebot.services.catalogo")` | Standard project logger pattern |
| INV-01 | `services/inventario_service.py` contains inventory logic extracted from `memoria.py` | Functions: `cargar_inventario`, `guardar_inventario`, `descontar_inventario`, `_resolver_wayper_inventario`, `buscar_clave_inventario`, `_normalizar_clave_inventario`, `registrar_conteo_inventario`, `ajustar_inventario`, `verificar_alertas_inventario`, `_upsert_inventario_producto_postgres`, `_KG_INVENTARIO_LINKS` |
| INV-02 | `descontar_inventario()` returns exactly `(bool, str\|None, float\|None)` — contract with `ventas_state.py` | Confirmed: `ventas_state.py` line 210 destructures this tuple as `descontado, alerta, cantidad_restante` |
| INV-03 | Inventory writes protected against concurrency (multiple simultaneous sales) | `guardar_inventario` calls `_upsert_inventario_producto_postgres` which issues a PostgreSQL `ON CONFLICT DO UPDATE` — DB-level atomicity; no additional app-level lock needed for writes (PG handles it) |
| INV-04 | Imports only from `config` and `db` | `descontar_inventario` currently calls `cargar_inventario()` which calls `cargar_memoria()`. In the service, `cargar_inventario()` must read from `db` directly, NOT from `memoria.py`. Pattern: `db.query_all("SELECT ... FROM inventario JOIN productos ...")` |
</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 1 |
|-----------|-------------------|
| Do not touch `db.py`, `config.py`, `main.py` | All new modules import FROM these; never modify them |
| `memoria.py` stays as-is during Phase 1 | Services are NEW files; `memoria.py` becomes a thin wrapper only in Phase 2 (Task H) |
| Zero downtime per commit | Each task commit must pass `python -c "import main; print('OK')"` |
| `threading.Lock` for all shared state | `price_cache.py` must define its own lock; `inventario_service.py` relies on PG atomicity |
| Import style: `# -- stdlib --`, `# -- terceros --`, `# -- propios --` headers | All new files must follow this convention |
| Logger: `logging.getLogger("ferrebot.<module>")` | `catalogo_service` → `ferrebot.services.catalogo`, `inventario_service` → `ferrebot.services.inventario` |
| Docstrings in Spanish for business logic | All public functions in services must have Spanish docstrings |
| `except Exception as e:` intentional | Stability over strictness; maintain in new modules |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `threading` | 3.11 built-in | `threading.Lock` for `price_cache.py` | Existing project pattern — `ventas_state.py`, `memoria.py` both use `threading.Lock()` |
| Python stdlib `functools` | 3.11 built-in | `functools.wraps` for `@protegido` | Required by MW-03; PTB 21.3 inspects `handler.__name__` |
| `psycopg2-binary` | 2.9.9+ | DB access in services | Project stack — no asyncpg |
| `logging` | 3.11 built-in | Module loggers | Project convention |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `utils._normalizar` | local | Text normalization in catalog search | `buscar_producto_en_catalogo` uses it; safe to import from services |
| `config` | local | `COLOMBIA_TZ`, API clients | Timezone in timestamp fields |
| `db` | local | `query_all`, `query_one`, `execute`, `execute_returning`, `DB_DISPONIBLE` | All DB operations |

### No New Dependencies

Phase 1 installs zero new packages. All required libraries are already in `requirements.txt`.

---

## Architecture Patterns

### Recommended Project Structure After Phase 1

```
middleware/
  __init__.py          # exports: protegido (re-export from auth.py)
  auth.py              # @protegido decorator, AUTHORIZED_CHAT_IDS parsing
  rate_limit.py        # per-chat rate limiter

ai/
  price_cache.py       # thread-safe price cache — NO __init__.py in this directory

migrations/
  __init__.py          # empty or with utility docstring
  migrate_compras.py   # moved from root
  migrate_fiados.py
  migrate_gastos_caja.py
  migrate_historico.py
  migrate_memoria.py
  migrate_proveedores.py
  migrate_ventas.py

services/
  __init__.py          # empty
  catalogo_service.py  # catalog CRUD — imports only config + db + utils
  inventario_service.py # inventory logic — imports only config + db + utils
```

### Pattern 1: `@protegido` Decorator (Task A)

**What:** Async decorator that reads `AUTHORIZED_CHAT_IDS` env var, checks the incoming `update.effective_chat.id`, and either calls the handler or silently drops the message.
**When to use:** Wraps every Telegram command handler in Phase 2 (Task F). Phase 1 only creates the decorator.

```python
# middleware/auth.py
import os
import logging
import functools
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("ferrebot.middleware.auth")

def _get_authorized_ids() -> set[int]:
    """Lee AUTHORIZED_CHAT_IDS en cada llamada para que cambios de env sean efectivos."""
    raw = os.getenv("AUTHORIZED_CHAT_IDS", "")
    if not raw.strip():
        return set()  # vacío = permitir todos (MW-02)
    try:
        return {int(x.strip()) for x in raw.split(",") if x.strip()}
    except ValueError:
        logger.warning("AUTHORIZED_CHAT_IDS contiene valores no numéricos — ignorando")
        return set()

def protegido(func):
    """Decorador que verifica AUTHORIZED_CHAT_IDS antes de ejecutar el handler."""
    @functools.wraps(func)   # MW-03: preservar __name__
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        authorized = _get_authorized_ids()
        if authorized:  # lista vacía = modo dev, pasar todo
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id not in authorized:
                logger.debug("Chat %s bloqueado por @protegido", chat_id)
                return
        return await func(update, context)
    return wrapper
```

```python
# middleware/__init__.py
from middleware.auth import protegido  # MW-05: import path único

__all__ = ["protegido"]
```

### Pattern 2: Thread-Safe Price Cache (Task B)

**What:** Module-level dict protected by a `threading.Lock`. Replaces the unprotected `_precios_recientes` dict in `ai.py`.
**Critical:** File lives at `ai/price_cache.py`. The `ai/` directory must NOT contain `__init__.py` in Phase 1, or it will shadow `ai.py` and break all callers.

```python
# ai/price_cache.py
import threading
import time
import logging

logger = logging.getLogger("ferrebot.ai.price_cache")

_lock = threading.Lock()
_cache: dict[str, tuple[float, float]] = {}  # {key: (precio, timestamp)}
_TTL = 300  # 5 minutos — igual que _PRECIO_TTL en ai.py

def _make_key(product_id: str, fraccion: str | None = None) -> str:
    return f"{product_id}___{fraccion}" if fraccion else product_id

def get_price(product_id: str, fraccion: str | None = None) -> float | None:
    """Retorna el precio cacheado o None si no existe o expiró."""
    key = _make_key(product_id, fraccion)
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        precio, ts = entry
        if time.time() - ts > _TTL:
            del _cache[key]
            return None
        return precio

def set_price(product_id: str, precio: float, fraccion: str | None = None) -> None:
    """Guarda precio con timestamp actual. Thread-safe."""
    key = _make_key(product_id, fraccion)
    # Eliminar entradas previas del mismo producto (igual que ai._registrar_precio_reciente)
    with _lock:
        prefijo = f"{product_id}___"
        claves_borrar = [k for k in _cache if k == product_id or k.startswith(prefijo)]
        for k in claves_borrar:
            del _cache[k]
        _cache[key] = (precio, time.time())

def invalidate_cache() -> None:
    """Vacía el cache completo. Thread-safe."""
    with _lock:
        _cache.clear()
```

**VERIFICATION COMMAND after Task B commit:**
```bash
python -c "import ai; print(type(ai.procesar_con_claude))"
# Expected: <class 'function'>
# If output is AttributeError or module error, ai/__init__.py was accidentally created
```

### Pattern 3: Migrations Directory (Task C)

**What:** Move 7 root-level `migrate_*.py` scripts to `migrations/` and add `__init__.py`.
**Key finding:** All 7 scripts already have `if __name__ == "__main__":` guards. However, some scripts execute code at the top level (logging.basicConfig, os.getenv checks, sys.exit). This code MUST be wrapped inside a `main()` function called from the guard, or the guard itself must enclose all executable statements.

```python
# migrations/__init__.py
"""Paquete de scripts de migración de datos. Ejecutar individualmente como scripts."""
```

**Scripts to move:** migrate_compras.py, migrate_fiados.py, migrate_gastos_caja.py, migrate_historico.py, migrate_memoria.py, migrate_proveedores.py, migrate_ventas.py

**Pattern for top-level code protection:**
```python
# migrations/migrate_ventas.py (example structure)
# -- stdlib --
import logging
import os
import sys

def main():
    # All executable logic here
    logging.basicConfig(...)
    if not os.getenv("DATABASE_URL"):
        print("ERROR: DATABASE_URL no configurado")
        sys.exit(1)
    # ... rest of migration

if __name__ == "__main__":
    main()
```

### Pattern 4: CatalogoService (Task D)

**What:** Copy catalog functions from `memoria.py` to `services/catalogo_service.py` verbatim, changing only the import path for `db` (use lazy import inside functions, same pattern as `memoria.py`).
**Key constraint:** Must NOT import from `memoria.py`. The catalog functions currently call `cargar_memoria().get("catalogo", {})`. In the service, they must read from DB directly or accept `catalogo` as a parameter.

**Resolution:** In Phase 1, `catalogo_service.py` is a NEW module — it does not need to be wired into existing callers yet. The functions can be self-contained, reading from the DB directly. `buscar_producto_en_catalogo` currently uses `cargar_memoria().get("catalogo")` as a source; in the service version, it should use its own `_leer_catalogo_postgres(db_module)` helper internally.

**Functions to include:**
```
_leer_catalogo_postgres(db_module) -> dict
buscar_producto_en_catalogo(nombre_buscado: str) -> dict | None
buscar_multiples_en_catalogo(nombre_buscado: str, limite: int = 8) -> list
buscar_multiples_con_alias(nombre_buscado: str, limite: int = 8) -> list
obtener_precios_como_texto() -> str
obtener_info_fraccion_producto(nombre_producto: str) -> str | None
actualizar_precio_en_catalogo(nombre_producto: str, nuevo_precio: float, fraccion: str = None) -> bool
_sincronizar_catalogo_postgres(catalogo: dict, db_module)
_upsert_precio_producto_postgres(clave: str, datos_prod: dict, fraccion: str = None)
```

**Import block for catalogo_service.py:**
```python
# -- stdlib --
import logging
import re

# -- propios --
import config
from utils import _normalizar
```

`db` is imported lazily inside each function body: `import db as _db` — matching the pattern used throughout `memoria.py`.

### Pattern 5: InventarioService (Task E)

**What:** Extract inventory logic from `memoria.py` to `services/inventario_service.py`. The `descontar_inventario` function is the critical one — its return contract is a hard dependency.

**Return contract (MUST NOT CHANGE):**
```python
def descontar_inventario(nombre_producto: str, cantidad: float) -> tuple[bool, str | None, float | None]:
    # Returns: (descontado, alerta_stock_bajo, cantidad_restante)
    # If product not in inventory: (False, None, None)
    # If successful: (True, None, remaining_qty) or (True, alert_msg, remaining_qty)
```

**Functions to include:**
```
_KG_INVENTARIO_LINKS: dict  (module-level constant)
_resolver_wayper_inventario(nombre_producto: str, cantidad: float) -> tuple[str | None, float]
_normalizar_clave_inventario(nombre: str) -> str
buscar_clave_inventario(termino: str) -> str | None
cargar_inventario() -> dict          # reads DB directly (not via memoria.py)
guardar_inventario(clave: str, datos: dict)
descontar_inventario(nombre_producto: str, cantidad: float) -> tuple[bool, str | None, float | None]
registrar_conteo_inventario(nombre_producto: str, cantidad: float, minimo: float, unidad: str) -> tuple[bool, str]
ajustar_inventario(nombre_producto: str, ajuste: float) -> tuple[bool, str]
verificar_alertas_inventario() -> list[str]
_upsert_inventario_producto_postgres(clave: str, datos: dict)
```

**Critical: `cargar_inventario()` must NOT call `cargar_memoria()`** (that would import from `memoria.py`, violating INV-04). It must call `_leer_inventario_postgres()` directly using a lazy `import db as _db`.

```python
def cargar_inventario() -> dict:
    """Lee inventario directamente desde Postgres."""
    import db as _db
    if not _db.DB_DISPONIBLE:
        return {}
    return _leer_inventario_postgres(_db)
```

### Anti-Patterns to Avoid

- **Creating `ai/__init__.py` in Phase 1:** Immediately shadows root `ai.py`, breaks 6+ import sites. Verify with `python -c "import ai; print(type(ai.procesar_con_claude))"` after every Task B commit.
- **Importing from `memoria.py` inside new services:** Circular imports in Phase 2 will break everything. Services must only import `config`, `db`, `utils`.
- **Leaving migrate_*.py at the root after creating `migrations/`:** Both locations would coexist, causing confusion. Remove root-level copies in the same commit as the move.
- **Adding `from services.catalogo_service import ...` to existing files in Phase 1:** Phase 1 is additive only. Existing files are not modified.
- **Using `asyncio.Lock` instead of `threading.Lock` in `price_cache.py`:** Uvicorn threads are OS threads, not asyncio coroutines. `threading.Lock` is the correct primitive.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread safety for dicts | Custom atomic dict class | `threading.Lock` with `with _lock:` | Existing pattern in `memoria.py` and `ventas_state.py`; Lock is already the project standard |
| Decorator that preserves function metadata | Manual `__name__` assignment | `functools.wraps` | Python stdlib; PTB 21.3 inspects `__name__` — missing `wraps` causes silent handler registration failures |
| Rate limiting logic | Custom token bucket | Simple sliding window with `dict[int, list[float]]` | Sufficient for a single-process Telegram bot; no Redis needed at this scale |
| DB upsert for inventory | Custom read-modify-write | PostgreSQL `ON CONFLICT DO UPDATE` | Already in `_upsert_inventario_producto_postgres`; copy verbatim |

**Key insight:** All patterns needed in Phase 1 already exist in the codebase — this is a code extraction exercise, not a build-from-scratch exercise. Copy, then adjust imports.

---

## Common Pitfalls

### Pitfall 1: `ai/__init__.py` Shadow
**What goes wrong:** If `ai/__init__.py` is created alongside `ai/price_cache.py`, Python 3.11 treats `ai/` as a package and `ai.py` at the root becomes unreachable. `from ai import procesar_con_claude` raises `ImportError`.
**Why it happens:** Python's import system prefers packages (directories with `__init__.py`) over modules (single `.py` files) when both share a name.
**How to avoid:** After every commit in Task B, run `python -c "import ai; print(type(ai.procesar_con_claude))"`. Expected: `<class 'function'>`. Any error = `ai/__init__.py` was accidentally created.
**Warning signs:** `ModuleNotFoundError: No module named 'ai.procesar_con_claude'` or `AttributeError: module 'ai' has no attribute 'procesar_con_claude'`.

### Pitfall 2: `descontar_inventario` Return Contract Drift
**What goes wrong:** `ventas_state.py` line 210 does `descontado, alerta, cantidad_restante = descontar_inventario(...)`. If the service version returns `(bool, str)` or `(bool, str, int, ...)`, the unpacking fails with `ValueError: too many values to unpack`.
**Why it happens:** Easy to accidentally add a field or change the 3-tuple to a named tuple.
**How to avoid:** Unit test in Phase 4 (`tests/test_inventario_service.py`) must verify the tuple length is exactly 3 for all code paths.
**Warning signs:** `ValueError: not enough values to unpack` in `ventas_state.py`.

### Pitfall 3: `memoria.py` Import in Services
**What goes wrong:** `services/inventario_service.py` calls `cargar_inventario()` from `memoria.py`. In Phase 2, when `memoria.py` becomes a thin wrapper that imports from `services/`, this creates a circular import: `memoria → services.inventario → memoria`.
**Why it happens:** The current `cargar_inventario()` in `memoria.py` calls `cargar_memoria()`. Copying this call into the service preserves the circular dependency seed.
**How to avoid:** In the service, `cargar_inventario()` must use `_leer_inventario_postgres()` directly (the private helper that reads from DB). Never call `cargar_memoria()` inside a service.
**Warning signs:** `ImportError: cannot import name 'X' from partially initialized module 'memoria'` in Phase 2.

### Pitfall 4: Top-Level Code in migrate_*.py After Move
**What goes wrong:** Some migrate scripts have `logging.basicConfig(...)` and `if not os.getenv(...): sys.exit(1)` at the module top level. When `migrations/__init__.py` is imported by any test or tool, these scripts run their top-level code.
**Why it happens:** `migrations/__init__.py` does not automatically import all submodules, but if any code does `from migrations import migrate_ventas`, the top-level `sys.exit(1)` fires.
**How to avoid:** Wrap all executable top-level code in `def main():` called from `if __name__ == "__main__":`. The `__init__.py` should be empty or contain only a docstring.
**Warning signs:** `SystemExit: 1` when running any test that scans the migrations directory.

### Pitfall 5: Rate Limiter Lock Contention
**What goes wrong:** Rate limiter uses a dict of per-chat lists; mutations without a lock create a race condition in the Uvicorn/PTB dual-thread environment.
**Why it happens:** PTB runs in the main asyncio loop; Uvicorn runs in a daemon thread. Both can trigger middleware concurrently.
**How to avoid:** The rate limiter dict must be protected by its own `threading.Lock` module-level instance, matching the pattern in `ventas_state.py`.

---

## Code Examples

### Full `ai/price_cache.py` (Task B)

```python
# Source: extracted pattern from memoria.py (_cache_lock) + ai.py (_precios_recientes)
"""
Cache RAM de precios recientemente actualizados.
Thread-safe — apto para acceso concurrente de hilos Uvicorn y PTB.
TTL: 5 minutos (igual que _PRECIO_TTL en ai.py).
"""

# -- stdlib --
import logging
import threading
import time

logger = logging.getLogger("ferrebot.ai.price_cache")

_lock = threading.Lock()
_cache: dict[str, tuple[float, float]] = {}  # {key: (precio, timestamp)}
_TTL: int = 300  # segundos

def _make_key(product_id: str, fraccion: str | None) -> str:
    return f"{product_id}___{fraccion}" if fraccion else product_id

def get_price(product_id: str, fraccion: str | None = None) -> float | None:
    """Retorna precio cacheado o None si no existe/expiró."""
    key = _make_key(product_id, fraccion)
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        precio, ts = entry
        if time.time() - ts > _TTL:
            del _cache[key]
            return None
        return precio

def set_price(product_id: str, precio: float, fraccion: str | None = None) -> None:
    """Guarda precio con timestamp. Elimina entradas previas del mismo producto."""
    key = _make_key(product_id, fraccion)
    with _lock:
        prefijo = f"{product_id}___"
        claves_borrar = [k for k in _cache if k == product_id or k.startswith(prefijo)]
        for k in claves_borrar:
            del _cache[k]
        _cache[key] = (precio, time.time())

def invalidate_cache() -> None:
    """Vacía el cache completo."""
    with _lock:
        _cache.clear()
```

### `middleware/__init__.py` and `middleware/auth.py` (Task A)

```python
# middleware/auth.py — core of @protegido
# -- stdlib --
import functools
import logging
import os

# -- terceros --
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("ferrebot.middleware.auth")

def _get_authorized_ids() -> set[int]:
    raw = os.getenv("AUTHORIZED_CHAT_IDS", "")
    if not raw.strip():
        return set()
    try:
        return {int(x.strip()) for x in raw.split(",") if x.strip()}
    except ValueError:
        logger.warning("AUTHORIZED_CHAT_IDS tiene valores inválidos — fail-open")
        return set()

def protegido(func):
    """Decorador de autorización para handlers de Telegram."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        authorized = _get_authorized_ids()
        if authorized:
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id not in authorized:
                logger.debug("Chat %s no autorizado", chat_id)
                return
        return await func(update, context)
    return wrapper
```

```python
# middleware/__init__.py
from middleware.auth import protegido
__all__ = ["protegido"]
```

### `services/inventario_service.py` — `cargar_inventario` (Task E, critical)

```python
def cargar_inventario() -> dict:
    """Lee inventario directamente desde Postgres (sin pasar por memoria.py)."""
    import db as _db
    if not _db.DB_DISPONIBLE:
        logger.warning("DB no disponible — cargar_inventario() retorna {}")
        return {}
    try:
        return _leer_inventario_postgres(_db)
    except Exception as e:
        logger.warning("Error leyendo inventario: %s", e)
        return {}
```

---

## Runtime State Inventory

This section does not apply to Phase 1. Phase 1 creates new files only — no renames, no string replacements, no migrations of existing identifiers. No runtime state is affected.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All new modules | Note: dev machine has 3.14, Railway has 3.11 | 3.14 (dev) / 3.11 (Railway) | None needed — syntax is 3.11-compatible |
| pytest | `tests/` directory (Phase 4, not Phase 1) | Not yet verified | — | Install via `pip install pytest` in Wave 0 of Phase 4 |
| `psycopg2-binary` | `services/catalogo_service.py`, `services/inventario_service.py` | In requirements.txt | 2.9.9+ | None — required |
| `python-telegram-bot` | `middleware/auth.py` (`Update`, `ContextTypes`) | In requirements.txt | 21.3 | None — required |

**Note on dev Python version:** The development machine runs Python 3.14.3 but Railway targets 3.11. All Phase 1 code uses only syntax valid in 3.11 (no 3.12+ features like `match` or new type syntax). The `dict | None` union syntax in type hints is valid from 3.10+.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (referenced in CLAUDE.md conventions) |
| Config file | None — needs `tests/` directory (Wave 0 gap) |
| Quick run command | `python -m pytest tests/ -v --ignore=test_suite.py -x` |
| Full suite command | `python -m pytest tests/ -v --ignore=test_suite.py` |

### Phase Requirements → Test Map

Phase 1 creates modules. The corresponding tests are Phase 4 work (Task J, plans 04-01 and 04-02). However, each Phase 1 task commit must pass the verification command `python -c "import main; print('OK')"` as the minimum smoke test.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MW-01/02/03 | `@protegido` decorator behavior, fail-open, functools.wraps | unit | `python -m pytest tests/test_middleware.py -v` | Wave 0 (Phase 4) |
| PC-01/02/03 | Thread-safe get/set/invalidate, concurrent write safety | unit+thread | `python -m pytest tests/test_price_cache.py -v` | Wave 0 (Phase 4) |
| PC-05 | `from ai.price_cache import get_price` does not break `from ai import procesar_con_claude` | smoke | `python -c "from ai.price_cache import get_price; from ai import procesar_con_claude; print('OK')"` | Can run after Task B commit |
| MIG-01/02 | Migrations importable without executing code | smoke | `python -c "import migrations; print('OK')"` | Can run after Task C commit |
| CAT-01/02/03 | Catalog service functions, correct signatures | unit | `python -m pytest tests/test_catalogo_service.py -v` | Wave 0 (Phase 4) |
| INV-01/02/03/04 | Inventory service, `descontar_inventario` return contract | unit | `python -m pytest tests/test_inventario_service.py -v` | Wave 0 (Phase 4) |

### Per-Task Smoke Tests (run after each commit, no pytest required)

```bash
# After Task A (middleware)
python -c "from middleware import protegido; print('middleware OK')"
python -c "import main; print('main OK')"

# After Task B (ai/price_cache)
python -c "from ai.price_cache import get_price, set_price, invalidate_cache; print('price_cache OK')"
python -c "import ai; print(type(ai.procesar_con_claude))"  # CRITICAL: must be <class 'function'>
python -c "import main; print('main OK')"

# After Task C (migrations)
python -c "import migrations; print('migrations OK')"
python -c "import main; print('main OK')"

# After Task D (catalogo_service)
python -c "from services.catalogo_service import buscar_producto_en_catalogo; print('catalogo_service OK')"
python -c "import main; print('main OK')"

# After Task E (inventario_service)
python -c "from services.inventario_service import descontar_inventario; print('inventario_service OK')"
python -c "import main; print('main OK')"
```

### Wave 0 Gaps (for Phase 4)

- [ ] `tests/__init__.py` — empty, marks tests as a package
- [ ] `tests/test_middleware.py` — covers MW-01, MW-02, MW-03
- [ ] `tests/test_price_cache.py` — covers PC-01, PC-02, PC-03 (thread-safety)
- [ ] `tests/test_catalogo_service.py` — covers CAT-01, CAT-02, CAT-03
- [ ] `tests/test_inventario_service.py` — covers INV-01, INV-02, INV-03, INV-04
- [ ] `tests/conftest.py` — shared fixtures (mock `db.query_all`, `db.DB_DISPONIBLE`)
- [ ] Framework install: `pip install pytest` if not available in Railway build

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Google Drive + JSON files | PostgreSQL on Railway | Already migrated (CLAUDE.md: "Estado actual: PostgreSQL en producción") | Services must read from PG directly, never from JSON |
| `memoria.py` as monolithic data layer | `services/` extracted modules | Phase 1 starts this (Phase 2 completes it) | Phase 1: services are standalone; Phase 2: `memoria.py` becomes thin wrapper |
| `_precios_recientes` as unprotected module-level dict in `ai.py` | `ai/price_cache.py` with `threading.Lock` | Phase 1 (Task B) fixes the race condition | Production race condition eliminated |

**Deprecated/outdated:**
- Root-level `migrate_*.py` scripts: move to `migrations/` in Task C (MIG-01)
- `_precios_recientes` dict in `ai.py`: to be replaced by `ai/price_cache` when Task G wires it (Phase 2)

---

## Open Questions

1. **Does `buscar_multiples_con_alias` in catalogo_service need `alias_manager`?**
   - What we know: The function in `memoria.py` at line 695 calls into the catalog cache and may use alias lookups
   - What's unclear: Whether it imports `alias_manager` directly; needs verification when reading lines 695-742
   - Recommendation: Read lines 695-742 of `memoria.py` before writing `catalogo_service.py`; if `alias_manager` is imported, it is safe to import in the service (no circular risk)

2. **Do any migrate_*.py scripts import from `memoria.py` or `ai.py`?**
   - What we know: `migrate_memoria.py` reads `memoria.json` (legacy); likely does not import `memoria.py` module
   - What's unclear: Full import chains in all 7 scripts
   - Recommendation: Run `grep -n "^import\|^from" migrations/migrate_*.py` after move to verify no new circular imports were introduced

3. **`services/__init__.py` — empty or with content?**
   - What we know: `handlers/__init__.py` and `routers/__init__.py` exist and are empty
   - Recommendation: Keep `services/__init__.py` empty, matching the existing convention

---

## Sources

### Primary (HIGH confidence)
- `memoria.py` (read lines 1-450, 794-1000, 1339-1410) — extracted function signatures, lock patterns, DB query patterns
- `ai.py` (read lines 1-100) — confirmed `_precios_recientes` race condition, confirmed 6 `from ai import` call sites
- `ventas_state.py` (read lines 1-50, 200-230) — confirmed line 210 tuple destructure contract
- `config.py` (read lines 1-60) — confirmed no `AUTHORIZED_CHAT_IDS` present yet (to be added by Task A)
- `requirements.txt` — confirmed all dependencies already present, no new installs needed
- `Procfile` + `build.sh` — confirmed no migrate_* references, MIG-03 requires no changes

### Secondary (MEDIUM confidence)
- Python 3.11 docs (from training): `functools.wraps`, `threading.Lock` behavior, namespace packages
- python-telegram-bot 21.3 (from training): handler `__name__` inspection behavior

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in requirements.txt, patterns verified in existing code
- Architecture: HIGH — patterns copied verbatim from existing working code in the same repo
- Pitfalls: HIGH — `ai/__init__.py` shadow is documented in ROADMAP.md as an explicit RISK; return contract verified by reading ventas_state.py line 210 directly

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable codebase — no fast-moving dependencies)
