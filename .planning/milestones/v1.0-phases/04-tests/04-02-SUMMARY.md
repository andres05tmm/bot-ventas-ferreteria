---
phase: 04-tests
plan: 02
subsystem: testing
tags: [pytest, unit-tests, mocking, catalogo_service, inventario_service, services]

# Dependency graph
requires:
  - phase: 01-infra
    provides: "services/catalogo_service.py and services/inventario_service.py modules to test"
  - phase: 04-01
    provides: "Test patterns for stub injection (config, db, ai, memoria) established in test_middleware + test_price_cache"
provides:
  - "tests/test_catalogo_service.py — 12 unit tests for catalog search and pricing functions"
  - "tests/test_inventario_service.py — 10 unit tests for inventory functions, descontar_inventario 3-tuple contract"
affects: [04-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sys.modules stub injection for config/db/memoria before service import to bypass SystemExit(1)"
    - "patch('memoria.cargar_memoria', return_value=...) for per-test data isolation"
    - "patch('services.inventario_service.guardar_inventario') to prevent PG writes in unit tests"

key-files:
  created:
    - tests/test_catalogo_service.py
    - tests/test_inventario_service.py
  modified: []

key-decisions:
  - "Patch target is `memoria.cargar_memoria` (not `services.catalogo_service.cargar_memoria`) because the service imports from memoria lazily — patching at source"
  - "services.inventario_service.guardar_inventario patched directly to prevent _upsert_inventario_producto_postgres → db calls"
  - "Return type of obtener_precio_para_cantidad second element is (int, int) not (int, float) — tests use isinstance(x, (int, float)) to handle both"

patterns-established:
  - "Stub injection before import: inject config, db, memoria stubs into sys.modules at top of test file"
  - "Contract testing: explicit 3-element tuple destructure + type assertions for descontar_inventario()"

requirements-completed: [TST-03, TST-05]

# Metrics
duration: 12min
completed: 2026-03-29
---

# Phase 04 Plan 02: Catalogo + Inventario Service Tests Summary

**22 unit tests (12 catalogo + 10 inventario) with full mock isolation — descontar_inventario() 3-tuple contract explicitly validated**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-29T23:32:11Z
- **Completed:** 2026-03-29T23:44:00Z
- **Tasks:** 3 (tasks 1+2 committed atomically; task 3 combined verification)
- **Files modified:** 2

## Accomplishments

- Created `tests/test_catalogo_service.py` with 12 passing tests covering buscar_producto_en_catalogo, buscar_multiples_en_catalogo, obtener_precio_para_cantidad, obtener_precios_como_texto
- Created `tests/test_inventario_service.py` with 10 passing tests, including mandatory 3-tuple contract test for descontar_inventario()
- Full test suite (39 tests across 4 files) passes with 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Write tests/test_catalogo_service.py** - `3b4e2c3` (test)
2. **Task 2: Write tests/test_inventario_service.py** - `1c36346` (test)
3. **Task 3: Run combined suite** - verified inline (no new files, combined with plan metadata commit)

## Files Created/Modified

- `tests/test_catalogo_service.py` — 12 unit tests for catalog search, multi-match, pricing functions
- `tests/test_inventario_service.py` — 10 unit tests for inventory discounting, alerts, key lookup, cargar

## Decisions Made

- Patch target is `memoria.cargar_memoria` (not a service-local alias) because lazy `from memoria import cargar_memoria` inside each function body resolves at call time — patching the source module works correctly
- `guardar_inventario` is patched at `services.inventario_service.guardar_inventario` to intercept the write path before it reaches `_upsert_inventario_producto_postgres` → `import db as _db`
- `obtener_precio_para_cantidad` returns `(int, int)` in the actual implementation (both elements are rounded integers from the catalog); test assertions updated to `isinstance(x, (int, float))` to reflect the real contract

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CATALOGO_MOCK field names corrected from plan spec**
- **Found during:** Task 1 (after reading catalogo_service.py)
- **Issue:** Plan's CATALOGO_MOCK used `precio` and `precio_fraccion` but the actual service reads `precio_unidad` and `precios_fraccion`; tests would have passed empty assertions
- **Fix:** Updated fixture to use correct field names (`precio_unidad`, `precios_fraccion`) matching the real service schema
- **Files modified:** tests/test_catalogo_service.py
- **Verification:** Tests against real return values — `assert result["precio_unidad"] == 500` passes
- **Committed in:** 3b4e2c3

**2. [Rule 1 - Bug] Return type assertion for obtener_precio_para_cantidad fixed**
- **Found during:** Task 1 verification (2 tests failed)
- **Issue:** Plan specified `isinstance(cantidad_final, float)` but service returns `precio_u` (int from catalog dict) as second element
- **Fix:** Changed assertion to `isinstance(precio_u, (int, float))` to match actual return contract
- **Files modified:** tests/test_catalogo_service.py
- **Verification:** 12/12 tests pass
- **Committed in:** 3b4e2c3

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Fixes were necessary to make assertions match real service behavior. No scope creep.

## Issues Encountered

- `config.py` raises `SystemExit(1)` at import time when TELEGRAM_TOKEN/ANTHROPIC_API_KEY/OPENAI_API_KEY are missing. Resolved by injecting a `config` stub into `sys.modules` before importing the service — same pattern used in `tests/test_price_cache.py`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04-03 can now reference the established test patterns for remaining service modules (caja_service, fiados_service, ai/prompts)
- All 39 tests green: test_middleware (10) + test_price_cache (8) + test_catalogo_service (12) + test_inventario_service (10)

## Self-Check: PASSED

- tests/test_catalogo_service.py: FOUND
- tests/test_inventario_service.py: FOUND
- Commit 3b4e2c3: FOUND
- Commit 1c36346: FOUND

---
*Phase: 04-tests*
*Completed: 2026-03-29*
