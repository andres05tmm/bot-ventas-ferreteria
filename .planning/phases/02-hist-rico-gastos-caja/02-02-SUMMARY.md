---
phase: 02-hist-rico-gastos-caja
plan: 02
subsystem: database
tags: [postgres, psycopg2, historico, migration, drive-elimination]

# Dependency graph
requires:
  - phase: 02-01
    provides: gastos/caja Postgres migration pattern (lazy db import, non-fatal errors, ON CONFLICT UPSERT)
  - phase: 01-db-infra-cat-logo-inventario
    provides: db.py with ThreadedConnectionPool, historico_ventas table schema, DB_DISPONIBLE flag

provides:
  - Postgres-first reads for all GET /historico/* endpoints
  - Postgres dual-write in _guardar_historico() and _sync_historico_hoy()
  - migrate_historico.py for one-time migration of historico_ventas.json + historico_diario.json
  - Elimination of all Drive uploads of historico JSON/Excel files

affects:
  - phase-03-ventas-postgres (uses historico endpoints)
  - dashboard TabHistorico (reads from /historico/ventas, /historico/diario, /historico/resumen)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Lazy db import inside helper functions (import db as _db) — prevents circular import
    - Non-fatal Postgres operations with logger.warning fallback — bot cannot fall
    - Postgres-first read pattern: try Postgres, fall back to Drive/JSON
    - Drive upload elimination: Postgres replaces Drive as persistence destination

key-files:
  created:
    - migrate_historico.py
  modified:
    - routers/historico.py

key-decisions:
  - "Drive uploads of historico_ventas.json, historico_diario.json, historico_ventas.xlsx eliminated from all paths (HIS-04): Postgres is now the source of truth"
  - "JSON local files preserved as read fallback — ensures bot survives DB failure"
  - "historico_sincronizar_excel endpoint Drive upload removed but JSON local write preserved — maintains manual sync workflow"
  - "migrate_historico.py merges both JSON sources: historico_ventas.json for totals + historico_diario.json for enriched breakdown"

patterns-established:
  - "Postgres helper functions follow 02-01 pattern: lazy import, DB_DISPONIBLE check, non-fatal except + logger.warning"
  - "Read order: Postgres -> Excel/Drive legacy -> JSON local -> JSON on Drive"
  - "Write order: Postgres first, then JSON/Excel local (no Drive)"

requirements-completed: [HIS-01, HIS-02, HIS-03, HIS-04]

# Metrics
duration: 3min
completed: 2026-03-26
---

# Phase 02 Plan 02: Historico Postgres Migration Summary

**Postgres-first reads and dual-writes for all historico endpoints + Drive upload elimination via 4 helper functions and a merge-aware migration script**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-26T19:44:26Z
- **Completed:** 2026-03-26T19:47:08Z
- **Tasks:** 2
- **Files modified:** 2 (routers/historico.py modified, migrate_historico.py created)

## Accomplishments

- Added 4 Postgres helper functions to routers/historico.py: `_leer_historico_postgres`, `_leer_diario_postgres`, `_guardar_historico_postgres`, `_guardar_diario_postgres`
- All Drive uploads of historico JSON and Excel files eliminated (zero `subir_a_drive_urgente` calls remain)
- All historico GET endpoints now read Postgres first with JSON/Drive fallback preserved
- Created idempotent migrate_historico.py that merges both JSON source files into historico_ventas table

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Postgres paths to routers/historico.py + eliminate Drive uploads** - `0dc0a02` (feat)
2. **Task 2: Create migrate_historico.py migration script** - `8f0d9cd` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `routers/historico.py` - Added 4 Postgres helpers; modified _leer_historico, _guardar_historico, _sync_historico_hoy, historico_diario_get, historico_corregir_dia, historico_reconstruir_desglose, historico_sincronizar_excel to use Postgres + eliminate Drive uploads
- `migrate_historico.py` - New one-time migration script: reads historico_ventas.json + historico_diario.json, merges both, UPSERTs to historico_ventas table with ON CONFLICT (fecha) DO UPDATE

## Decisions Made

- Drive uploads eliminated rather than made non-fatal: Postgres is the new source of truth; Excel/JSON stay as local fallback only
- handlers/comandos.py required no changes: Drive elimination happens inside routers/historico.py functions that comandos.py calls
- historico_sincronizar_excel endpoint: Drive upload of historico_ventas.json removed but JSON local write preserved — manual sync workflow still works for import from Excel

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

Run migration after deploy:
```
railway run python migrate_historico.py
```

## Next Phase Readiness

- Phase 02 is now complete: gastos/caja (02-01) + historico (02-02) both migrated to Postgres
- Phase 03 can proceed: ventas registration in Postgres + _leer_excel_rango() replacement

---
*Phase: 02-hist-rico-gastos-caja*
*Completed: 2026-03-26*
