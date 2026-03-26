# Phase 3: Ventas - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Migrar la escritura y lectura de ventas desde Sheets/Excel a Postgres. Cuando un vendedor confirma el método de pago en Telegram, la venta se escribe en `ventas` + `ventas_detalle` en Postgres (en paralelo con Sheets). `/cerrar` sincroniza Sheets → Postgres Y Excel (triple-write). `_leer_excel_rango()` en `routers/shared.py` se reemplaza por queries a Postgres. Los endpoints `/ventas/hoy` y `/ventas/historial` del dashboard leen desde Postgres. Un script migra ventas históricas del `ventas.xlsx` activo a Postgres. Cambios en `ai.py`, `ventas_state.py` de lógica de negocio, y estructura del frontend están fuera de scope.

</domain>

<decisions>
## Implementation Decisions

### Escritura en `ventas_state.py` (VEN-01)
- **D-01:** La escritura a Postgres ocurre dentro de `registrar_ventas_con_metodo()` en `ventas_state.py` directamente — lazy `import db` dentro de la función, igual que el patrón de Fases 1-2. No se crea un módulo separado.
- **D-02:** El consecutivo sigue generándose con `obtener_siguiente_consecutivo()` (lee el Excel); Postgres almacena ese valor en `ventas.consecutivo`. Sin cambios en la lógica de numeración.
- **D-03:** El INSERT a `ventas` y `ventas_detalle` es non-fatal: `except Exception → logger.warning`. Si Postgres falla, la venta igual queda en Sheets/Excel.
- **D-04:** Secuencia: primero `INSERT INTO ventas` (obtiene `venta_id`), luego `INSERT INTO ventas_detalle` para cada ítem del mismo consecutivo. Usar `execute_returning` para obtener el `id` de la venta recién insertada.

### `/cerrar` (VEN-02)
- **D-05:** Triple-write: `/cerrar` escribe Sheets → Postgres Y Excel. El write a Excel se mantiene durante la transición (Fase 5 lo elimina). Nuevo bloque en `comando_cerrar_dia()` en `handlers/comandos.py` que llama a la función de sincronización Postgres después del write a Excel existente.
- **D-06:** El write a Postgres en `/cerrar` también es non-fatal — si falla, el cierre diario igual se completa con Excel+Sheets.

### Reemplazo de `_leer_excel_rango()` (VEN-03)
- **D-07:** `_leer_excel_rango()` se reemplaza por una nueva función `_leer_ventas_postgres(dias, mes_actual)` en `routers/shared.py`. La firma externa que usan los routers no cambia.
- **D-08:** Fallback: si `DB_DISPONIBLE` es False o la query falla, se llama a la implementación Excel original. Igual que el patrón de fallback usado en fases anteriores.
- **D-09:** El formato de respuesta JSON de `_leer_ventas_postgres()` es idéntico al de `_leer_excel_rango()` — mismas claves: `num`, `fecha`, `hora`, `id_cliente`, `cliente`, `producto`, `cantidad`, `unidad_medida`, `precio_unitario`, `total`, `alias`, `vendedor`, `metodo`.

### Endpoints `/ventas/hoy` y `/ventas/historial` (VEN-04)
- **D-10:** `/ventas/hoy` mantiene Sheets como fuente primaria para el día actual (Sheets tiene datos en tiempo real; Postgres no tiene todo hasta que `/cerrar` sincroniza). Postgres se usa como fallback si Sheets falla o está vacío.
- **D-11:** `/ventas/historial` y endpoints que leen rangos históricos (`/ventas/semana`, `/ventas/resumen`, `/ventas/top`) usan Postgres como fuente primaria vía `_leer_ventas_postgres()`.

### Migración de ventas históricas (VEN-05)
- **D-12:** El script `migrate_ventas.py` lee solo el `ventas.xlsx` activo (todas sus hojas mensuales). No migra archivos archivados externos.
- **D-13:** Idempotencia por UPSERT en `ventas_detalle` usando `(consecutivo, producto_nombre)` como clave de conflicto. El script es seguro de re-ejecutar.
- **D-14:** Ejecución manual vía `railway run python migrate_ventas.py` — igual que `migrate_memoria.py` y `migrate_historico.py`.

### Claude's Discretion
- Índice de constraint para el UPSERT en `ventas_detalle` (`UNIQUE(venta_id, producto_nombre)` o `UNIQUE` en `ventas` por `consecutivo`)
- Cómo resolver `cliente_id` (FK a `clientes`) durante la migración cuando el cliente es "Consumidor Final" — usar NULL o insertar un cliente por defecto
- Tamaño de batch para el script de migración
- Cómo mapear `alias` del Excel al campo `alias_usado` en `ventas_detalle`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Schema y Tablas
- `db.py` lines 168-197 — Schema completo de `ventas`, `ventas_detalle` e índices; `query_one`, `query_all`, `execute`, `execute_returning` API
- `MIGRATION.md` §"Phase 3" — plan de migración de ventas, archivos a modificar

### Código a Modificar
- `ventas_state.py` lines 143-224 — `registrar_ventas_con_metodo()`: aquí va el INSERT a Postgres (D-01 a D-04)
- `routers/shared.py` — `_leer_excel_rango()`: reemplazar por `_leer_ventas_postgres()` con fallback (D-07 a D-09)
- `routers/ventas.py` — endpoints `/ventas/hoy`, `/ventas/semana`, `/ventas/resumen`, `/ventas/top`; ajustar fuentes según D-10 y D-11
- `handlers/comandos.py` lines 1101-1327 — `comando_cerrar_dia()`: agregar triple-write Postgres (D-05, D-06)

### Patrones de Fases Anteriores
- `.planning/phases/01-db-infra-cat-logo-inventario/01-CONTEXT.md` — decisiones D-03, D-04, D-05 sobre DB_DISPONIBLE y fallback
- `.planning/phases/02-hist-rico-gastos-caja/` — patrón de dual-write non-fatal con lazy import db

### Requisitos
- `REQUIREMENTS.md` §"Ventas (Fase 3)" — VEN-01 a VEN-06

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db.execute_returning(sql, params)` — retorna el dict de la fila insertada; usar para obtener `venta_id` después de INSERT en `ventas`
- `db.execute(sql, params)` — para los INSERT en `ventas_detalle` (no necesita retorno)
- `db.DB_DISPONIBLE` — flag global; chequear antes de cualquier write/read a Postgres
- `_leer_excel_rango()` en `routers/shared.py` — mantener como fallback; `_leer_ventas_postgres()` la llama si DB falla

### Established Patterns
- Lazy `import db` dentro de la función (no top-level) — evita circular import; usado en `memoria.py`, `routers/historico.py`, `routers/caja.py`
- Write non-fatal: `try: ... except Exception as e: logger.warning(f"Postgres write failed: {e}")` — bot no puede caer
- `DB_DISPONIBLE` check antes de write: `if not db.DB_DISPONIBLE: return` al inicio del bloque Postgres
- `logger = logging.getLogger("ferrebot.<módulo>")` — mantener por módulo

### Integration Points
- `ventas_state.py::registrar_ventas_con_metodo()` — punto de entrada principal; llamado desde `handlers/callbacks.py` al confirmar pago
- `routers/shared.py::_leer_excel_rango()` — usada por `routers/ventas.py`, `routers/reportes.py`, `routers/historico.py` (todos los routers que muestran ventas)
- `handlers/comandos.py::comando_cerrar_dia()` — el bloque de write a Excel es el punto donde agregar el write a Postgres

</code_context>

<specifics>
## Specific Ideas

- No crear un módulo `ventas_pg.py` separado — toda la lógica Postgres va inline dentro de las funciones existentes, igual que se hizo en Fases 1-2
- Durante Fase 3: Sheets sigue siendo la fuente de verdad para el día actual en `/ventas/hoy`; Postgres es la nueva fuente para historial y rangos

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-ventas*
*Context gathered: 2026-03-26*
