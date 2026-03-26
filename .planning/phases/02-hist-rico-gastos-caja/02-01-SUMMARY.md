---
phase: 02
plan: 01
subsystem: gastos-caja
tags: [postgres, gastos, caja, dual-write, fallback, migration]
depends_on:
  requires: [01-02]
  provides: [gastos-caja-postgres-read-write]
  affects: [guardar_gasto, guardar_caja, cargar_caja, cargar_gastos_hoy, GET /caja, GET /gastos]
tech-stack:
  added: []
  patterns:
    - lazy-import-db-inside-functions
    - dual-write-json-and-postgres
    - postgres-first-read-with-json-fallback
    - idempotent-migration-script
key-files:
  modified:
    - memoria.py
    - routers/caja.py
  created:
    - migrate_gastos_caja.py
decisions:
  - "Same lazy import pattern as 01-02: import db as _db inside each helper function to avoid circular imports"
  - "All Postgres helpers are non-fatal: any Exception caught with logger.warning — bot cannot fall (core value)"
  - "cargar_caja() reads from Postgres first, falls back to JSON when DB unavailable or no row for today"
  - "cargar_gastos_hoy() reads from Postgres first (returns all gastos if _leer_gastos_postgres returns empty list vs None — returns [] which is correct for 'no gastos'"
  - "migrate_gastos_caja.py deduplicates gastos by fecha+concepto+monto (no unique constraint in table)"
  - "caja uses ON CONFLICT (fecha) DO UPDATE — safe to re-run migration"
metrics:
  duration_seconds: 600
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_modified: 2
  files_created: 1
---

# Phase 02 Plan 01: gastos/caja Postgres Migration Summary

**One-liner:** memoria.py and routers/caja.py refactored with Postgres dual-write for gastos/caja and Postgres-first reads, plus idempotent migration script.

## What Was Built

### New Private Functions in memoria.py

**`_guardar_gasto_postgres(gasto: dict)`**
Inserts a gasto into the `gastos` table. Lazy `import db as _db` inside function. Non-fatal: wraps in try/except with `logger.warning`. Called by `guardar_gasto()` after JSON write.

**`_guardar_caja_postgres(caja: dict)`**
UPSERT of caja state into the `caja` table using `ON CONFLICT (fecha) DO UPDATE`. Sets `cerrada_at = NOW()` when `abierta = FALSE`. Non-fatal. Called by `guardar_caja()` after JSON write.

**`_leer_caja_postgres() -> dict | None`**
Reads today's caja row from Postgres. Returns None when `DB_DISPONIBLE=False` or no row exists for today. Maps Postgres columns to the dict format `cargar_caja()` previously returned from JSON.

**`_leer_gastos_postgres(fecha_inicio, fecha_fin) -> list[dict]`**
Reads gastos from Postgres for a date range, ordered by fecha+hora descending. Returns empty list on failure or DB unavailable.

### Modified Public Functions in memoria.py (signatures unchanged)

**`cargar_caja()`**: Tries `_leer_caja_postgres()` first; if None, falls back to `cargar_memoria()["caja_actual"]`.

**`guardar_caja(caja)`**: JSON write unchanged + dual-write call to `_guardar_caja_postgres()` (non-fatal).

**`cargar_gastos_hoy()`**: Checks `DB_DISPONIBLE` first, calls `_leer_gastos_postgres(hoy, hoy)`; if not available, falls back to `cargar_memoria()["gastos"][hoy]`.

**`guardar_gasto(gasto)`**: JSON write unchanged + dual-write call to `_guardar_gasto_postgres()` (non-fatal).

### Modified Endpoints in routers/caja.py

**`GET /caja`**: Postgres-first block added at top of handler. Queries `caja` table for today's row, then `gastos` table for today's expenses. Full response construction from Postgres data. Falls through to original JSON-reading code when `DB_DISPONIBLE=False` or after any exception.

**`GET /gastos`**: Postgres-first block added at top of handler. Queries `gastos` table for date range. Builds `resultado`, `por_categoria`, `historico` from Postgres rows. Falls through to original JSON-reading code as fallback.

### New File: migrate_gastos_caja.py

Idempotent one-time migration script following `migrate_memoria.py` pattern:
- Fails fast with `sys.exit(1)` if `DATABASE_URL` not set
- Migrates all `gastos` entries from `memoria["gastos"]` dict (by date) to `gastos` table
- Deduplication: checks `fecha+concepto+monto` before inserting to prevent double-migration
- Migrates `caja_actual` to `caja` table using `ON CONFLICT (fecha) DO UPDATE`
- Prints summary counts at end

Run via: `railway run python migrate_gastos_caja.py`

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 6ce498c | feat(02-01): dual-write gastos/caja to Postgres in memoria.py + Postgres-first reads in routers/caja.py |
| Task 2 | b8deee5 | feat(02-01): create migrate_gastos_caja.py migration script |

## Test Results

`python test_suite.py` (with `PYTHONIOENCODING=utf-8`):
- Total: 201 tests executed
- Passed: 201
- Failed: 0
- Errors: 0
- Exit code: 0

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All functions are fully implemented with real logic. When `DB_DISPONIBLE=False`, functions fall back to JSON (correct behavior for JSON-only mode). The `_leer_gastos_postgres` function returns `[]` when DB unavailable, which is correct — `cargar_gastos_hoy()` treats this as "no gastos from Postgres" and falls through to the JSON path.

## Self-Check

### Files created/modified exist
- [x] `memoria.py` — modified
- [x] `routers/caja.py` — modified
- [x] `migrate_gastos_caja.py` — created

### Commits exist
- [x] 6ce498c (Task 1)
- [x] b8deee5 (Task 2)

### Verification checks
- [x] `_guardar_gasto_postgres` in memoria.py — confirmed
- [x] `_guardar_caja_postgres` in memoria.py — confirmed
- [x] `_leer_caja_postgres` in memoria.py — confirmed
- [x] `_leer_gastos_postgres` in memoria.py — confirmed
- [x] `guardar_gasto` calls `_guardar_gasto_postgres` — confirmed
- [x] `guardar_caja` calls `_guardar_caja_postgres` — confirmed
- [x] `cargar_caja` calls `_leer_caja_postgres` — confirmed
- [x] `query_one("SELECT * FROM caja` in routers/caja.py — confirmed
- [x] `query_all` in routers/caja.py (gastos) — confirmed
- [x] `open(config.MEMORIA_FILE` in routers/caja.py (JSON fallback preserved) — confirmed
- [x] `db.init_db()` in migrate_gastos_caja.py — confirmed
- [x] `sys.exit(1)` in migrate_gastos_caja.py — confirmed
- [x] `INSERT INTO gastos` in migrate_gastos_caja.py — confirmed
- [x] `INSERT INTO caja` in migrate_gastos_caja.py — confirmed
- [x] `ON CONFLICT (fecha) DO UPDATE` in migrate_gastos_caja.py — confirmed
- [x] `SELECT id FROM gastos WHERE` deduplication in migrate_gastos_caja.py — confirmed
- [x] test_suite.py exits 0 — confirmed (201/201 passed)

## Self-Check: PASSED
