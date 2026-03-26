<!-- GSD:project-start source:PROJECT.md -->
## Project

**FerreBot — Migración a PostgreSQL**

FerreBot es un sistema POS completo para Ferretería Punto Rojo (Cartagena, Colombia). Los vendedores registran ventas por voz o texto en Telegram, Claude AI interpreta los mensajes, y un dashboard React muestra analíticas en tiempo real. Actualmente persiste en Google Drive (JSON + Excel); el objetivo de este milestone es migrar toda la persistencia estructurada a PostgreSQL en Railway.

**Core Value:** El bot debe registrar ventas sin interrupciones — si la DB falla, el bot no puede caer.

### Constraints

- **Tech stack:** Python 3.11, psycopg2-binary (sync, no asyncpg — bot usa threading no asyncio puro)
- **Compatibilidad:** interfaz pública de `memoria.py` no puede cambiar (firmas de función)
- **Uptime:** cero downtime — cada commit debe dejar el sistema operativo
- **Tests:** `test_suite.py` 1096+ tests deben pasar después de cada fase
- **Dependencia circular:** Drive solo para fotos de facturas al finalizar la migración
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11 - Core bot and API backend (`.python-version`)
- JavaScript/JSX - React frontend dashboard (React 18.3.1)
- TypeScript-compatible patterns in some files
## Runtime
- Python 3.11 (specified in `nixpacks.toml`)
- Node.js 20 (for dashboard builds)
- `pip` for Python dependencies - `requirements.txt`
- `npm` for Node.js dependencies - `dashboard/package.json`
- Lockfiles: `package-lock.json` present in `/dashboard/`
## Frameworks
- `python-telegram-bot[webhooks]` 21.3 - Telegram bot framework with webhook support (polling fallback)
- FastAPI >=0.111.0 - REST API server (`api.py`)
- Uvicorn >=0.29.0 - ASGI server for FastAPI
- React ^18.3.1 - UI framework (`dashboard/package.json`)
- Vite ^5.4.2 - Build tool and dev server
- Recharts ^2.12.7 - Charting library for data visualization
- Anthropic SDK (`anthropic>=0.49.0`) - Claude API integration
- OpenAI SDK (`openai>=1.40.0`) - GPT API integration
- OpenPyXL 3.1.2 - Excel file handling (`ventas.xlsx`)
- gspread >=6.0.0 - Google Sheets integration (read/write)
## Key Dependencies
- `google-api-python-client` 2.108.0 - Google Drive API for file sync and backups
- `google-auth` 2.25.2 - Google authentication
- `gspread` >=6.0.0 - Google Sheets client
- `openpyxl` 3.1.2 - Excel workbook manipulation (`ventas.xlsx`)
- `rapidfuzz` >=3.0.0 - Fuzzy string matching for product search
- `matplotlib` - Chart generation (used in handlers)
- `httpx` >=0.27.0 - Async HTTP client
- `python-dotenv` >=1.0.0 - Environment variable loading
- `python-multipart` >=0.0.9 - Multipart form data handling for FastAPI
## Configuration
- Configuration file: `config.py` - Central configuration module
- Variables stored in environment (loaded via `python-dotenv`)
- Secret credentials: `GOOGLE_CREDENTIALS_JSON` (JSON service account key)
- Build configuration: `railway.json`, `nixpacks.toml`, `Procfile`
- `.python-version` - Python version lock (3.11)
- `requirements.txt` - Python dependencies
- `config.py` - API clients initialization, timezone (Colombia TZ), paths
- `api.py` - FastAPI app setup with CORS middleware
- `dashboard/package.json` - Node dependencies and build scripts
- `dashboard/vite.config.js` - Vite build configuration
## Platform Requirements
- Python 3.11 or higher
- Node.js 20+ (for dashboard)
- pip package manager
- npm or compatible package manager
- Railway.app deployment platform (uses Nixpacks build system)
- Docker container runtime (via Railway)
- Public HTTPS endpoint for Telegram webhook (optional - polling fallback available)
## Build & Deployment
- Railway.app with Nixpacks builder
- Start command: `python3 start.py` (`railway.json`, `start.py`)
- Primary: Python bot process (runs polling or webhook mode)
- Secondary: FastAPI daemon thread (port configurable, default 8001)
- Watch threads: Excel monitor (2-hour interval), historical safety net
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Language & Style
## Code Organization
- Separated by blank lines with comment headers: `# -- stdlib --`, `# -- terceros --`, `# -- propios --`
- Example: `handlers/mensajes.py` lines 16-48
- Module-level docstring with version corrections history
- Module-level constants (UPPER_SNAKE)
- Module-level logger: `logger = logging.getLogger("ferrebot.<module>")`
- Private helpers prefixed with `_`
- Public functions below
## Naming Patterns
- Functions: `snake_case` (`cargar_memoria`, `guardar_cliente_nuevo`)
- Telegram handlers: `comando_<name>` for commands, `manejar_<name>` for messages/events
- Private: `_underscore_prefix` (`_normalizar`, `_parsear_precio`, `_cache`)
- Constants: `UPPER_SNAKE` (`EXCEL_FILE`, `COLOMBIA_TZ`, `VERSION`)
- Config vars: `UPPER_SNAKE` matching env var names (`TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`)
- Components: `PascalCase` with `Tab` prefix for dashboard tabs (`TabResumen`, `TabCaja`)
- Props/state: `camelCase`
- API URLs: lowercase with dashes/slashes
## Error Handling Patterns
- Try Google Sheets first (real-time)
- Fall back to Excel (local archive)
- Log warning but don't crash
- Failed uploads enqueued in `cola_drive.json`
- Retried on next successful operation
- Pattern in `drive.py`
- Most handlers use `except Exception as e:` (intentionally broad for bot stability)
- Log with `logger.error()` or `logger.warning()`
- Send user-friendly message via Telegram
## Async Patterns
- Used for: Excel operations, Sheets writes, Drive uploads
## Configuration Pattern
- Validates required keys immediately (raises SystemExit if missing)
- Google API clients created lazily with `@lru_cache` or manual cache
- Constants for Excel structure (column names, row offsets)
## Data Format Conventions
- Parsing handles: `$1,500`, `1.500`, `1500` formats via `utils.parsear_precio()`
- Conversion via `utils.convertir_fraccion_a_decimal()`
- Display via `utils.decimal_a_fraccion_legible()`
- Internal: `datetime.now(config.COLOMBIA_TZ)`
- Display: Spanish month names from `config.MESES`
## Centralization Rules
- `utils._normalizar()` - text normalization (eliminated duplicates in memoria.py, excel.py)
- `utils.parsear_precio()` - price parsing (eliminated duplicates in ventas_state.py, callbacks.py)
- `utils.convertir_fraccion_a_decimal()` - fraction handling
- `handlers.comandos` <-> `handlers.mensajes` use lazy imports inside functions
- Documented in module docstrings: "Imports que SI crean ciclo siguen siendo lazy"
## Logging Convention
- Logger per module: `logging.getLogger("ferrebot.<module_name>")`
- Configured centrally in `start.py` before any imports
- Noisy libraries silenced: httpx, httpcore, telegram.ext.Updater, apscheduler
- Format: `%(asctime)s [%(levelname)s] %(name)s -- %(message)s`
## Documentation Style
- Module-level docstrings with version history (CORRECCIONES v2, v3...)
- Function docstrings in Spanish for business logic
- Section dividers with ASCII art: `# ═══════════════════`
- Inline comments for non-obvious logic
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Multi-process deployment: bot runs on polling/webhook, API runs on separate thread (Railway Procfile)
- Event-driven message handling through Telegram handlers + FastAPI routers
- Google Drive + Sheets as primary data layer with local JSON cache
- Excel as historical archive with monthly sheet rotation
- Async I/O for blocking operations via asyncio.to_thread()
## Layers
- Purpose: Handle user interactions via Telegram chat interface
- Location: `main.py`, `start.py` (unified Railway launcher)
- Contains: Message handlers, command handlers, callback query handlers
- Depends on: handlers/, memoria.py, excel.py, sheets.py, drive.py, config.py
- Purpose: Serve JSON endpoints for dashboard + third-party integrations
- Location: `api.py`, `routers/` (8 domain routers)
- Contains: ventas, catalogo, caja, clientes, reportes, historico, chat, proveedores
- Purpose: Process messages and commands
- Location: `handlers/`
- Files: `comandos.py` (50+ commands), `mensajes.py` (AI sales capture), `callbacks.py` (inline buttons), `productos.py` (product browser), `alias_handler.py`
- Purpose: Business logic endpoints
- Location: `routers/shared.py`, `ventas.py`, `catalogo.py`, `caja.py`, `clientes.py`, `reportes.py`, `historico.py`, `chat.py`, `proveedores.py`
- Purpose: State sync with Google Cloud
- Location: `memoria.py`, `excel.py`, `sheets.py`, `drive.py`
- Pattern: In-memory cache with debounced writes to disk/Drive
- Location: `ventas_state.py`
- Contains: pending_ventas, clientes_en_proceso (thread-safe with lock)
- Location: `ai.py`
- Claude + OpenAI for intent parsing, product matching, validation
## Data Flow
## Key Abstractions
- Examples: `cargar_memoria()`, `guardar_memoria()`, `buscar_producto_en_catalogo()`
- Examples: `inicializar_excel()`, `registrar_venta_en_excel()`
- Examples: `_obtener_hoja_sheets()`, `sheets_escribir_venta()`
- Examples: `subir_a_drive()`, `descargar_de_drive()`
- Pattern: exact -> all words -> all-but-one -> partial
## Entry Points
- Initialize Drive + Excel + Fuzzy index
- Build Application with handlers
- Run polling or webhook
- Force polling mode
- Restore memoria.json from Drive
- Start API server (daemon thread)
- Start Excel watcher (2-hour sync)
- Start historical safety net (9pm auto-closure)
- Run polling bot
- Initialize FastAPI + CORS
- Mount 8 routers
- Serve React dashboard static files
- Render 12 tabs
- Poll API endpoints on interval
- Allow theme toggle
## Error Handling
- Google Sheets offline -> fallback to Excel
- Drive upload fails -> retry queue + `cola_drive.json`
- Product not found -> fuzzy match suggestions
- Excel locked -> continue (data safe in Sheets)
- AI ambiguous -> ask user for clarification
- Large messages -> split into 4000-char chunks
## Cross-Cutting Concerns
- Config in `start.py` (lines 23-34)
- Format: `%(asctime)s [%(levelname)s] %(name)s -- %(message)s`
- Per-module: `logging.getLogger("ferrebot.mensajes")`
- `convertir_fraccion_a_decimal()` - "1 1/2" -> 1.5
- `_cantidad_a_float()` - handles "1/2", "1.5", "1 y 1/2"
- AI validates product existence + quantity > 0
- Telegram user_id as implicit auth
- Admin check via ADMIN_CHAT_ID config
- Sheets: 5-min worksheet cache + 429 retry
- Drive: 2-sec debounce per file
- Excel: 5-min TTL client cache
- Claude: 5-min TTL prompt cache
- threading.Lock for shared state (memoria._cache, config._DRIVE_DISPONIBLE)
- asyncio.to_thread() for blocking I/O (Excel writes, Sheets updates)
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
