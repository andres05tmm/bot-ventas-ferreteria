# FerreBot — Contexto para Claude Code

FerreBot es un bot de Telegram para Ferretería Punto Rojo (Cartagena, Colombia).
Los vendedores registran ventas por voz o texto, Claude AI interpreta los mensajes,
y un dashboard React muestra analíticas en tiempo real.

**Estado actual:** PostgreSQL en producción (Railway). Refactorización v2.0 completada (97 tests, todos verdes).
**Objetivo actual:** Refactorización v3.0 — dividir `_procesar_mensaje` y `_construir_parte_dinamica`.

---

## Stack

- **Bot:** Python 3.11 + python-telegram-bot 21.3
- **API:** FastAPI + Uvicorn (hilo daemon, puerto 8001)
- **DB:** PostgreSQL en Railway — psycopg2-binary (sync, no asyncpg)
- **IA:** Claude (Anthropic SDK) + OpenAI SDK
- **Dashboard:** React 18 + Vite + Recharts
- **Deploy:** Railway con Nixpacks — `python3 start.py`

---

## Reglas absolutas

1. **No tocar** `db.py`, `config.py`, `main.py` — están correctos, no necesitan cambios
2. **Nunca borrar** funciones o archivos sin instrucción explícita — solo crear o editar
3. **Respetar los imports existentes** — `memoria.py` sigue existiendo como thin wrapper
4. **Cero downtime** — cada commit debe dejar el bot operativo (`python main.py` arranca sin errores)
5. **Un commit por tarea** con el mensaje indicado en el plan

6. **Imports circulares conocidos — resolver SOLO con lazy imports (dentro del cuerpo de función):**
   - `handlers.comandos` → `mensajes`: lazy ✓
   - `catalogo_service` → `memoria`: lazy ✓
   - `ai.__init__` → `ventas_state`: lazy ✓
   - `ai.__init__` → `ai.prompt_context` / `ai.prompt_products`: lazy (nuevo en v3.0)
   - `handlers.dispatch` → `ventas_state` / `memoria`: lazy (nuevo en v3.0)
   - Antes de cualquier commit que mueva funciones entre módulos, correr:
     `python -c "import handlers.mensajes; import ai; import handlers.callbacks; print('OK')"`

7. **`memoria.py` es thin wrapper — no modificar firmas sin actualizar el service de origen:**
   - `buscar_producto_*`, `cargar_memoria` → `services/catalogo_service.py`
   - `cargar_inventario` → `services/inventario_service.py`
   - `cargar_caja`, `guardar_gasto` → `services/caja_service.py`
   - `guardar_fiado_movimiento`, `abonar_fiado` → `services/fiados_service.py`

8. **`ventas_state.py` — no tocar sin tests previos:**
   Los dicts `ventas_pendientes`, `clientes_en_proceso`, `mensajes_standby` se importan
   por referencia. Moverlos o reimportarlos crea una segunda instancia vacía → bug invisible.
   `get_chat_lock(chat_id)` retorna un `asyncio.Lock` real — no mockear con lambda+yield.

---

## Arquitectura actual (post refactorización v2.0 — estado real)

```
config.py        ← configuración central, clientes API, timezone Colombia
db.py            ← ThreadedConnectionPool (2-10 conns), reconexión automática, 8s timeout
main.py          ← entry point del bot, registro de handlers
start.py         ← launcher Railway (bot + API en hilo daemon)
ventas_state.py  ← estado thread-safe de ventas en curso (NO TOCAR sin tests)

ai/
  __init__.py        ← motor Claude: procesar_con_claude, _pg_* helpers (~690 líneas)
  prompts.py         ← system prompt: _construir_parte_dinamica (1069 líneas — objetivo v3.0)
  response_builder.py← parsing de acciones [VENTA]/[GASTO]/[EXCEL] — NUEVO en v2.0 (~629 líneas)
  excel_gen.py       ← generación y edición de Excel con Claude
  price_cache.py     ← cache RAM thread-safe de precios recientes

memoria.py       ← thin wrapper de re-exports sobre services/ (~1151 líneas)

services/
  catalogo_service.py   ← búsqueda y actualización de productos
  inventario_service.py ← descuento y alertas de inventario
  caja_service.py       ← caja, gastos, resumen
  fiados_service.py     ← fiados, abonos, resumen por cliente

handlers/
  mensajes.py      ← _procesar_mensaje (619 líneas — objetivo v3.0) + audio/foto/doc (~1297 total)
  callbacks.py     ← botones inline (~650 líneas)
  parsing.py       ← parseo puro de texto sin efectos — NUEVO en v2.0 (~178 líneas)
  cliente_flujo.py ← wizard de creación de cliente (preguntas/botones) — NUEVO en v2.0 (~52 líneas)
                     PENDIENTE: absorber _insertar_cliente_pg desde _procesar_mensaje (fase 02 v3.0)
  comandos.py      ← re-export hub de los cmd_*.py
  cmd_ventas.py, cmd_inventario.py (~1011 líneas), cmd_clientes.py,
  cmd_caja.py, cmd_proveedores.py, cmd_admin.py
  productos.py, alias_handler.py

middleware/
  auth.py        ← @protegido decorator + rate limiter

routers/
  ventas.py (~812), chat.py (~954), historico.py (~567),
  catalogo.py (~784), caja.py (~437),
  clientes.py, proveedores.py, reportes.py, shared.py

migrations/      ← 7 scripts numerados 001-007 (todos ejecutados)
tests/           ← 97 tests, 0 failed
  test_caja_service.py, test_catalogo_service.py, test_fiados_service.py,
  test_inventario_service.py, test_middleware.py, test_price_cache.py,
  test_callbacks.py, test_response_builder.py,
  test_router_chat.py, test_router_historico.py, test_router_ventas.py
```

---

## Lo que falta (objetivo v3.0)

| Archivo | Líneas | Problema | Plan |
|---|---|---|---|
| `handlers/mensajes.py` | 1297 | `_procesar_mensaje` (619L) mezcla 5 flujos distintos | Extraer `dispatch.py` + `intent.py`; completar `cliente_flujo.py` |
| `ai/prompts.py` | 1370 | `_construir_parte_dinamica` (1069L) en una función | Extraer `prompt_context.py` + `prompt_products.py` |
| `routers/catalogo.py` | 784 | 0 tests | `tests/test_router_catalogo.py` |
| `routers/caja.py` | 437 | 0 tests | `tests/test_router_caja.py` |
| `handlers/cmd_inventario.py` | 1011 | 0 tests | `tests/test_cmd_inventario.py` |

Ver `.planning/milestones/v3.0-refactoring/` para los planes detallados.

**Archivos nuevos que existirán al final de v3.0:**
- `handlers/dispatch.py` — flujos especiales no-Claude (~350L)
- `handlers/intent.py` — detección de intención (~60L)
- `ai/prompt_context.py` — contexto de negocio para el prompt (~300L)
- `ai/prompt_products.py` — precálculos de productos para el prompt (~700L)

---

## Cómo ejecutar una fase v3.0

```bash
# Fase 01 — red de seguridad (tests routers)
claude "Lee .planning/milestones/v3.0-refactoring/01-tests-routers-catalogo-caja-PLAN.md completamente y ejecútalo paso a paso sin saltarte ninguna verificación"

# /clear — contexto limpio entre fases

# Fase 02 — split _procesar_mensaje
claude "Lee .planning/milestones/v3.0-refactoring/02-split-procesar-mensaje-PLAN.md completamente y ejecútalo paso a paso sin saltarte ninguna verificación"
```

Orden obligatorio: `01 → 02 → 03 → 04`. Ver README en el directorio del milestone.

---

## Verificación estándar antes de cada commit

```bash
# 1. Imports limpios — obligatorio si tocaste handlers/ o ai/
python -c "import handlers.mensajes; import ai; import handlers.callbacks; print('imports OK')"

# 2. Tests completos
pytest tests/ -x -q --tb=short

# 3. Si tocaste ai/__init__.py, ai/prompts.py o memoria.py
python -c "from ai import procesar_con_claude, procesar_acciones, procesar_acciones_async; print('ai OK')"

# 4. Bot arranca
python -c "import main; print('main OK')"
```

---

## Patrón de tests del proyecto

Stubs de módulo en `sys.modules` ANTES de cualquier import propio.
Replicar el patrón de `tests/test_catalogo_service.py`:

```python
import sys, types, threading

for mod, attrs in [
    ("config", {"COLOMBIA_TZ": None, "claude_client": None}),
    ("db", {
        "DB_DISPONIBLE": False,
        "execute": lambda *a, **kw: None,
        "query_one": lambda *a, **kw: None,
        "query_all": lambda *a, **kw: [],
    }),
    ("memoria", {"cargar_memoria": lambda: {}, "invalidar_cache_memoria": lambda: None}),
    ("ventas_state", {
        "ventas_pendientes": {},
        "clientes_en_proceso": {},
        "esperando_correccion": {},
        "_estado_lock": threading.Lock(),
        "_guardar_pendiente": lambda *a: None,
        # get_chat_lock DEBE retornar asyncio.Lock real — no lambda+yield
        "get_chat_lock": lambda cid: __import__("asyncio").Lock(),
    }),
]:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        for k, v in attrs.items(): setattr(m, k, v)
        sys.modules[mod] = m
    else:
        m = sys.modules[mod]
        for k, v in attrs.items():
            if not hasattr(m, k): setattr(m, k, v)
```

Usar `pytest` + `pytest-mock` (fixture `mocker`). No usar conexión real a DB ni Telegram.
`pytest-asyncio` requerido para tests `async` — configurar `asyncio_mode = auto` en `pytest.ini`.

---

## Convenciones de código

- **Imports:** agrupados con headers `# -- stdlib --`, `# -- terceros --`, `# -- propios --`
- **Logger:** `logger = logging.getLogger("ferrebot.<modulo>")`
- **Funciones privadas:** prefijo `_underscore`
- **Constantes:** `UPPER_SNAKE_CASE`
- **Docstrings:** en español para lógica de negocio
- **Errores:** `except Exception as e:` intencional — estabilidad del bot primero
- **Threading:** `threading.Lock` para todo estado compartido — nunca modificar dicts sin lock
- **DB en async handlers:** `await asyncio.to_thread(funcion_sync)` — nunca llamar directo

---

## Variables de entorno

```
DATABASE_URL          # PostgreSQL Railway
TELEGRAM_TOKEN        # Token del bot
ANTHROPIC_API_KEY     # Claude API
OPENAI_API_KEY        # GPT (fallback)
ADMIN_CHAT_ID         # ID Telegram del admin
AUTHORIZED_CHAT_IDS   # IDs separados por coma — enforced por middleware/auth.py
```

<!-- GSD:project-start source:PROJECT.md -->
## Project

**FerreBot — Refactorización v3.0**

FerreBot es un bot de Telegram para Ferretería Punto Rojo (Cartagena, Colombia) que permite a vendedores registrar ventas por voz o texto usando IA (Claude). La refactorización v3.0 divide los dos últimos monolitos: `_procesar_mensaje` (619 líneas) en `handlers/mensajes.py` y `_construir_parte_dinamica` (1069 líneas) en `ai/prompts.py`. El bot debe permanecer operativo en cada commit.

**Core Value:** El bot no se rompe durante la refactorización — cada commit deja `python main.py` arrancando sin errores.

### Constraints

- **Tech stack**: Python 3.11, python-telegram-bot 21.3, psycopg2-binary (sync) — no cambiar
- **Archivos protegidos**: `db.py`, `config.py`, `main.py` — no modificar
- **Deploy**: Railway con Nixpacks, `python3 start.py` — cada commit debe arrancar
- **Threading**: `threading.Lock` para todo estado compartido — mantener patrón existente
- **Backwards compat**: `memoria.py` sigue exportando las mismas funciones (thin wrapper)
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11 - Bot backend, API, database operations, AI processing
- JavaScript/TypeScript - React dashboard frontend
- SQL - PostgreSQL database schema and queries
- Shell - Build and startup scripts
- YAML/TOML - Configuration files
## Runtime
- Python 3.11 (specified in `.python-version`)
- Node.js 20 (specified in `nixpacks.toml`)
- Railway - Nixpacks build system
- Startup: `python3 start.py` via Procfile
## Frameworks
- python-telegram-bot 21.3 - Telegram bot framework with webhook support
- FastAPI 0.111.0+ - REST API for dashboard
- Uvicorn 0.29.0+ - ASGI server (runs on port 8001 as daemon thread)
- React 18.3.1 - UI framework for dashboard
- Vite 5.4.2 - Build tool and dev server (port 5173)
- Recharts 2.12.7 - Charting/visualization library
- PostgreSQL (on Railway) - primary data store
- psycopg2-binary 2.9.9+ - PostgreSQL sync driver (NOT asyncpg)
- ThreadedConnectionPool - thread-safe connection pooling in `db.py`
## Key Dependencies
- anthropic 0.49.0+ - Claude API client
- openai 1.40.0+ - OpenAI SDK (fallback)
- python-telegram-bot[webhooks] 21.3
- psycopg2-binary 2.9.9+
- fastapi 0.111.0+
- uvicorn[standard] 0.29.0+
- python-dotenv 1.0.0+
- openpyxl 3.1.2
- httpx 0.27.0+
- rapidfuzz 3.0.0+
- pytest, pytest-mock, pytest-asyncio - testing
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- `snake_case.py` for modules and scripts
- Private/internal functions prefixed with single underscore: `_normalizar()`, `_leer_catalogo_postgres()`
- Handler functions: `comando_*` for command handlers, `manejar_*` for action handlers
- Constants use `UPPER_SNAKE_CASE`
- Type hints use lowercase: `dict | None` not `Optional[dict]`
## Code Style
- Indentation: 4 spaces
- Imports organized with headers: `# -- stdlib --`, `# -- terceros --`, `# -- propios --`
- Lazy imports inside function bodies to avoid circular imports
## Error Handling
- `except Exception as e:` is intentional — stability over strictness
- `db.DB_DISPONIBLE` flag: bot operates in degraded mode if DB is offline
## Threading & Concurrency
- `threading.Lock()` for all shared state
- `asyncio.to_thread()` for sync DB operations inside async handlers
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- **Dual-process unified launcher** (`start.py`) — async bot + sync API
- **Thread-safe state management** — `ventas_state.py` guarded by `threading.Lock`
- **Message-driven bot layer** (`handlers/`) — text, voice, photos → Claude AI
- **Router-based API layer** (`routers/`) — REST endpoints for dashboard
- **Centralized data layer** (`db.py`, `memoria.py`, `services/`)

## Error Handling
- **Database unavailable:** `db.DB_DISPONIBLE` flag — graceful degraded mode
- **Claude API failures:** Caught in `ai.procesar_con_claude()`, fallback to rule-based parsing
- **State expiration:** `ventas_state.limpiar_pendientes_expirados()` — removes sales pending >5 min
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
