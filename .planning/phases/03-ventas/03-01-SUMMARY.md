---
phase: 03-ventas
plan: 01
subsystem: database
tags: [postgres, psycopg2, ventas, ventas_detalle, triple-write]

# Dependency graph
requires:
  - phase: 01-db-infra-cat-logo-inventario
    provides: db.py with ThreadedConnectionPool, execute_returning, query_one, DB_DISPONIBLE flag
  - phase: 02-hist-rico-gastos-caja
    provides: Pattern for lazy db import inside functions, non-fatal Postgres writes

provides:
  - Postgres write path for ventas + ventas_detalle on payment confirmation (ventas_state.py)
  - Postgres triple-write in /cerrar: Sheets -> Excel AND Postgres (handlers/comandos.py)

affects: [03-02, 03-03, ventas endpoints, /export/ventas.xlsx]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "items_para_pg list collects data during existing for loop, Postgres INSERT happens after loop completes"
    - "check-then-insert idempotent pattern: SELECT before INSERT to avoid duplicate consecutivo"
    - "inner function _sync_ventas_postgres() wrapped with asyncio.to_thread for async handlers"
    - "lazy import db as _db inside function — prevents circular import, consistent with prior phases"

key-files:
  created: []
  modified:
    - ventas_state.py
    - handlers/comandos.py

key-decisions:
  - "items_para_pg collected during existing for loop rather than re-iterating ventas list — avoids duplicating business logic"
  - "Check-then-insert in /cerrar (not UPSERT) because ventas schema lacks UNIQUE constraint on consecutivo"
  - "Inner function _sync_ventas_postgres() in comando_cerrar_dia keeps Postgres logic isolated and asyncio.to_thread-compatible"
  - "logging.getLogger() called directly in ventas_state.py because module has no top-level logger variable"

patterns-established:
  - "Triple-write: Sheets is realtime buffer, Excel is file archive, Postgres is structured DB — all three updated on /cerrar"
  - "Non-fatal Postgres writes: except Exception + logger.warning, bot never falls due to DB failure"

requirements-completed: [VEN-01, VEN-02]

# Metrics
duration: 3min
completed: 2026-03-26
---

# Phase 3 Plan 01: Ventas Write Path Summary

**Postgres INSERT into ventas + ventas_detalle on payment confirmation and /cerrar triple-write using lazy db import, DB_DISPONIBLE guard, and idempotent check-then-insert pattern**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-26T22:17:45Z
- **Completed:** 2026-03-26T22:21:01Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Payment confirmation in Telegram now writes to ventas + ventas_detalle in Postgres in parallel with existing Sheets/Excel path
- /cerrar daily close syncs all Sheets sales to Postgres after Excel save (triple-write: Sheets -> Excel AND Postgres)
- Both writes are non-fatal: Postgres failure does not crash the bot or block Sheets/Excel writes
- Idempotent /cerrar sync: SELECT check before INSERT prevents duplicate rows if /cerrar is re-run

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Postgres INSERT to registrar_ventas_con_metodo** - `fdc5080` (feat)
2. **Task 2: Add triple-write Postgres block to comando_cerrar_dia** - `f8e342a` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `ventas_state.py` - Added items_para_pg collection during for loop + Postgres write block after caja update
- `handlers/comandos.py` - Added _sync_ventas_postgres() inner function wrapped in asyncio.to_thread after Drive upload

## Decisions Made
- items_para_pg collected during existing for loop (not re-iterating) to avoid duplicating business logic
- Check-then-insert pattern in /cerrar because ventas table lacks UNIQUE constraint on consecutivo
- Inner function pattern for _sync_ventas_postgres() to support asyncio.to_thread in async handler
- Used logging.getLogger() directly in ventas_state.py since the module has no top-level logger

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- ventas_state.py has no top-level `logger` variable (unlike handlers/). Used `logging.getLogger("ferrebot.ventas_state").warning(...)` directly in the except block, which is functionally equivalent and follows project conventions.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Postgres write path for ventas is live. Phase 03-02 can now add API read endpoints that query from ventas + ventas_detalle.
- Both files pass static import verification (import errors only due to missing env vars in dev, expected behavior).

---
*Phase: 03-ventas*
*Completed: 2026-03-26*
