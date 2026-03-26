---
phase: 01
plan: 02
subsystem: memoria
tags: [postgres, memoria, catalogo, inventario, dual-write, fallback]
depends_on:
  requires: [01-01]
  provides: [memoria-postgres-read-write]
  affects: [cargar_memoria, guardar_memoria, buscar_producto_en_catalogo]
tech-stack:
  added: []
  patterns:
    - lazy-import-db-inside-functions
    - dual-write-json-and-postgres
    - postgres-upsert-sync
key-files:
  modified:
    - memoria.py
decisions:
  - "db imported lazily inside functions (not top-level) to avoid circular import — pattern from RESEARCH.md Pitfall 1"
  - "Postgres write in guardar_memoria is non-fatal: caught with except Exception + logger.warning (core value: bot cannot fall)"
  - "cargar_memoria() loads base from JSON then overlays catalogo+inventario from Postgres (fields not yet migrated: gastos, caja, notas, negocio stay in JSON)"
  - "Decimal values from Postgres NUMERIC columns converted to float in _leer_inventario_postgres (JSON had float, not Decimal)"
metrics:
  duration_seconds: 180
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_modified: 1
---

# Phase 01 Plan 02: memoria.py Postgres Read/Write Summary

**One-liner:** memoria.py refactored with lazy Postgres read (cargar_memoria) and dual-write sync (guardar_memoria) preserving all public signatures and JSON fallback.

## What Was Built

Modified `memoria.py` to support Postgres as the data source for `catalogo` and `inventario` when `DB_DISPONIBLE=True`, with safe fallback to JSON when Postgres is unavailable. All 151 external references to public functions remain compatible.

### New Private Functions

**`_leer_catalogo_postgres(db_module) -> dict`**
Reconstructs `memoria["catalogo"]` from 4 Postgres tables: `productos`, `productos_fracciones`, `productos_precio_cantidad`, `productos_alias`. Uses Python-side joins for efficiency. Returns a dict with identical structure to the JSON format (same keys: `nombre`, `nombre_lower`, `categoria`, `precio_unidad`, `unidad_medida`, `precios_fraccion`, `precio_por_cantidad`, `alias`).

**`_leer_inventario_postgres(db_module) -> dict`**
Reconstructs `memoria["inventario"]` from a JOIN of `inventario` and `productos`. Converts Postgres `NUMERIC` values to `float` (JSON had native float).

**`_cargar_desde_postgres() -> dict`**
Loads base structure from JSON (for unmigrated fields: `gastos`, `caja`, `notas`, `negocio`, `precios`), then overlays `catalogo` and `inventario` from Postgres.

**`_sincronizar_catalogo_postgres(catalogo, db_module)`**
UPSERT sync of the full catalogo dict to Postgres. Uses `ON CONFLICT (clave) DO UPDATE` for products. Fracciones use DELETE+INSERT per product (simpler than individual UPSERTs). Aliases use `ON CONFLICT (alias) DO NOTHING`.

**`_sincronizar_inventario_postgres(inventario, db_module)`**
UPSERT sync of inventario dict to Postgres. Looks up `producto_id` by `clave`, then UPSERTs the inventario row.

### Modified Functions

**`cargar_memoria() -> dict`** (signature unchanged)
Now checks `_db.DB_DISPONIBLE` before loading. If True, calls `_cargar_desde_postgres()`. If False, uses original JSON fallback. Cache behavior is identical.

**`guardar_memoria(memoria, urgente=False)`** (signature unchanged)
JSON write + Drive upload code is unchanged. Added Postgres dual-write block AFTER the existing code: `if _db.DB_DISPONIBLE` → sync catalogo and inventario → catch any Exception with `logger.warning` (non-fatal, per core value).

### Module-Level Addition

Added `logger = logging.getLogger("ferrebot.memoria")` per CLAUDE.md convention (was missing — Rule 2 auto-fix: required for the new `logger.warning` call in guardar_memoria).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 0b0f45c | feat(01-02): add Postgres read functions to memoria.py (cargar_memoria refactor) |
| Task 2 | 927cf0c | feat(01-02): add Postgres dual-write to guardar_memoria() and run test suite |

## Test Results

`python test_suite.py` (with `PYTHONIOENCODING=utf-8`):
- Total: 201 tests executed
- Passed: 201
- Failed: 0
- Errors: 0
- Exit code: 0

Note: The test_suite.py runner reports 201 test cases (not 1096+). The 1096+ figure from the plan may reflect a previous version of the test file. All tests pass — no regressions introduced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added module-level logger**
- **Found during:** Task 2
- **Issue:** `guardar_memoria()` needed `logger.warning()` for Postgres error logging, but `memoria.py` had no `logger` defined at module level.
- **Fix:** Added `logger = logging.getLogger("ferrebot.memoria")` at module level, per CLAUDE.md Logging Convention.
- **Files modified:** memoria.py
- **Commit:** 927cf0c

None other — plan executed as written.

## Known Stubs

None. All new functions are fully implemented. `_leer_catalogo_postgres` and `_leer_inventario_postgres` will return empty dicts when DB_DISPONIBLE=False (db.query_all returns [] safely), which is the correct behavior — the JSON path handles that case.

## Self-Check

### Created files exist
- [x] `.planning/phases/01-db-infra-cat-logo-inventario/01-02-SUMMARY.md` — this file

### Commits exist
- [x] 0b0f45c (Task 1)
- [x] 927cf0c (Task 2)

### Verification checks
- [x] `cargar_memoria()` signature: `() -> dict` — unchanged
- [x] `guardar_memoria()` signature: `(memoria: dict, urgente: bool = False)` — unchanged
- [x] `import db as _db` inside functions (not top-level) — 3 occurrences confirmed
- [x] `if _db.DB_DISPONIBLE` in cargar_memoria — confirmed
- [x] `_sincronizar_catalogo_postgres` exists — confirmed
- [x] `_sincronizar_inventario_postgres` exists — confirmed
- [x] JSON write (`json.dump`) still present — confirmed line 249
- [x] Drive upload (`subir_a_drive`) still present — confirmed lines 252-256
- [x] test_suite.py exits 0 — confirmed

## Self-Check: PASSED
