# Architecture

**Analysis Date:** 2026-03-25

## Pattern Overview

**Overall:** Hybrid event-driven architecture with layered separation between Telegram bot (handlers/commands), REST API (routers), and persistent state (memory/drive).

**Key Characteristics:**
- Multi-process deployment: bot runs on polling/webhook, API runs on separate thread (Railway Procfile)
- Event-driven message handling through Telegram handlers + FastAPI routers
- Google Drive + Sheets as primary data layer with local JSON cache
- Excel as historical archive with monthly sheet rotation
- Async I/O for blocking operations via asyncio.to_thread()

## Layers

**Telegram Bot Layer:**
- Purpose: Handle user interactions via Telegram chat interface
- Location: `main.py`, `start.py` (unified Railway launcher)
- Contains: Message handlers, command handlers, callback query handlers
- Depends on: handlers/, memoria.py, excel.py, sheets.py, drive.py, config.py

**API Layer (FastAPI):**
- Purpose: Serve JSON endpoints for dashboard + third-party integrations
- Location: `api.py`, `routers/` (8 domain routers)
- Contains: ventas, catalogo, caja, clientes, reportes, historico, chat, proveedores

**Handler Layer (Telegram):**
- Purpose: Process messages and commands
- Location: `handlers/`
- Files: `comandos.py` (50+ commands), `mensajes.py` (AI sales capture), `callbacks.py` (inline buttons), `productos.py` (product browser), `alias_handler.py`

**Router Layer (FastAPI):**
- Purpose: Business logic endpoints
- Location: `routers/shared.py`, `ventas.py`, `catalogo.py`, `caja.py`, `clientes.py`, `reportes.py`, `historico.py`, `chat.py`, `proveedores.py`

**Persistence Layer:**
- Purpose: State sync with Google Cloud
- Location: `memoria.py`, `excel.py`, `sheets.py`, `drive.py`
- Pattern: In-memory cache with debounced writes to disk/Drive

**State Management:**
- Location: `ventas_state.py`
- Contains: pending_ventas, clientes_en_proceso (thread-safe with lock)

**AI Processing:**
- Location: `ai.py`
- Claude + OpenAI for intent parsing, product matching, validation

## Data Flow

**Sales Entry:**
1. User message -> `manejar_mensaje()` (`handlers/mensajes.py`)
2. -> `procesar_con_claude()` (`ai.py`) for intent + product matching
3. -> `ventas_state.pendientes_ventas` (in-memory queue)
4. User confirms via buttons -> written to Google Sheets (Ventas del Dia pizarra)
5. /cerrar command -> Sheets -> Excel (monthly sheet) -> Drive backup

**API Data:**
1. `/ventas/hoy` endpoint -> tries Sheets (real-time), fallback Excel
2. Returns JSON with product, vendor, method, total
3. Dashboard polls every 30-300 seconds

**State Sync:**
1. `memoria.guardar_memoria()` -> writes JSON + `drive.subir_a_drive()` (debounce 2s)
2. Drive fails -> enqueue in `cola_drive.json` for retry
3. Startup -> `_restaurar_memoria()` downloads from Drive

## Key Abstractions

**Memory:** Centralized catalog/prices/inventory cache with thread-safe lock
- Examples: `cargar_memoria()`, `guardar_memoria()`, `buscar_producto_en_catalogo()`

**Excel:** Append-only monthly sheets with lazy open + read_only
- Examples: `inicializar_excel()`, `registrar_venta_en_excel()`

**Sheets:** Real-time pizarra with 5-min worksheet cache (avoid 429)
- Examples: `_obtener_hoja_sheets()`, `sheets_escribir_venta()`

**Drive:** Debounce + retry queue with threading.Timer
- Examples: `subir_a_drive()`, `descargar_de_drive()`

**Fuzzy Match:** 4-level fallback for product search
- Pattern: exact -> all words -> all-but-one -> partial

## Entry Points

**Telegram Bot (Polling) - `main.py`:**
- Initialize Drive + Excel + Fuzzy index
- Build Application with handlers
- Run polling or webhook

**Telegram Bot (Railway) - `start.py`:**
- Force polling mode
- Restore memoria.json from Drive
- Start API server (daemon thread)
- Start Excel watcher (2-hour sync)
- Start historical safety net (9pm auto-closure)
- Run polling bot

**API Server - `api.py`:**
- Initialize FastAPI + CORS
- Mount 8 routers
- Serve React dashboard static files

**Dashboard - `dashboard/src/App.jsx`:**
- Render 12 tabs
- Poll API endpoints on interval
- Allow theme toggle

## Error Handling

**Graceful degradation:**
- Google Sheets offline -> fallback to Excel
- Drive upload fails -> retry queue + `cola_drive.json`
- Product not found -> fuzzy match suggestions
- Excel locked -> continue (data safe in Sheets)
- AI ambiguous -> ask user for clarification
- Large messages -> split into 4000-char chunks

## Cross-Cutting Concerns

**Logging:**
- Config in `start.py` (lines 23-34)
- Format: `%(asctime)s [%(levelname)s] %(name)s -- %(message)s`
- Per-module: `logging.getLogger("ferrebot.mensajes")`

**Validation:**
- `convertir_fraccion_a_decimal()` - "1 1/2" -> 1.5
- `_cantidad_a_float()` - handles "1/2", "1.5", "1 y 1/2"
- AI validates product existence + quantity > 0

**Authentication:**
- Telegram user_id as implicit auth
- Admin check via ADMIN_CHAT_ID config

**Rate Limiting:**
- Sheets: 5-min worksheet cache + 429 retry
- Drive: 2-sec debounce per file
- Excel: 5-min TTL client cache
- Claude: 5-min TTL prompt cache

**Concurrency:**
- threading.Lock for shared state (memoria._cache, config._DRIVE_DISPONIBLE)
- asyncio.to_thread() for blocking I/O (Excel writes, Sheets updates)

---

*Architecture analysis: 2026-03-25*
