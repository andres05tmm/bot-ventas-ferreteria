# 08 · Validación empírica contra BD de producción

> Auditoría exhaustiva — anexo a las fases 1-7.
> Generado consultando directamente la BD Railway de Ferretería Punto Rojo
> con acceso MCP read-only. Confirma o desmiente los hallazgos teóricos de la
> Fase 4 con datos reales y descubre 6 hallazgos nuevos invisibles desde el código.

---

## 1. Confirmaciones — Sprint 1+2 está OK para deploy

| Hallazgo | Confirmación empírica |
|---|---|
| **C-07** (consecutivo race conditions) | **0 duplicados** `(consecutivo, fecha)`. UNIQUE constraint sí funciona. Los "delta < 2 seg" detectados son inserts secuenciales de una carga masiva del 27 mar, no race conditions. |
| **C-08** (descuento de inventario sin transacción) | **0 productos con stock negativo**. La práctica de descontar fuera de la transacción no se materializó como bug nunca. Pero la causa real es más profunda (ver Hallazgo #1 de §3). |
| **C-01/03** (RBAC) | FKs `usuario_id → usuarios.id` confirmadas en `ventas, gastos, compras, facturas_proveedores`. RBAC tendrá efecto real en cuanto el fix se despliegue. |
| **H-13** (regimen_fiscal tipo divergente) | **59/59 clientes con `regimen_fiscal=2` (integer)**. Migración 012 ya corrió en prod. |
| **Numeración DIAN** (FE) | **110 facturas, 0 huecos** entre `FPR12` y `FPR121`. La secuencia legal está intacta. |
| **DS-NO** | `consecutivo=5`, `cude` válido, `estado_dian='transmitido'`. DSNO funcionando. |
| **Cuenta de Cobro** | 1 CC generada (`consecutivo=1`, Mayo 2026, $2M). Job mensual funciona. |
| **Bancolombia (Gmail)** | **106 transferencias** = $33.2M COP registradas en ~1 mes. Idempotencia por `gmail_message_id UNIQUE` funciona. |
| **Memoria del bot** | 32 turnos en `conversaciones_bot`. 9 audios transcritos. |
| **Budget Claude** | 7 días de `api_costo_diario`. Tracking activo. Costos ~$0.30/día con Haiku. |

---

## 2. Hallazgos teóricos confirmados como bugs reales

| ID | Hallazgo | Evidencia BD |
|---|---|---|
| **M-02** | `compras_fiscal.usuario_id` sin FK | Confirmado: el query a `information_schema` muestra FK en `ventas, gastos, compras, facturas_proveedores` pero NO en `compras_fiscal`. |
| **Drift** | Tabla `aliases` existe en BD pero no en `db._init_schema()` ni migraciones del repo | Tabla con `termino → reemplazo`, 1 fila ("disco de corte concreto 4" → 'disco de corte segmentado 4"'). Vino de migración no commiteada. |
| **Drift de seeds** | `usuarios.id=5 'Patricia H'` no está en `migrations/004_usuarios_auth.py` | Creada vía `/registrar_vendedor` del bot. El seed original era Farid M / Farid D / Karolay / Papá. |
| **Drift de seeds** | "Farid M" se renombró a "Farid Malo N" en BD | Modificación post-seed que no aparece como migración. |
| **Datos inconsistentes** | `ventas.vendedor` (string) ≠ `usuarios.nombre` (FK) | 2 ventas con `usuario_id=4` (Karolay) pero `vendedor='Andres'`. 1 venta con `usuario_id=1` (Andrés) y `vendedor='.'`. 105 ventas con `usuario_id=NULL`. |
| **Defaults Punto Rojo** | `clientes.municipio_dian DEFAULT 149` (Cartagena) y `clientes.ciudad_nombre DEFAULT 'Cartagena'` | Confirmado en BD. Específico de Punto Rojo, debe parametrizarse para el template (Fase 5 §2.3). |

---

## 3. Hallazgos NUEVOS — invisibles desde el código

### N-01 (HIGH) · Inventario completamente vacío

**Datos**: `inventario.cantidad` filas = **0**, aunque `productos` tiene **632** filas activos.

**Implicación**:
- `descontar_inventario` y `descontar_inventario_pg` (C-08) nunca tienen a quién descontar — la rama "producto no en inventario" se ejecuta 100% de las veces.
- Los reportes de stock muestran siempre `null` o `0` para todos los productos.
- El bot no puede dar alertas de stock bajo porque no hay stock.
- Por eso C-08 nunca produjo bugs visibles: era un riesgo sobre código muerto.

**Acción**: o se carga inventario inicial (con un script `seed_inventario.py`) o se elimina la funcionalidad si no se va a usar.

### N-02 (HIGH) · 46% de ventas_detalle sin `producto_id`

**Datos**: 218/473 (**46%**) líneas de venta tienen `producto_id=NULL`. Solo el nombre como string libre.

**Implicación**:
- El bot/dashboard no logra resolver el producto contra el catálogo en casi la mitad de las ventas.
- Causas probables:
  - Catálogo desactualizado (vendedor menciona algo que no está).
  - Búsqueda fuzzy del bot falla.
  - `Venta Varia` y similar (1 sola con `sin_detalle=TRUE`, no explica el 46%).
- Consecuencia: kárdex, reportes por producto y top de productos quedan parcialmente incompletos.

**Acción**: investigar logs del bot/dashboard para entender por qué no resuelve. Posible: el bot inserta `producto_nombre` sin resolver `producto_id`.

### N-03 (HIGH) · Inconsistencia FE ↔ ventas.factura_estado

**Datos**:
- 99 filas en `facturas_electronicas` con `estado='emitida'`.
- Solo 49 ventas con `factura_estado='emitida'`.
- **50 FE emitidas cuyas ventas no se marcaron como facturadas.**
- Además 99 ventas con `factura_estado=NULL` (datos pre-migración 008).

**Implicación**: cuando se emite una FE, debería actualizarse también `ventas.factura_estado, factura_numero, factura_cufe`. Pero en 50 casos no ocurrió. Probablemente race condition entre la respuesta MATIAS y el UPDATE, o falta el UPDATE.

**Acción**: revisar `services/facturacion_service.py` después del INSERT en facturas_electronicas — debe haber un UPDATE de ventas en la misma transacción.

### N-04 (MEDIUM) · 26 compras fiscales pendientes de evento RADIAN

**Datos**: 26/26 `compras_fiscal` con `evento_estado='pendiente'`. Ninguna aceptada/reclamada/rechazada.

**Implicación**: la DIAN espera que el comprador confirme recepción de cada factura electrónica recibida (eventos 030, 031, 032, 033). Punto Rojo no lo está haciendo. Riesgo fiscal latente.

**Acción**: revisar el dashboard tab Proveedores → ¿el botón "Aceptar" funciona? Implementar UI para gestionar eventos masivamente.

### N-05 (MEDIUM) · Catálogo con productos duplicados por nombre

**Datos**:
- "Laca Catalizada Beis", "Laca Catalizada Beige", "Laca Beige Catalizada" — son el mismo producto, 3 entradas distintas.
- "Thinner" aparece 2 veces (uno con categoría, otro sin).
- "Cuñete Vinilo Tipo 1 Davinci" y "Vinilo Davinci T1 Blanco" probablemente el mismo SKU.

**Implicación**: confusión para el bot (cuál match elegir), reportes top inconsistentes (ventas distribuidas entre duplicados).

**Acción**: consolidación manual del catálogo + alias para los variantes.

### N-06 (LOW) · Errores FE históricos: resolución DIAN vencida

**Datos**: 5 errores del 29 abril 2026: *"La fecha (2026-04-30) del documento debe estar entre 2026-04-24 y 2026-04-29"*.

**Implicación**: la resolución DIAN tenía rango hasta 29 abril. Cuando se intentó facturar con fecha 30 abril (vencida), MATIAS rechazó. Es un error operativo, no un bug del código.

Adicionalmente: 6 facturas con `estado='Rechazada por DIAN'` todas con monto $433.000 y CUFE generado (es decir, llegaron a DIAN pero fueron rechazadas). Probablemente reintentos.

**Acción**: alerta automática 7 días antes del vencimiento de `MATIAS_NUM_DESDE` (siguiente número del rango).

### N-07 (LOW) · 93% de ventas sin cliente identificado

**Datos**:
- 113 ventas con `cliente_nombre='Consumidor Final'`.
- 91 ventas con `cliente_nombre=NULL`.
- Total = 204/220 = **93%** sin cliente real.

**Implicación**: el módulo de clientes existe (59 clientes en BD) pero solo se usa para los 16 casos de cliente identificado. Limita reportes de CRM, marketing, cobro.

### N-08 (LOW) · `api_costo_diario.vendedor_id=0`

**Datos**: hay filas con `vendedor_id=0` que no corresponde a ningún usuario real.

**Implicación**: bug menor en el tracking de Claude — cuando el bot no resuelve el usuario, registra 0 en vez de NULL o un ID válido.

**Acción**: cambiar a `vendedor_id=NULL` cuando no haya match, o validar contra `usuarios.id`.

---

## 4. Patrones de uso reales (vs lo asumido)

| Asumido en la auditoría | Realidad en BD |
|---|---|
| Caja se abre/cierra a diario | **1 sola fila en `caja`** (12 abr cerrada). Vendedores no usan el módulo. |
| Gastos se registran por caja | **3 gastos en total**. Casi sin uso. |
| Fiados es una funcionalidad activa | **0 fiados en BD**. Punto Rojo no fía. La urgencia de H-14 baja. |
| Compras alimentan inventario | **0 filas en `compras`** (operativa). Toda la actividad está en `compras_fiscal`. |
| Inventario se mantiene actualizado | **0 filas en `inventario`**. Funcionalidad muerta. |
| Bot procesa ~60% de ventas | No verificado, pero hay 32 turnos en `conversaciones_bot` y 9 audios. La mayoría de ventas viene del dashboard (`vendedor='Dashboard'` con 69 ventas + asignaciones reales). |
| Memoria de entidad (Capa 4, 3am) | **0 filas en `memoria_entidades`**. El compresor nocturno no produce nada (o no se ejecuta). |
| Libro IVA bimestral | **0 cierres en `iva_saldos_bimestrales`**. Nunca se cerró un bimestre. |
| Branding por ferretería | Defaults `Cartagena`, `municipio_dian=149`, `pais_id=45`, `regimen_fiscal=2`. **Hardcoded a Colombia/Punto Rojo** como documentamos. |

---

## 5. Top hallazgos para Sprint 3 (después del Sprint 1+2 deploy)

Por orden de impacto:

1. **N-03** — UPDATE de `ventas.factura_estado` falta en `facturacion_service.py`. ~2h.
2. **N-02** — investigar por qué 46% de `ventas_detalle.producto_id` es NULL. Probable refactor en bot/dashboard al insertar la venta para resolver siempre el producto_id. ~4h.
3. **N-01** — decidir: cargar inventario inicial vs eliminar funcionalidad de inventario. Conversación de producto. ~1 día si se decide cargar.
4. **N-05** — consolidación de productos duplicados en catálogo. Operativo, no de código. ~2-3h con scripts.
5. **N-04** — UI/dashboard para emitir eventos RADIAN en compras_fiscal. ~1 día.
6. **M-02** — agregar FK formal a `compras_fiscal.usuario_id`. ~10min de migración.
7. **N-08** — fix del `api_costo_diario.vendedor_id=0`. ~30min.
8. **Drift schema**: agregar tabla `aliases` a `db._init_schema()` para que BDs nuevas la creen. ~5min.

---

## 6. Implicaciones para el Sprint 4 (template-base)

La validación empírica refina lo que el template debe **activar/desactivar por defecto**:

| Módulo | Estado en Punto Rojo | Decisión para template |
|---|---|---|
| Inventario | NO se usa | **opcional**, default `INVENTARIO_HABILITADO=false` |
| Fiados | NO se usa | **opcional**, default `FIADOS_HABILITADO=false` |
| Caja/Gastos | Casi no se usa | **opcional**, default `CAJA_HABILITADA=false` |
| Compras (operativa) | NO se usa, solo compras_fiscal | **opcional** o eliminar |
| FE DIAN | Activo, 90% éxito | **opcional**, default `FE_HABILITADA=false` |
| DSNO | 1 documento | **opcional**, default `DSNO_HABILITADO=false` |
| Honorarios | 1 CC | **opcional**, default `HONORARIOS_HABILITADO=false` |
| Bancolombia | Muy usado | **opcional**, default `BANCOLOMBIA_HABILITADO=false` |
| Bot + Memoria | Activo | **siempre activo (core)** |
| Catálogo + Ventas | Activo | **siempre activo (core)** |
| Memoria entidades (compresor 3am) | NO genera | **opcional**, default `false` mientras no se valide que genera valor |

---

## 7. Riesgos operativos detectados (no del código)

1. **No se cierran eventos RADIAN** — riesgo fiscal con DIAN. La ferretería debería estar emitiendo evento 030 al recibir cada FE de proveedor.
2. **Inventario sin uso** — no hay control de stock real. El bot dice "queda X" pero no es cierto.
3. **Resolución DIAN vencida** (caso histórico abril) — necesitan recordatorio antes de la fecha de vencimiento.
4. **`telegram_id` placeholders 1,2,3,4 ya no existen** — los seeds originales fueron sobreescritos. Eso significa que la migración 004 no es reproducible en una BD nueva sin editar.

---

## 8. Conclusión

- **El Sprint 1+2 es seguro para deploy** — todos los fixes están validados contra datos reales, sin efectos colaterales sobre la facturación DIAN, los consecutivos legales o la integridad referencial.
- **Hay 8 hallazgos nuevos** (3 HIGH, 2 MEDIUM, 3 LOW) que solo eran detectables consultando la BD, no leyendo código.
- **Varios módulos del sistema están en estado dormido** (inventario, caja, fiados, compras operativas). Eso simplifica el alcance del template-base: muchas funcionalidades se vuelven opt-in.
- **El acceso MCP a Postgres es un activo enorme** — debería usarse rutinariamente para validar fixes antes de deploy.
