# Project Research Summary

**Project:** FerreBot — Refactorización Modular
**Domain:** Incremental structural refactoring of a live Python 3.11 Telegram bot + FastAPI
**Researched:** 2026-03-28
**Confidence:** HIGH

## Executive Summary

FerreBot's refactoring is a pure structural decomposition — no new functionality, no stack changes. Two monolithic files (`ai.py` at 2685 lines, `handlers/comandos.py` at ~2200 lines) and one over-loaded module (`memoria.py`) are split into focused modules while the bot remains deployed and operational on every commit. The entire refactoring uses stdlib and existing dependencies; no new libraries are introduced.

The recommended approach is strictly additive-first: Phase 1 (Tasks A-E) only creates new modules that nothing imports yet, so breakage risk is near zero. Phase 2 (Tasks F-H) wires them in, and Phase 3 (Task I) removes dead code from `ai.py`. The most dangerous single operation in the entire plan is Task H (thin-wrapping `memoria.py` with ~151 public names) and Task I (renaming `ai.py` to `ai/__init__.py`). Both have clear mitigation strategies.

The active production risk that cannot wait is in Task B: a race condition on the `_precios_recientes` dict in `ai.py` (lines 35-48) is being hit from concurrent threads today. Task B is the highest-priority fix in Phase 1, even though it carries no external breakage risk.

---

## Key Findings

### Stack (no changes required)

No new libraries. The refactoring uses Python 3.11's package system, `functools.wraps`, `threading.Lock`, and pytest — all already present.

**Critical patterns:**
- `functools.wraps` on every decorator — PTB 21 inspects `__name__`/`__qualname__` for error reporting; omitting it makes all handlers appear as `"wrapper"` in logs.
- `threading.Lock` (not `asyncio.Lock`) for all shared state — Uvicorn workers and PTB handlers run in separate threads; `asyncio.Lock` only works within one event loop.
- Package-with-`__init__` for every new directory — re-export explicitly in `__init__.py`, no wildcard exports.
- Acyclic import graph: `config → db → services/ → ai/ → handlers/` — services never import from ai/, ai/ never imports from handlers/.

### Per-Task Table Stakes

| Task | Must work after commit |
|------|----------------------|
| A | `from middleware import protegido` works; empty `AUTHORIZED_CHAT_IDS` allows all (fail-open) |
| B | `threading.Lock` guards cache dict; `ai.py` still importable (no `ai/__init__.py` yet) |
| C | `migrations/__init__.py` added; migrate scripts have `if __name__ == "__main__"` guard |
| D | `services/catalogo_service.py` importable; never imports from `ai/` or `handlers/` |
| E | `descontar_inventario()` returns same `(bool, str|None, float|None)` tuple — `ventas_state.py:210` depends on this |
| F | `handlers/comandos.py` is pure re-export hub; `main.py` unchanged; every handler wrapped with `@protegido` |
| G | `ai/prompts.py` are pure functions (no db calls); `ai/__init__.py` does NOT exist yet |
| H | `memoria.py` thin wrapper re-exports all ~151 names; `python -c "from memoria import *"` count matches original |
| I | `ai.py` renamed to `ai/__init__.py`; `from ai import procesar_con_claude` still works for all 5+ callers |
| J | Tests mock `db.query_*`; never require `TELEGRAM_TOKEN` or `DATABASE_URL`; `test_suite.py` untouched |

### Architecture: Target Module Layers

```
Layer 0: config, threading, stdlib
Layer 1: db
Layer 2: services/, middleware/, ai/price_cache, ai/prompts
Layer 3: ai/__init__ (full), memoria (thin wrapper)
Layer 4: handlers/, routers/, ventas_state
Layer 5: main, start, api
```

Rule: never import from a higher layer. `memoria.py` imports from `services/`, but `services/` never imports from `memoria.py`.

**Key structural insight:** Task B must create `ai/` as a directory with `ai/price_cache.py` but without `ai/__init__.py`. Python prefers the package over `ai.py` when `__init__.py` exists — creating it before Task I breaks all `from ai import ...` call sites immediately.

### Critical Pitfalls (Top 5)

1. **Silent circular import via partial module object** — `services/` importing from `ai/` or `memoria.py` returns `None` attributes at call time with no `ImportError`. Detection: `python -c "import ai; print(type(ai.procesar_con_claude))"`. Prevention: `grep -r "from ai import\|from memoria import" services/` must return zero results.

2. **`ai/__init__.py` created before Task I** — if Task B creates `ai/__init__.py`, Python picks the package over `ai.py` and all 5+ callers of `from ai import procesar_con_claude` break immediately. Task B creates only `ai/price_cache.py`, no `__init__.py`.

3. **Thin wrapper missing even one symbol (Task H)** — 18+ files import from `memoria.py`; a missing name is a silent `ImportError` in production. Pre-task audit: `grep -r "from memoria import\|import memoria" . --include="*.py"` — every symbol must be enumerated in `__all__`.

4. **Function signature drift in services/ (Task H)** — parameter order changes in `caja_service` or `fiados_service` pass wrong values with no exception. Copy signatures verbatim from original `memoria.py`; no "cleanup" improvements during refactoring.

5. **`threading.Lock` + `await` deadlock (Task F)** — holding a `threading.Lock` while calling `await` inside a handler leaves the lock held during coroutine suspension. Rule: release lock before any `await`. No runtime warning; code review only.

---

## Implications for Roadmap

### Phase 1: Infrastructure Creation (Tasks A, B, C, D, E — parallel)

**Rationale:** Additive only — nothing existing imports these modules yet. All 5 tasks are independent of each other.
**Delivers:** `middleware/`, `ai/price_cache.py`, `migrations/`, `services/catalogo_service.py`, `services/inventario_service.py`
**Priority within phase:** B first (fixes active production race condition); others in any order.
**Avoids:** No wiring = no breakage. Verification per task: `python -c "from <new_module> import *; print('OK')"`.

### Phase 2: Wiring (Tasks F, G, H — sequential by dependency)

**Rationale:** Each task in this phase modifies existing import structure. Must follow dependency order: F after A, G after B, H after D+E.
**Delivers:** Auth-gated command handlers, extracted prompts/Excel, thin-wrapped `memoria.py`.
**Highest risk:** Task H — run pre-audit script before starting; verify symbol count after.
**Avoids pitfalls:** One handler group per commit in Task F (not all 50 at once); copy signatures verbatim in Task H.

### Phase 3: Reduction (Task I — only after B+G complete)

**Rationale:** `ai.py` can only shrink after both `price_cache.py` and `prompts.py`/`excel_gen.py` are wired in and proven stable.
**Delivers:** `ai.py` → `ai/__init__.py`, reduced from 2685 to ~800 lines.
**Critical step:** `mv ai.py ai/__init__.py` — one atomic operation; verify with `from ai import procesar_con_claude, procesar_acciones` immediately after.
**Avoids:** Never delete `ai.py` before `ai/__init__.py` exists in its place.

### Parallel: Tests (Task J — runs alongside every phase)

Each new module gets its test file before Phase 2 wires it in. Thread-safety test for Task B is mandatory before Task G touches `ai/`.

### Research Flags

Standard patterns (no additional research needed):
- Phase 1 (A-E): Pure module creation, well-understood Python packaging patterns.
- Phase 3 (I): Single rename operation, deterministic.

Needs careful validation during execution:
- **Task H:** Symbol audit must be done manually before starting — no tooling can automate the full `memoria.py` public API enumeration reliably.
- **Task F:** Requires mapping all 50+ handlers to thematic files before writing code — grouping decision has no obvious single right answer.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Direct codebase inspection; no guesswork about deps |
| Features | HIGH | TAREA-*.md specs are authoritative; table stakes derived from actual code |
| Architecture | HIGH | Import graph traced from actual files; collision risk verified |
| Pitfalls | HIGH | Race condition confirmed with line references; signature contract verified |

**Overall confidence:** HIGH

### Gaps to Address

- **Exact symbol count in `memoria.py`:** Must be audited at Task H start — ARCHITECTURE.md estimates ~151 but the real number determines wrapper completeness.
- **Handler grouping for Task F:** The 5-file split (`cmd_ventas`, `cmd_inventario`, `cmd_clientes`, `cmd_caja`, `cmd_admin`) is a suggested minimum; actual grouping should be confirmed against the ~50 command names in `handlers/comandos.py` before starting Task F.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection — `ai.py`, `memoria.py`, `handlers/comandos.py`, `ventas_state.py`, `db.py`, `start.py`
- `_obsidian/01-Proyecto/TAREA-A.md` through `TAREA-J.md` — authoritative task specifications
- `CLAUDE.md` — project constraints and absolute rules

---
*Research completed: 2026-03-28*
*Ready for roadmap: yes*
