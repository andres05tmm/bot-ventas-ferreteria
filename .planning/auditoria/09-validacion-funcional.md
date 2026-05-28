# 09 · Validación funcional módulo por módulo

> Auditoría exhaustiva — Sprint 2.5.
> Generado consultando directamente la BD de producción de Punto Rojo en Railway
> con acceso MCP read-only. Veredicto operativo por módulo: ¿funciona? ¿se usa?
> ¿hay datos inconsistentes? ¿qué falta?

---

## Resumen ejecutivo

| Módulo | Estado | Notas críticas |
|---|---|---|
| **1. Ventas** | ✅ FUNCIONA | Integridad contable perfecta (0 descuadres header↔detalle). 220 ventas, $13.5M. |
| **2. Caja + Gastos** | 🟡 SUBUTILIZADO + bugs | Solo 1 cierre histórico, 3 gastos. `historico_ventas` DIVERGE de `ventas` reales. |
| **3. Inventario + Kardex** | 🟡 MUERTO | Catálogo activo (631 productos) pero tabla `inventario` VACÍA. |
| **4. Fiados** | 🟡 SIN USO | 0 fiados. Tabla `fiados_movimientos` (Sprint 2) aún no aplicada. |
| **5. Proveedores** | ✅ OK | 1 factura, invariante `pagado+pendiente=total` correcta. |
| **6. Compras fiscal** | ⚠️ RIESGO FISCAL | 26 compras pendientes de evento RADIAN nunca emitido. |
| **7. FE DIAN** | ✅ FUNCIONA | 99 emitidas / 11 errores (90% éxito). 0 notas crédito ni débito. |
| **7b. Libro IVA** | 🟡 NUNCA CERRADO | 0 bimestres cerrados pese a tener datos. |
| **8. Honorarios + DSNO** | ✅ FUNCIONA | 1 CC + 1 DSNO emitidos. |
| **9. Clientes** | ⚠️ CALIDAD | 97% sin teléfono. Default `Cartagena` no aplica al 96%. Drift de normalización en `tipo_persona`. |
| **10. Pagos Bancolombia** | ✅ FUNCIONA | 106 transferencias, $33.2M. Idempotencia OK. |
| **10b. Bold / Wompi** | ⚪ no aplica | No persisten (solo Telegram). Sin forma de validar sin logs. |
| **11. Gmail webhook compras** | ⚠️ MIGRATION FALTANTE | 26 compras_fiscal vía Gmail OK. Pero `ferrebot_config` no existe en prod. |
| **12. IA del bot** | 🟡 PARCIAL | 4 días activos en abril, después nada. Compresor nocturno NO genera. |
| **12b. IA dashboard chat** | ⚪ no validable | Sin datos persistidos por el chat widget. |
| **13. RBAC + Auth** | ✅ OK | 2 admins, 4 vendedores. 0 placeholders sueltos. |
| **14. Tiempo real SSE** | ✅ Código OK | Solo validable en vivo (C-04 ya fixado). |

---

## Módulo 1 — Ventas

### Estado: ✅ FUNCIONA

**Métricas**:
- 220 ventas, 26 días con actividad, $13.5M total, ticket promedio $61.449.
- Métodos: efectivo (183, $8M), transferencia (35, $5.3M), datáfono (2, $262k).
- Primera venta: 19 mar 2026 · última: 26 may 2026.

**Integridad**:
- ✅ `total` header == suma de detalles → **0 descuadradas**.
- ✅ Ninguna venta con `total NULL`, `total = 0`, `total negativo`.
- ✅ Ninguna sin fecha, vendedor o método de pago.
- ✅ FK CASCADE funciona — 0 ventas huérfanas, 0 detalles huérfanos.
- ✅ 0 race conditions del consecutivo (UNIQUE constraint).

**Defectos menores**:
- ⚠️ 107/220 ventas (49%) con `hora IS NULL` — el bot no setea hora en sus inserts.
- ⚠️ 105/220 ventas con `usuario_id = NULL` (datos pre-RBAC).
- ⚠️ 218/473 detalles (46%) con `producto_id = NULL` (no resuelve catálogo).
- ⚠️ Inconsistencia: 2 ventas con `usuario_id=4` (Karolay) pero `vendedor='Andres'`.

**Veredicto**: módulo más maduro del sistema. Funciona correctamente.

---

## Módulo 2 — Caja y Gastos

### Estado: 🟡 SUBUTILIZADO + 3 BUGS REALES

**Datos**:
- `caja`: 1 sola fila (12 abr 2026, cerrada).
- `gastos`: 3 gastos total (2 de caja, 1 abono proveedor).
- `historico_ventas`: 27 días registrados.

**🔴 Bug 1 — `historico_ventas` divergente de `ventas`**:
| Fecha | Histórico | Ventas reales | Diferencia |
|---|---|---|---|
| 22 mar | $844.500 | $0 (sin ventas) | +$844k |
| 24 mar | $1.349.708 | $428.900 (13 ventas) | +$920k |
| 25 mar | $511.100 | $0 (sin ventas) | +$511k |
| 26 mar | $1.407.812 | $591.100 (1 venta) | +$816k |

La tabla `historico_ventas` fue importada del `historico_ventas.json` (migración 002) y **nunca se reconcilia con `ventas` reales**. Los reportes que la usan para días pre-abril muestran datos falsos.

**🟡 Bug 2 — `historico_ventas.datafono = 0`** aunque hay 2 ventas datafono por $262k. El cron del histórico no suma datafono.

**🟡 Bug 3 — `historico_ventas.gastos = 0`** aunque hay 3 gastos por $114k. El cron no suma gastos.

**Veredicto**: el bot/dashboard tiene la funcionalidad pero los vendedores no la usan. Los datos importados del JSON original están desactualizados. Acción: pasarle al usuario el endpoint `/historico/reconstruir-desglose` o decidir si vale la pena seguir con `historico_ventas` o derivar todo al vuelo.

---

## Módulo 3 — Inventario + Kardex

### Estado: 🟡 FUNCIONALIDAD MUERTA

**Datos**:
- `productos`: 631 activos, 100% con IVA 19%.
- `inventario`: **0 filas**.
- `productos_fracciones`: 723 filas (150 productos con fracciones).
- 23 productos con mayorista (`precio_umbral`).

**Implicación**:
- `descontar_inventario` y `descontar_inventario_pg` (C-08) nunca tienen a quién descontar.
- Reportes de stock muestran siempre 0/null.
- El bot no puede dar alertas de stock bajo.
- Endpoint `/inventario/bajo` retorna lista vacía o solo productos sin precio.

**Acciones posibles**:
1. **Cargar inventario inicial** desde Excel/conteo físico (script `seed_inventario.py`).
2. **Eliminar la funcionalidad** si no se quiere mantener.
3. **Activar automáticamente**: cada compra (`compras` o `compras_fiscal`) debería INSERT en inventario para inicializar.

---

## Módulo 4 — Fiados

### Estado: 🟡 SIN USO

**Datos**:
- `fiados`: 0 filas.
- `fiados_movimientos`: **NO EXISTE EN PROD** (migración 024 del Sprint 2 no se ha corrido).

**Veredicto**: Punto Rojo no fía. La urgencia de H-14 (crear tabla de movimientos) baja: nadie depende del histórico que se pierde porque no hay movimientos. Aún así correr la migración cuando se haga deploy del Sprint 2 para que la tabla exista cuando alguien fíe por primera vez.

---

## Módulo 5 — Proveedores (CxP)

### Estado: ✅ FUNCIONA

**Datos**:
- 1 sola factura (`FAC-001`, Pinturas Davinci, $100k, pagada).
- 1 abono ($100k).
- ✅ Invariante `pagado + pendiente == total` cumplida.

**Veredicto**: módulo correcto pero subutilizado. Una sola factura registrada manualmente. La mayoría de la actividad real de compras va por `compras_fiscal` (Gmail webhook), no por este módulo.

---

## Módulo 6 — Compras Fiscal

### Estado: ⚠️ RIESGO FISCAL — eventos RADIAN nunca emitidos

**Datos**:
- 26 compras fiscales, $12.7M.
- Proveedores: PINTURAS DAVINCI ($8.7M / 14 facturas), SEGAR ($1.7M / 6), QCA ($1.4M / 1), CACHARRERIA ($658k / 1), COESCO ($300k / 4).
- 22 con IVA, 4 sin IVA.
- Todas con `evento_estado='pendiente'`.

**⚠️ Hallazgo crítico**: la DIAN requiere que el comprador emita eventos RADIAN al recibir cada factura electrónica:
- Evento 030 (acuse de recibo)
- Evento 031 (acuse de bienes/servicios)
- Evento 032 (aceptación expresa)
- Evento 033 (rechazo)

**Ninguna factura recibida tiene evento emitido**. Esto puede generar problemas con la DIAN.

**Acción**: revisar el botón "Aceptar" en el tab Proveedores del dashboard. Posiblemente no funciona o no se conoce.

---

## Módulo 7 — Facturación Electrónica DIAN

### Estado: ✅ FUNCIONA (90%)

**Datos**:
- 99 facturas emitidas con éxito, $23.1M.
- 11 con error (5 por resolución DIAN vencida en abril, 6 rechazadas por DIAN con CUFE asignado).
- Tasa de éxito: 90%.
- Primera FE: 9 abr 2026 · última: 27 may 2026.
- Numeración DIAN: **FPR12 → FPR121, 0 huecos** (auditoría legal limpia).

**🔴 Bug N-03 confirmado**:
- 99 FE emitidas en `facturas_electronicas`.
- Solo 49 ventas con `factura_estado='emitida'`.
- **50 FE emitidas cuya venta correspondiente no se actualizó**.

**0 notas crédito ni débito** emitidas históricamente — el feature está implementado pero sin uso. Cuando los vendedores quieran anular o ajustar, no han usado este flujo.

---

## Módulo 7b — Libro IVA Bimestral

### Estado: 🟡 NUNCA CERRADO

**Datos**: `iva_saldos_bimestrales`: 0 filas.

**Implicación**: el feature de cierre bimestral está implementado (endpoint `POST /libro-iva/cerrar-bimestre`) pero Punto Rojo nunca lo ha usado. La declaración de IVA bimestral probablemente se hace manualmente en otro sistema (contador externo).

**Veredicto**: feature opt-in. Para el template, default `LIBRO_IVA_HABILITADO=false`.

---

## Módulo 8 — Honorarios + DSNO

### Estado: ✅ FUNCIONA

**Datos**:
- `cuentas_cobro`: 1 fila (`CC-001`, Mayo 2026, $2M).
- `documentos_soporte`: 1 fila (`DS-5`, $2M, `estado_dian='transmitido'`, CUDE válido).

**Veredicto**: el job mensual del día 23 funcionó correctamente:
1. Generó CC-001 con PDF.
2. Transmitió DS5 a DIAN con CUDE.
3. Idempotencia OK (no se duplica).
4. Numeración respeta `MATIAS_DS_NUM_DESDE=5`.

---

## Módulo 9 — Clientes

### Estado: ⚠️ CALIDAD DE DATOS

**Datos**: 59 clientes.

**Defectos**:
- 57/59 sin teléfono (97%).
- 2/59 sin correo (3%).
- 57/59 con `municipio_dian ≠ 149` (Cartagena) — el default `149` no aplica al 96% real.
- **Bug nominal**: `tipo_persona` tiene "Juridica" y "Jurídica" (con/sin tilde). Falta normalización.
- 3 tipos de persona encontrados: Natural, Jurídica, Juridica (mezcla).

**Acción**:
1. UPDATE para normalizar `tipo_persona='Juridica'` → `'Jurídica'`.
2. Capturar teléfono en el wizard de cliente (importante para WhatsApp/llamadas).

---

## Módulo 10 — Pagos Bancolombia

### Estado: ✅ FUNCIONA

**Datos**:
- 106 transferencias recibidas, $33.2M COP.
- Idempotencia por `gmail_message_id UNIQUE` OK.
- Período: 24 abr - 27 may 2026 (28 días con actividad).
- Distribución:
  - Transferencia: 45 mov ($23.7M) — mayoría **internas familia** (FARID MALO, FARID DAVID MALO NAVARRO, ANDRES MALO).
  - PSE: 23 mov ($4.9M) — pagos de clientes.
  - Código QR: 38 mov ($4.6M) — Bold/QR de clientes.

**Sobre el "descuadre" Bancolombia ↔ ventas**:
- $33.2M Bancolombia vs $4.3M ventas transferencia (mismo período).
- **Causa real**: las transferencias top son entre cuentas de la familia, NO pagos de clientes. El descuadre operativo es esperable.
- Sólo $4.9M PSE + $4.6M QR = $9.5M son pagos reales de clientes. Si comparamos con $4.3M en ventas registradas, faltan ~$5M de ventas no registradas (pagos QR/PSE recibidos sin venta correspondiente).

**Veredicto**: el módulo funciona perfectamente. Lo que falla es la disciplina del vendedor de registrar la venta cuando recibe el QR/PSE.

---

## Módulo 10b — Bold / Wompi

### Estado: ⚪ no aplica para validación

Bold y Wompi no persisten en BD; solo procesan webhook y reenvían a Telegram. La única forma de validar es revisar logs de Railway o el chat de Telegram.

---

## Módulo 11 — Gmail Webhook (compras fiscales)

### Estado: ⚠️ MIGRATION FALTANTE EN PROD

**Datos**:
- 26 filas en `compras_fiscal` con `gmail_message_id` (todas vienen de Gmail).
- 9 `message_id` únicos (cada correo genera N filas, 1 por producto).
- Período: 5 abr - 25 may 2026.

**🔴 Bug detectado**: la tabla **`ferrebot_config` NO EXISTE en prod**. La migración 012 nunca se aplicó.

**Implicación**:
- `gmail_last_history_id` no se persiste.
- Cuando el servicio se reinicia, el watch de Gmail probablemente pierde algunos eventos (no sabe desde qué `history_id` reanudar).

**Acción urgente antes de cualquier deploy futuro**: correr `railway run python migrations/012_ferrebot_config.py`.

---

## Módulo 12 — IA del bot (Claude + bypass + memoria)

### Estado: 🟡 PARCIALMENTE OPERATIVO

**Datos**:
- `conversaciones_bot`: 32 turnos (21 user + 11 assistant). **Solo 1 chat distinct**. Actividad concentrada del **27-29 abril** (3 días); después nada.
- `audio_logs`: 9 audios el 12 abril, 1 solo chat.
- `api_costo_diario`: 7 días tracked. $0.90 Haiku + $0.73 Sonnet = $1.63 total.
- `memoria_entidades`: **0 filas**. El compresor nocturno NO genera.

**Análisis**:
- **Bot subutilizado** — solo 1 chat tuvo actividad en abril, después se apagó la persistencia.
- **Ratio user:assistant = 21:11** sugiere que el bot **no responde a todos los mensajes** (deberían estar 1:1). Probable bug.
- **Compresor nocturno NO genera memoria** — el job de 3am del APScheduler no se está ejecutando, o se ejecuta sin producir output. Capa 4 de memoria del bot inactiva.

**Acción**:
1. Verificar logs de Railway del job `compresor_nocturno` (¿se ejecuta?).
2. Investigar por qué la persistencia de conversaciones se cortó después del 29 abr.

---

## Módulo 12b — IA del dashboard (Chat Widget)

### Estado: ⚪ no validable desde BD

El chat widget no persiste sus interacciones — usa `conversaciones_bot` solo si la sesión es del bot. Para validarlo: probar manualmente en el dashboard.

---

## Módulo 13 — RBAC + Autenticación

### Estado: ✅ OK

**Datos**:
- 2 admins activos: `Andrés` (id=1) y `Andrés (cel nuevo)` (id=6).
- 4 vendedores activos: `Farid Malo N`, `Farid D`, `Karolay`, `Patricia H`.
- **0 placeholders telegram_id (1, 2, 3, 4)** — todos asociados a chats reales.

**Veredicto**: el RBAC tiene los datos en orden. Solo falta aplicar el fix de Sprint 1 (C-01/C-03) para que el filtro por rol funcione efectivamente en endpoints.

**Detalle nuevo descubierto**: `Patricia H` (id=5) está en BD pero NO en `migrations/004_usuarios_auth.py`. Vino vía comando `/registrar_vendedor` del bot. El seed original "Papá" fue reemplazado.

---

## Módulo 14 — Tiempo real (SSE + pg_notify)

### Estado: ✅ Código OK (no se puede validar desde BD)

- C-04 fixado en Sprint 1 (apertura de caja ya notifica).
- H-04 fixado en Sprint 2 (notify_all loguea ERROR cuando falla).
- Solo se puede validar en navegador con la página abierta.

---

## Hallazgos NUEVOS de Sprint 2.5 (no estaban en auditorías previas)

| # | Hallazgo | Severidad |
|---|---|---|
| V-01 | `ventas.hora IS NULL` en 49% (107/220) — el bot no setea hora | LOW |
| V-02 | `historico_ventas` divergente de `ventas` reales (caso de datos pre-abril importados de JSON, nunca reconciliados) | **HIGH** |
| V-03 | `historico_ventas.datafono` y `historico_ventas.gastos` siempre 0 — el cron no los suma | MEDIUM |
| V-04 | `ferrebot_config` no existe en prod (migración 012 no aplicada) → Gmail puede perder eventos en reinicios | **HIGH** |
| V-05 | `tipo_persona` tiene "Juridica" y "Jurídica" — falta normalizar | LOW |
| V-06 | Ratio user:assistant en `conversaciones_bot` = 21:11 → bot a veces no responde | MEDIUM |
| V-07 | Compresor nocturno (3am) NO genera filas en `memoria_entidades` (0 filas) | MEDIUM |
| V-08 | $5M+ de pagos QR/PSE Bancolombia sin venta correspondiente registrada → vendedores cobran sin registrar | informativo |
| V-09 | 57/59 clientes (97%) sin teléfono | LOW |
| V-10 | 0 notas crédito/débito emitidas históricamente — feature implementada sin uso | informativo |

---

## Prioridades para Sprint 3 (refinadas con la realidad de uso)

Después de esta validación, las prioridades cambian:

| # | Hallazgo | Esfuerzo | Por qué importa |
|---|---|---|---|
| 1 | V-04 — Aplicar migración 012 (`ferrebot_config`) | 1 min | Gmail webhook actualmente puede perder eventos |
| 2 | N-03 — UPDATE faltante en FE → `ventas.factura_estado` | 2h | 50 FE emitidas sin marcar la venta |
| 3 | N-04 — UI para emitir eventos RADIAN proveedores | 4-6h | Riesgo fiscal con DIAN |
| 4 | V-02 — Reconciliar `historico_ventas` o derivar al vuelo | 3h | Reportes pre-abril muestran datos falsos |
| 5 | N-02 — Investigar por qué 46% de ventas_detalle sin producto_id | 4h | Degrada kárdex y reportes |
| 6 | M-02 — FK formal en `compras_fiscal.usuario_id` | 10 min | Integridad |
| 7 | V-07 — Investigar compresor nocturno | 2h | Capa 4 IA inactiva |
| 8 | V-06 — Bot que no responde a 50% mensajes | investigación | Posible bug serio en handlers |
| 9 | N-05 — Consolidar productos duplicados | 3h | Catálogo más limpio |
| 10 | V-03 — Histórico sin datáfono ni gastos | 1h | Cron incompleto |

Total estimado para los 10 fixes: ~20 horas (~2.5 días) — sigue siendo un sprint cómodo.

---

## Implicaciones para el template-base (Sprint 4)

La validación funcional confirma las decisiones de Fase 6:

**Módulos `siempre activos` (core)**:
- Catálogo + Ventas + RBAC + Auth + Bot Telegram + Dashboard + Tiempo real.

**Módulos `opt-in` con default `false`**:
- Inventario (Punto Rojo: 0 uso → default false).
- Caja + Gastos (Punto Rojo: 1 cierre histórico → default false).
- Fiados (Punto Rojo: 0 uso → default false).
- Libro IVA (Punto Rojo: 0 cierres → default false).
- Compresor IA nocturno (Punto Rojo: 0 output → default false).

**Módulos `opt-in` con default `true` solo si DIAN/MATIAS activo**:
- Facturación electrónica.
- DSNO.
- Compras fiscal.
- Notas crédito/débito.

**Integraciones externas (siempre opt-in)**:
- Honorarios (CC mensual).
- Bancolombia (Gmail Pub/Sub).
- Gmail compras fiscales.
- Bold / Wompi.
- Cloudinary.

---

## Cierre — el sistema está más sano de lo que se ve

A pesar de los **47 hallazgos del audit teórico** + **10 hallazgos empíricos nuevos**, la realidad operativa es:

- ✅ El **flujo principal** (registrar ventas, facturar electrónicamente, generar CC mensual, recibir pagos Bancolombia) **funciona sin errores graves** y con datos contablemente consistentes.
- ⚠️ Hay **3 bugs concretos a corregir en Sprint 3** (V-04 migración faltante, N-03 UPDATE FE, V-02 histórico divergente).
- 🟡 Hay **mucho código de features no usados** (inventario, caja, fiados, libro IVA) — eso ayuda al template-base porque casi todo se puede convertir a opt-in.
- 💡 El **acceso MCP a PostgreSQL es un activo enorme** — debería usarse rutinariamente para validar fixes antes de cada deploy, y para diagnosticar bugs reportados por el cliente sin necesidad de logs.
