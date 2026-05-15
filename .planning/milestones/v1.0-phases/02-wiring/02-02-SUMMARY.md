---
phase: 02-wiring
plan: 02
subsystem: ai
tags: [python, claude-ai, refactoring, prompts, excel]

# Dependency graph
requires:
  - phase: 01-infrastructure-creation
    provides: ai/price_cache.py (namespace package), middleware, services
provides:
  - ai/prompts.py with all prompt-building functions extracted from ai.py
  - ai/excel_gen.py with Excel generation functions extracted from ai.py
affects: [ai, prompt-building, excel-generation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive extraction — ai.py kept byte-identical, new modules are forward-only copies"
    - "Lazy imports inside function bodies to avoid circular dependencies between ai.py and ai/prompts.py"
    - "Namespace package pattern — ai/ directory with no __init__.py coexists with ai.py"

key-files:
  created:
    - ai/prompts.py
    - ai/excel_gen.py
  modified: []

key-decisions:
  - "Lazy imports for _pg_* helpers and memoria functions inside _construir_parte_dinamica body — avoids circular import since ai/prompts.py would need to import from ai.py which imports everything at module level"
  - "No ai/__init__.py created — would shadow ai.py and break all existing from ai import procesar_con_claude call sites"
  - "ai.py kept byte-identical — deletions happen only in Phase 3 Task I after all extractions are verified"

patterns-established:
  - "Functions extracted as copies — ai.py original code is the source of truth until Phase 3"
  - "Pure prompt construction (no db at module level) per PRM-01/PRM-02/PRM-03/PRM-04"

requirements-completed: [PRM-01, PRM-02, PRM-03, PRM-04]

# Metrics
duration: 10min
completed: 2026-03-29
---

# Phase 2 Plan 02: AI Prompts and Excel Extraction Summary

**Extract prompt-building and Excel generation functions from ai.py into ai/prompts.py (1370 lines) and ai/excel_gen.py (97 lines), with lazy imports preserving ai.py byte-identical**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-29T13:19:24Z
- **Completed:** 2026-03-29T13:29:23Z
- **Tasks:** 2
- **Files modified:** 2 created, 0 modified

## Accomplishments

- Created `ai/prompts.py` (1370 lines) with all prompt-building functions: `_ALIAS_FERRETERIA`, `aplicar_alias_ferreteria`, `_construir_parte_estatica`, `_construir_catalogo_imagen`, `_construir_parte_dinamica`, `_calcular_historial`, `MODELO_HAIKU`, `MODELO_SONNET`, `_elegir_modelo`
- Created `ai/excel_gen.py` (97 lines) with `generar_excel_personalizado` and `editar_excel_con_claude`
- `ai.py` left byte-identical — all deletions deferred to Phase 3 Task I
- No `ai/__init__.py` created — namespace package integrity preserved
- Lazy imports inside `_construir_parte_dinamica` body for `ai._pg_*` helpers and `memoria.*` functions — no circular imports

## Task Commits

1. **Task 1: Create ai/prompts.py with prompt-building functions** - `11b060e` (feat)
2. **Task 2: Create ai/excel_gen.py with Excel generation functions** - `76acd61` (feat)

## Files Created/Modified

- `ai/prompts.py` — 1370 lines: _ALIAS_FERRETERIA constant, aplicar_alias_ferreteria, _construir_parte_estatica, _construir_catalogo_imagen, _construir_parte_dinamica (largest function with all product matching logic), _calcular_historial, MODELO_HAIKU, MODELO_SONNET, _elegir_modelo
- `ai/excel_gen.py` — 97 lines: generar_excel_personalizado (styled xlsx creator), editar_excel_con_claude (async Claude-powered Excel editor)

## Decisions Made

- Used lazy imports inside `_construir_parte_dinamica` function body for both `from ai import _pg_*` helpers and `from memoria import *` calls — module-level imports would create circular dependency since ai.py imports from memoria and would be imported back from ai/prompts.py
- `_construir_parte_estatica` uses a single lazy `from memoria import obtener_precios_como_texto` inside the function body to keep the module pure at load time
- `ai/__init__.py` explicitly NOT created — if it existed, Python would shadow `ai.py` and break all 6+ existing `from ai import procesar_con_claude` call sites in handlers and routers

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None — these are additive extractions. All function logic is complete and exact copies from ai.py. They will not be called in production until Phase 3 Task I wires up the references.

## Self-Check: PASSED

- ai/prompts.py: FOUND (1370 lines)
- ai/excel_gen.py: FOUND (97 lines)
- ai/__init__.py: NOT FOUND (correct — namespace package)
- Commit 11b060e (feat: create ai/prompts.py): FOUND
- Commit 76acd61 (feat: create ai/excel_gen.py): FOUND
- ai.py unchanged: CONFIRMED (git diff shows 0 lines)

---
*Phase: 02-wiring*
*Completed: 2026-03-29*
