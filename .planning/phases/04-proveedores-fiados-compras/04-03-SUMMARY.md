---
phase: 04-proveedores-fiados-compras
plan: 03
subsystem: database
tags: [postgres, psycopg2, migration, proveedores, fiados, compras]

# Dependency graph
requires:
  - phase: 04-proveedores-fiados-compras
    provides: facturas_proveedores, facturas_abonos, fiados, fiados_historial, compras tables in Postgres (Plan 01)
provides:
  - migrate_proveedores.py: idempotent migration of cuentas_por_pagar → facturas_proveedores + facturas_abonos
  - migrate_fiados.py: idempotent migration of fiados dict → fiados + fiados_historial
  - migrate_compras.py: idempotent migration of historial_compras → compras (graceful empty)
affects: [phase-05-finalizacion, production-cutover]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - ON CONFLICT (id) DO NOTHING for VARCHAR PK tables (facturas_proveedores)
    - check-before-insert deduplication for tables without UNIQUE constraints
    - application-level upsert (query_one + branch) for name-keyed lookups (fiados)
    - execute_returning for INSERT ... RETURNING id pattern

key-files:
  created:
    - migrate_proveedores.py
    - migrate_fiados.py
    - migrate_compras.py
  modified: []

key-decisions:
  - "migrate_proveedores.py uses ON CONFLICT (id) DO NOTHING — facturas have VARCHAR PK like 'FAC-001'"
  - "migrate_fiados.py uses SELECT-then-branch (update or insert RETURNING id) — fiados.nombre has no UNIQUE constraint"
  - "migrate_compras.py handles both 'total' and 'costo_total' key names from JSON source for forward compatibility"
  - "All three scripts fail fast (exit 1) if DATABASE_URL absent or DB unavailable"
  - "All three handle empty sources gracefully (exit 0, 'Nada que migrar' log) — matches live data state of 0 facturas, 0 compras"

patterns-established:
  - "Migration scripts follow canonical structure: logging.basicConfig → import db → def migrar() → if __name__ == __main__"
  - "Idempotency strategies: ON CONFLICT for PK tables, check-before-insert for non-unique, SELECT+branch for name-keyed"

requirements-completed: [PROV-01, PROV-02, PROV-03]

# Metrics
duration: 2min
completed: 2026-03-27
---

# Phase 04 Plan 03: Migration Scripts for Proveedores, Fiados, and Compras Summary

**Three idempotent one-time migration scripts (migrate_proveedores.py, migrate_fiados.py, migrate_compras.py) to populate Postgres from memoria.json, each with empty-source graceful exit and fail-fast on missing DATABASE_URL**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-27T03:21:28Z
- **Completed:** 2026-03-27T03:23:24Z
- **Tasks:** 2
- **Files modified:** 3 (all created)

## Accomplishments

- Created `migrate_proveedores.py`: migrates `cuentas_por_pagar` list to `facturas_proveedores` (ON CONFLICT DO NOTHING) + `facturas_abonos` (check-before-insert)
- Created `migrate_fiados.py`: migrates `fiados` dict (3 live clients) to `fiados` (SELECT-then-branch upsert) + `fiados_historial` (check-before-insert)
- Created `migrate_compras.py`: migrates `historial_compras` list (currently empty) to `compras` (check-before-insert on fecha+producto+cantidad+cu)
- All three scripts idempotent, re-runnable without duplicating records
- 201/201 test_suite.py tests still passing after additions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create migrate_proveedores.py** - `4a5e348` (feat)
2. **Task 2: Create migrate_fiados.py and migrate_compras.py** - `6ce1a72` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `/migrate_proveedores.py` - Migrates cuentas_por_pagar → facturas_proveedores + facturas_abonos; idempotent via ON CONFLICT (id) DO NOTHING + check-before-insert
- `/migrate_fiados.py` - Migrates fiados dict → fiados + fiados_historial; idempotent via SELECT-then-UPDATE-or-INSERT for clients, check-before-insert for movements
- `/migrate_compras.py` - Migrates historial_compras → compras; idempotent via check-before-insert on (fecha, producto_nombre, cantidad, costo_unitario)

## Decisions Made

- `migrate_proveedores.py` uses `ON CONFLICT (id) DO NOTHING` because `facturas_proveedores.id` is a VARCHAR PK (e.g. "FAC-001") — deterministic and collision-safe
- `migrate_fiados.py` uses application-level upsert (SELECT id + branch) because `fiados.nombre` has no UNIQUE constraint; on re-run existing records are updated with current saldo
- `migrate_compras.py` handles both `"total"` and `"costo_total"` key names since the JSON source key may vary depending on how the record was originally written
- Scripts follow canonical structure from `migrate_gastos_caja.py` (established in Phase 02)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

Run scripts after Phase 4 deploy:
```bash
railway run python migrate_proveedores.py
railway run python migrate_fiados.py
railway run python migrate_compras.py
```

## Next Phase Readiness

- All three migration scripts ready for production run via `railway run python migrate_*.py`
- Scripts are safe to run on current live data: 0 facturas (exit 0 gracefully), 3 fiados clients (will insert), 0 compras (exit 0 gracefully)
- No blockers for Phase 05 finalization

## Self-Check: PASSED

---
*Phase: 04-proveedores-fiados-compras*
*Completed: 2026-03-27*
