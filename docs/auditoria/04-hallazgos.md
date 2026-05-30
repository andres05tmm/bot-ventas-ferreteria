# 04 · Hallazgos técnicos

> Auditoría exhaustiva — Fase 4 de 8.
> Hallazgos clasificados por severidad y dominio. Cada hallazgo lleva archivo:línea, descripción y propuesta de fix. Total: **47 hallazgos** (8 CRITICAL, 14 HIGH, 18 MEDIUM, 7 LOW).

---

## ✅ ESTADO DE RESOLUCIÓN (actualizado 2026-05-28)

Verificado contra el código actual (branch `feat/dashboard-polish`). Resumen:

| Severidad | Total | ✅ Resueltos | ⚠️ Parcial | ⬜ Abiertos |
|---|:-:|:-:|:-:|:-:|
| CRITICAL | 8 | **8** (C-01..C-08) | 0 | 0 |
| HIGH | 14 | **14** (H-01..H-14) | 0 | 0 |
| MEDIUM | 18 | M-01, M-08 | M-12 | resto |
| LOW | 7 | — | — | resto |

**CRITICAL — todos resueltos** (Sprints 1 y 4):
- C-01/C-03 RBAC → `routers/deps.py` con `get_filtro_usuario`/`get_filtro_efectivo` reales.
- C-02 `@protegido` en handlers del bot (`middleware/auth.py`).
- C-04 caja `notify_all` antes del return.
- C-05 CORS centralizado en `config.CORS_ORIGIN` (sin fallback hardcoded).
- C-06 doble schema → **Alembic** (`_init_schema` eliminado de db.py; `run.sh` corre `alembic upgrade head`).
- C-07 consecutivo atómico con reset diario unificado.
- C-08 inventario dentro de la transacción de la venta.

**HIGH — todos resueltos** (Sprint 2): H-01..H-14, incl. H-08 (secret token webhook Telegram), H-13 (regimen_fiscal INTEGER), H-14 (tabla `fiados_movimientos` creada).

**MEDIUM/LOW resueltos confirmados:**
- M-01 `_init_schema` en una transacción → eliminado (Alembic).
- M-08 `bypass.py` sin tests → `tests/test_bypass.py` existe; además arnés `pruebas_motor.py` (sesión 3) + bugs del motor de ventas arreglados.
- M-12 hardcoded admin en `migrations/004` → ⚠️ **PARCIAL**: `migrations/004` es legacy (Alembic usa baseline, no la corre), así que un clon NO arrastra a Andrés como admin — PERO falta `seed_admin.py` con `ADMIN_TELEGRAM_ID` (ver gap #1 en `07-onboarding`). Queda abierto el seed.

**Abiertos (relevantes para clonar / template)**: M-09/M-10 (plurales y `_ALIAS_FERRETERIA` consolidados en `alias_manager.py` pero aún específicos de Punto Rojo), M-13/M-14 (datos de honorarios a env — ya parcialmente vía `.env.example`), M-15 (tabla `config` vs `ferrebot_config`), M-16 (historico_ventas manual), M-17/M-18 (dashboard). LOW: en su mayoría abiertos (cosméticos).

> Nota: los hallazgos abajo conservan su texto ORIGINAL de la auditoría (estado al momento del análisis). Para el estado actual, usar esta tabla.
>
> Severidad:
> - **CRITICAL**: vulnerabilidad de seguridad, pérdida de datos, contradicción con el modelo de seguridad documentado.
> - **HIGH**: bug funcional, incumple invariante de negocio, drift documental crítico.
> - **MEDIUM**: deuda técnica, mantenibilidad, performance.
> - **LOW**: estilo, sugerencia, mejora.

---

## CRITICAL — ✅ TODOS RESUELTOS (Sprints 1 y 4)

### C-01 · RBAC desactivado — `get_filtro_usuario` siempre retorna `None`
**Archivo**: `routers/deps.py:60-65`
**Riesgo**: vendedores ven datos de todos los demás vendedores, contradice CLAUDE.md §RBAC.

```python
def get_filtro_usuario(current_user=Depends(get_current_user)):
    """Siempre retorna None — todos los usuarios ven datos de todos los vendedores."""
    return None
```

CLAUDE.md afirma:
> "vendedor solo ve los suyos" / "Admin puede impersonar un vendedor pasando ?vendor_id=N"

El código no lo cumple. Los routers que usan `get_filtro_efectivo` (ventas, catálogo, historico, …) no respetan el rol del usuario.

**Fix**: implementar correctamente:
```python
def get_filtro_usuario(current_user=Depends(get_current_user)):
    if current_user.get("rol") == "admin":
        return None
    return current_user.get("usuario_id")

def get_filtro_efectivo(vendor_id=Query(None), current_user=Depends(get_current_user)):
    if current_user.get("rol") == "admin":
        return vendor_id  # admin puede impersonar
    return current_user.get("usuario_id")  # vendedor: ignorar ?vendor_id
```

---

### C-02 · Bot — `manejar_mensaje` y handlers críticos sin `@protegido`
**Archivos**: `handlers/mensajes.py`, `handlers/callbacks.py`, `handlers/cliente_flujo.py`, `handlers/dispatch.py`, `handlers/alias_handler.py`, `handlers/comandos.py`, `handlers/productos.py`
**Riesgo**: cualquier chat externo puede invocar el handler principal de mensajes del bot, registrar ventas, etc., si `AUTHORIZED_CHAT_IDS` no está cargado o si el handler no se protege.

Grep `@protegido` solo encuentra 8 archivos (`cmd_*.py`). Los siguientes handlers principales **no usan el decorador**:
- `manejar_mensaje` (texto) — punto de entrada del 90% de la actividad.
- `manejar_audio`, `manejar_foto`, `manejar_documento`.
- `manejar_callback_*` (todos los botones inline).
- `manejar_flujo_cliente`, `manejar_flujo_pago_texto`, etc.

`handlers/mensajes.py` implementa **su propio** rate limiting (`_check_rate_limit`) pero **no valida `AUTHORIZED_CHAT_IDS`**. Si la variable de entorno no se configura (que es lo que CLAUDE.md llama "fail-open"), cualquier persona que conozca el bot puede chatear con él.

**Fix**: decorar todos los handlers expuestos a Telegram con `@protegido`, o mover la verificación a un middleware único en `main.py.build_app()` (preferible — una sola fuente de verdad).

---

### C-03 · Vendedor puede impersonar a otro vendedor vía `?vendor_id=N`
**Archivo**: `routers/deps.py:68-79`
**Riesgo**: ataque interno trivial.

`get_filtro_efectivo` retorna `vendor_id` sin verificar rol. Cualquier endpoint que use esta dep acepta `?vendor_id=42` desde un vendedor con JWT propio y le devuelve los datos del vendedor 42.

**Fix**: combinado con C-01.

---

### C-04 · Apertura de caja nunca notifica al dashboard (código muerto)
**Archivo**: `routers/caja.py:172-173`
**Riesgo**: el dashboard no refresca cuando se abre caja porque el `await notify_all(...)` está **después del `return`** — es código muerto. Discrepancia silenciosa con `caja_cerrada` (que sí notifica).

```python
return {"ok": True, "mensaje": "...", "caja": caja_abierta}
await notify_all("caja_abierta", {"monto_apertura": int(body.monto_apertura)})  # ← unreachable
```

**Fix**: mover el `await` antes del `return`.

---

### C-05 · CORS hardcoded a la URL de Punto Rojo en múltiples lugares
**Archivos**: `api.py:323`, `api.py:452`, `routers/auth.py:136`
**Riesgo**: imposible clonar a otra ferretería sin tocar 3 archivos del código fuente. Si alguien edita uno y olvida los otros, queda incoherente.

```python
# api.py:323
allow_origins=[os.getenv("CORS_ORIGIN", "https://bot-ventas-ferreteria-production.up.railway.app")]
# api.py:452
_CORS_ORIGIN = os.getenv("CORS_ORIGIN", "https://bot-ventas-ferreteria-production.up.railway.app")
# routers/auth.py:136
"Access-Control-Allow-Origin": "https://bot-ventas-ferreteria-production.up.railway.app",  # ← sin env!
```

**Fix**: una sola constante leída de env, importada donde se necesite. Sin fallback hardcoded.

---

### C-06 · Doble fuente de verdad para el esquema
**Archivos**: `db.py:_init_schema()` + `migrations/*.py`
**Riesgo**: clonar el repo y arrancar API produce un **schema incompleto**: `_init_schema()` no crea `usuarios`, `compras_fiscal`, `facturas_electronicas`, `cuentas_cobro`, `documentos_soporte`, `conversaciones_bot`, `memoria_entidades`, `api_costo_diario`, etc. El admin debe correr 30 migraciones manualmente. Sin tabla `schema_migrations`, no hay forma de saber cuáles se aplicaron. **Onboarding roto** sin documentación clara.

**Fix**: adoptar Alembic, eliminar `_init_schema()` inline y dejar las migraciones como única fuente.

---

### C-07 · Consecutivo de venta inconsistente entre bot y API
**Archivos**: `db.py:509-522` (bot) vs `routers/ventas.py:365` (API)
**Riesgo**: contradicción del modelo. Bot reinicia consecutivo cada día; API toma MAX global. Una venta del bot puede coincidir consecutivamente con una del dashboard si pasaron pocos días.

```python
# bot — reinicia diariamente
"SELECT COALESCE(MAX(consecutivo), 0) AS max_c FROM ventas WHERE fecha = %s"

# venta-rapida — global
"SELECT COALESCE(MAX(consecutivo), 0) + 1 AS siguiente FROM ventas"
```

La tabla tiene `UNIQUE(consecutivo, fecha)`, lo cual permite que el mismo número se repita en otra fecha. Si bot y API insertan en el mismo día con valores distintos calculados (uno desde MAX hoy, otro desde MAX global), pueden chocar con `IntegrityError`.

**Fix**: una sola función `obtener_siguiente_consecutivo()` en `db.py` con la regla decidida (reset diario), llamada desde ambos lados.

---

### C-08 · Descuento de inventario fuera de la transacción de la venta
**Archivo**: `routers/ventas.py:407-414` (también en otros flujos del bot)
**Riesgo**: si la venta se inserta y luego `descontar_inventario` lanza, la venta queda registrada pero el stock no se descuenta. Se silencia con `except Exception: pass`. Llevaría a sobreventa.

```python
conn.commit()  # ← venta ya persistida

for ic in items_calc:
    try:
        from memoria import descontar_inventario
        descontar_inventario(ic["item"].nombre, ic["cant_num"])
    except Exception:
        pass  # ← silencioso
```

**Fix**: incluir el `descontar_inventario` dentro del mismo `with _db._get_conn()` (mismo cursor + commit final) o usar `SAVEPOINT`. Loguear con `logger.error` los fallos.

---

## HIGH — ✅ TODOS RESUELTOS (Sprint 2)

### H-01 · `mensajes.py` ignora `AUTHORIZED_CHAT_IDS` aunque tiene su propio rate limit
**Archivo**: `handlers/mensajes.py:73-91`
Implementa ventana deslizante con `collections.deque` por `chat_id`, pero **no chequea autorización**. Confía en `@protegido`, pero el decorador no está aplicado (ver C-02). Doble código de rate limit divergente: el del middleware (5/2s) y el de mensajes (18/60s).

**Fix**: unificar en el middleware. Eliminar la lógica duplicada de `mensajes.py`.

---

### H-02 · `routers/usuarios.py` declara prefix `/usuarios` pero el endpoint usa `/vendedores`
**Archivo**: `routers/usuarios.py:9, 12`
Único router con `APIRouter(prefix="/usuarios")` — resultado final: `/usuarios/vendedores`. Los demás routers no usan prefix y declaran rutas con el dominio en cada decorator. Inconsistencia que confunde y dificulta refactorización masiva.

**Fix**: estandarizar — o todos con `prefix`, o ninguno.

---

### H-03 · Doble registro de `GET /kardex` (catalogo + reportes)
**Archivo**: `routers/reportes.py:33`, `routers/catalogo.py:402`
Dos handlers `GET /kardex` registrados. `api.py` registra `reportes` antes de `catalogo`, así que el de `catalogo.py` es **dead code** que confunde y nunca se ejecuta.

**Fix**: eliminar el duplicado o consolidar lógica.

---

### H-04 · `notify_all` con fallback local genera inconsistencia silenciosa en multi-réplica
**Archivo**: `routers/events.py:154-158`
Si `pg_notify` falla, se hace `broadcast()` local — pero éste **solo** notifica a los clientes SSE de la réplica actual. En multi-réplica Railway, las otras réplicas no reciben el evento. El usuario no nota nada hasta que un dashboard quede "out of sync".

**Fix**: cuando `pg_notify` falla, loguear como ERROR (no warning), incluir un identificador del evento perdido, y considerar reintentos. Mejor: usar `pg_notify` sincrónicamente en la misma transacción de la mutación.

---

### H-05 · `start-bot.py:228` ejecuta `_db.execute` sincrónico dentro de un job async
**Archivo**: `start-bot.py:228-231` (en `_job_honorarios`)
```python
await bot.send_document(...)
_db.execute("UPDATE cuentas_cobro SET ...", [...])  # ← bloquea el event loop
```
`_db.execute` no es async — bloquea uvloop. Si la BD está lenta, todo el bot se atasca.

**Fix**: usar `await _db.execute_async(...)`.

---

### H-06 · `datetime.utcnow()` deprecado (Python 3.12+)
**Archivo**: `routers/auth.py:114`
```python
now = datetime.utcnow()  # DeprecationWarning en 3.12+
```
Y la variable `now` se usa primero como int (`time.time()`) en línea 84 y luego como datetime en 114 — **shadowing dentro de la misma función**.

**Fix**: `datetime.now(timezone.utc)` + renombrar variables.

---

### H-07 · Auth Telegram: `auth_date` válido por 24 horas
**Archivo**: `routers/auth.py:85`
```python
if now - request.auth_date > 86400:
```
24 h es muy permisivo. El estándar Telegram recomienda 5-15 minutos. Permite replay attacks por un día entero.

**Fix**: reducir a 600 s (10 min).

---

### H-08 · Sin validación de payload de webhooks de Telegram (`/{TELEGRAM_TOKEN}`)
**Archivo**: `start-bot.py:349-356`
Telegram envía POST a `/{TOKEN}` y la app confía en que el path mismo es la auth. Pero el TOKEN aparece en logs HTTP de cualquier intermediario y en el dashboard de Railway. **Mejor práctica**: usar `setWebhook(secret_token=...)` con `X-Telegram-Bot-Api-Secret-Token` validado en el handler.

**Fix**: configurar secret token al hacer `set_webhook` y validarlo en `telegram_webhook()`.

---

### H-09 · Renovación duplicada del watch Bancolombia
**Archivos**: `start-bot.py:269-310` (APScheduler) + `api.py:220-247` (asyncio task)
Dos jobs independientes tratan de renovar el mismo Gmail watch cada 6 días. No coordinan — si ambos servicios corren a la vez (Railway escala API), se renueva 2 veces.

**Fix**: dejar la renovación solo en uno (preferible: el servicio API porque siempre está vivo).

---

### H-10 · `wompi_webhook` registrado en `api.py` pero **no listado** en el docstring del módulo
**Archivo**: `api.py:9-18` vs `api.py:51`
El docstring de `api.py` enumera los routers existentes pero omite `wompi_webhook`, `bold_webhook`, `bancolombia_notifier`, `gmail_webhook`, `auth`, `usuarios`, `proveedores`, `facturacion`, `libro_iva`, `honorarios`. Drift documental severo en el propio módulo.

**Fix**: regenerar docstring o eliminarlo (los routers son auto-descubribles por imports).

---

### H-11 · Catch-all SPA con blocklist hardcoded, frágil
**Archivo**: `api.py:489-504`
```python
_API_HYPHEN_PREFIXES = ("compras-fiscal", "libro-iva")
```
Cualquier nuevo endpoint API con guión queda atrapado por el catch-all SPA y devuelve `index.html` con HTTP 200. Detección tardía y confusa.

**Fix**: usar `APIRouter(prefix="/api")` para todos los routers y `app.mount("/", StaticFiles(...))` solo para `/assets`, `/icons`, etc. — o invertir el orden: el SPA cae únicamente si no hubo match anterior.

---

### H-12 · Tests faltantes para dominios sensibles
**Archivos**: `tests/`
Hay 24 archivos de test pero faltan:
- `test_router_facturacion.py` (FE DIAN — riesgo legal).
- `test_router_proveedores.py`.
- `test_router_clientes.py`.
- `test_documento_soporte.py`.
- `test_honorarios.py`.
- `test_deps.py` (justamente donde está el RBAC roto).
- `test_bancolombia_notifier.py`.
- `test_gmail_webhook.py`.
- `test_bypass.py` (¡el bypass es el corazón de las ventas!).

**Fix**: priorizar tests del bypass y de los flujos DIAN.

---

### H-13 · `clientes.regimen_fiscal` con tipo inconsistente entre migraciones
**Archivos**: `migrations/008_migrate_facturacion.py:47` (VARCHAR(30) DEFAULT 'no_responsable_iva'`) vs `migrations/011_clientes_campos_fe.py:36-38` (INTEGER DEFAULT 2) vs `migrations/012_fix_regimen_fiscal.py`
Tipos opuestos en la misma columna en distintas migraciones. Una BD que aplicó solo la 008 termina con VARCHAR; una que aplicó 011/012 termina con INTEGER. **Schema divergente entre instancias** según el orden de aplicación.

**Fix**: documentar el tipo definitivo y migrar todo a INTEGER (1=Responsable, 2=No responsable).

---

### H-14 · Estado de fiados sólo persiste el saldo, los movimientos viven en memoria
**Archivo**: `services/fiados_service.py:88-94`
```python
fiados[cliente]["movimientos"].append({...})  # ← se pierde al reiniciar
```
La tabla `fiados` solo tiene `saldo_actual` — no hay tabla `fiados_movimientos`. Si el proceso se reinicia, **`detalle_fiado_cliente()` ya no muestra los movimientos del día**. Solo sobrevive el saldo.

**Fix**: crear tabla `fiados_movimientos` con `(cliente_id, fecha, concepto, cargo, abono, saldo_resultante)`. Persistir cada `guardar_fiado_movimiento`.

---

## MEDIUM

### M-01 · `db._init_schema()` corre TODO el SQL en una sola transacción
**Archivo**: `db.py:451-454`
Si una sentencia falla (ej. una columna ya existe con tipo distinto), todo el schema se rollback-ea y la API queda sin BD. Las migraciones modernas se ejecutan en transacciones pequeñas para aislamiento de errores.

**Fix**: dividir en chunks o, mejor, eliminar `_init_schema()` y delegar a migraciones (C-06).

---

### M-02 · 6 colisiones de número en migraciones
**Archivos**: `migrations/004_*.py` (2), `011_*.py` (3), `012_*.py` (2), `013_*.py` (2), `016_*.py` (2)
Sin orden estricto entre archivos con el mismo prefijo numérico. Hace que onboarding requiera conocimiento implícito del orden.

**Fix**: renumerar con prefijos únicos (`023a`, `023b`) o adoptar timestamps (`20260321093045_descripcion.py`).

---

### M-03 · `iva_saldos_bimestrales.iva_*` usa BIGINT mientras el resto usa INTEGER/NUMERIC
**Archivo**: `migrations/009_iva_compras_saldos.py:43-49`
3 estilos de tipo para montos en la BD: INTEGER (mayoría), BIGINT (iva), NUMERIC(15,2)/DECIMAL(12,2) (CC/DSNO).

**Fix**: estandarizar a NUMERIC(15,2) para todas las columnas de dinero.

---

### M-04 · `TIMESTAMP` vs `TIMESTAMPTZ` mezclados
**Archivos**: db.py:_init_schema + varias migraciones
Tablas viejas usan `TIMESTAMP` (sin TZ), tablas nuevas `TIMESTAMPTZ`. Queries cross-tabla con zona horaria pueden dar resultados sutilmente incorrectos.

**Fix**: migrar todo a `TIMESTAMPTZ`. El runtime convierte a Bogotá con `COLOMBIA_TZ`.

---

### M-05 · `productos.aliases TEXT[]` + tabla `aliases` (alias_manager.py) — doble fuente
**Archivo**: `alias_manager.py` + `productos.aliases`
`productos.aliases` se mantiene como array nativo; el manager dinámico maneja otros aliases. Posible duplicación de información.

**Fix**: investigar y consolidar (Fase 5 marca esto como parametrizable).

---

### M-06 · F-strings con SQL detectados (revisados, ninguno explota input usuario)
**Archivos**: `routers/caja.py:308, 412, 531, 807`, `routers/clientes.py:99, 253, 361`, `routers/ventas.py:228, 241, 333, 626, 636`, `routers/catalogo.py:842`
Todos los casos vistos concatenan **nombres de columnas o placeholders `%s`**, no datos. Aún así, es un olor: si alguien refactoriza un endpoint y mete una variable de usuario en el f-string, queda vulnerable a SQL injection silenciosamente.

**Fix**: política "ningún SQL con f-string"; siempre `%s` con `params`. Para columnas dinámicas, usar `psycopg2.sql.Identifier`.

---

### M-07 · `_obtener_siguiente_consecutivo()` en bot no usa `LOCK TABLE`
**Archivo**: `db.py:509-522`
Race condition: dos ventas del bot simultáneas pueden computar el mismo `MAX + 1` y chocar con `UNIQUE(consecutivo, fecha)`. `services/facturacion_service.py` y `services/documento_soporte_service.py` sí usan `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE` para el consecutivo DIAN.

**Fix**: mismo patrón de LOCK TABLE en `obtener_siguiente_consecutivo()` (o `SELECT ... FOR UPDATE`).

---

### M-08 · `bypass.py` no testeado (sólo grep sin tests de regresión)
**Archivo**: `tests/test_bypass.py` no existe
El bypass es el camino crítico del 60% de los mensajes; sin tests, cada cambio es un riesgo.

**Fix**: armar `tests/test_bypass.py` con casos representativos (entero, fracción, mixta, multilínea, bloqueadores).

---

### M-09 · `bypass.py` con listas hardcoded de plurales específicos
**Archivo**: `bypass.py:133-139`
Plurales `tornillos→tornillo, puntillas→puntilla, chazos→chazo` están hardcoded. Otra ferretería con otros productos comunes (cables, tuberías) necesitará tocar el código.

**Fix**: cargar plurales desde tabla `ferrebot_config` o archivo `config/aliases.yml`.

---

### M-10 · `ai/prompts.py` `_ALIAS_FERRETERIA` con regex específicas Punto Rojo
**Archivo**: `ai/prompts.py:93-130+`
Patrones específicos: lija $→#, drywall 6x3, rodillo convencional como default, pita carpa azul. **Otra ferretería tendrá otros aliases** — el archivo necesita editarse cada vez.

**Fix**: extraer a `config/aliases.py` o `ferrebot_config` tabla.

---

### M-11 · Conexión `psycopg2.connect()` directa en `api.py:_pg_listen_worker` (sin pool)
**Archivo**: `api.py:121-152`
Aunque está justificado (LISTEN requiere AUTOCOMMIT, no calza con `ThreadedConnectionPool`), conviene comentar mejor por qué se evita el pool y asegurar reconexión robusta.

**Fix**: documentar la decisión explícita y agregar métrica de "pg_listener_reconnects_total".

---

### M-12 · Hardcoded admin telegram_id en migración 004
**Archivo**: `migrations/004_usuarios_auth.py:57-63`
```python
seed_data = [(1831034712, "Andrés", "admin"), (1, "Farid M", "vendedor"), ...]
```
La migración instala el admin de Punto Rojo. Para otra ferretería, hay que editar la migración antes de aplicarla.

**Fix**: separar seed de migración; usar env vars `ADMIN_TELEGRAM_ID`, `ADMIN_NAME`.

---

### M-13 · Datos personales de Andrés hardcoded en módulos de honorarios y DSNO
**Archivos**: `services/honorarios_service.py:31-38`, `services/documento_soporte_service.py:44-67`
CC, NIT, dirección, mobile, email. Estos módulos son específicos de la relación Andrés↔PR.

**Fix**: en el template, condicionar la activación del módulo honorarios a una variable `HONORARIOS_HABILITADO=true` y leer los datos del proveedor del entorno (o de una tabla `freelancers` si una ferretería contrata múltiples freelancers).

---

### M-14 · `HONORARIOS_VALOR` default 2 000 000 hardcoded
**Archivo**: `config.py:84`
Otra ferretería no necesariamente le paga lo mismo al desarrollador.

**Fix**: sin default razonable — si quieren CC, deben configurar `HONORARIOS_VALOR`.

---

### M-15 · Tabla `config` duplicada (`config` y `ferrebot_config`)
**Archivos**: `db.py:_init_schema`, `migrations/012_ferrebot_config.py`
Dos tablas K/V con el mismo propósito.

**Fix**: consolidar en `ferrebot_config` (la nueva), migrar las claves de `config` y eliminar la vieja.

---

### M-16 · `historico_ventas` se mantiene manualmente — 3 endpoints de "reparación"
**Archivo**: `routers/historico.py:357-518`
- `POST /historico/auto-sync`
- `POST /historico/corregir-dia`
- `POST /historico/reconstruir-desglose`
- `POST /historico/sync-rango`

Múltiples endpoints de mantenimiento sugieren que la tabla deriva incorrectamente con frecuencia.

**Fix**: derivar `historico_ventas` con una **vista materializada** o quitar la tabla y calcular al vuelo.

---

### M-17 · `dashboard/dist` mountado en `/assets` solo si existe
**Archivo**: `api.py:469-487`
Si el operador olvida correr `cd dashboard && npm run build`, la API arranca pero sirve JSON en `/` en vez de SPA. **No hay aviso al usuario** que llegue por browser hasta que mira la consola.

**Fix**: panel de "build no encontrado" en HTML mínimo con instrucciones, o `health` que devuelva `degraded: dashboard not built`.

---

### M-18 · `dashboard/src/components/ChatWidget.jsx` toggles modelo (Auto/Haiku/Sonnet)
**Archivo**: `dashboard/src/components/ChatWidget.jsx`
Exponer el modelo al usuario final es una decisión de UX peculiar. Para un dueño de ferretería esto no significa nada.

**Fix**: dejar el toggle solo para admin y por defecto Auto.

---

## LOW

### L-01 · `start-bot.py` mezcla configuración Python y handlers en el mismo módulo
Sugerencia: extraer la inicialización de schedulers y threads a un módulo `runtime/` separado.

### L-02 · 438 `except Exception` repartidos por todo el código
Patrón consistente para estabilidad en producción, pero faltan logs de severidad alta o métricas para diagnosticar.
**Fix**: política de "todo except Exception loggea WARNING con traceback y emite métrica `errors_total{module=…}`".

### L-03 · Comentarios y código mezclan español e inglés
Convención no documentada formalmente — se ve "import propios" pero también `BROKEN`. CLAUDE.md menciona docstrings en español pero no comentarios. Inconsistencia leve.

### L-04 · Endpoints de webhook no listan ejemplos de payload en docstrings
`/bold/webhook`, `/wompi/webhook`, `/facturacion/webhook` no documentan formato esperado. Onboarding más fácil con ejemplo en el docstring.

### L-05 · `dashboard/src/App.jsx` declara `<Route path="/historico" element={<Navigate to="/historial?view=mes" replace />} />` — redirect de compatibilidad
Si se sabe que nadie usa la URL vieja, eliminar. Si no, dejar pero documentar cuándo se puede quitar.

### L-06 · Mensajes de error en HTTPException mezclan español/inglés
`detail="Token inválido"`, `detail="Hash verification failed"`. Decidir un idioma y aplicar.

### L-07 · `_obsidian/` y `.planning/` agregan ruido al repo
Recomendación: si ese vault Obsidian es personal, moverlo a un repo aparte. `.planning/` queda OK pero documentar su propósito en README.

---

## Resumen por dominio

| Dominio | CRIT | HIGH | MED | LOW |
|---|:-:|:-:|:-:|:-:|
| Seguridad / RBAC | 3 (C-01, C-02, C-03) | 2 (H-07, H-08) | 0 | 0 |
| Ventas / Caja | 2 (C-04, C-07, C-08) | 0 | 1 (M-07) | 0 |
| Infra / Configuración | 1 (C-05) | 0 | 4 (M-04, M-11, M-15, M-17) | 2 (L-01, L-07) |
| Esquema / migraciones | 1 (C-06) | 1 (H-13) | 4 (M-01, M-02, M-03, M-15) | 0 |
| Eventos / SSE | 0 | 1 (H-04) | 0 | 0 |
| Bot (handlers) | 0 | 2 (H-01, H-05) | 1 (M-09) | 0 |
| Realtime / multi-réplica | 0 | 1 (H-09) | 0 | 0 |
| Drift documental | 0 | 1 (H-10) | 1 (M-18) | 1 (L-04) |
| Catch-all / API hygiene | 0 | 2 (H-02, H-03, H-11) | 1 (M-06) | 1 (L-05) |
| Tests | 0 | 1 (H-12) | 1 (M-08) | 0 |
| Reusabilidad | 0 | 0 | 4 (M-10, M-12, M-13, M-14) | 0 |
| Fiados | 0 | 1 (H-14) | 0 | 0 |
| Errores swallowed | 0 | 0 | 0 | 1 (L-02) |
| Estilo | 0 | 1 (H-06) | 0 | 2 (L-03, L-06) |

---

## Tabla TOP-10 (criticidad combinada)

| # | ID | Hallazgo | Severidad | Esfuerzo |
|---|---|---|---|---|
| 1 | C-01+C-03 | RBAC desactivado (vendedores ven datos de otros) | CRITICAL | 1 día |
| 2 | C-02 | Handlers del bot sin `@protegido` | CRITICAL | 1 día |
| 3 | C-06 | Doble fuente de verdad del esquema | CRITICAL | 3-5 días (Alembic + migración) |
| 4 | C-05 | CORS hardcoded en 3 lugares | CRITICAL | 30 min |
| 5 | C-08 | Inventario fuera de transacción de venta | CRITICAL | 2 horas |
| 6 | C-04 | Apertura de caja con `notify_all` muerto | CRITICAL | 5 min |
| 7 | C-07 | Consecutivo bot vs API inconsistente | CRITICAL | 1 hora |
| 8 | H-13 | `clientes.regimen_fiscal` con tipo divergente | HIGH | 2 horas |
| 9 | H-14 | Fiados sin tabla de movimientos | HIGH | 4 horas |
| 10 | H-08 | Webhook Telegram sin secret token | HIGH | 1 hora |

**Tiempo total estimado para CRIT + TOP-10 HIGH**: ~10 días persona.

---

**Siguiente paso**: Fase 5 — matriz de reutilización para extraer el template-base.
