---
phase: 01-db-infra-cat-logo-inventario
plan: "01"
subsystem: database
tags: [postgresql, psycopg2, db-infra, connection-pool, schema]
dependency_graph:
  requires: []
  provides: [db.py, ThreadedConnectionPool, DB_DISPONIBLE, 18-table-schema, init_db]
  affects: [start.py, config.py, memoria.py (future plans)]
tech_stack:
  added: [psycopg2-binary>=2.9.9]
  patterns: [ThreadedConnectionPool, RealDictCursor, contextmanager, lazy-psycopg2-import, DB_DISPONIBLE-flag]
key_files:
  created: [db.py]
  modified: [requirements.txt, config.py, start.py]
decisions:
  - "psycopg2 imported lazily inside init_db() (not top-level) — prevents ImportError when psycopg2 not installed locally"
  - "DATABASE_URL NOT added to _CLAVES_REQUERIDAS — remains optional per D-05"
  - "init_db() called before _restaurar_memoria() in start.py — ensures DB_DISPONIBLE set before first cargar_memoria() call"
  - "18 tables in schema (plan said 17 — facturas_abonos is a separate table, MIGRATION.md has 18)"
metrics:
  duration: "2 minutes"
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_changed: 4
requirements_fulfilled: [DB-01, DB-02, DB-03, DB-04]
---

# Phase 01 Plan 01: PostgreSQL Infrastructure Summary

**One-liner:** Central PostgreSQL access module (`db.py`) with `ThreadedConnectionPool`, 18-table idempotent schema, `DB_DISPONIBLE` flag, and safe JSON fallback wired into boot sequence.

## What Was Built

Created `db.py` as the single entry point for all PostgreSQL access in FerreBot. The module uses `psycopg2.pool.ThreadedConnectionPool` (thread-safe, sync — compatible with bot's threading model) and exposes four public functions: `query_one`, `query_all`, `execute`, `execute_returning`. All functions return safe empty values (`None`/`[]`/`0`) when `DB_DISPONIBLE=False`, enabling zero-error fallback to JSON mode.

The `_init_schema()` function deploys the complete 18-table schema idempotently using `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`. Includes a `uq_prod_fraccion` unique index on `productos_fracciones(producto_id, fraccion)` to support safe UPSERT in future `migrate_memoria.py`.

`config.py` gains `DATABASE_URL = os.getenv("DATABASE_URL")` as an optional variable (not in `_CLAVES_REQUERIDAS`). `start.py` calls `init_db()` immediately after `import config` and before `_restaurar_memoria()`, ensuring `DB_DISPONIBLE` is set before the first `cargar_memoria()` invocation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create db.py and add psycopg2-binary | be46fa3 | db.py, requirements.txt |
| 2 | Wire init_db() into start.py and add DATABASE_URL to config.py | b7e19aa | start.py, config.py |

## Verification Results

1. `python -c "import db; assert db.DB_DISPONIBLE == False; print('OK')"` — PASSED
2. `grep -c "CREATE TABLE IF NOT EXISTS" db.py` — 18 (all tables present)
3. `grep "init_db" start.py` — line 44 (before _restaurar_memoria on line 63)
4. `DATABASE_URL` not in `_CLAVES_REQUERIDAS` — confirmed
5. `psycopg2` imported only inside `init_db()`, not at module level — confirmed

## Deviations from Plan

**1. [Rule 1 - Minor] 18 tables instead of the 17 stated in plan**

- **Found during:** Task 1
- **Issue:** The plan acceptance criteria says `grep -c "CREATE TABLE IF NOT EXISTS" db.py` returns 17, but MIGRATION.md (the authoritative source) defines 18 tables — `facturas_abonos` is a distinct table from `facturas_proveedores`. The plan's "17" was a counting error in the requirements.
- **Fix:** Implemented all 18 tables from MIGRATION.md as written. All tables listed in the plan's acceptance criteria description are present.
- **Files modified:** db.py
- **Commit:** be46fa3

## Known Stubs

None. This plan creates infrastructure only — no data-display components.

## Boot Sequence After This Plan

```
start.py:
  1. Logging setup (lines 23-34)
  2. import config  (line 40)
  3. import db as _db; _db.init_db()  (lines 43-44)  <-- NEW
  4. _restaurar_memoria()  (line 63)
  5. API thread, Excel watcher, historico safety net, bot
```
