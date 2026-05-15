# Phase 1 Context — Infrastructure Creation

## Decisions

### Task A — middleware/

- **Fail-open** when `AUTHORIZED_CHAT_IDS` is empty or absent (allow all chats). This preserves current behavior and avoids breaking the bot the moment Task F deploys before the env var is configured in Railway.
- `@protegido` must use `functools.wraps` — PTB 21.3 inspects `handler.__name__` internally.
- `threading.Lock` for rate limiter state — never `asyncio.Lock`. The decorator runs inside PTB's async handlers but the rate limit dict is shared across threads (PTB uses a thread pool internally).
- The decorator must guard against `update.message` being `None` (callback queries don't have `.message`). Use `reply = update.message or (update.callback_query and update.callback_query.message)` before calling `reply_text`.
- Do NOT apply `@protegido` to any existing handler in this task — that happens in Task F.

### Task B — ai/price_cache.py

- Create the `ai/` directory with `ai/price_cache.py` ONLY. **Do NOT create `ai/__init__.py`** — if it exists, Python treats `ai/` as a package and shadows `ai.py`, breaking 6+ call sites immediately.
- Public API surface: `registrar()`, `get_activos()`, `invalidar()`, `limpiar_expirados()`. Match the names in the migration notes so Task I can do a mechanical find/replace.
- TTL default: 300 seconds (5 minutes) — same as current `_TIMEOUT_PENDIENTE` pattern in the codebase.
- The module must work standalone: no imports from `ai.py`, `memoria.py`, or any other project module.
- Mandatory verification after commit: `python -c "import ai; print(type(ai.procesar_con_claude))"` must print a function type, not NoneType or raise ImportError.

### Task C — migrations/

- Copy file contents verbatim — do NOT refactor internal code. Only add the `# Migrado desde migrate_XXXX.py` header comment and the `if __name__ == "__main__":` guard if missing.
- Keep original `migrate_*.py` files at root until all tasks confirm green — they are not deleted in Phase 1.
- Numbering: 001–007 matching the dependency order already specified in the roadmap (memoria → historico → ventas → gastos_caja → compras → fiados → proveedores).

### Task D — services/catalogo_service.py

- Copy functions verbatim from `memoria.py` — no signature changes, no logic improvements.
- `cargar_memoria()` calls inside the functions stay as-is for now. The service still depends on the cache layer. Decoupling from `cargar_memoria()` is out of scope for Phase 1.
- Allowed imports: `logging`, `re`, `rapidfuzz`, `db`, `config`, `utils`, `alias_manager`, `fuzzy_match`. Never import from `ai`, `handlers`, or `memoria`.
- This file is NOT wired into anything in Phase 1 — it just has to exist and import cleanly.

### Task E — services/inventario_service.py

- `descontar_inventario()` return contract is **hard**: must return exactly `(bool, str|None, float|None)`. `ventas_state.py` line 210 destructures this tuple — any change breaks sales flow silently.
- Same verbatim-copy rule as Task D. No refactoring.
- Allowed imports: `logging`, `db`, `config`, `utils`. Never import from `ai`, `handlers`, or `memoria`.
- This file is NOT wired into anything in Phase 1 — it just has to exist and import cleanly.

---

## Style Preferences

- Import grouping headers in every new file:
  ```python
  # -- stdlib --
  # -- terceros --
  # -- propios --
  ```
- Logger naming: `logging.getLogger("ferrebot.<module>")` — e.g. `ferrebot.middleware.auth`, `ferrebot.price_cache`, `ferrebot.services.catalogo`
- Docstrings in Spanish for all public functions
- `except Exception as e:` is intentional — stability over strictness (matches existing codebase pattern)
- Type hints using modern syntax: `dict[str, int]` not `Dict[str, int]`, `str | None` not `Optional[str]`

---

## Out of Scope for Phase 1

- Do not wire new modules into existing code — that is Phase 2
- Do not delete or modify `ai.py`, `memoria.py`, `handlers/comandos.py`
- Do not touch `db.py`, `config.py`, `main.py` under any circumstances
- Do not apply `@protegido` to handlers — that is Task F
- Do not create `ai/__init__.py` — that is Task I
- Do not convert `memoria.py` to thin wrapper — that is Task H

---

## Commit Messages (exact, one per task)

- Task A: `feat: add middleware auth + rate_limit (Tarea A)`
- Task B: `feat: add ai/price_cache thread-safe (Tarea B)`
- Task C: `feat: organize migrations/ directory (Tarea C)`
- Task D: `feat: add services/catalogo_service (Tarea D)`
- Task E: `feat: add services/inventario_service (Tarea E)`
