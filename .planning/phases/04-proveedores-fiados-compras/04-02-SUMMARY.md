---
phase: 04-proveedores-fiados-compras
plan: "02"
subsystem: proveedores-fiados-compras
tags: [postgres, read-migration, proveedores, fiados, compras]
dependency_graph:
  requires: [04-01]
  provides: [PROV-04, PROV-05, PROV-06]
  affects: [memoria.py, routers/caja.py, routers/proveedores.py]
tech_stack:
  added: []
  patterns:
    - Postgres-first read with JSON fallback (same as gastos/historico pattern)
    - json_agg with FILTER (WHERE id IS NOT NULL) to avoid NULL rows in aggregation
    - Non-fatal try/except Postgres sync after Drive upload
key_files:
  modified:
    - memoria.py
    - routers/caja.py
    - routers/proveedores.py
decisions:
  - listar_facturas uses json_agg ORDER BY created_at for deterministic abono ordering
  - cargar_fiados reconstructs running saldo in Python after fetching ordered movements
  - GET /compras maps producto_nombre column to "producto" key to preserve API response shape
  - Photo sync is non-fatal — Drive remains authoritative; Postgres gets best-effort URL update
metrics:
  duration_minutes: 2
  completed_date: "2026-03-27"
  tasks_completed: 2
  files_modified: 3
---

# Phase 04 Plan 02: Proveedores/Fiados/Compras Read Migration Summary

Postgres-first reads for listar_facturas(), cargar_fiados(), and GET /compras; non-fatal photo URL sync to Postgres after Drive uploads.

## What Was Built

### Task 1 — memoria.py: Postgres-first listar_facturas() and cargar_fiados()

`listar_facturas()` now queries `facturas_proveedores` JOIN `facturas_abonos` using `json_agg` with `FILTER (WHERE fa.id IS NOT NULL)` to prevent NULL rows when a factura has no abonos. Results are ordered by `fecha DESC`. Falls back to `cargar_memoria().get("cuentas_por_pagar", [])` on any Postgres error.

`cargar_fiados()` queries `fiados` JOIN `fiados_historial` and reconstructs running saldo in Python by iterating movements ordered by `created_at`. The authoritative current balance comes from `fiados.deuda`; the per-movement `saldo` field is computed as a cumulative sum. Falls back to `cargar_memoria().get("fiados", {})` on any Postgres error.

Both functions use lazy `import db as _db` to avoid circular imports, and wrap the entire Postgres block in `except Exception as e: logger.warning(...)`.

### Task 2 — routers/caja.py: Postgres-first GET /compras

GET /compras now queries the `compras` table with a date range filter (`fecha >= %s AND fecha <= %s`). The `producto_nombre` column is mapped to the `"producto"` key in the response to preserve the existing API shape (D-04). Falls back to JSON `historial_compras` on Postgres unavailability.

### Task 2 — routers/proveedores.py: Non-fatal photo URL sync

`subir_foto_factura` and `subir_foto_abono` both add a non-fatal Postgres UPDATE after the `guardar_memoria()` call. For facturas: `UPDATE facturas_proveedores SET foto_url, foto_nombre WHERE id`. For abonos: fetches the latest `facturas_abonos` row via `query_one` then updates it. Both sync blocks are wrapped in `try/except` with `logger.warning` — Drive upload flow is unchanged.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1    | 2ccfcb6 | feat(04-02): Postgres-first reads in listar_facturas() and cargar_fiados() |
| 2    | e15cd71 | feat(04-02): Postgres-first GET /compras and non-fatal photo URL sync |

## Verification

All grep acceptance criteria passed:
- `SELECT fp.id, fp.proveedor` in memoria.py
- `LEFT JOIN facturas_abonos fa ON fa.factura_id = fp.id` in memoria.py
- `FILTER (WHERE fa.id IS NOT NULL)` in memoria.py
- `LEFT JOIN fiados_historial fh ON fh.fiado_id = f.id` in memoria.py
- `SELECT fecha::text, hora::text, proveedor, producto_nombre` in routers/caja.py
- `FROM compras` in routers/caja.py
- `UPDATE facturas_proveedores SET foto_url` in routers/proveedores.py
- `UPDATE facturas_abonos SET foto_url` in routers/proveedores.py

Test suite: 201/201 tests passed, 0 failures.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

Files verified:
- FOUND: /c/Users/Dell/Documents/GitHub/bot-ventas-ferreteria/memoria.py (modified)
- FOUND: /c/Users/Dell/Documents/GitHub/bot-ventas-ferreteria/routers/caja.py (modified)
- FOUND: /c/Users/Dell/Documents/GitHub/bot-ventas-ferreteria/routers/proveedores.py (modified)

Commits verified:
- FOUND: 2ccfcb6
- FOUND: e15cd71
