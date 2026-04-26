# FerreBot — Ferretería Punto Rojo

Bot de Telegram + Dashboard web para gestión de ventas, inventario, caja y facturación electrónica DIAN.

---

## Arquitectura

Dos servicios independientes en Railway, mismo repositorio, mismo build:

```
run.sh
  ├── SERVICE_TYPE=bot  → python3 start-bot.py     (Bot Telegram, webhook)
  └── SERVICE_TYPE=api  → uvicorn api:app           (API FastAPI + Dashboard React)
```

**Bot** (`start-bot.py`, `main.py`): recibe updates de Telegram vía webhook. Usa Claude (Anthropic) + OpenAI para procesar lenguaje natural. Registra ventas, consulta inventario, responde al vendedor por chat. El ~60% de ventas simples se resuelven en Python puro vía `bypass.py` sin llamar a Claude (800ms → <5ms).

**API + Dashboard** (`api.py`): FastAPI sirve la API REST y el build estático de React (`dashboard/dist/`). El dashboard se comunica con el bot en tiempo real vía SSE usando `pg_notify` como bus de eventos.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Bot | python-telegram-bot 21.3, webhook mode |
| API | FastAPI + Uvicorn (uvloop), Python 3.11 |
| Base de datos | PostgreSQL — `db.py` con `ThreadedConnectionPool` (minconn=2, maxconn=10) |
| Tiempo real | `pg_notify` → `_pg_listen_worker` (hilo daemon) → SSE → `useRealtime.js` |
| Frontend | React + Vite, servido como static files por FastAPI |
| IA | Anthropic Claude (chat/análisis), OpenAI Whisper (transcripción de audio) |
| Facturación | MATIAS API — UBL 2.1, DIAN Colombia |
| Imágenes | Cloudinary (fotos de facturas de proveedores) |
| Deploy | Railway (Nixpacks), Node 20 + Python 3.11 |

---

## Mapa de archivos

```
# ── Entrypoints ──────────────────────────────────────────────────────────────
api.py              — Entry point FastAPI: lifespan, CORS, routers, static files, pg_listen_worker
start-bot.py        — Entry point Bot: inicializa DB, webhook, registra handlers de main.py
start.py            — Desarrollo local: corre bot + API juntos
main.py             — Registro de todos los handlers PTB (comandos + mensajes + callbacks)
run.sh              — Script Railway: bifurca por SERVICE_TYPE

# ── Núcleo compartido ─────────────────────────────────────────────────────────
config.py           — Variables de entorno, clientes Anthropic/OpenAI, COLOMBIA_TZ
db.py               — Pool PostgreSQL, wrappers sync y async, _init_schema()
memoria.py          — Thin wrapper (~151 callers). Re-exporta desde services/catalogo_service.py
ventas_state.py     — Estado de ventas pendientes, fiados en proceso, clientes en proceso
utils.py            — Helpers de formato: convertir_fraccion_a_decimal, decimal_a_fraccion_legible
bypass.py           — Bypass Python para ventas simples sin Claude (enteros, fracciones, puntillas por peso/caja)
fuzzy_match.py      — Búsqueda fuzzy de productos por nombre
alias_manager.py    — Gestión de aliases dinámicos (typos: drwayll→drywall, tiner→thinner)
skill_loader.py     — Carga skills personalizados del bot desde la BD
graficas.py         — Generación de gráficas para reportes
keepalive.py        — Ping periódico para evitar sleep en Railway free tier

# ── Módulo ai/ — Procesamiento IA ────────────────────────────────────────────
ai/__init__.py      — Re-exporta procesar_con_claude, procesar_acciones, procesar_acciones_async
ai/prompts.py       — Construcción del system prompt de Claude (incluye _ALIAS_FERRETERIA)
ai/prompt_context.py— Contexto dinámico por mensaje (caja abierta, deudas, fiados)
ai/prompt_products.py — Serialización del catálogo para el prompt de Claude
ai/response_builder.py— Parseo y construcción de respuesta desde la respuesta de Claude
ai/price_cache.py   — Caché en memoria de precios recientes (TTL 300s) para contexto del prompt
ai/excel_gen.py     — Generación de reportes Excel vía IA

# ── Módulo handlers/ — Bot Telegram ──────────────────────────────────────────
handlers/mensajes.py   — Handler principal: texto, audio (Whisper), documentos Excel
handlers/dispatch.py   — Flujos especiales sin Claude (wizards, bypasses). TODOS los imports son LAZY
handlers/intent.py     — Clasificación de intención del mensaje antes de Claude
handlers/parsing.py    — Parseo de respuestas estructuradas de Claude
handlers/comandos.py   — /start, /help, /comandos y utilidades generales
handlers/callbacks.py  — InlineKeyboard callbacks (confirmación pago, botones de método)
handlers/cliente_flujo.py — Wizard multi-paso de creación de cliente
handlers/alias_handler.py — Gestión de aliases desde el chat del bot
handlers/cmd_ventas.py    — /ultima, /anular, /fiado, /deudas del bot
handlers/cmd_caja.py      — /caja, /apertura, /cierre, /gasto del bot
handlers/cmd_inventario.py— /inventario, /precio, /stock del bot
handlers/cmd_clientes.py  — /cliente, /buscar del bot
handlers/cmd_admin.py     — /admin, /usuarios (solo admin) del bot
handlers/cmd_auth.py      — /registro, /rol del bot
handlers/cmd_facturacion.py — /factura_electronica del bot
handlers/cmd_proveedores.py — /factura, /abonar, /borrar_factura del bot

# ── Módulo middleware/ — Bot Telegram ─────────────────────────────────────────
middleware/auth.py      — Decorador @protegido: autenticación por chat_id + rate limiting

# ── Módulo auth/ — Usuarios del bot ──────────────────────────────────────────
auth/usuarios.py        — get_usuario(telegram_id), es_admin(), registrar_telegram_id(), crear_vendedor()
                          (separado de routers/usuarios.py para evitar imports circulares con handlers)

# ── Módulo routers/ — API FastAPI ─────────────────────────────────────────────
routers/deps.py        — Dependencias de auth: get_current_user, get_filtro_usuario, get_filtro_efectivo
routers/events.py      — SSE: notify_all(), broadcast(), _event_generator(), _notify_sem
routers/ventas.py      — CRUD ventas, venta-rapida, venta-varia
routers/caja.py        — Apertura/cierre caja, gastos, compras, compras fiscales
routers/catalogo.py    — Productos, precios, stock, fracciones, mayorista
routers/facturacion.py — Emisión DIAN, historial, webhook MATIAS
routers/chat.py        — /chat y /chat-stream: IA del dashboard (Haiku → Sonnet según complejidad)
routers/clientes.py    — CRUD clientes
routers/proveedores.py — Facturas proveedores + Cloudinary
routers/auth.py        — JWT login/logout (Telegram Login Widget)
routers/usuarios.py    — CRUD usuarios (admin)
routers/libro_iva.py   — Libro IVA
routers/historico.py   — Historial ventas con filtros
routers/reportes.py    — /kardex, /resultados, /proyeccion
routers/shared.py      — Helpers compartidos entre routers: _hoy(), _leer_excel_rango(),
                          _leer_ventas_postgres(), _stock_wayper(), _leer_compras()

# ── Módulo services/ ──────────────────────────────────────────────────────────
services/catalogo_service.py  — Fuente de verdad del catálogo (memoria.py re-exporta desde aquí)
services/caja_service.py      — Lógica de caja: apertura, cierre, balance del día
services/facturacion_service.py — Integración MATIAS API (auth, emisión, PDF, ciudades)
services/fiados_service.py    — Gestión de créditos/fiados a clientes
services/inventario_service.py— Actualización de stock, kardex de movimientos

# ── Migraciones ────────────────────────────────────────────────────────────────
migrations/001_migrate_memoria.py     — productos / catálogo
migrations/002_migrate_historico.py   — histórico de ventas
migrations/003_migrate_ventas.py      — tabla ventas + ventas_detalle
migrations/004_migrate_gastos_caja.py — gastos y caja
migrations/004_usuarios_auth.py       — tabla usuarios (RBAC)
migrations/005_migrate_compras.py     — compras a proveedores
migrations/006_migrate_fiados.py      — fiados / créditos
migrations/007_migrate_proveedores.py — facturas de proveedores
migrations/008_migrate_facturacion.py — facturación electrónica DIAN
migrations/009_iva_compras_saldos.py  — IVA y saldos proveedores
migrations/010_compras_fiscal.py      — compras fiscales

# ── Dashboard React ───────────────────────────────────────────────────────────
dashboard/src/App.jsx                  — Router principal, layout con tabs
dashboard/src/pages/Login.jsx          — Telegram Login Widget + JWT
dashboard/src/hooks/useRealtime.js     — SSE hook con backoff exponencial y evento 'reconnected'
dashboard/src/hooks/useAuth.js         — JWT storage, logout, token validation
dashboard/src/hooks/useVendorFilter.jsx— Selector de vendedor para admins
dashboard/src/components/ChatWidget.jsx— Chat IA del dashboard (Haiku/Sonnet, toggle Auto/Haiku/Sonnet)
dashboard/src/components/shared.jsx    — Componentes reutilizables (modales, badges, etc.)
dashboard/src/components/ui/AnimatedBackground.jsx — Fondo animado con color #C8200E
dashboard/src/tabs/                    — Un componente .jsx por tab del dashboard
dashboard/src/utils/generarPDF.js      — Generación de PDF de facturas en cliente

# ── Tests ──────────────────────────────────────────────────────────────────────
test_suite.py           — Runner principal: corre todos los tests/test_*.py
tests/                  — 145+ tests unitarios organizados por módulo
```

---

## Reglas críticas — leer antes de tocar código

### 1. async/await
Cualquier función de router que llame `await notify_all()` **debe ser `async def`**. FastAPI soporta ambas, pero `await` dentro de `def` es `SyntaxError` en tiempo de importación — crashea el servidor completo.

```python
# ✅ correcto
async def registrar_venta(...):
    ...
    await notify_all("venta_registrada", {...})

# ❌ revienta el deploy
def registrar_venta(...):
    ...
    await notify_all("venta_registrada", {...})
```

### 2. Zona horaria — siempre Colombia (UTC-5)
Railway corre en UTC. `date.today()` y `new Date().toISOString()` devuelven UTC — a las 7 PM Colombia ya es medianoche UTC del día siguiente.

```python
# ✅ Python — usar COLOMBIA_TZ de config.py
from config import COLOMBIA_TZ
from datetime import datetime
hoy = datetime.now(COLOMBIA_TZ).strftime('%Y-%m-%d')

# ❌ nunca esto en el backend
from datetime import date
hoy = str(date.today())  # UTC, no Colombia
```

```js
// ✅ JS — en-CA produce YYYY-MM-DD, timeZone fija la zona
new Date().toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })

// ❌ nunca esto en el frontend
new Date().toISOString().slice(0, 10)  // UTC
```

### 3. Logging — siempre getLogger, nunca print
```python
import logging
log = logging.getLogger("ferrebot.<modulo>")
log.info("mensaje")   # visible en Railway
# nunca: print("mensaje")
```

### 4. Base de datos — nunca psycopg2 directo
```python
# ✅ usar siempre el módulo db.py
import db as _db
rows = _db.query_all("SELECT ...", [params])
await _db.execute_async("INSERT ...", [params])

# ❌ nunca conectar directamente
conn = psycopg2.connect(DATABASE_URL)
```

### 5. memoria.py — no cambiar firmas públicas
`memoria.py` tiene ~151 callers en el proyecto. Es un thin wrapper que re-exporta desde `services/catalogo_service.py`. Cambiar una firma sin actualizar el service original rompe silenciosamente.

### 6. notify_all — siempre await, nunca broadcast directo desde routers
```python
# ✅ desde routers: usa pg_notify → llega a TODAS las réplicas
from routers.events import notify_all
await notify_all("venta_registrada", {"consecutivo": 42})

# ⚠️ broadcast() es solo para uso interno de _pg_listen_worker
```

### 7. Handlers del bot — siempre decorar con @protegido
Todo handler de Telegram registrado en `main.py` debe llevar el decorador `@protegido` de `middleware/auth.py`. Este decorador aplica autenticación por `chat_id` (variable `AUTHORIZED_CHAT_IDS`) y rate limiting thread-safe.

```python
from middleware.auth import protegido

# ✅ correcto
@protegido
async def comando_mi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ...

# ❌ handler sin proteger — cualquier chat externo puede invocarlo
async def comando_mi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ...
```

Si `AUTHORIZED_CHAT_IDS` está vacío, el middleware es **fail-open** (permite todo). En producción debe contener el chat_id del grupo de la ferretería.

### 8. Imports lazy en handlers/dispatch.py y similares
Los módulos `handlers/dispatch.py`, `handlers/callbacks.py` y similares tienen **todos sus imports dentro de las funciones**, no al nivel del módulo. Esto es obligatorio para evitar ciclos de importación con `mensajes.py` y `ventas_state.py`.

```python
# ✅ import lazy — dentro de la función
async def manejar_flujo_cliente(update, chat_id: int, mensaje: str) -> bool:
    from ventas_state import clientes_en_proceso, _estado_lock
    from handlers.cliente_flujo import guardar_cliente_y_continuar
    ...

# ❌ import al nivel del módulo en estos archivos — genera ciclo
from ventas_state import clientes_en_proceso  # NO en dispatch.py
```

### 9. Auth en routers de la API — usar deps.py
Al crear un endpoint nuevo en cualquier router, usar siempre las dependencias de `routers/deps.py`:

```python
from routers.deps import get_current_user, get_filtro_usuario, get_filtro_efectivo
from fastapi import Depends

# ── Las tres dependencias disponibles ──────────────────────────────────────────

# Valida JWT y retorna payload: {usuario_id, telegram_id, nombre, rol}
# Usar en endpoints que necesitan saber quién hace la petición
@router.get("/mi-endpoint")
async def mi_endpoint(current_user=Depends(get_current_user)):
    ...

# Retorna usuario_id si rol=vendedor, None si rol=admin
# Usar para filtros WHERE simples (vendedor ve solo sus datos)
@router.get("/ventas")
async def listar_ventas(filtro=Depends(get_filtro_usuario)):
    ...

# Admin puede impersonar un vendedor pasando ?vendor_id=N
# Usar cuando el admin necesita ver datos de un vendedor específico
@router.get("/ventas-admin")
async def listar_ventas_admin(filtro=Depends(get_filtro_efectivo)):
    ...
```

### 10. MATIAS API — IDs de ciudad no son códigos DANE
MATIAS API usa IDs internos secuenciales propios para ciudades, **no** los códigos DANE municipales del DANE colombiano. Enviar el código DANE como `city_id` causa el error `"El campo customer.city_id no existe en la tabla cities"`.

```python
# ✅ siempre usar el caché que mapea DANE → ID interno de MATIAS
from services.facturacion_service import _get_city_id
city_id = await _get_city_id(dane_code="13001")  # Cartagena

# ❌ nunca pasar el código DANE directo como city_id
payload = {"customer": {"city_id": 13001}}  # INCORRECTO
```

El caché `_cities_cache` se carga del endpoint `GET /cities` de MATIAS API y es thread-safe con `threading.Lock`. Si el caché no está cargado, llamar `_cargar_cities()` primero.

---

## Convenciones de código

### Orden de imports — siempre respetar esta estructura
```python
"""
Docstring del módulo en español.
"""

# -- stdlib --
import os
import logging
from datetime import datetime

# -- terceros --
from fastapi import HTTPException, Depends
import httpx

# -- propios --
import db as _db
from config import COLOMBIA_TZ
from routers.deps import get_current_user
```

### Type hints — sintaxis moderna de Python 3.10+
```python
# ✅ correcto
def buscar(id: int) -> dict | None: ...
def listar() -> list[dict]: ...
param: str | None = None

# ❌ nunca esto
from typing import Optional, Dict, List, Union
def buscar(id: int) -> Optional[Dict]: ...
```

### Docstrings en español
Todos los módulos y funciones públicas usan docstrings en español. Las funciones internas (prefijo `_`) pueden omitirlos si el nombre es autoexplicativo.

```python
def registrar_venta(datos: dict) -> int:
    """
    Registra una venta en PostgreSQL y actualiza el stock.
    Retorna el consecutivo asignado.
    """
    ...
```

### Separadores visuales de sección
```python
# ─────────────────────────────────────────────
# NOMBRE DE SECCIÓN
# ─────────────────────────────────────────────
```

### Nombres
- Módulos y archivos: `snake_case.py`
- Funciones y variables: `snake_case`
- Funciones privadas/internas: `_snake_case` (prefijo underscore)
- Constantes: `UPPER_SNAKE_CASE`
- Estado de módulo protegido: `_pool`, `_cache`, `_cache_ts`
- Handlers de comando: `comando_*` — handlers de acción: `manejar_*`
- Claves de diccionario: `snake_case` (nunca camelCase)

### Error handling
- `except Exception as e:` es intencional en la mayoría de casos (estabilidad en producción)
- Las funciones retornan defaults seguros en vez de propagar excepciones: `dict | None`, `[]`, `0.0`
- Logging del error con `logger.warning(f"contexto: {e}")` antes de retornar el default
- Retry logic en `_get_conn()` de `db.py` — no reimplementar en otros módulos

---

## Variables de entorno

| Variable | Servicio | Requerida |
|----------|----------|-----------|
| `TELEGRAM_TOKEN` | Bot | Sí |
| `ANTHROPIC_API_KEY` | Bot + API | Sí |
| `OPENAI_API_KEY` | Bot + API | Sí |
| `DATABASE_URL` | Ambos | Sí |
| `SECRET_KEY` | API | Sí (JWT) |
| `WEBHOOK_URL` | Bot | Sí (modo webhook) |
| `SERVICE_TYPE` | Ambos | Sí (`bot` o `api`) |
| `CORS_ORIGIN` | API | No (default: URL Railway) |
| `CLOUDINARY_CLOUD_NAME` | API | Para proveedores |
| `CLOUDINARY_API_KEY` | API | Para proveedores |
| `CLOUDINARY_API_SECRET` | API | Para proveedores |
| `MATIAS_EMAIL` | API | Sí (facturación DIAN) |
| `MATIAS_PASSWORD` | API | Sí (facturación DIAN) |
| `MATIAS_RESOLUTION` | API | Sí (resolución DIAN) |
| `MATIAS_PREFIX` | API | Sí (prefijo factura, ej: `LZT`) |
| `MATIAS_NUM_DESDE` | API | Sí (primer número rango DIAN) |
| `MATIAS_API_URL` | API | No (default: `https://api-v2.matias-api.com/api/ubl2.1`) |
| `AUTHORIZED_CHAT_IDS` | Bot | No (IDs separados por coma — fail-open si vacío) |
| `RATE_LIMIT_SEGUNDOS` | Bot | No (default: 2) |
| `RATE_LIMIT_MAX` | Bot | No (default: 5 mensajes por ventana) |
| `PORT` | Ambos | Railway lo inyecta automáticamente |

---

## Comandos frecuentes

```bash
# Desarrollo local (bot + API juntos)
python start.py

# Solo API en local
uvicorn api:app --reload --port 8000

# Dashboard en desarrollo
cd dashboard && npm run dev

# Build del dashboard (Railway lo hace automático)
cd dashboard && npm run build

# Tests — correr manualmente antes de merge a main
python test_suite.py

# Ver logs Railway en tiempo real
railway logs --tail
```

---

## Flujo de una venta (bot)

```
Usuario Telegram
  └─► mensajes.py → _procesar_mensaje()
        ├─► dispatch.py: flujos especiales (wizard cliente, confirmación pago)
        │     └─► LAZY imports obligatorios aquí
        ├─► bypass.py: intentar_bypass_python()    ← ~60% de ventas simples
        │     └─► resuelve en <5ms sin llamar a Claude
        └─► ai/: procesar_con_claude()             ← el 40% restante
              ├─► ai/prompts.py: construir system prompt
              ├─► ai/prompt_context.py: agregar contexto dinámico
              ├─► ai/prompt_products.py: serializar catálogo relevante
              ├─► Claude API call
              └─► ai/response_builder.py: parsear respuesta → registrar venta
```

---

## Flujo de tiempo real (SSE)

```
Router FastAPI
  └─► await notify_all("evento", data)
        └─► SELECT pg_notify('ferrebot_events', payload)   ← escribe en PG
              └─► _pg_listen_worker (hilo daemon en api.py) ← lee con LISTEN
                    └─► broadcast() → _do_broadcast()
                          └─► Queue.put_nowait() × N clientes
                                └─► GET /events (SSE stream) → browser
                                      └─► useRealtime.js → onEvent()
```

**Semáforo**: `_notify_sem = Semaphore(3)` limita concurrencia de `notify_all` para no agotar el pool (maxconn=10).

**Detección de desconexión**: ciclo interno de 5s (no 25s). Heartbeat sale cada 25s acumulando ciclos. Suscriptores fantasma se limpian en ≤5s.

**Reconexión frontend**: `useRealtime.js` emite evento sintético `'reconnected'` en cada reconexión (no en la primera conexión). El consumer debe hacer re-fetch completo de datos al recibirlo.

---

## RBAC — Roles y permisos

Dos roles: `admin` y `vendedor`. Columna `rol` en tabla `usuarios`.

| Capacidad | admin | vendedor |
|-----------|-------|----------|
| Ver datos de todos los vendedores | ✅ | ❌ (solo los suyos) |
| Selector de vendedor en dashboard | ✅ | ❌ |
| CRUD usuarios | ✅ | ❌ |
| Comandos `/admin` en bot | ✅ | ❌ |
| Registrar ventas/caja | ✅ | ✅ |

El Telegram ID de Andrés (`1831034712`) está sembrado como admin en la migración `004_usuarios_auth.py`.

**En routers**: usar `get_filtro_efectivo` para que el admin pueda impersonar un vendedor vía `?vendor_id=N`. El filtro retorna `None` cuando el admin no selecciona vendedor (ve todo).

**En el bot**: `auth/usuarios.py` provee `get_usuario(telegram_id)` para verificar si el usuario está registrado y su rol. Los handlers usan `middleware/auth.py` (`@protegido`) para la capa de autenticación básica del chat.

---

## Notas de contexto del proyecto

- **Sin linter configurado**: no hay `.flake8`, `.pylintrc` ni `.black`. Seguir las convenciones del código existente.
- **Sin CI**: `test_suite.py` se corre manualmente antes de merge a main.
- **Sin paginación en endpoints de lista**: el volumen de una ferretería lo permite. Tener en cuenta si crece.
- **Nombres de eventos SSE**: `snake_case` descriptivos — `venta_registrada`, `caja_cerrada`, `inventario_actualizado`, `compra_registrada`, `gasto_registrado`.
- **Commits**: `tipo: descripción` — tipos: `feat`, `fix`, `refactor`, `chore`. Sin atribución de Claude.
- **`.planning/`**: directorio con roadmap GSD (milestones, fases, retrospectivas). No tocar al hacer cambios de código.
- **`_obsidian/`**: vault de Obsidian para notas del proyecto. Ignorar.
- **`routers/shared.py`**: helpers compartidos entre routers. Antes de crear una función de utilidad en un router, verificar si ya existe aquí. `_leer_excel_rango()` mantiene su nombre por compatibilidad aunque ya no lea Excel — delega a `_leer_ventas_postgres()`.
