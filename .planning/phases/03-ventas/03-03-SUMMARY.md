---
phase: 03-ventas
plan: "03"
subsystem: migration
tags: [migration, ventas, excel, postgres, idempotent]
dependency_graph:
  requires: [db.py, config.py, ventas.xlsx, openpyxl]
  provides: [migrate_ventas.py]
  affects: [ventas, ventas_detalle]
tech_stack:
  added: []
  patterns: [fail-fast DATABASE_URL check, openpyxl read_only, consecutivo+fecha deduplication]
key_files:
  created: [migrate_ventas.py]
  modified: []
decisions:
  - "cliente_id set to None during migration — FK resolution is too unreliable against live catalog"
  - "alias_usado mapped directly from alias column, None if column absent"
  - "No batching needed — ventas.xlsx is not large enough to require it"
metrics:
  duration_seconds: 80
  completed_date: "2026-03-26"
  tasks_completed: 1
  files_created: 1
  files_modified: 0
---

# Phase 03 Plan 03: migrate_ventas.py Summary

One-time migration script that reads all monthly sheets from ventas.xlsx, groups rows by consecutivo+fecha, and inserts into ventas + ventas_detalle tables with idempotency via SELECT check before each group.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create migrate_ventas.py migration script | f4cdb65 | migrate_ventas.py |

## What Was Built

`migrate_ventas.py` (308 lines) is a standalone one-time migration script:

- **Fail-fast guard:** exits immediately if `DATABASE_URL` not set or `db.init_db()` fails
- **Sheet discovery:** iterates all `wb.sheetnames`, skips non-monthly sheets (Compras, Registro de Ventas-Acumulado, Productos) using a heuristic against `config.MESES` values
- **Column detection:** mirrors `_leer_excel_rango()` in `routers/shared.py` — reads header row at `config.EXCEL_FILA_HEADERS`, maps column names case-insensitively
- **Grouping:** groups data rows by `(consecutivo_int, fecha_str)` key — one group = one sale transaction
- **Idempotency:** before inserting each group, runs `SELECT id FROM ventas WHERE consecutivo = %s AND fecha = %s`; skips if already exists (per D-13)
- **INSERT ventas:** inserts header-level data (consecutivo, fecha, hora, cliente_nombre, vendedor, metodo_pago, total = sum of line totals); `cliente_id` always None
- **INSERT ventas_detalle:** inserts one row per line in the group (producto_nombre, cantidad, unidad_medida, precio_unitario, total, alias_usado)
- **Error handling:** per-group `except Exception` with `logger.warning` — one bad row never aborts the migration
- **Summary output:** prints sheets_count, ventas_count, detalle_count, skipped_count at end

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this is a migration script with no UI rendering or API endpoints. All data flows to Postgres directly.

## Self-Check: PASSED

- migrate_ventas.py exists: FOUND
- Commit f4cdb65 exists: FOUND
- Syntax check: PASSED (ast.parse)
- INSERT INTO ventas: 2 occurrences (header insert + idempotency check context)
- INSERT INTO ventas_detalle: 1 occurrence
- sys.exit(1) on missing DATABASE_URL: FOUND
- SELECT id FROM ventas WHERE consecutivo idempotency check: FOUND
- >= 80 lines: 308 lines
- No asyncio import: CONFIRMED
