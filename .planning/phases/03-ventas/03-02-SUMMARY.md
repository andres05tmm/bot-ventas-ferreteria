---
phase: 03-ventas
plan: 02
subsystem: routers/ventas
tags: [postgres, read-path, ventas, api]
dependency_graph:
  requires: [db.py, routers/shared.py, routers/ventas.py]
  provides: [_leer_ventas_postgres, postgres-first ventas read path]
  affects: [/ventas/semana, /ventas/top, /ventas/top2, /ventas/resumen, /ventas/hoy]
tech_stack:
  added: []
  patterns: [postgres-first with Excel fallback, lazy db import, None-signals-fallback]
key_files:
  created: []
  modified:
    - routers/shared.py
    - routers/ventas.py
decisions:
  - "_leer_ventas_postgres returns None (not []) on unavailability so callers can distinguish 'no data' from 'DB not available'"
  - "ventas_hoy keeps Sheets as primary, adds Postgres as middle fallback, keeps Excel as last resort (three-tier)"
  - "All other endpoints use Postgres-first (two-tier: Postgres -> Excel)"
metrics:
  duration_seconds: 142
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_modified: 2
---

# Phase 03 Plan 02: Ventas Read Path — Postgres Primary Summary

**One-liner:** Ventas read endpoints now query Postgres (ventas + ventas_detalle JOIN) with identical JSON format, falling back to Excel when DB unavailable.

## What Was Built

Added `_leer_ventas_postgres()` to `routers/shared.py` as a drop-in replacement for `_leer_excel_rango()` for historical read queries. The function produces identical dict keys so downstream callers and the React dashboard need zero changes (VEN-06).

Updated all five historical/summary ventas endpoints in `routers/ventas.py` to call Postgres first:

| Endpoint | Source strategy |
|----------|----------------|
| `GET /ventas/hoy` | Sheets (primary) → Postgres fallback → Excel last resort |
| `GET /ventas/semana` | Postgres primary → Excel fallback |
| `GET /ventas/top` | Postgres primary → Excel fallback |
| `GET /ventas/resumen` | Sheets for today; Postgres for semana + mes; Excel fallback |
| `GET /ventas/top2` | Postgres primary → Excel fallback |

Write endpoints (`/venta-rapida`, `/ventas/{numero}` DELETE/PATCH, `/ventas/varia`) are unchanged.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 2708968 | feat(03-02): add _leer_ventas_postgres() to routers/shared.py |
| 2 | 69652f9 | feat(03-02): update ventas endpoints to Postgres-first reads |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The function returns real data from Postgres when DB_DISPONIBLE=True. When DB is unavailable it returns None, triggering Excel fallback — existing behavior preserved.

## Self-Check: PASSED

Files verified:
- `routers/shared.py`: `_leer_ventas_postgres` defined, `DB_DISPONIBLE` guard, SQL JOIN, `codigo_producto: ""`, `logger.warning` on except
- `routers/ventas.py`: 7 occurrences of `_leer_ventas_postgres` (import + 6 call sites), `postgres_fallback` fuente label, `sheets_leer_ventas_del_dia` preserved as primary for today
- Commits 2708968 and 69652f9 present in git log
