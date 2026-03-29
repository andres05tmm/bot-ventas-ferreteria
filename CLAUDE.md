# FerreBot — Contexto para Claude Code

FerreBot es un bot de Telegram para Ferretería Punto Rojo (Cartagena, Colombia).
Los vendedores registran ventas por voz o texto, Claude AI interpreta los mensajes,
y un dashboard React muestra analíticas en tiempo real.

**Estado actual:** PostgreSQL en producción (Railway). Migración completada.
**Objetivo actual:** Refactorización — dividir archivos monolíticos en módulos pequeños.

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

---

## Arquitectura actual

```
config.py        ← configuración central, clientes API, timezone Colombia
db.py            ← pool de conexiones PostgreSQL
main.py          ← entry point del bot, registro de handlers
start.py         ← launcher Railway (bot + API en hilo daemon)

ai.py            ← motor Claude: procesar_con_claude, procesar_acciones (2685 líneas — reducir en Tarea I)
memoria.py       ← capa de datos: catálogo, inventario, caja, fiados (convertir en thin wrapper en Tarea H)

handlers/
  comandos.py    ← 50+ comandos Telegram (~2200 líneas — dividir en Tarea F)
  mensajes.py    ← captura de ventas por IA
  callbacks.py   ← botones inline
  productos.py   ← navegador de productos
  alias_handler.py

routers/         ← 8 routers FastAPI (ventas, catalogo, caja, clientes, etc.)
skills/          ← archivos .md con conocimiento del dominio ferretero
ventas_state.py  ← estado thread-safe de ventas en curso
```

---

## Refactorización en curso

Las notas detalladas de cada tarea están en `_obsidian/01-Proyecto/TAREA-X.md`.

### Fase 1 — paralelo total (empezar aquí)
| Tarea | Qué crear | Prioridad |
|---|---|---|
| A | `middleware/` — auth + rate_limit | 🔴 CRÍTICA |
| B | `ai/price_cache.py` — thread-safe | 🔴 CRÍTICA |
| C | `migrations/` — mover migrate_*.py | 🟡 |
| D | `services/catalogo_service.py` | 🟡 |
| E | `services/inventario_service.py` | 🟡 |

### Fase 2 — después de Fase 1
| Tarea | Qué crear/editar | Depende de |
|---|---|---|
| F | `handlers/cmd_*.py` + aplicar `@protegido` | A |
| G | `ai/prompts.py` + `ai/excel_gen.py` | B |
| H | `services/caja_service.py` + `fiados_service.py` + thin wrapper `memoria.py` | D + E |

### Fase 3 — solo al final
| Tarea | Qué editar | Depende de |
|---|---|---|
| I | Limpiar `ai.py` (2685 → ~800 líneas) | B + G |

### Paralelo con todo
| Tarea | Qué crear |
|---|---|
| J | `tests/` unitarios por módulo |

---

## Cómo ejecutar una tarea

Cuando el usuario diga "ejecuta TAREA-X":

1. Lee `_obsidian/01-Proyecto/TAREA-X.md`
2. Verifica que sus dependencias estén completas
3. Ejecuta exactamente lo que indica la nota
4. Corre los tests indicados
5. Verifica: `python -c "import main; print('OK')"`
6. Haz commit con el mensaje indicado en la nota
7. Reporta: `✅ TAREA X COMPLETA`

---

## Verificación estándar antes de cada commit

```bash
python -c "from <modulo_nuevo> import *; print('imports OK')"
python -m pytest tests/test_<modulo>.py -v
python -m pytest tests/ -v --ignore=test_suite.py
python -c "import main; print('main OK')"
```

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
AUTHORIZED_CHAT_IDS   # Nueva (Tarea A) — IDs separados por coma
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
- `MEMORIA_FILE` - Legacy JSON file path (default "memoria.json")
- `ADMIN_CHAT_IDS` - Comma-separated Telegram chat IDs for admin access
- `config.py` - Centralized configuration, API client initialization
- `.env` - Environment variables (git-ignored)
- `nixpacks.toml` - Railway build configuration with Node 20 + Python 3.11 setup
- `nixpacks.toml`:
## Platform Requirements
- Python 3.11
- Node.js 20
- PostgreSQL (or fallback in-memory mode if DATABASE_URL unset)
- Telegram bot token
- Anthropic API key
- OpenAI API key
- PostgreSQL instance (Railway managed)
- Environment variables configured in Railway dashboard
- Nixpacks buildpack (automatic with Railway)
- Single dyno runs both:
## Architecture Notes
- `start.py` spawns two threads:
- Optional: Safety net background thread for daily close automation
- Synchronous psycopg2 with ThreadedConnectionPool
- 2-10 connection limit pool with 8-second query timeout
- No async/await at database layer — only at Telegram bot level
- FastAPI serves dashboard and API endpoints
- CORS enabled for all origins (`allow_origins=["*"]`)
- Request logging middleware adds `X-Request-ID` header
- Static React build mounted at `/` for SPA serving
- OpenAPI docs at `/docs`
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- `snake_case.py` for modules and scripts
- `handlers/` subdirectory contains handler files (`comandos.py`, `mensajes.py`, `callbacks.py`, etc.)
- `routers/` subdirectory contains FastAPI route modules (`ventas.py`, `catalogo.py`, `caja.py`, etc.)
- Migration files prefixed with `migrate_` (e.g., `migrate_ventas.py`, `migrate_memoria.py`)
- `snake_case` for all functions, both public and private
- Private/internal functions prefixed with single underscore: `_normalizar()`, `_leer_catalogo_postgres()`, `_reconectar()`
- Handler functions: `comando_*` for command handlers, `manejar_*` for action handlers (e.g., `comando_inicio()`, `manejar_audio()`)
- Async functions use `async def` and typically have clear names indicating their async nature
- `snake_case` for all variables
- Dictionary keys use `snake_case` (camelCase discouraged)
- Constants use `UPPER_SNAKE_CASE` (e.g., `COLOMBIA_TZ`, `MAX_STANDBY`, `_TIMEOUT_PENDIENTE`, `DB_DISPONIBLE`)
- Protected module-level state variables prefixed with underscore: `_pool`, `_cache`, `_cache_ts`, `_estado_lock`
- Type hints use lowercase except for custom types (e.g., `dict[int, str]`, not `Dict[int, str]`)
- Use modern union syntax: `dict | None` instead of `Optional[dict]` or `Union[dict, None]`
- Use lowercase built-in types for hints: `list[dict]`, `dict[str, int]`, `tuple[str, str]`
## Code Style
- No linter/formatter explicitly configured (check for `.flake8`, `.pylintrc`, `.black` — none found)
- Line length appears to follow Python conventions (~79-100 char soft limit based on code observed)
- Indentation: 4 spaces consistently
- No explicit linting config found
- Imports follow PEP 8 conventions but organized with custom headers (see Import Organization below)
## Import Organization
- Used inside functions to avoid circular imports: `import db as _db` and `import psycopg2` appear in function bodies
- Example in `db.py`: `from psycopg2.pool import ThreadedConnectionPool` imported inside `init_db()` function
- No path aliases observed (no `jsconfig.json` or `tsconfig` for paths)
- Imports use relative module names: `from memoria import ...`, `import config`, `import db as _db`
## Error Handling
- **Broad except**: `except Exception as e:` is intentional throughout codebase (documented in `CLAUDE.md` as stabilizing pattern)
- **Graceful fallbacks**: Functions return sensible defaults instead of raising
- **Logging errors**: Most exception handlers log the error but don't always re-raise (see Logging below)
- **Resource cleanup**: Context managers (`with` statements) used for DB connections and file handles
- **Retry logic**: `_get_conn()` in `db.py` automatically reconnects pool if connection broken, retries once
- `_check_db()` in `db.py` raises `RuntimeError` if database unavailable (used at start of all public DB functions)
- Environment variable validation in `config.py`: missing TELEGRAM_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY causes `SystemExit(1)` at import
## Logging
- Module-level logger created at top of each file after imports
- Pattern: `logger = logging.getLogger("ferrebot.<module>")`
- Examples:
- `logger.info()` for normal operations (pool created, DB connected, schema verified)
- `logger.warning()` for degraded states (DB offline, DB reconnection needed, missing config)
- Lazy logging for initialization: examples in `db.py` lines 64, 87, 100
- No explicit log levels enforced; application uses INFO and WARNING at minimum
## Comments
- Docstrings (in Spanish) required for all public functions and modules
- Inline comments used sparingly, mostly for:
- Docstrings in Spanish for business logic modules (e.g., `db.py`, `memoria.py`, `ai.py`)
- Docstring includes purpose and sometimes parameter/return documentation
- Example from `db.py` line 35-39:
- Not applicable (Python project)
## Function Design
- No enforced line limit observed
- Functions range from 10 lines (simple getters) to 300+ lines (complex handlers)
- Complex functions like `procesar_con_claude()` and `procesar_acciones()` in `ai.py` break logic into smaller internal helper functions
- Use descriptive parameter names
- Type hints used throughout (modern syntax: `dict`, `list`, not `Dict`, `List`)
- Default parameters documented in docstrings when complex
- Example from `handlers/comandos.py` line 46-50:
- Explicit return type hints: `-> dict`, `-> list[dict]`, `-> dict | None`, `-> int`
- Nullable returns documented: functions returning `None` on failure use `-> dict | None` syntax
- Dictionary returns use consistent key naming across related functions
## Module Design
- No explicit `__all__` lists found
- Public functions are those without leading underscore
- Import style is selective: `from module import specific_function` (not `from module import *`)
- Example from `handlers/mensajes.py`: explicit imports with internal names preserved: `from handlers.callbacks import _enviar_botones_pago as _botones_central`
- `handlers/__init__.py` and `routers/__init__.py` exist but appear empty (checked via file listings)
- No re-exports through barrel files observed
## Threading & Concurrency
- `threading.Lock()` used for all shared state access in multi-threaded contexts
- Pattern: `with _estado_lock:` wraps reads/writes to shared dicts
- Examples:
- Handlers use `async def` and `await` with python-telegram-bot's `ContextTypes`
- Non-blocking DB access: `asyncio.to_thread()` delegates sync DB operations to thread pool
- Example from `db.py` lines 523-540: async wrapper functions use `await _asyncio.to_thread(sync_func, args)`
## State Management
- Protected by locks and timestamps for expiration
- Examples:
- Explicit cleanup functions: `limpiar_pendientes_expirados()` in `ventas_state.py`
- Timestamp-based expiration: `_TIMEOUT_PENDIENTE = 300` (5 minutes in ventas_state.py)
- Background reloading: `_reload_cache_background()` in `memoria.py` uses daemon threads
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- **Dual-process unified launcher** (`start.py`) — manages lifecycle of async bot + sync API
- **Thread-safe state management** — in-memory state for chat-specific workflows guarded by `threading.Lock`
- **Message-driven bot layer** (`handlers/`) consuming text, voice, photos; triggers Claude AI processing
- **Router-based API layer** (`routers/`) providing REST endpoints for dashboard and batch operations
- **Centralized data layer** (`db.py`, `memoria.py`) — PostgreSQL with lazy-loaded in-memory cache
## Layers
- Purpose: Process messages from users, render UI with inline buttons, handle callbacks
- Location: `main.py` (app initialization), `handlers/` (message/command processing)
- Contains: Command handlers, message routing, button callbacks, Telegram API interactions
- Depends on: `config`, `db`, `memoria`, `ai`, `ventas_state`, `utils`
- Used by: End users via Telegram app
- Purpose: Expose dashboard analytics and batch operations via HTTP
- Location: `api.py` (app creation, middleware), `routers/` (domain logic)
- Contains: 8 routers for ventas, catalogo, caja, clientes, reportes, historico, chat, proveedores
- Depends on: `config`, `db`, `memoria`, `ai`, `utils`
- Used by: React dashboard, batch operations, external integrations
- Purpose: Interpret voice/text sales messages, generate Excel reports, answer questions
- Location: `ai.py` (2685 lines — large file pending refactoring)
- Contains: Claude prompt construction, response parsing, Excel generation, client search
- Depends on: `config.claude_client`, `config.openai_client`, `memoria`, `utils`
- Used by: `handlers/mensajes`, `routers/chat`
- Purpose: PostgreSQL operations, connection pooling, schema management
- Location: `db.py` (sync pool using psycopg2), `memoria.py` (cache layer)
- Contains: Pool initialization, query execution with automatic reconnection, thread-safe caching
- Depends on: `config`, `psycopg2`
- Used by: All other layers
- Purpose: Track in-flight sales, pending confirmations, client creation workflows
- Location: `ventas_state.py`
- Contains: Dictionaries for pending sales, standby messages, corrections; timeout expiration logic
- Depends on: `threading.Lock`, `config`
- Used by: `handlers/`, `routers/`, `ai.py`
- Purpose: Shared functions for text parsing, number conversion, normalization
- Location: `utils.py`, `fuzzy_match.py`, `skill_loader.py`, `alias_manager.py`
- Contains: Fraction conversion, audio transcription cleanup, fuzzy product search
- Depends on: Only stdlib
- Used by: All other layers
## Data Flow
- `ventas_pendientes` — sales awaiting payment method selection
- `clientes_en_proceso` — chat-specific client creation workflows
- `esperando_correccion` — pending user corrections to sale lines
- `fotos_pendientes_confirmacion` — user-captured receipt photos awaiting approval
## Key Abstractions
- Representation: `catalogo[clave]` dict with keys:
- Source: `db.productos`, `db.productos_fracciones`, `db.productos_alias`
- Loaded via: `memoria._leer_catalogo_postgres(db_module)`
- Representation: `ventas_state.ventas_pendientes[chat_id]` list containing dicts:
- Persistence: Written to `db.ventas` + `db.ventas_detalle` on payment confirmation
- Workflow: Parsed from text → pending → payment button confirmation → persisted
- Representation: `db.clientes` table with:
- Creation flow: Interactive via `handlers/callbacks.manejar_callback_cliente()`
- Cache: Not cached; queried per-request to avoid stale data
- Representation: `inventario[clave]` dict:
- Source: `db.inventario`
- Updates: Auto-decremented on sale confirmation, manual via `/ajuste`
- Special handling: Wayper products stored as units, shown as kg (see `routers/shared._WAYPER_KG_KEYS`)
## Entry Points
- Location: `main.py`
- Triggers: App initialization on `start.py` import
- Responsibilities:
- Location: `api.py`
- Triggers: Spawned as daemon thread from `start.py`
- Responsibilities:
- Location: `start.py`
- Triggers: `python start.py` (Railway Procfile runs this)
- Responsibilities:
## Error Handling
- **Database unavailable:** `db.DB_DISPONIBLE` flag set once at startup. If False, bot operates in degraded mode (no inventory tracking, no sale persistence). Graceful fallback via lazy imports of `db` module.
- **Claude API failures:** Caught in `ai.procesar_con_claude()`, logged, fallback to rule-based parsing. User sees "No entiendo..." response.
- **Telegram connectivity:** `run_polling()` built-in retry logic. API errors logged but don't crash bot.
- **State expiration:** `ventas_state.limpiar_pendientes_expirados()` runs periodically, removes sales pending >5 minutes to prevent stuck state.
- **Async lock deadlock:** Per-chat locks via `_chat_locks[chat_id]` prevent serial message processing bottleneck. Never taken outside message handler.
## Cross-Cutting Concerns
- Module loggers: `logger = logging.getLogger("ferrebot.<module>")`
- API request logging: `RequestLoggingMiddleware` in `api.py` adds request_id and timing
- Level: INFO for normal flow, WARNING for recoverable errors, ERROR for unexpected failures
- Claude outputs validated via regex in `ai.procesar_acciones()` — extracts JSON blocks
- Fractions converted via `utils.convertir_fraccion_a_decimal()`
- Product search via fuzzy matching + alias lookup (not strict equality)
- Price parsing handles "1,5" (comma) and "1.5" (dot) formats
- Telegram: Handled by `python-telegram-bot` (validates bot token in message signature)
- API: Currently open (CORS allows "*") — no token/auth middleware
- Planned (Tarea A): `middleware/` will add `@protegido` decorator for authorized chat IDs only
- Bot: Uses asyncio internally (`python-telegram-bot` v21+)
- API: Uvicorn handles async ASGI
- Shared state: Protected by `threading.Lock` in `ventas_state`
- Database: `psycopg2.pool.ThreadedConnectionPool` handles concurrent access
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
