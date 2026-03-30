# FerreBot — Contexto para Claude Code

FerreBot es un bot de Telegram para Ferretería Punto Rojo (Cartagena, Colombia).
Los vendedores registran ventas por voz o texto, Claude AI interpreta los mensajes,
y un dashboard React muestra analíticas en tiempo real.

**Estado actual:** PostgreSQL en producción (Railway). Migración completada.
**Objetivo actual:** Refactorización fase 2 — dividir archivos monolíticos restantes en módulos pequeños.

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
2. **Nunca borrar** funciones o archivos sin instrucción explícita — solo crear o editar dentro del archivo asignado
3. **Respetar los imports existentes** — `memoria.py` sigue existiendo como thin wrapper durante toda la refactorización
4. **Cero downtime** — cada commit debe dejar el bot operativo (`python main.py` debe arrancar sin errores)
5. **Un commit por tarea** con el mensaje indicado en la nota de tarea

6. **Imports circulares conocidos — no resolver de otra forma:**
   - `handlers.comandos` → `mensajes`: lazy import dentro del cuerpo de función ✓
   - `catalogo_service` → `memoria`: lazy `from memoria import` dentro de cada función ✓
   - `ai.__init__` → `ventas_state`: lazy dentro de `procesar_acciones` ✓
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

---

## Arquitectura actual (post refactorización v1.0)

```
config.py        ← configuración central, clientes API, timezone Colombia
db.py            ← pool de conexiones PostgreSQL
main.py          ← entry point del bot, registro de handlers
start.py         ← launcher Railway (bot + API en hilo daemon)

ai/
  __init__.py    ← motor Claude: procesar_con_claude, procesar_acciones (~1267 líneas — pendiente fase 2)
  prompts.py     ← construcción de system prompt, catálogo, historial
  excel_gen.py   ← generación y edición de Excel con Claude
  price_cache.py ← cache RAM thread-safe de precios recientes

memoria.py       ← thin wrapper de re-exports sobre services/ (~1120 líneas)

services/
  catalogo_service.py   ← búsqueda y actualización de productos
  inventario_service.py ← descuento y alertas de inventario
  caja_service.py       ← caja, gastos, resumen
  fiados_service.py     ← fiados, abonos, resumen por cliente

handlers/
  mensajes.py    ← captura de ventas por IA (~1509 líneas — pendiente fase 2)
  callbacks.py   ← botones inline (~650 líneas — pendiente tests)
  comandos.py    ← re-export hub de los cmd_*.py
  cmd_ventas.py, cmd_inventario.py, cmd_clientes.py,
  cmd_caja.py, cmd_proveedores.py, cmd_admin.py
  productos.py, alias_handler.py

middleware/
  auth.py        ← @protegido decorator + rate limiter

routers/         ← 8 routers FastAPI
  ventas.py (~812 líneas), chat.py (~954 líneas),
  historico.py (~567 líneas), catalogo.py, caja.py,
  clientes.py, proveedores.py, reportes.py, shared.py

ventas_state.py  ← estado thread-safe de ventas en curso (NO TOCAR sin tests)
migrations/      ← 7 scripts de migración numerados 001-007
tests/           ← 62 tests, 0 failed (cobertura: services + middleware + price_cache)
```

---

## Lo que falta (objetivo de la fase 2)

| Archivo | Líneas | Problema | Plan |
|---|---|---|---|
| `handlers/mensajes.py` | 1509 | Parsing + despacho + estado mezclados | Extraer `parsing.py` + `cliente_flujo.py` |
| `ai/__init__.py` | 1267 | Llamadas API + parsing de acciones mezclados | Extraer `ai/response_builder.py` |
| `handlers/callbacks.py` | 650 | Sin tests | Agregar `tests/test_callbacks.py` |
| `routers/ventas.py` | 812 | Sin tests | Agregar `tests/test_router_ventas.py` |
| `routers/chat.py` | 954 | Sin tests | Agregar `tests/test_router_chat.py` |
| `routers/historico.py` | 567 | Sin tests | Agregar `tests/test_router_historico.py` |
| `memoria.py` | — | Thin wrapper sin documentar | Agregar advertencia con tabla de re-exports |

Ver `.planning/milestones/v2.0-refactoring/` para el plan detallado de cada tarea.

---

## Cómo ejecutar una tarea

Cuando el usuario diga "ejecuta fase X" o "sigue el plan de fase X":

1. Lee `.planning/phases/0X-*.md` completamente antes de tocar cualquier archivo
2. Verifica que las dependencias estén completas (pytest pasa en verde)
3. Ejecuta exactamente lo que indica el plan, paso a paso
4. Corre la verificación estándar antes de cada commit
5. Haz commit con el mensaje indicado en el plan
6. Reporta: `✅ Fase X completa — N líneas eliminadas, M tests agregados`

---

## Verificación estándar antes de cada commit

```bash
# 1. Imports limpios — obligatorio si tocaste handlers/ o ai/
python -c "import handlers.mensajes; import ai; import handlers.callbacks; print('imports OK')"

# 2. Tests completos
pytest tests/ -x -q --tb=short

# 3. Si tocaste ai/__init__.py o memoria.py
python -c "from ai import procesar_con_claude, procesar_acciones, procesar_acciones_async; print('ai OK')"

# 4. Bot arranca
python -c "import main; print('main OK')"
```

---

## Patrón de tests del proyecto

Replicar el patrón de `tests/test_catalogo_service.py` — stubs de módulo en `sys.modules` ANTES de cualquier import propio:

```python
import sys, types, threading

if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    _cfg.COLOMBIA_TZ = None
    _cfg.claude_client = None
    sys.modules["config"] = _cfg

if "memoria" not in sys.modules:
    _mem = types.ModuleType("memoria")
    _mem.cargar_memoria = lambda: {}
    sys.modules["memoria"] = _mem

if "ventas_state" not in sys.modules:
    _vs = types.ModuleType("ventas_state")
    _vs.ventas_pendientes = {}
    _vs._estado_lock = threading.Lock()
    sys.modules["ventas_state"] = _vs
```

Usar `pytest` + `unittest.mock.patch`. No usar conexión real a DB ni Telegram.

---

## Convenciones de código

- **Imports:** agrupados con headers `# -- stdlib --`, `# -- terceros --`, `# -- propios --`
- **Logger:** `logger = logging.getLogger("ferrebot.<modulo>")`
- **Funciones privadas:** prefijo `_underscore`
- **Constantes:** `UPPER_SNAKE_CASE`
- **Docstrings:** en español para lógica de negocio
- **Errores:** `except Exception as e:` intencional — estabilidad del bot primero
- **Threading:** `threading.Lock` para todo estado compartido — nunca modificar dicts desde múltiples hilos sin lock

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

**FerreBot — Refactorización**

FerreBot es un bot de Telegram para Ferretería Punto Rojo (Cartagena, Colombia) que permite a vendedores registrar ventas por voz o texto usando IA (Claude). Esta iniciativa es una refactorización estructural: dividir archivos monolíticos (`ai.py` de 2685 líneas, `handlers/comandos.py` de ~2200 líneas) en módulos pequeños y cohesivos, sin cambiar funcionalidad externa. El bot debe permanecer operativo en cada commit del proceso.

**Core Value:** El bot no se rompe durante la refactorización — cada commit deja `python main.py` arrancando sin errores.

### Constraints

- **Tech stack**: Python 3.11, python-telegram-bot 21.3, psycopg2-binary (sync) — no cambiar
- **Archivos protegidos**: `db.py`, `config.py`, `main.py` — no modificar
- **Deploy**: Railway con Nixpacks, `python3 start.py` — cada commit debe arrancar
- **Threading**: `threading.Lock` para todo estado compartido — mantener patrón existente
- **Backwards compat**: `memoria.py` sigue exportando las mismas funciones durante toda la refactorización (thin wrapper)
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
- pip (Python) - installed via Nixpacks
- npm (Node.js) - installed via Nixpacks for dashboard
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
- pytest - test runner (referenced in CLAUDE.md conventions)
## Key Dependencies
- anthropic 0.49.0+ - Claude API client (primary AI engine)
- openai 1.40.0+ - OpenAI SDK (fallback AI, GPT)
- python-telegram-bot[webhooks] 21.3 - Telegram integration
- psycopg2-binary 2.9.9+ - PostgreSQL sync access (pool-based, no async)
- fastapi 0.111.0+ - REST API server
- uvicorn[standard] 0.29.0+ - ASGI server with extra dependencies
- starlette (via FastAPI) - middleware support
- python-dotenv 1.0.0+ - Environment variable loading
- openpyxl 3.1.2 - Excel file generation
- httpx 0.27.0+ - HTTP client library
- rapidfuzz 3.0.0+ - Fuzzy string matching for product search
- matplotlib - Data visualization (legacy, may be phased out)
- cloudinary - Image/file hosting for photos in facturas/abonos
- python-multipart 0.0.9 - Multipart form data handling (FastAPI uploads)
## Configuration
- `TELEGRAM_TOKEN` - Bot token from @BotFather
- `ANTHROPIC_API_KEY` - Claude API key
- `OPENAI_API_KEY` - OpenAI API key (fallback)
- `DATABASE_URL` - PostgreSQL connection string (Railway)
- `WEBHOOK_URL` - Set to empty string to force polling mode (default)
- `PORT` - API port (default 8001 for API, 8443 for webhook)
- `ADMIN_CHAT_IDS` - Comma-separated Telegram chat IDs for admin access
- `config.py` - Centralized configuration, API client initialization
- `.env` - Environment variables (git-ignored)
- `nixpacks.toml` - Railway build configuration with Node 20 + Python 3.11 setup
## Platform Requirements
- Python 3.11 + Node.js 20 + PostgreSQL (Railway)
- Single dyno runs both bot and API
## Architecture Notes
- `start.py` spawns two threads: async bot + sync API daemon
- Synchronous psycopg2 with ThreadedConnectionPool (2-10 connections, 8s timeout)
- No async/await at database layer — only at Telegram bot level
- FastAPI serves dashboard and API endpoints
- CORS enabled for all origins (`allow_origins=["*"]`)
- Static React build mounted at `/` for SPA serving
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- `snake_case.py` for modules and scripts
- Private/internal functions prefixed with single underscore: `_normalizar()`, `_leer_catalogo_postgres()`
- Handler functions: `comando_*` for command handlers, `manejar_*` for action handlers
- Constants use `UPPER_SNAKE_CASE` (e.g., `COLOMBIA_TZ`, `MAX_STANDBY`, `DB_DISPONIBLE`)
- Type hints use lowercase: `dict | None` not `Optional[dict]`, `list[dict]` not `List[dict]`
## Code Style
- Indentation: 4 spaces consistently
- Imports organized with headers: `# -- stdlib --`, `# -- terceros --`, `# -- propios --`
- Used inside functions to avoid circular imports: `import db as _db` in function bodies
## Error Handling
- `except Exception as e:` is intentional throughout — stability over strictness
- Graceful fallbacks: functions return sensible defaults instead of raising
- `db.DB_DISPONIBLE` flag: bot operates in degraded mode if DB is offline
## Logging
- Pattern: `logger = logging.getLogger("ferrebot.<module>")`
- `logger.info()` for normal operations, `logger.warning()` for degraded states
## Threading & Concurrency
- `threading.Lock()` for all shared state — pattern: `with _estado_lock:`
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
