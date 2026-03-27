# Phase 5: Limpieza - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Eliminar todas las dependencias de Drive y Sheets para datos estructurados. Postgres queda como única fuente de verdad. Drive queda solo para fotos de facturas. El Excel se genera bajo demanda desde Postgres vía un nuevo endpoint. El arranque del sistema ya no descarga nada desde Drive.

Fuera de scope: migrar campos `notas` u otros residuales de memoria.json a Postgres, modificar la estructura del dashboard, cambiar la lógica de ai.py.

</domain>

<decisions>
## Implementation Decisions

### Sheets Cutover

- **D-01:** Eliminar `sheets_agregar_venta()` de `excel.py:registrar_venta_en_excel()`. Sheets deja de recibir ventas nuevas.
- **D-02:** `/ventas/hoy` pasa de Sheets-primary a Postgres-primary. Nuevo orden de fuentes: Postgres → Excel (fallback). La lectura de `sheets_leer_ventas_del_dia()` se elimina de ese endpoint.
- **D-03:** `sheets_borrar_consecutivo()` y `sheets_editar_consecutivo()` se reemplazan con operaciones DELETE/UPDATE directas en Postgres (`ventas` + `ventas_detalle`). Los callers en `handlers/callbacks.py` y `routers/ventas.py` se actualizan para usar `db.execute()`.
- **D-04:** Todos los uploads de `ventas.xlsx` a Drive en `excel.py` (~6 llamadas a `subir_a_drive(config.EXCEL_FILE)`) se eliminan. El Excel local sigue escribiéndose como fallback de lectura, pero ya no va a Drive.

### Drive + memoria.json

- **D-05:** `_restaurar_memoria()` eliminada de `start.py`. El arranque ya no descarga `memoria.json` desde Drive. Si el archivo no existe localmente, el bot arranca con estado vacío (comportamiento ya manejado).
- **D-06:** `guardar_memoria()` en `memoria.py` deja de llamar a `subir_a_drive_urgente()` y `subir_a_drive()`. El JSON local (`memoria.json`) sigue escribiéndose como cache para campos no migrados (notas, config residual).
- **D-07:** `drive.py` permanece en el codebase (sigue siendo necesario para fotos de facturas). Solo se eliminan los call-sites de Drive para datos estructurados.

### Excel Watcher

- **D-08:** Eliminar el hilo `_run_excel_watcher` y la función `_get_excel_modified_time` de `start.py`. El cat logo ya vive en Postgres; reimportar desde Excel se hace manualmente vía `migrate_memoria.py` si es necesario.
- **D-09:** Eliminar también el hilo de arranque (`threading.Thread(target=_run_excel_watcher, ...)`). `start.py` queda más limpio sin hilos de Drive.

### Export Endpoint (CLEAN-01)

- **D-10:** Nuevo endpoint `GET /export/ventas.xlsx` en `routers/ventas.py` (o router dedicado). Genera el archivo en memoria con `openpyxl` y lo devuelve como `FileResponse` o `StreamingResponse`.
- **D-11:** Contenido: todas las ventas en Postgres sin filtro de fecha. Una sola hoja plana (`Ventas`).
- **D-12:** Columnas: `consecutivo`, `fecha`, `hora`, `cliente`, `producto`, `cantidad`, `unidad_medida`, `precio_unitario`, `total`, `vendedor`, `metodo_pago`. Mismo orden legible para el dueño.
- **D-13:** Query base: JOIN `ventas` + `ventas_detalle`. Ordenado por `fecha DESC, consecutivo DESC`.

### Claude's Discretion

- Nombre del router/archivo para el endpoint de export (puede ir en `routers/ventas.py` o `routers/export.py`)
- Nombre de la hoja en el Excel exportado
- Headers HTTP exactos (`Content-Disposition`, `Content-Type`)
- Manejo de errores del endpoint de export (DB unavailable)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requisitos de Fase 5
- `.planning/REQUIREMENTS.md` §Limpieza y Finalización — CLEAN-01 a CLEAN-06, criterios de aceptación

### Código afectado (lectura obligatoria)
- `start.py` — `_restaurar_memoria()`, `_run_excel_watcher`, `_get_excel_modified_time`, hilos de arranque
- `memoria.py` — `guardar_memoria()` dual-write a Drive; `cargar_memoria()` (interfaz pública intacta)
- `excel.py` — `registrar_venta_en_excel()` con `sheets_agregar_venta()` + ~6 `subir_a_drive(EXCEL_FILE)`
- `routers/ventas.py` — `/ventas/hoy` three-tier fallback (Sheets → Postgres → Excel); `sheets_borrar_consecutivo`; `sheets_editar_consecutivo`
- `handlers/callbacks.py` — llamada a `sheets_borrar_consecutivo` en el handler de borrado
- `sheets.py` — funciones a reemplazar: `sheets_agregar_venta`, `sheets_borrar_consecutivo`, `sheets_editar_consecutivo`, `sheets_leer_ventas_del_dia`
- `drive.py` — permanece; solo se eliminan call-sites de datos estructurados
- `db.py` — `execute()`, `query_all()` para las nuevas operaciones DELETE/UPDATE en Postgres

### Decisiones de fases anteriores relevantes
- `.planning/phases/03-ventas/03-CONTEXT.md` — D-10 (reemplazado por D-02), D-05 (reemplazado por D-04)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db.execute(sql, params)` / `db.query_all(sql, params)` — patrón establecido para DELETE/UPDATE en Postgres
- `openpyxl` ya está en `requirements.txt` y usado en `excel.py` — reutilizable para generar el export
- `StreamingResponse` / `FileResponse` de FastAPI — patrón para servir archivos binarios desde routers
- `_leer_ventas_postgres(dias, mes_actual)` en `routers/shared.py` — query base reutilizable para el export

### Established Patterns
- Drive removals anteriores (HIS-04 en Fase 2): se eliminaron call-sites en routers, no se tocó `drive.py` — mismo patrón aquí
- Fallback non-fatal: `except Exception → logger.warning` — mantener en qualquier código que quede con Excel como fallback
- Lazy import de `db` dentro de funciones (no top-level) — patrón establecido en fases anteriores para evitar circular imports

### Integration Points
- `start.py` línea 63: `_restaurar_memoria()` — eliminar esta llamada
- `start.py` ~línea 130+: `threading.Thread(target=_run_excel_watcher)` — eliminar
- `memoria.py` líneas 252-256: bloque `subir_a_drive_urgente` / `subir_a_drive` en `guardar_memoria()` — eliminar
- `excel.py` líneas 173, 460, 496, 513, 604, 620, 699, 1033, 1082: `subir_a_drive(config.EXCEL_FILE)` — eliminar
- `excel.py` línea 514/606: `from sheets import sheets_agregar_venta` + llamada — eliminar
- `routers/ventas.py` línea 20: `from sheets import sheets_leer_ventas_del_dia` + uso en `/ventas/hoy` — reemplazar con Postgres-primary
- `routers/ventas.py` líneas 510-511, 570, 639: `sheets_borrar/editar_consecutivo` — reemplazar con `db.execute()`
- `handlers/callbacks.py` línea 303: `sheets_borrar_consecutivo` — reemplazar con `db.execute()`
- Nuevo endpoint `GET /export/ventas.xlsx` — agregar a `routers/ventas.py` o nuevo `routers/export.py`

</code_context>

<specifics>
## Specific Ideas

- El export devuelve todas las ventas históricas (sin filtro de fecha), una hoja plana, columnas operativas: `consecutivo, fecha, hora, cliente, producto, cantidad, unidad_medida, precio_unitario, total, vendedor, metodo_pago`
- `memoria.json` local se mantiene como cache (no desaparece), solo se elimina el I/O con Drive
- El watcher del Excel se elimina completamente — actualizaciones de catálogo van por `migrate_memoria.py` manual

</specifics>

<deferred>
## Deferred Ideas

- Migrar campos residuales de `memoria.json` (notas, config) a tabla `config_sistema` en Postgres — no está en scope de Fase 5
- Watcher de Drive adaptado para actualizar Postgres en vez de memoria.json — fuera de scope
- Export con filtro de fechas (`?desde=&hasta=`) — fuera de scope de Fase 5
- Export de histórico (`GET /export/historico.xlsx`) — v2 requirement (EXP-01), fuera de scope
- Eliminar `memoria.json` local completamente — requiere migrar campos residuales primero

None — analysis stayed within phase scope.

</deferred>

---

*Phase: 05-limpieza*
*Context gathered: 2026-03-26*
