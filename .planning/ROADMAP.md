# Roadmap: FerreBot Refactorización Modular

## Overview

FerreBot is a live Telegram bot + FastAPI in production on Railway. This roadmap covers a pure structural refactoring: two monolithic files (`ai.py` at 2685 lines, `handlers/comandos.py` at ~2200 lines) and one over-loaded module (`memoria.py`) are decomposed into focused modules while the bot stays operational on every single commit. No functional changes. No stack changes. The task structure is authoritative from CLAUDE.md (Tasks A–J). The refactoring proceeds in three sequential phases plus one parallel test track, with Phase 1 tasks fully independent of each other.

---

## Phases

- [x] **Phase 1: Infrastructure Creation** - Create all new modules additively — nothing existing imports them yet (Tasks A, B, C, D, E — fully parallel)
- [ ] **Phase 2: Wiring** - Integrate new modules into existing code: auth-gate handlers, extract prompts/Excel, thin-wrap memoria.py (Tasks F, G, H)
- [x] **Phase 3: Reduction** - Shrink ai.py from 2685 to ~800 lines and rename to ai/__init__.py (Task I) (completed 2026-03-29)
- [ ] **Phase 4: Tests** - Unit tests for every new module; runs in parallel alongside all phases (Task J)

---

## Phase Details

### Phase 1: Infrastructure Creation
**Goal**: Every new module (middleware/, ai/price_cache.py, migrations/, services/catalogo_service.py, services/inventario_service.py) exists on disk, imports cleanly, and fixes the active race condition — without touching any existing file that already works.
**Depends on**: Nothing (first phase)
**Requirements**: MW-01, MW-02, MW-03, MW-04, MW-05, PC-01, PC-02, PC-03, PC-04, PC-05, MIG-01, MIG-02, MIG-03, CAT-01, CAT-02, CAT-03, CAT-04, INV-01, INV-02, INV-03, INV-04
**Success Criteria** (what must be TRUE):
  1. `from middleware import protegido` resolves without error and `@protegido` wraps an async function without losing its `__name__`
  2. `from ai.price_cache import get_price, set_price, invalidate_cache` works; concurrent writes from two threads produce no RuntimeError (race condition on `_precios_recientes` is eliminated)
  3. All `migrate_*.py` scripts live under `migrations/` and none executes code at import time
  4. `from services.catalogo_service import *` and `from services.inventario_service import *` both resolve; neither module imports from `ai`, `handlers`, or `memoria`
  5. `python main.py` starts without errors after every individual task commit

**Plans**: 5 plans

Plans:
- [x] 01-01: Task A — `middleware/` auth + rate limiting (`@protegido` decorator, `AUTHORIZED_CHAT_IDS` env var, fail-open for empty list)
- [x] 01-02: Task B — `ai/price_cache.py` thread-safe cache (PRIORITY: fixes active production race condition; creates `ai/` directory WITHOUT `ai/__init__.py`)
- [x] 01-03: Task C — `migrations/` directory (move all `migrate_*.py`, add `__init__.py`, add `if __name__ == "__main__"` guards)
- [x] 01-04: Task D — `services/catalogo_service.py` (extract catalog CRUD from `memoria.py`, identical signatures, imports only `config` + `db`)
- [x] 01-05: Task E — `services/inventario_service.py` (extract inventory logic; preserve `descontar_inventario()` return contract `(bool, str|None, float|None)`)

> **RISK — Task B (race condition fix):** `ai/price_cache.py` must be created inside a new `ai/` directory but WITHOUT `ai/__init__.py`. If `ai/__init__.py` is created here, Python will shadow `ai.py` and all 5+ callers of `from ai import procesar_con_claude` will break immediately. Verify after commit: `python -c "import ai; print(type(ai.procesar_con_claude))"`.

> **RISK — Task E (return contract):** `descontar_inventario()` must return exactly `(bool, str|None, float|None)`. `ventas_state.py` line 210 destructures this tuple. Any signature change breaks the sales flow silently.

---

### Phase 2: Wiring
**Goal**: The new infrastructure from Phase 1 is integrated into the running bot: all 50+ command handlers are split into themed files and auth-gated with `@protegido`, prompt-building and Excel generation are extracted from `ai.py`, and `memoria.py` becomes a thin wrapper delegating to services/ — while `main.py` and all callers remain completely unchanged.
**Depends on**: Phase 1 complete
**Requirements**: HDL-01, HDL-02, HDL-03, HDL-04, HDL-05, PRM-01, PRM-02, PRM-03, PRM-04, CAJA-01, CAJA-02, CAJA-03, CAJA-04, CAJA-05
**Success Criteria** (what must be TRUE):
  1. `from handlers.comandos import <any_original_handler_name>` still resolves for all ~50 handlers — `main.py` requires zero changes
  2. Every handler in `cmd_*.py` files is decorated with `@protegido`; no `threading.Lock` block contains an `await` in any `cmd_*.py`
  3. `from ai.prompts import *` and `from ai.excel_gen import *` resolve; prompt functions are pure (no db calls); excel_gen imports only `openpyxl` + `config`
  4. `from memoria import *` exports the same ~151 public names as before; `python -c "from memoria import *; print(len([x for x in dir() if not x.startswith('_')]))"` matches the pre-task baseline count
  5. `python main.py` starts without errors after every individual task commit

**Plans**: 3 plans

Plans:
- [x] 02-01: Task F — `handlers/cmd_*.py` split + `@protegido` (split comandos.py into cmd_ventas, cmd_inventario, cmd_clientes, cmd_caja, cmd_admin; convert comandos.py to re-export hub; depends on Task A)
- [x] 02-02: Task G — `ai/prompts.py` + `ai/excel_gen.py` (extract from ai.py; pure functions only; no `ai/__init__.py` yet; depends on Task B)
- [ ] 02-03: Task H — `services/caja_service.py` + `services/fiados_service.py` + thin wrapper `memoria.py` (depends on Tasks D+E; highest breakage risk)

> **RISK — Task F (handler split):** Move handlers in logical groups, one commit per group. Never remove a function from `comandos.py` before the re-export line for that function is already in place and verified. Pre-task: map all ~50 command names to their target `cmd_*.py` file before writing code.

> **RISK — Task H (thin wrapper — HIGHEST RISK in entire refactoring):** Before starting, run `grep -r "from memoria import\|import memoria" . --include="*.py"` and enumerate every symbol. A single missing name in `__all__` is a silent `ImportError` in production. `services/` must never import from `memoria.py` (circular import). Verify symbol count matches original after commit.

---

### Phase 3: Reduction
**Goal**: `ai.py` shrinks from 2685 lines to ~800 by removing code that now lives in `ai/price_cache.py`, `ai/prompts.py`, and `ai/excel_gen.py`, then is renamed to `ai/__init__.py` — making `ai/` a proper package while all existing `from ai import ...` call sites continue working without any changes.
**Depends on**: Phase 2 complete (specifically Tasks B and G must be merged and stable)
**Requirements**: AI-01, AI-02, AI-03
**Success Criteria** (what must be TRUE):
  1. `ai.py` no longer exists at the repo root; `ai/__init__.py` exists in its place
  2. `python -c "from ai import procesar_con_claude, procesar_acciones; print('OK')"` passes for all 5+ original callers
  3. `ai/__init__.py` is approximately 800 lines (down from 2685); the deleted code is confirmed to exist in `ai/price_cache.py`, `ai/prompts.py`, or `ai/excel_gen.py`
  4. `python main.py` starts without errors after the single task commit

**Plans**: 1 plan

Plans:
- [x] 03-01: Task I — clean `ai.py` and rename to `ai/__init__.py` (remove extracted code; atomic `mv ai.py ai/__init__.py`; verify all callers)

> **RISK — Task I (naming collision — HIGH RISK):** `mv ai.py ai/__init__.py` is an atomic operation. Python cannot have both `ai.py` and `ai/__init__.py` — the rename must happen in a single commit with no intermediate broken state. Immediately after: `python -c "from ai import procesar_con_claude, procesar_acciones; print('OK')"`. Never delete `ai.py` in one commit and create `ai/__init__.py` in a separate commit.

---

### Phase 4: Tests
**Goal**: Every new module created in Phases 1-3 has a corresponding unit test file that runs without real database or Telegram credentials — providing a regression guard that runs in CI alongside the existing `test_suite.py`.
**Depends on**: Runs in parallel alongside Phases 1, 2, and 3 (each test file added after its target module is committed)
**Requirements**: TST-01, TST-02, TST-03, TST-04, TST-05, TST-06
**Success Criteria** (what must be TRUE):
  1. `python -m pytest tests/ -v --ignore=test_suite.py` passes green with zero failures
  2. `test_suite.py` is unmodified and continues passing
  3. No test requires `TELEGRAM_TOKEN` or `DATABASE_URL` to be set in the environment
  4. Thread-safety test for `price_cache.py` exercises concurrent reads and writes from multiple threads

**Plans**: 3 plans

Plans:
- [x] 04-01: Task J (Phase 1 modules) — `tests/test_price_cache.py` (thread-safety, concurrent reads/writes) + `tests/test_middleware.py` (decorator behavior, fail-open, functools.wraps)
- [ ] 04-02: Task J (Phase 1 services) — `tests/test_catalogo_service.py` + `tests/test_inventario_service.py` (mock `db.query_*`; verify return contracts)
- [ ] 04-03: Task J (Phase 2 services) — `tests/test_caja_service.py` + `tests/test_fiados_service.py` (mock db; verify thin wrapper symbol count)

---

## Progress

**Execution Order:**
Phases execute in order: 1 → 2 → 3. Phase 4 (tests) runs in parallel with each phase as modules are created.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure Creation | 0/5 | Not started | - |
| 2. Wiring | 1/3 | In Progress|  |
| 3. Reduction | 1/1 | Complete   | 2026-03-29 |
| 4. Tests | 1/3 | In Progress|  |

---

## Requirement Coverage

| Requirement Group | Requirements | Phase |
|-------------------|-------------|-------|
| Middleware (Task A) | MW-01, MW-02, MW-03, MW-04, MW-05 | Phase 1 |
| PriceCache (Task B) | PC-01, PC-02, PC-03, PC-04, PC-05 | Phase 1 |
| Migrations (Task C) | MIG-01, MIG-02, MIG-03 | Phase 1 |
| CatalogoService (Task D) | CAT-01, CAT-02, CAT-03, CAT-04 | Phase 1 |
| InventarioService (Task E) | INV-01, INV-02, INV-03, INV-04 | Phase 1 |
| HandlersModulares (Task F) | HDL-01, HDL-02, HDL-03, HDL-04, HDL-05 | Phase 2 |
| AIPrompts (Task G) | PRM-01, PRM-02, PRM-03, PRM-04 | Phase 2 |
| ServiciosCajaFiados (Task H) | CAJA-01, CAJA-02, CAJA-03, CAJA-04, CAJA-05 | Phase 2 |
| AILimpio (Task I) | AI-01, AI-02, AI-03 | Phase 3 |
| Tests (Task J) | TST-01, TST-02, TST-03, TST-04, TST-05, TST-06 | Phase 4 |

**v1 requirements mapped: 38/38 — no orphans**

---

*Roadmap created: 2026-03-28*
*Granularity: standard*
*Mode: yolo*
