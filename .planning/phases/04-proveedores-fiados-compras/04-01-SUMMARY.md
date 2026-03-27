---
phase: 04-proveedores-fiados-compras
plan: 01
subsystem: database
tags: [postgres, psycopg2, dual-write, memoria, proveedores, fiados, compras]

# Dependency graph
requires:
  - phase: 03-ventas
    provides: Established non-fatal dual-write pattern in memoria.py (lazy import db, DB_DISPONIBLE guard, except/logger.warning)
provides:
  - Non-fatal Postgres dual-write in registrar_factura_proveedor (facturas_proveedores)
  - Non-fatal Postgres dual-write in registrar_abono_factura (facturas_abonos + UPDATE facturas_proveedores)
  - Non-fatal Postgres dual-write in guardar_fiado_movimiento (fiados upsert + fiados_historial)
  - Non-fatal Postgres dual-write in _registrar_historial_compra (compras)
affects:
  - 04-02 (read paths for proveedores, fiados, compras)
  - 04-03 (migration scripts for these domains)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Non-fatal dual-write: lazy `import db as _db`, `if _db.DB_DISPONIBLE:`, try/except/logger.warning"
    - "fiados upsert: query_one SELECT + conditional UPDATE or execute_returning INSERT"

key-files:
  created: []
  modified:
    - memoria.py

key-decisions:
  - "registrar_factura_proveedor uses ON CONFLICT (id) DO NOTHING — idempotent if same fac_id re-registered"
  - "registrar_abono_factura does two separate db.execute calls (INSERT abono, UPDATE header) inside single try block — atomic failure, non-fatal"
  - "guardar_fiado_movimiento uses query_one+UPDATE or execute_returning INSERT pattern (no DB UPSERT) — consistent with Phase 01 decision to use application-level upsert for fiados"
  - "datetime and config already imported at module level in memoria.py — no new imports added to guardar_fiado_movimiento or _registrar_historial_compra"

patterns-established:
  - "Non-fatal inline dual-write block: always after guardar_memoria() call, before return statement"
  - "fiado upsert via query_one then branch: avoids INSERT conflict on nombre which has no UNIQUE constraint"

requirements-completed: [PROV-04]

# Metrics
duration: 2min
completed: 2026-03-27
---

# Phase 4 Plan 01: Proveedores/Fiados/Compras Dual-Write Summary

**Non-fatal Postgres dual-write added to 4 memoria.py write functions covering facturas_proveedores, facturas_abonos, fiados+fiados_historial, and compras tables**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-27T03:17:32Z
- **Completed:** 2026-03-27T03:19:04Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- `registrar_factura_proveedor`: now writes to `facturas_proveedores` (INSERT ON CONFLICT DO NOTHING) after JSON save
- `registrar_abono_factura`: now writes to `facturas_abonos` (INSERT) and syncs `facturas_proveedores` (UPDATE pagado/pendiente/estado) after JSON save
- `guardar_fiado_movimiento`: now upserts `fiados` row and appends to `fiados_historial` after JSON save
- `_registrar_historial_compra`: now writes to `compras` after JSON save
- All four blocks are non-fatal: try/except with logger.warning, guarded by `if _db.DB_DISPONIBLE`
- 201 tests pass, zero regressions

## Task Commits

1. **Task 1: Dual-write Postgres in registrar_factura_proveedor and registrar_abono_factura** - `89371f8` (feat)
2. **Task 2: Dual-write Postgres in guardar_fiado_movimiento and _registrar_historial_compra** - `71b67f6` (feat)

## Files Created/Modified

- `memoria.py` - Added 4 non-fatal Postgres dual-write blocks (82 lines added total)

## Decisions Made

- `registrar_factura_proveedor` uses `ON CONFLICT (id) DO NOTHING` because `fac_id` is the PK — safe for idempotent retries
- `registrar_abono_factura` does two `db.execute` calls in one try block; if either fails the whole block is skipped as non-fatal
- `guardar_fiado_movimiento` uses `query_one` + conditional UPDATE/INSERT (application-level upsert) because `fiados.nombre` has no UNIQUE constraint in the schema
- No new module-level imports added in any function — `datetime` and `config` already available at module scope; `db` imported lazily inside each block

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Four write paths for proveedores/fiados/compras domains now write to Postgres in parallel with JSON
- Ready for 04-02: read endpoints for these domains can now source data from Postgres
- Ready for 04-03: migration scripts can safely import historical data knowing the write path is wired

---
*Phase: 04-proveedores-fiados-compras*
*Completed: 2026-03-27*
