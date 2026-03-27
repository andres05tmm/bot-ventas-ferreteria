# Phase 5: Limpieza - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-03-26
**Phase:** 05-limpieza
**Mode:** discuss
**Areas discussed:** Sheets cutover, Drive + memoria.json, Excel watcher, Export endpoint

## Discussion

### Sheets Cutover

| Question | Options Presented | Selected |
|----------|------------------|----------|
| Borrar/editar ventas del día (sheets_borrar/editar_consecutivo) | Reemplazar con Postgres / Solo quitar escrituras / Eliminar funcionalidad | Reemplazar con Postgres |
| Uploads de ventas.xlsx a Drive | Eliminar todos los uploads / Mantener upload del Excel | Eliminar todos los uploads |

### Drive + memoria.json

| Question | Options Presented | Selected |
|----------|------------------|----------|
| Destino de memoria.json y Drive I/O | Eliminar Drive I/O, mantener JSON local / Eliminar JSON completamente | Eliminar Drive I/O, mantener JSON local |

### Excel Watcher

| Question | Options Presented | Selected |
|----------|------------------|----------|
| Hilo _run_excel_watcher | Eliminar el hilo completo / Redirigir a Postgres | Eliminar el hilo completo |

### Export Endpoint

| Question | Options Presented | Selected |
|----------|------------------|----------|
| Datos que incluye | Todas las ventas / Por período configurable / Replicar formato actual | Todas las ventas |
| Columnas | Columnas operativas / Todas las columnas de Postgres | Columnas operativas |

## Corrections Made

No corrections — all recommended defaults selected.

## Prior Decisions Applied

- Phase 3 D-10 (Sheets primary para /ventas/hoy) → reemplazado por D-02 (Postgres primary)
- Phase 3 D-05 (triple-write en /cerrar, "Fase 5 lo elimina") → eliminado en D-04
