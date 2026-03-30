---
phase: 04-tests
plan: 03
subsystem: testing
tags: [pytest, mocking, caja_service, fiados_service, thin-wrapper, DB_DISPONIBLE]

# Dependency graph
requires:
  - phase: 02-services
    provides: services/caja_service.py and services/fiados_service.py (caja/fiados logic extracted from memoria.py)
  - phase: 04-tests
    provides: sys.modules stub injection pattern established in plans 04-01 and 04-02
provides:
  - tests/test_caja_service.py — 10 unit tests for caja_service with mocked db
  - tests/test_fiados_service.py — 13 unit tests for fiados_service with mocked db + 2 thin wrapper smoke tests
  - Full suite: 62 tests, 0 failed across all 6 test files
affects: [future-tests, ci-setup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sys.modules stub injection (config, db, memoria) before service imports"
    - "patch('db.DB_DISPONIBLE', False) to exercise no-DB fallback paths"
    - "Save/restore sys.modules['memoria'] in thin wrapper smoke tests to load real memoria.py"
    - "Patch internal helper functions (e.g. guardar_fiado_movimiento) to isolate abonar_fiado contract test"

key-files:
  created:
    - tests/test_caja_service.py
    - tests/test_fiados_service.py
  modified: []

key-decisions:
  - "Thin wrapper smoke tests temporarily pop sys.modules['memoria'] to load real module, then restore stub after assertion — avoids polluting test isolation"
  - "abonar_fiado (bool, str) contract tests mock guardar_fiado_movimiento to avoid RuntimeError from DB unavailable — isolates contract from implementation"

patterns-established:
  - "Pattern: Thin wrapper smoke test pattern — pop stub, import real module, assert hasattr, restore stub"
  - "Pattern: abonar_fiado contract isolation — patch internal writes to test return type without DB"

requirements-completed: [TST-04, TST-05, TST-06]

# Metrics
duration: 8min
completed: 2026-03-29
---

# Phase 04 Plan 03: Caja + Fiados Service Tests Summary

**23 pytest unit tests covering caja_service and fiados_service fallback/DB paths, plus thin wrapper smoke tests confirming memoria.py still re-exports all caja and fiados symbols**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-29T23:32:00Z
- **Completed:** 2026-03-29T23:40:38Z
- **Tasks:** 3
- **Files modified:** 2 created

## Accomplishments
- 10 tests for caja_service: cargar_caja fallback dict structure, postgres path mock, obtener_resumen_caja string contract in open/closed/no-DB cases, cargar_gastos_hoy empty list fallback, guardar_caja/guardar_gasto RuntimeError without DB
- 13 tests for fiados_service: cargar_fiados DB path with rows_mock/fallback, abonar_fiado (bool, str) tuple contract, client-not-found returns (False, str), resumen_fiados with/without pendientes, detalle_fiado_cliente
- 2 thin wrapper smoke tests confirming memoria.py exports all 5 caja symbols and all 5 fiados symbols
- Full test suite: 62 tests passed, 0 failed (all 6 test files)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write tests/test_caja_service.py** - part of `5e9c7e5` (test)
2. **Task 2: Write tests/test_fiados_service.py** - part of `5e9c7e5` (test)
3. **Task 3: Run full suite and commit** - `5e9c7e5` (test: add test_caja_service + test_fiados_service — Phase 2 unit tests (Tarea J))

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `tests/test_caja_service.py` - 10 unit tests for services/caja_service.py; exercises DB fallback paths with db stub + per-test patches
- `tests/test_fiados_service.py` - 13 unit tests for services/fiados_service.py including 2 thin wrapper smoke tests for memoria.py re-exports

## Decisions Made
- Thin wrapper smoke tests temporarily pop the `memoria` stub from `sys.modules`, import the real `memoria.py`, assert `hasattr`, then restore the stub. This ensures the real module is loaded without permanently polluting test isolation.
- `abonar_fiado` contract tests (tuple, not-found) work with DB unavailable because `_buscar_cliente_fiado` returns `None` before reaching `guardar_fiado_movimiento`. For the "client found" test, `guardar_fiado_movimiento` is patched to return a saldo mock value, avoiding RuntimeError from missing DB.

## Deviations from Plan

None - plan executed exactly as written. Test structure followed the plan's specified patterns. Task 1 and Task 2 commits were combined into a single atomic commit as they were written and verified in sequence within Task 3's commit step.

## Issues Encountered
- `python -c "import main; print('main OK')"` fails on dev machine because `config.py` calls `SystemExit(1)` when TELEGRAM_TOKEN/ANTHROPIC_API_KEY/OPENAI_API_KEY are not set. This is a pre-existing constraint on the dev environment, not introduced by this plan. All tests use sys.modules injection to bypass this. On Railway (production) all env vars are set and the check passes.

## Known Stubs
None — all test data is controlled mock data. No production stubs were introduced.

## Next Phase Readiness
- Phase 4 (tests) is complete — all 3 plans executed, 62 tests green
- Full refactorization test coverage established for: middleware, price_cache, catalogo_service, inventario_service, caja_service, fiados_service
- Ready for project milestone completion review

---
*Phase: 04-tests*
*Completed: 2026-03-29*
