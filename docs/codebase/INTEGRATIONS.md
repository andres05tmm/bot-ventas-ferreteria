# External Integrations

**Analysis Date:** 2026-03-28

## APIs & External Services

**AI & Language Models:**
- Claude (Anthropic) - Primary AI engine for interpreting vendor sales messages
  - SDK/Client: `anthropic` 0.49.0+
  - Auth: `ANTHROPIC_API_KEY` env var
  - Usage: `config.py` initializes `claude_client` singleton with prompt caching enabled
  - Implementation: `ai.py` contains `procesar_con_claude()` and AI message processing logic

- OpenAI (GPT) - Fallback AI if Claude unavailable
  - SDK/Client: `openai` 1.40.0+
  - Auth: `OPENAI_API_KEY` env var
  - Implementation: Fallback functionality in AI processing layer

**Messaging & Chat:**
- Telegram Bot API - Main user interface for vendors and admins
  - SDK/Client: `python-telegram-bot[webhooks]` 21.3
  - Auth: `TELEGRAM_TOKEN` env var
  - Mode: Polling (forced by `start.py` setting `WEBHOOK_URL=""`)
  - Handlers: `handlers/` directory handles commands, messages, callbacks
  - Features: Inline buttons, file uploads, photos, voice messages

**File Storage & Images:**
- Cloudinary - Cloud storage for invoice/payment receipt photos
  - SDK/Client: `cloudinary` package
  - Auth: Configured via URL format `cloudinary://<api_key>:<api_secret>@<cloud_name>`
  - Usage: `handlers/comandos.py` function `upload_foto_cloudinary()` handles image uploads
  - Flow: Photos from Telegram → upload to Cloudinary → stored URL in database
  - Location: `handlers/comandos.py` (lines ~2200+), `handlers/mensajes.py` for async uploads

## Data Storage

**Databases:**
- PostgreSQL (Railway managed)
  - Connection: `DATABASE_URL` env var (example: `postgresql://user:pass@host:5432/dbname`)
  - Client: `psycopg2-binary` 2.9.9+ with `ThreadedConnectionPool`
  - Access Pattern: Synchronous blocking calls, NO asyncpg
  - Pool Config: 2-10 connections, 8-second query timeout
  - Initialization: `db.py` centralized access, called from `start.py`
  - Flag: `DB_DISPONIBLE` set once at startup — all queries check this flag

**File Storage:**
- Local filesystem (legacy) - `memoria.json` for backward compatibility during migration
  - Path: Configurable via `MEMORIA_FILE` env var
  - Status: Being phased out as data migrates to PostgreSQL

## Authentication & Identity

**Auth Provider:**
- Custom Telegram-based - No external auth service
  - Implementation: Admin control via `ADMIN_CHAT_IDS` env var (comma-separated)
  - Mechanism: Chat ID whitelist checks in handlers (`handlers/alias_handler.py`)
  - Status: Being enhanced in Tarea A with `@protegido` decorator and rate limiting middleware

## Monitoring & Observability

**Error Tracking:**
- None detected - No Sentry, Datadog, or equivalent service integrated

**Logs:**
- Python `logging` stdlib module
  - Configured in `start.py` with format: `%(asctime)s [%(levelname)s] %(name)s — %(message)s`
  - Request logging via `RequestLoggingMiddleware` in `api.py`
  - Each request gets unique `X-Request-ID` header for correlation
  - Logger hierarchy: `ferrebot`, `ferrebot.db`, `ferrebot.request`, etc.
  - Verbose libraries silenced: httpx, httpcore, telegram.ext.Updater, apscheduler
  - Output: stdout (Railway logs)

## CI/CD & Deployment

**Hosting:**
- Railway.app
  - Build system: Nixpacks
  - Node: 20 (for dashboard build)
  - Python: 3.11
  - Startup: `bash build.sh` (from Procfile)
  - Build steps: Install Python deps, install/build React dashboard
  - Environment: Auto-loads `.env` via Railway dashboard

**CI Pipeline:**
- None detected - Direct deployments via Railway git integration

**Build Process (`nixpacks.toml`):**
- Setup: nodejs_20, python311, pip
- Install: `pip3 install -r requirements.txt --break-system-packages` + `cd dashboard && npm install`
- Build: `cd dashboard && npm run build` generates `/dashboard/dist/`
- Start: `python3 start.py`

**Dashboard Build (`dashboard/vite.config.js`):**
- Vite dev server on port 5173
- Production: Static files in `dist/` mounted by FastAPI
- API proxy in dev: `/api` → `http://localhost:8001`

## Environment Configuration

**Required env vars:**
- `TELEGRAM_TOKEN` - Telegram bot token (from @BotFather)
- `ANTHROPIC_API_KEY` - Claude API authentication
- `OPENAI_API_KEY` - OpenAI fallback (required by validation in `config.py`)
- `DATABASE_URL` - PostgreSQL Railway connection string

**Optional env vars:**
- `WEBHOOK_URL` - Leave empty to force polling (default)
- `PORT` - API server port (default 8001)
- `MEMORIA_FILE` - Legacy JSON cache file (default "memoria.json")
- `ADMIN_CHAT_IDS` - Comma-separated Telegram IDs for admin access

**Secrets location:**
- Local: `.env` file (git-ignored)
- Production: Railway dashboard environment variables panel
- Never commit: API keys, tokens, database credentials

## Webhooks & Callbacks

**Incoming:**
- Telegram updates - Bot receives all messages, commands, callback queries via polling
- No external webhooks currently configured (polling-only mode)

**Outgoing:**
- None detected - No webhook notifications to external services
- Database writes only (PostgreSQL)
- File uploads to Cloudinary (synchronous requests)

## Request/Response Flow

**Sales Message Processing:**
1. Vendor sends text/voice/photo via Telegram
2. `handlers/mensajes.py` receives message
3. Message → `ai.py` `procesar_con_claude()` (interprets sales intent)
4. Claude identifies products and quantities
5. `handlers/callbacks.py` presents inline buttons for payment method
6. Selection stored to PostgreSQL via routers (`routers/ventas.py`)
7. Dashboard (`dashboard/src/`) queries API endpoints to display analytics

**Photo Handling (invoices/receipts):**
1. Vendor sends photo via Telegram
2. `handlers/mensajes.py` intercepts photo
3. `upload_foto_cloudinary()` uploads to Cloudinary
4. URL stored in PostgreSQL `facturas` or payment records
5. Dashboard fetches and displays via API

**API Response Format:**
- All endpoints return JSON
- Health check: `GET /api/health` → `{"estado": "activo", "version": "1.0.0"}`
- Dashboard: SPA served at `/` with static assets at `/assets/`

---

*Integration audit: 2026-03-28*
