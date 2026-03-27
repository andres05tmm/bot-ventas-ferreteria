---
phase: "05-limpieza"
plan: "01"
subsystem: "persistence"
tags: ["drive-cutover", "sheets-cutover", "postgres-primary", "cleanup"]
dependency_graph:
  requires: []
  provides: ["postgres-primary-ventas", "drive-free-transactional-flow"]
  affects: ["start.py", "memoria.py", "excel.py", "routers/ventas.py", "handlers/callbacks.py"]
tech_stack:
  added: []
  patterns: ["postgres-primary-with-excel-fallback", "no-drive-writes-transactional"]
key_files:
  created: []
  modified:
    - start.py
    - memoria.py
    - excel.py
    - routers/ventas.py
    - handlers/callbacks.py
decisions:
  - "Mantener firma guardar_memoria(memoria, urgente=False) — 151+ callers; urgente ahora es no-op pero no rompe callers"
  - "obtener_siguiente_consecutivo usa Postgres MAX(consecutivo) como primario (no Sheets)"
  - "/ventas/resumen reemplaza Sheets con Postgres para ventas del dia (consistente con /ventas/hoy)"
metrics:
  duration_minutes: 7
  completed_date: "2026-03-27"
  tasks_completed: 3
  files_modified: 5
---

# Phase 05 Plan 01: Drive/Sheets Cutover — Transactional Flow Summary

Eliminacion de todas las llamadas a Drive y Sheets en el flujo transaccional. Postgres es ahora la fuente de verdad para ventas; Excel local sigue como fallback de lectura pero no se sincroniza con Drive.

## What Was Built

Cinco archivos modificados para eliminar dependencias de Drive y Sheets del camino critico:

**start.py** — Bloque `_restaurar_memoria()` eliminado (Drive no es fuente de verdad para `memoria.json`). Excel watcher thread eliminado (constantes `EXCEL_WATCH_INTERVAL`, `EXCEL_NOMBRE`, funciones `_get_excel_modified_time`, `_run_excel_watcher`, thread `excel_watcher_thread`). `historico_safety_thread` permanece intacto.

**memoria.py** — Bloque `if not _bloquear_subida_drive` con `subir_a_drive` y `subir_a_drive_urgente` eliminado de `guardar_memoria()`. JSON local y sincronizacion a Postgres permanecen. Firma publica sin cambios.

**excel.py** — 9 bloques `subir_a_drive(config.EXCEL_FILE)` eliminados de: `inicializar_excel`, `guardar_cliente_nuevo`, `borrar_cliente`, `guardar_venta_excel`, `borrar_venta_excel`, funcion de fiados, `registrar_compra_en_excel`, `actualizar_hoja_inventario`. `sheets_agregar_venta` y `sheets_borrar_fila` eliminados. `obtener_siguiente_consecutivo` ahora usa `MAX(consecutivo)` de Postgres como primario en lugar de Sheets.

**routers/ventas.py** — `/ventas/hoy` reescrito con Postgres como fuente primaria y Excel como fallback (eliminando Sheets como fuente principal). `/ventas/resumen` idem para el calculo de ventas del dia. `eliminar_linea_venta` limpiado: sin Drive ni Sheets block. `editar_venta` limpiado: sin Drive ni Sheets; agrega `UPDATE ventas_detalle` y `UPDATE ventas` en Postgres.

**handlers/callbacks.py** — Bloque de borrado de consecutivo reemplazado: `sheets_borrar_consecutivo` sustituido por `db.execute("DELETE FROM ventas_detalle ...")` + `db.execute("DELETE FROM ventas ...")`.

## Verification Results

```
OK: start.py
OK: memoria.py
OK: excel.py
OK: routers/ventas.py
OK: handlers/callbacks.py

=== subir_a_drive / descargar_de_drive (debe vaciar) ===
(sin resultados)

=== Sheets writes (debe vaciar) ===
(sin resultados)

=== _restaurar_memoria / excel_watcher (debe vaciar) ===
(sin resultados)

=== drive.py existe ===
drive.py
```

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 — start.py | `50e66da` | Eliminar _restaurar_memoria y excel_watcher |
| Task 2 — memoria.py | `53ef073` | Eliminar Drive uploads de guardar_memoria |
| Task 3 — excel.py, ventas.py, callbacks.py | `8ca9597` | Eliminar Drive/Sheets del flujo transaccional |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] obtener_siguiente_consecutivo usaba Sheets como primario**
- **Found during:** Task 3 — verificacion final del done criteria
- **Issue:** `excel.py:obtener_siguiente_consecutivo` tenia `sheets_leer_ventas_del_dia()` como fuente primaria; el done criteria especificaba que este simbolo deberia desaparecer de excel.py
- **Fix:** Reemplazar bloque Sheets con consulta `SELECT MAX(consecutivo) FROM ventas WHERE fecha::date = %s::date` via `db.query_one`; fallback a Excel intacto
- **Files modified:** excel.py
- **Commit:** 8ca9597

**2. [Rule 2 - Missing] /ventas/resumen usaba Sheets para ventas del dia**
- **Found during:** Task 3 — revision de sheets_leer_ventas_del_dia en routers/ventas.py
- **Issue:** `/ventas/resumen` tenia un bloque "Sheets — tolerante a fallo" para calcular `total_hoy` y `pedidos_hoy`; consistente con el objetivo del plan, debe usar Postgres
- **Fix:** Reemplazar con `_leer_ventas_postgres(dias=1)` con fallback a `_leer_excel_rango(dias=1)`
- **Files modified:** routers/ventas.py
- **Commit:** 8ca9597

## Known Stubs

None — todos los cambios conectan a Postgres real o Excel local como fallback.

## Self-Check: PASSED

All 5 modified files exist. All 3 task commits verified in git log.
