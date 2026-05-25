# Pitfalls Research: FerreBot Refactoring

**Date:** 2026-03-28
**Domain:** Python 3.11 bot refactoring — specific to this codebase

---

## Critical Pitfalls (silent failures)

### 1. Circular import via module-level state (silent `None` attributes)

`ai.py` imports 15+ things from `memoria.py` at the module level. If a new `services/` module creates an import triangle (`ai → memoria → services → ai`), Python returns a **partial module object** with no `ImportError`. Attributes that weren't defined yet at import time come back as `None`. This fails silently at call time, not at import time.

**Detection:** `python -c "import ai; print(type(ai.procesar_con_claude))"` — if it prints `<class 'NoneType'>`, you have a circular import.

**Mitigation:** `services/` must never import from `ai.py` or `memoria.py`. Verify with `grep -r "from ai import\|from memoria import" services/ --include="*.py"` — must return zero results.

---

### 2. `asyncio.Lock` created outside its event loop

`ventas_state.get_chat_lock()` returns asyncio locks. The daemon thread in `start.py` that launches Uvicorn runs before the final PTB event loop is created. Any new module that instantiates `asyncio.Lock()` at module level (not inside an `async def`) will bind to the wrong event loop.

**Detection:** `RuntimeError: no running event loop` — but only at runtime, not at import.

**Mitigation:** Use `threading.Lock` for all state shared between threads. Only use `asyncio.Lock` inside `async def` handlers, and only for state that never crosses thread boundaries.

---

### 3. `threading.Lock` + `await` deadlock

```python
# WRONG — deadlock waiting to happen:
with _estado_lock:
    await update.message.reply_text("...")  # releases GIL, suspends coroutine
    # lock is still held while coroutine is suspended
    # another coroutine trying to acquire _estado_lock hangs forever
```

Task F splits `handlers/comandos.py` into `cmd_*.py` files. If any developer adds a `with lock:` block wrapping an `await`, the bot deadlocks silently (no error, just stops responding).

**Detection:** Code review only — no runtime warning.

**Mitigation:** Rule: `with threading.Lock():` blocks must contain only synchronous code. Release the lock before any `await`.

---

### 4. Thin wrapper signature drift (Task H — highest risk)

`memoria.py` has ~151 callers. If any function in `services/` has a different parameter order or default value than the original in `memoria.py`, callers pass wrong values with no exception raised.

```python
# Original in memoria.py:
def registrar_movimiento_caja(monto, tipo, descripcion=None): ...

# Service with silently changed signature:
def registrar_movimiento_caja(tipo, monto, descripcion=None): ...
# Caller: registrar_movimiento_caja(500, "ingreso") → monto="ingreso", tipo=500
```

**Detection:** Diff every function signature between original `memoria.py` and the new service. Script: `grep -n "^def " memoria.py > /tmp/before.txt && grep -n "^def " services/caja_service.py > /tmp/after.txt && diff /tmp/before.txt /tmp/after.txt`

**Mitigation:** Copy function signatures verbatim. No "improvements" to parameter order during refactoring.

---

### 5. psycopg2 pool connection leak (existing, don't make worse)

`db.py` has a reconnect path that can double-`putconn` a connection, silently exhausting the 10-connection pool. The bot then hangs waiting for a connection that never comes. New service modules must follow the `with db.get_connection() as conn:` pattern strictly — never manually call `putconn`.

**Detection:** Bot stops responding to all commands simultaneously (pool exhausted). `SELECT count(*) FROM pg_stat_activity;` on Railway DB shows 10 connections all idle.

**Mitigation:** Services must use exactly the pattern established in existing routers. Never open a connection without guaranteeing it's returned.

---

## Moderate Pitfalls

### 6. `ai/` directory shadows `ai.py` (Task B + Task I ordering)

If Task B creates an `ai/` **package** (directory with `__init__.py`) while `ai.py` still exists, Python's import resolution picks the **package** over the module on most systems. `from ai import procesar_con_claude` breaks immediately for all 5+ call sites.

**The safe sequence for Task B:**
```bash
mkdir ai  # directory only, NO __init__.py yet
touch ai/price_cache.py  # standalone module
# ai.py still exists and imports normally
# ai/price_cache.py is only imported via "from ai.price_cache import ..."
```

Do NOT create `ai/__init__.py` until Task I. The `ai/` directory can coexist with `ai.py` as long as `ai/__init__.py` doesn't exist (Python will choose `ai.py`).

**Verification after Task B:** `python -c "from ai import procesar_con_claude; print('ai.py still wins')"` must succeed.

---

### 7. `@protegido` without `functools.wraps`

PTB 21 inspects handler function names for its internal dispatcher and error logging. Without `functools.wraps`, all handlers appear as `"wrapper"` in error reports, making debugging nearly impossible.

**Detection:** After deploying Task A+F, check bot logs for error source — if it says `wrapper` instead of the handler name, `functools.wraps` is missing.

**Mitigation:** Always include `@functools.wraps(func)` inside `protegido`. Template in STACK.md.

---

### 8. FastAPI daemon thread crashes silently

`start.py` launches Uvicorn as a daemon thread. If the API crashes (unhandled exception in a router), the daemon thread dies but the bot thread keeps running. Railway health check passes (bot is alive), but the dashboard breaks. There's no alert.

**Mitigation:** New routers must have `try/except Exception` at the route handler level (matching existing router pattern). Don't let exceptions bubble up to the Uvicorn thread.

---

### 9. Cache dict reference race (Task D/E)

If `catalogo_service.get_catalogo()` returns the internal dict directly (not a copy), concurrent threads can corrupt iteration:

```python
# Thread 1: for p in _catalogo.values():  ← iterating
# Thread 2: _catalogo["nuevo"] = {...}     ← modifying during iteration
# Result: RuntimeError: dictionary changed size during iteration
```

**Mitigation:** Cache getters return `dict(self._cache)` (shallow copy) or use `threading.Lock` around all reads AND writes.

---

### 10. `AUTHORIZED_CHAT_IDS` not set → fail-closed

If `@protegido` is fail-closed (rejects all when env var is missing) and `AUTHORIZED_CHAT_IDS` isn't set in Railway, the entire bot stops responding the moment Task F deploys.

**Mitigation:** Fail-open when env var is absent (empty string = allow all). Log a warning at startup: `logger.warning("AUTHORIZED_CHAT_IDS not set — all chats allowed")`.

---

## Minor Pitfalls

### 11. Migration scripts without `__name__ == "__main__"` guard

Any `migrate_*.py` that runs code at module level will execute when imported (e.g., during a test that does `import migrations`).

**Mitigation:** Wrap all executable code in `if __name__ == "__main__":`.

### 12. `asyncio.get_event_loop()` is deprecated in Python 3.10+

New code in `ai/` or `handlers/` that calls `asyncio.get_event_loop()` raises `DeprecationWarning` in Python 3.10+ and `RuntimeError` in 3.12+. Use `asyncio.get_running_loop()` inside async context.

### 13. Skills directory path assumption

`skill_loader.py` likely uses a relative path to `skills/`. If any new module changes the working directory (e.g., a migration script does `os.chdir()`), skill loading breaks silently.

**Mitigation:** No `os.chdir()` in any new module.

---

## Verification Checklist (run before every commit)

```bash
# 1. Basic import check
python -c "import main; print('main OK')"

# 2. New module imports
python -c "from <new_module> import *; print('imports OK')"

# 3. No circular imports
python -c "import ai; import memoria; import handlers.comandos; print('no circular')"

# 4. Thread safety (Task B specifically)
python -m pytest tests/test_price_cache.py -v -k "thread"

# 5. Pool not exhausted
python -c "from db import get_connection; c = get_connection(); c.close(); print('pool OK')"

# 6. Run tests (excluding legacy suite)
python -m pytest tests/ -v --ignore=test_suite.py
```

---

*Confidence: High — 14 pitfalls identified from direct codebase inspection with exact line references*
