# Architecture

**Analysis Date:** 2026-03-28

## Pattern Overview

**Overall:** Hybrid multi-threaded architecture — Telegram bot running on main thread with polling, FastAPI REST API running in background thread, shared PostgreSQL database as single source of truth.

**Key Characteristics:**
- **Dual-process unified launcher** (`start.py`) — manages lifecycle of async bot + sync API
- **Thread-safe state management** — in-memory state for chat-specific workflows guarded by `threading.Lock`
- **Message-driven bot layer** (`handlers/`) consuming text, voice, photos; triggers Claude AI processing
- **Router-based API layer** (`routers/`) providing REST endpoints for dashboard and batch operations
- **Centralized data layer** (`db.py`, `memoria.py`) — PostgreSQL with lazy-loaded in-memory cache

## Layers

**Telegram Bot Layer:**
- Purpose: Process messages from users, render UI with inline buttons, handle callbacks
- Location: `main.py` (app initialization), `handlers/` (message/command processing)
- Contains: Command handlers, message routing, button callbacks, Telegram API interactions
- Depends on: `config`, `db`, `memoria`, `ai`, `ventas_state`, `utils`
- Used by: End users via Telegram app

**FastAPI REST Layer:**
- Purpose: Expose dashboard analytics and batch operations via HTTP
- Location: `api.py` (app creation, middleware), `routers/` (domain logic)
- Contains: 8 routers for ventas, catalogo, caja, clientes, reportes, historico, chat, proveedores
- Depends on: `config`, `db`, `memoria`, `ai`, `utils`
- Used by: React dashboard, batch operations, external integrations

**AI Processing Layer:**
- Purpose: Interpret voice/text sales messages, generate Excel reports, answer questions
- Location: `ai.py` (2685 lines — large file pending refactoring)
- Contains: Claude prompt construction, response parsing, Excel generation, client search
- Depends on: `config.claude_client`, `config.openai_client`, `memoria`, `utils`
- Used by: `handlers/mensajes`, `routers/chat`

**Data Access Layer:**
- Purpose: PostgreSQL operations, connection pooling, schema management
- Location: `db.py` (sync pool using psycopg2), `memoria.py` (cache layer)
- Contains: Pool initialization, query execution with automatic reconnection, thread-safe caching
- Depends on: `config`, `psycopg2`
- Used by: All other layers

**State Management Layer:**
- Purpose: Track in-flight sales, pending confirmations, client creation workflows
- Location: `ventas_state.py`
- Contains: Dictionaries for pending sales, standby messages, corrections; timeout expiration logic
- Depends on: `threading.Lock`, `config`
- Used by: `handlers/`, `routers/`, `ai.py`

**Utilities Layer:**
- Purpose: Shared functions for text parsing, number conversion, normalization
- Location: `utils.py`, `fuzzy_match.py`, `skill_loader.py`, `alias_manager.py`
- Contains: Fraction conversion, audio transcription cleanup, fuzzy product search
- Depends on: Only stdlib
- Used by: All other layers

## Data Flow

**Voice Sale Entry (User Speaks → Recorded):**

1. User sends voice message in Telegram
2. `handlers/mensajes.manejar_audio()` downloads voice file
3. Transcribes via OpenAI Whisper (API)
4. Calls `ai.procesar_con_claude()` with transcript
5. Claude identifies products + quantities
6. `ai.procesar_acciones()` extracts sale intent
7. Sale stored in `ventas_state.ventas_pendientes[chat_id]`
8. User sees button grid for payment method
9. On callback: `handlers/callbacks.manejar_metodo_pago()` writes to `db.ventas`
10. Inventory auto-decremented via `memoria.descontar_inventario()`
11. Response sent back to user

**Text Sale Entry (User Types):**

1. User sends text message with product names/quantities
2. `handlers/mensajes.manejar_mensaje()` routes to Claude
3. Same flow as voice (steps 4-11)

**Excel Import (User Uploads File):**

1. User uploads .xlsx via `handlers/mensajes.manejar_documento()`
2. `memoria.importar_catalogo_desde_excel()` parses file
3. Updates `db.productos`, `db.productos_fracciones`, etc.
4. Invalidates `memoria._cache`
5. Rebuilds on next `cargar_memoria()` call

**Dashboard Data Request:**

1. React frontend calls `GET /routers/ventas/venta-rapida` or similar endpoint
2. `routers/ventas.py` handler executes
3. Reads from `memoria.cargar_memoria()` or direct `db.query_all()`
4. Returns JSON to dashboard
5. Dashboard renders charts via Recharts

**Startup Sequence:**

1. `start.py` sets `WEBHOOK_URL=""` (force polling mode)
2. Imports `config` (validates env vars, creates API clients)
3. Calls `db.init_db()` — creates pool, runs schema init
4. Spawns API thread (Uvicorn on port 8001)
5. Spawns cache warm-up thread (pre-loads memoria)
6. Spawns historico safety net thread (persists daily totals at 9pm)
7. Deletes old webhook via `Bot.delete_webhook()`
8. Creates fresh asyncio event loop
9. Calls `main()` which builds Telegram Application and runs `run_polling()`

**State Management:**

Thread-safe state management uses `ventas_state._estado_lock` (threading.Lock):
- `ventas_pendientes` — sales awaiting payment method selection
- `clientes_en_proceso` — chat-specific client creation workflows
- `esperando_correccion` — pending user corrections to sale lines
- `fotos_pendientes_confirmacion` — user-captured receipt photos awaiting approval

Each chat_id can have async per-chat lock via `_chat_locks[chat_id]` to serialize message processing.

## Key Abstractions

**Product Entity:**

- Representation: `catalogo[clave]` dict with keys:
  - `nombre`, `nombre_lower` — name and normalized name
  - `precio_unidad` — base price
  - `unidad_medida` — unit (e.g., "metros", "kg")
  - `precios_fraccion` — optional fractional pricing
  - `precio_por_cantidad` — optional bulk pricing
  - `alias` — alternative names for fuzzy matching
- Source: `db.productos`, `db.productos_fracciones`, `db.productos_alias`
- Loaded via: `memoria._leer_catalogo_postgres(db_module)`

**Sale Entity:**

- Representation: `ventas_state.ventas_pendientes[chat_id]` list containing dicts:
  - `producto` — product name
  - `cantidad` — quantity (float, may be fraction)
  - `precio_unitario` — unit price applied
  - `total` — line total
  - `alias_usado` — alias matched (if any)
- Persistence: Written to `db.ventas` + `db.ventas_detalle` on payment confirmation
- Workflow: Parsed from text → pending → payment button confirmation → persisted

**Client Entity:**

- Representation: `db.clientes` table with:
  - `nombre` — full name
  - `tipo_id` — CC or NIT
  - `identificacion` — ID number
  - `phone`, `email` — optional contact
  - `saldo_pendiente` — fiado amount
  - `created_at` — registration timestamp
- Creation flow: Interactive via `handlers/callbacks.manejar_callback_cliente()`
- Cache: Not cached; queried per-request to avoid stale data

**Inventory Entity:**

- Representation: `inventario[clave]` dict:
  - `cantidad` — current stock
  - `minimo` — reorder threshold
  - `unidad` — unit name
- Source: `db.inventario`
- Updates: Auto-decremented on sale confirmation, manual via `/ajuste`
- Special handling: Wayper products stored as units, shown as kg (see `routers/shared._WAYPER_KG_KEYS`)

## Entry Points

**Telegram Bot Entry:**
- Location: `main.py`
- Triggers: App initialization on `start.py` import
- Responsibilities:
  - Create Telegram Application
  - Register all command, message, and callback handlers
  - Configure webhook (production) or polling (development)
  - Start bot via `app.run_polling()` or `app.run_webhook()`

**FastAPI Entry:**
- Location: `api.py`
- Triggers: Spawned as daemon thread from `start.py`
- Responsibilities:
  - Create FastAPI app
  - Register CORS middleware and request logging middleware
  - Mount all routers (ventas, catalogo, caja, etc.)
  - Serve React dashboard static files
  - Listen on `0.0.0.0:{PORT}`

**Process Launcher:**
- Location: `start.py`
- Triggers: `python start.py` (Railway Procfile runs this)
- Responsibilities:
  - Force polling mode
  - Initialize database
  - Pre-warm cache in background
  - Start API in background thread
  - Start historico safety net in background thread
  - Clean up old webhook
  - Launch bot on main thread

## Error Handling

**Strategy:** "Fail open, log heavily" — the bot and API are more important than any individual operation succeeding.

**Patterns:**

- **Database unavailable:** `db.DB_DISPONIBLE` flag set once at startup. If False, bot operates in degraded mode (no inventory tracking, no sale persistence). Graceful fallback via lazy imports of `db` module.

- **Claude API failures:** Caught in `ai.procesar_con_claude()`, logged, fallback to rule-based parsing. User sees "No entiendo..." response.

- **Telegram connectivity:** `run_polling()` built-in retry logic. API errors logged but don't crash bot.

- **State expiration:** `ventas_state.limpiar_pendientes_expirados()` runs periodically, removes sales pending >5 minutes to prevent stuck state.

- **Async lock deadlock:** Per-chat locks via `_chat_locks[chat_id]` prevent serial message processing bottleneck. Never taken outside message handler.

**Exception Handling:** Catch-all `except Exception as e:` blocks throughout (intentional for stability). Rationale: bot staying online > perfect error handling.

## Cross-Cutting Concerns

**Logging:**
- Module loggers: `logger = logging.getLogger("ferrebot.<module>")`
- API request logging: `RequestLoggingMiddleware` in `api.py` adds request_id and timing
- Level: INFO for normal flow, WARNING for recoverable errors, ERROR for unexpected failures

**Validation:**
- Claude outputs validated via regex in `ai.procesar_acciones()` — extracts JSON blocks
- Fractions converted via `utils.convertir_fraccion_a_decimal()`
- Product search via fuzzy matching + alias lookup (not strict equality)
- Price parsing handles "1,5" (comma) and "1.5" (dot) formats

**Authentication:**
- Telegram: Handled by `python-telegram-bot` (validates bot token in message signature)
- API: Currently open (CORS allows "*") — no token/auth middleware
- Planned (Tarea A): `middleware/` will add `@protegido` decorator for authorized chat IDs only

**Concurrency:**
- Bot: Uses asyncio internally (`python-telegram-bot` v21+)
- API: Uvicorn handles async ASGI
- Shared state: Protected by `threading.Lock` in `ventas_state`
- Database: `psycopg2.pool.ThreadedConnectionPool` handles concurrent access

---

*Architecture analysis: 2026-03-28*
