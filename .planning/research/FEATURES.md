# Features Research: Refactoring Patterns per Task

**Date:** 2026-03-28
**Domain:** FerreBot — per-task feature requirements and anti-patterns

---

## Critical Path

```
B → G → I   (longest dependency chain — highest production risk)
A → F       (auth must exist before handlers use @protegido)
D+E → H     (services must exist before memoria.py thin wrapper)
```

Task J (tests) runs in parallel with every task.

---

## Task A — middleware/ (auth + rate limiting)

### Table Stakes (must have)
- `@protegido` async decorator that checks `AUTHORIZED_CHAT_IDS` env var
- Empty `AUTHORIZED_CHAT_IDS` = allow all (dev mode, no breaking change)
- `functools.wraps` — PTB inspects `__name__` for debug logging
- `middleware/__init__.py` re-exports `protegido` so callers use `from middleware import protegido`

### Improvements
- Rate limiter (calls per minute per chat_id) — configurable via env var
- Admin bypass flag for `ADMIN_CHAT_ID`

### Anti-patterns
- Reading `AUTHORIZED_CHAT_IDS` at module import time (breaks tests that set env vars after import)
- Using `asyncio.Lock` for rate limiter state (Uvicorn workers run in threads)
- Blocking the event loop with synchronous checks

---

## Task B — ai/price_cache.py (thread-safe price cache)

### Table Stakes (CRITICAL — fixes active race condition)
- `threading.Lock` protecting the cache dict
- Cache is a plain `dict[str, float]` in memory
- `get_price(product_id)` → `float | None`
- `set_price(product_id, price)` — atomic write
- `invalidate_cache()` — clears all entries (called when catalog updates)

### Improvements
- TTL per entry (cache staleness protection)
- Hit/miss counters for observability

### Anti-patterns
- **Using asyncio.Lock** — bot has both event loop thread AND Uvicorn worker threads
- Calling `db.query_*` from within a locked section (deadlock risk)
- Sharing a single lock with other modules (use module-local lock)

**Note:** TAREA-B.md documents an active production race condition in `ai.py` lines 35-48 where `_precios_recientes` dict is modified from multiple threads. This is the highest-priority fix in Phase 1.

---

## Task C — migrations/ directory

### Table Stakes
- Move all `migrate_*.py` scripts to `migrations/` directory
- Add `migrations/__init__.py` (empty)
- Update any references to these scripts (check Procfile, start.py, any imports)

### Anti-patterns
- Deleting migration scripts (history is valuable)
- Running migrations automatically on import (side effects at module level)

---

## Task D — services/catalogo_service.py

### Table Stakes
- Extract catalog CRUD from `memoria.py` into dedicated service
- All functions that currently live in `memoria.py` under catalog domain
- Import from `db` directly (not via `memoria`)
- `logger = logging.getLogger("ferrebot.services.catalogo")`

### Improvements
- Add docstrings explaining business rules (e.g., what "activo" flag means)

### Anti-patterns
- Importing from `ai.py` or `handlers/` (layer violation)
- Duplicating the ThreadedConnectionPool setup (use `db.get_connection()`)

---

## Task E — services/inventario_service.py

### Table Stakes
- Extract inventory logic from `memoria.py`
- **Preserve the `descontar_inventario()` return contract:** `(bool, str|None, float|None)` — `ventas_state.py` line 210 destructures this tuple; changing the contract breaks sales flow
- Thread-safe writes (inventory can be decremented from concurrent sales)

### Anti-patterns
- Changing the return type of `descontar_inventario` — contractual
- Forgetting to handle negative inventory edge case (already handled in original — preserve it)

---

## Task F — handlers/cmd_*.py + @protegido

### Table Stakes
- Split `handlers/comandos.py` (~2200 lines) into themed files: `cmd_ventas`, `cmd_inventario`, `cmd_clientes`, `cmd_caja`, `cmd_admin` (minimum — adjust to actual command groups)
- Every command handler wrapped with `@protegido` from `middleware`
- `handlers/comandos.py` becomes pure re-export hub — `main.py` unchanged
- `from middleware import protegido` import path is contractual (specified in TAREA-F.md)

### Anti-patterns
- Moving ALL ~50 handlers in one commit — split into logical groups, one commit per group
- Forgetting to add re-export line to `comandos.py` before removing function
- Using `@protegido` on non-async functions (all PTB handlers are async)

---

## Task G — ai/prompts.py + ai/excel_gen.py

### Table Stakes
- Extract prompt construction functions from `ai.py` into `ai/prompts.py`
- Extract Excel generation from `ai.py` into `ai/excel_gen.py`
- `ai/prompts.py` — pure functions, no side effects, no db calls
- `ai/excel_gen.py` — imports openpyxl + config only

### Anti-patterns
- Prompts calling `db` directly (prompts should receive data as parameters)
- Excel generator importing from `handlers/` (layer violation)

---

## Task H — caja_service + fiados_service + thin wrapper memoria.py

### Table Stakes (HIGHEST BREAKAGE RISK in entire refactoring)
- `services/caja_service.py` — extract caja logic
- `services/fiados_service.py` — extract fiados logic
- `memoria.py` → thin wrapper re-exporting all ~151 public names
- Pre-task audit: `grep -r "from memoria import\|import memoria" . --include="*.py"` — every symbol must be in the wrapper's `__all__`

### Anti-patterns
- Missing even ONE symbol from `memoria.py`'s `__all__` — silent `ImportError` in production
- Doing this before D+E are complete (services must exist first)
- Importing `memoria` from within `services/` (circular import)

---

## Task I — Clean ai.py (2685 → ~800 lines)

### Table Stakes
- Remove code that now lives in `ai/price_cache.py`, `ai/prompts.py`, `ai/excel_gen.py`
- Rename `ai.py` → `ai/__init__.py` to create the `ai/` package
- All existing `from ai import procesar_con_claude` call sites continue working unchanged
- Must not start until B AND G are both complete (TAREA-I.md explicit warning)

### Anti-patterns
- Starting before B+G are merged (will break ai.py imports)
- Deleting `ai.py` without creating `ai/__init__.py` (breaks all callers immediately)
- Trying to do `ai/` package AND reduction in separate commits without intermediate working state

---

## Task J — tests/

### Table Stakes
- One test file per new module: `tests/test_price_cache.py`, `tests/test_middleware.py`, etc.
- Test thread safety for Task B (concurrent reads/writes)
- Mock `db.query_*` — never hit real DB in unit tests
- `python -m pytest tests/ -v --ignore=test_suite.py` must pass

### Anti-patterns
- Modifying `test_suite.py` — it's the legacy regression guard
- Tests that require `TELEGRAM_TOKEN` or `DATABASE_URL` to be set
- Testing `main.py` (frozen file, already integration-tested by the bot itself)

---

## Coverage Summary

| Task | Risk | Phase | Depends on |
|------|------|-------|-----------|
| A | Low | 1 | — |
| B | Low (but fixes active bug) | 1 | — |
| C | Very Low | 1 | — |
| D | Low | 1 | — |
| E | Medium (return contract) | 1 | — |
| F | Medium | 2 | A |
| G | Medium | 2 | B |
| H | High (151 symbols) | 2 | D+E |
| I | High (naming collision) | 3 | B+G |
| J | Low | Parallel | per-module |

---

*Confidence: High — findings derived from TAREA-*.md specs and direct codebase inspection*
