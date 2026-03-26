# Phase 3: Ventas - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 03-ventas
**Areas discussed:** Escritura en ventas_state.py, Scope de /cerrar, Migración histórica, /ventas/hoy fuente de datos

---

## Escritura en `ventas_state.py`

| Option | Description | Selected |
|--------|-------------|----------|
| Dentro de `ventas_state.py` directamente | Lazy import db, INSERT non-fatal inline, mismo patrón que Fases 1-2 | ✓ |
| Helper separado `ventas_pg.py` | Nueva función `guardar_venta_postgres()` aislada y testeable | |

**User's choice:** Dentro de `ventas_state.py`
**Notes:** Consistente con el patrón establecido en fases anteriores.

---

## Consecutivo al escribir en Postgres

| Option | Description | Selected |
|--------|-------------|----------|
| Mantener `obtener_siguiente_consecutivo()` | Consecutivo sigue generándose desde Excel/memoria; Postgres solo almacena el valor | ✓ |
| Migrar a SEQUENCE de Postgres | Postgres genera el número; elimina dependencia del Excel | |

**User's choice:** Mantener `obtener_siguiente_consecutivo()` en memoria/Excel
**Notes:** Evita cambios en la lógica de numeración durante la transición.

---

## Scope de `/cerrar` (VEN-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Solo Postgres | `/cerrar` escribe Sheets → Postgres, ya no al Excel | |
| Triple-write | `/cerrar` escribe Sheets → Postgres Y Excel | ✓ |

**User's choice:** Triple-write
**Notes:** Excel sigue actualizado durante la transición; Fase 5 elimina el write a Excel.

---

## Migración de ventas históricas — Fuente

| Option | Description | Selected |
|--------|-------------|----------|
| Solo `ventas.xlsx` activo | Solo el archivo actual con todas sus hojas mensuales | ✓ |
| `ventas.xlsx` + archivos archivados | Incluye Excel de meses/años anteriores en Drive | |

**User's choice:** Solo `ventas.xlsx` activo

---

## Migración de ventas históricas — Idempotencia

| Option | Description | Selected |
|--------|-------------|----------|
| UPSERT por `(consecutivo, producto_nombre)` | Mismo patrón que fases anteriores. Seguro re-ejecutar | ✓ |
| Borrar y re-insertar por rango de fechas | Más agresivo, garantiza datos limpios pero borra lo existente | |

**User's choice:** UPSERT por `(consecutivo, producto_nombre)`

---

## `/ventas/hoy` fuente de datos

| Option | Description | Selected |
|--------|-------------|----------|
| Postgres primaria, Sheets fallback | Consistente con la dirección de la migración | |
| Sheets sigue primaria para el día actual | Sheets tiene datos en tiempo real; Postgres no tiene todo hasta `/cerrar` | ✓ |

**User's choice:** Sheets sigue siendo primaria para el día actual, Postgres solo para historial
**Notes:** Conservador y correcto: Postgres solo recibe los datos completos del día al ejecutar `/cerrar`.

---

## Claude's Discretion

- Índice de constraint para el UPSERT en `ventas_detalle`
- Cómo resolver `cliente_id` FK para "Consumidor Final" en la migración
- Tamaño de batch del script de migración
- Mapeo de campo `alias` del Excel a `alias_usado` en `ventas_detalle`
