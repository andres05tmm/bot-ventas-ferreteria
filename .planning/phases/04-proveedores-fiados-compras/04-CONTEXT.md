# Phase 4: Proveedores + Fiados + Compras - Context

**Gathered:** 2026-03-26 (assumptions mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

Migrar las cuentas por pagar a proveedores (`cuentas_por_pagar` en `memoria.json`), los fiados de clientes (`fiados` en `memoria.json`) y el historial de compras de mercancía a Postgres. Los routers de proveedores y compras leen desde Postgres con fallback a JSON/Excel. Las fotos de facturas siguen en Google Drive sin cambios. Al finalizar, el tab Proveedores del dashboard muestra facturas y abonos desde Postgres.

</domain>

<decisions>
## Implementation Decisions

### Write Path
- **D-01:** Las cuatro funciones de escritura en `memoria.py` reciben bloques de Postgres inline: `registrar_factura_proveedor()`, `registrar_abono_factura()`, `guardar_fiado_movimiento()`, y `_registrar_historial_compra()`. Mismo patrón que Fases 1-3: lazy `import db` dentro de la función, guard `if not db.DB_DISPONIBLE: return/continue`, non-fatal `try/except Exception → logger.warning`.
- **D-02:** No se crea ningún módulo nuevo (no `proveedores_pg.py`). Toda la lógica Postgres va inline dentro de las funciones existentes de `memoria.py`.

### Read Path: GET /compras
- **D-03:** `GET /compras` en `routers/caja.py` (líneas 396-427) se reescribe con Postgres como fuente primaria (query a tabla `compras`), con el bloque `mem.get("historial_compras")` como fallback — igual al patrón de `GET /gastos` ya implementado en el mismo archivo.
- **D-04:** El formato de respuesta JSON de `GET /compras` no cambia: mismas claves `fecha`, `hora`, `proveedor`, `producto`, `cantidad`, `costo_unitario`, `costo_total`.

### Read Path: Proveedores (facturas)
- **D-05:** `listar_facturas()` en `memoria.py` se actualiza para leer desde Postgres (`facturas_proveedores` + `facturas_abonos`) con fallback a `cuentas_por_pagar` en `memoria.json`. El router `routers/proveedores.py` no necesita cambios — solo consume `listar_facturas()`.
- **D-06:** El formato de cada factura retornado se mantiene idéntico: `id`, `proveedor`, `descripcion`, `total`, `pagado`, `pendiente`, `estado`, `fecha`, `foto_url`, `foto_nombre`, `abonos[]`.

### Photo URL en Postgres
- **D-07:** Las fotos de facturas siguen subiéndose a Drive sin cambios (PROV-05). Después del upload, los endpoints `POST /proveedores/facturas/{fac_id}/foto` y `POST /proveedores/abonos/{fac_id}/foto` agregan un `UPDATE` non-fatal en Postgres para sincronizar `foto_url` y `foto_nombre`. Sin cambios en el flujo Drive.

### Fiados: Scope Acotado
- **D-08:** Los fiados no tienen endpoint REST ni tab en el dashboard — se usan solo desde Telegram (`/fiados`, `/abonar`). La migración agrega dual-write solo en `guardar_fiado_movimiento()` en `memoria.py`. PROV-06 ("Tab Proveedores") cubre facturas únicamente; no se agrega `GET /proveedores/fiados`.
- **D-09:** `cargar_fiados()` en `memoria.py` se actualiza para leer desde la tabla `fiados` + `fiados_historial` con fallback a `memoria.json["fiados"]`.

### Scripts de Migración
- **D-10:** Tres scripts separados (o uno combinado): `migrate_proveedores.py` (cuentas_por_pagar → facturas_proveedores + facturas_abonos), `migrate_fiados.py` (fiados dict → fiados + fiados_historial), `migrate_compras.py` (historial_compras → compras). Ejecución manual vía `railway run python migrate_*.py`. Idempotentes con UPSERT o INSERT ON CONFLICT DO NOTHING.
- **D-11:** `migrate_compras.py` usa `historial_compras` de `memoria.json` como fuente (no el Excel). Razón: `memoria.json["historial_compras"]` es la fuente canónica para el bot; el Excel "Compras" sheet es secundario.

### Claude's Discretion
- Constraint de idempotencia para `migrate_proveedores.py` (facturas tienen ID alfanumérico `FAC-001` — usar `ON CONFLICT (id) DO NOTHING`)
- Constraint de idempotencia para `migrate_fiados.py` (fiados no tienen ID estable en JSON — usar nombre como clave de deduplicación)
- Tamaño de batch para los scripts de migración
- Exacta estructura de la query para `listar_facturas()` (JOIN entre `facturas_proveedores` y `facturas_abonos`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Schema y Tablas
- `db.py` lines 234-309 — Schema de `fiados`, `fiados_historial`, `facturas_proveedores`, `facturas_abonos`, `compras`; API `query_one`, `query_all`, `execute`, `execute_returning`

### Código a Modificar
- `memoria.py` lines 962-980 — `_registrar_historial_compra()`: agregar INSERT a `compras` (D-01)
- `memoria.py` lines 1264-1286 — `guardar_fiado_movimiento()`: agregar UPSERT a `fiados` + INSERT a `fiados_historial` (D-01)
- `memoria.py` lines 1518-1555 — `registrar_factura_proveedor()`: agregar INSERT a `facturas_proveedores` (D-01)
- `memoria.py` lines 1556-1617 — `registrar_abono_factura()`: agregar INSERT a `facturas_abonos` + UPDATE a `facturas_proveedores` (D-01)
- `memoria.py` lines 1238-1241 — `cargar_fiados()`: leer desde `fiados` + `fiados_historial` con fallback (D-09)
- `memoria.py` lines 1619-1625 — `listar_facturas()`: leer desde Postgres con fallback (D-05)
- `routers/caja.py` lines 396-427 — `GET /compras`: reemplazar JSON read por Postgres-first (D-03)
- `routers/proveedores.py` lines 91-139 — foto upload factura: agregar UPDATE no-fatal a Postgres (D-07)
- `routers/proveedores.py` lines 179-230 — foto upload abono: agregar UPDATE no-fatal a Postgres (D-07)

### Patrones de Fases Anteriores
- `.planning/phases/03-ventas/03-CONTEXT.md` — D-01, D-03, D-07, D-08: write non-fatal, lazy import, DB_DISPONIBLE guard, fallback pattern
- `routers/caja.py` lines 309-391 — `GET /gastos`: ejemplo del patrón Postgres-first con JSON fallback ya implementado en el mismo archivo

### Requisitos
- `REQUIREMENTS.md` §"Proveedores, Fiados y Compras (Fase 4)" — PROV-01 a PROV-06

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db.execute_returning(sql, params)` — usar para INSERT en `facturas_proveedores` (retorna el id generado, aunque aquí el id ya existe como VARCHAR)
- `db.execute(sql, params)` — para INSERTs en `facturas_abonos`, `fiados_historial`, `compras`
- `db.query_all(sql, params)` — para `listar_facturas()` y `cargar_fiados()` desde Postgres
- `db.DB_DISPONIBLE` — guard global; chequear antes de cada write/read
- `GET /gastos` en `routers/caja.py` lines 309-391 — implementación de referencia para el patrón Postgres-first + JSON fallback en el mismo archivo

### Established Patterns
- Lazy `import db` dentro de la función (no top-level) — `memoria.py`, `routers/historico.py`, `routers/caja.py`
- Write non-fatal: `try: ... except Exception as e: logger.warning(f"Postgres write failed: {e}")`
- `DB_DISPONIBLE` check: `if not db.DB_DISPONIBLE: return` al inicio del bloque Postgres
- Fallback en reads: `if db.DB_DISPONIBLE: ... else: return mem.get(...)`

### Integration Points
- `routers/proveedores.py` — consume `listar_facturas()`, `registrar_factura_proveedor()`, `registrar_abono_factura()` via lazy imports; el router no necesita cambios si las funciones de `memoria.py` manejan Postgres internamente
- `handlers/comandos.py` — `abonar_fiado()` delega a `guardar_fiado_movimiento()`; el dual-write en `guardar_fiado_movimiento()` cubre el camino Telegram sin tocar handlers
- `_registrar_historial_compra()` es llamada exclusivamente desde `registrar_compra()` en `memoria.py`; agregar el INSERT ahí cubre tanto el bot Telegram como el endpoint `POST /compras`

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- `GET /proveedores/fiados` REST endpoint — fiados no tienen tab en dashboard; agregar endpoint REST es una feature nueva
- Sincronización bidireccional foto_url Drive ↔ Postgres en tiempo real — la foto va primero a Drive, luego UPDATE en Postgres es suficiente para Phase 4

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-proveedores-fiados-compras*
*Context gathered: 2026-03-26*
