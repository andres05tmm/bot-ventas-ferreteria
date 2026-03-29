# Stack Research: Python Bot Refactoring

**Date:** 2026-03-28
**Domain:** Incremental modular refactoring of a live Python 3.11 Telegram bot + FastAPI

---

## What the existing stack already provides

| Component | Relevant feature | Use in refactoring |
|-----------|-----------------|-------------------|
| Python 3.11 | `__init__.py` package system, `functools.wraps`, `threading.Lock` | Module boundaries, decorator compat, thread safety |
| python-telegram-bot 21.3 | Inspects handler `__name__`/`__qualname__` for error reporting | Must preserve names via `functools.wraps` |
| FastAPI 0.111 | Middleware stack, dependency injection | Auth middleware can wrap API routes |
| psycopg2-binary | Sync ThreadedConnectionPool (already in db.py) | No changes needed — services just call db.query_* |
| pytest | Already referenced in CLAUDE.md | Unit tests per new module, isolate via fixtures |

No new libraries needed. The entire refactoring uses stdlib + existing deps.

---

## Pattern 1 — Package-with-`__init__` for Every New Directory

```python
# middleware/__init__.py
from .auth import protegido
from .rate_limit import rate_limiter

__all__ = ["protegido", "rate_limiter"]
```

Callers import `from middleware import protegido`, not `from middleware.auth import protegido`. This keeps internal module structure changeable without touching callers. Wildcard re-exports (`from .auth import *`) are forbidden — enumerate every name explicitly.

---

## Pattern 2 — Thin Wrapper for Backwards Compatibility (memoria.py)

`memoria.py` must keep all its public names after Tarea H. After services/ exists:

```python
# memoria.py (thin wrapper, post-Tarea H)
from services.catalogo_service import (
    obtener_catalogo,
    buscar_producto,
    actualizar_precio,
    # ... all names that were here before
)
from services.inventario_service import (
    descontar_inventario,
    obtener_inventario,
    # ...
)

# Re-export everything — callers don't change a single import
__all__ = [
    "obtener_catalogo", "buscar_producto", "actualizar_precio",
    "descontar_inventario", "obtener_inventario",
    # ... complete list
]
```

No caller (ai.py, handlers/, routers/) touches its import statements. The thin wrapper is the contract.

---

## Pattern 3 — `@protegido` Decorator with `functools.wraps`

```python
# middleware/auth.py
import functools
import os
from telegram import Update
from telegram.ext import ContextTypes

AUTHORIZED_IDS = set(
    filter(None, os.getenv("AUTHORIZED_CHAT_IDS", "").split(","))
)

def protegido(func):
    @functools.wraps(func)  # MANDATORY — PTB inspects __name__/__qualname__
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if AUTHORIZED_IDS and chat_id not in AUTHORIZED_IDS:
            await update.message.reply_text("No autorizado.")
            return
        return await func(update, context)
    return wrapper
```

Empty `AUTHORIZED_CHAT_IDS` = allow all (dev mode with no env var set). `functools.wraps` is mandatory — PTB uses `__name__` for logging and error reporting; without it, all handlers appear as "wrapper" in logs.

---

## Pattern 4 — `threading.Lock` per Module, Not Shared

Each new module owns its own lock:

```python
# ai/price_cache.py
import threading

_lock = threading.Lock()
_cache: dict = {}

def get_price(product_id: str) -> float | None:
    with _lock:
        return _cache.get(product_id)

def set_price(product_id: str, price: float) -> None:
    with _lock:
        _cache[product_id] = price
```

**Critical:** Never use `asyncio.Lock` for state shared across threads. The bot has an asyncio event loop (PTB handlers) AND plain threads (Uvicorn API workers, background jobs). `asyncio.Lock` only works within a single event loop. `threading.Lock` works across both.

---

## Pattern 5 — Import Graph Discipline (prevent circular imports)

Target acyclic graph:

```
config ← db ← memoria (thin wrapper) ← services/
                                              ↑
                                          ai/ modules
                                              ↑
                                          handlers/
                                              ↑
                                          routers/
```

Rules:
- `services/` NEVER imports from `ai/`
- `ai/` submodules NEVER import from `services/`
- Both import from `config` and `db` only
- `memoria.py` imports from `services/` but services/ does NOT import from `memoria.py`

The existing risk (`ai → memoria → services → ai`) is prevented by keeping the graph acyclic through this rule.

---

## Pattern 6 — Re-export Hub in `comandos.py` (frozen main.py)

`main.py` is frozen — it imports handlers from `handlers/comandos.py`. When splitting into `cmd_*.py` files, `comandos.py` becomes the re-export hub:

```python
# handlers/comandos.py (post-Tarea F)
# Re-export all handlers so main.py doesn't change

from .cmd_ventas import (
    cmd_ventas, cmd_ultima_venta, cmd_corregir_venta
)
from .cmd_inventario import (
    cmd_inventario, cmd_agregar_producto, cmd_precio
)
from .cmd_clientes import (
    cmd_clientes, cmd_fiado, cmd_pagar_fiado
)
# ... all ~50 handlers

__all__ = [
    "cmd_ventas", "cmd_ultima_venta", "cmd_corregir_venta",
    "cmd_inventario", "cmd_agregar_producto", "cmd_precio",
    "cmd_clientes", "cmd_fiado", "cmd_pagar_fiado",
    # ... complete list
]
```

Never remove a name from `comandos.py` before the re-export line is in place. The order is: add re-export line → move function → verify → commit.

---

## Pattern 7 — pytest with Mocks for New Modules

```python
# tests/test_price_cache.py
import pytest
from unittest.mock import patch
from ai.price_cache import get_price, set_price, invalidate_cache

def test_set_and_get():
    set_price("tornillo-1/4", 150.0)
    assert get_price("tornillo-1/4") == 150.0

def test_miss_returns_none():
    assert get_price("producto-inexistente") is None

def test_thread_safe_concurrent_writes():
    import threading
    errors = []
    def write():
        try:
            for i in range(100):
                set_price(f"prod-{i}", float(i))
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=write) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
```

Legacy `test_suite.py` stays unchanged — it's a regression smoke test. New tests use pytest fixtures. Mock `db.query_all` with fixture data, never hit real DB in unit tests.

---

## Phase-by-phase safe migration sequence

| Phase | What changes | Verification |
|-------|-------------|-------------|
| 1 (A-E) | Create new modules, nothing imports them yet | `python -c "from middleware import protegido; print('OK')"` |
| 2 (F-H) | Wire new modules into existing handlers/ai.py | `python -c "import main; print('OK')"` |
| 3 (I) | Delete dead code from ai.py | Line count diff, full test suite |

Each phase leaves the bot running. Phase 1 is pure addition — zero risk. Risk increases in Phase 2 when re-wiring imports.

---

*Research confidence: High — based on direct codebase analysis, not generic advice*
