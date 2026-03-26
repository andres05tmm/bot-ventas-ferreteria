# External Integrations

**Analysis Date:** 2026-03-25

## APIs & External Services

**AI/Language Models:**
- Claude (Anthropic) - Natural language processing for sales queries, analysis
  - SDK: `anthropic` >=0.49.0
  - Client: `config.claude_client` (initialized in `config.py` line 102)
  - Auth: `ANTHROPIC_API_KEY` environment variable
  - Usage: `ai.py`, `routers/chat.py` for dashboard chat and analysis

- OpenAI (GPT) - Alternative LLM for some operations
  - SDK: `openai` >=1.40.0
  - Client: `config.openai_client` (initialized in `config.py` line 106)
  - Auth: `OPENAI_API_KEY` environment variable
  - Usage: AI-powered analysis in bot handlers

**Messaging Platform:**
- Telegram Bot API - Chat interface and command handling
  - SDK: `python-telegram-bot[webhooks]` 21.3
  - Auth: `TELEGRAM_TOKEN` environment variable (required)
  - Modes: Webhook mode (production) or polling mode (development)
  - Webhook URL: `WEBHOOK_URL` env var (empty = polling)
  - Webhook port: `PORT` env var (Railway default)

**Fuzzy Matching:**
- rapidfuzz >=3.0.0 - String matching for product search
  - Usage: `fuzzy_match.py` module builds product index at startup
  - Method: Fuzzy matching against product catalog in memory

## Data Storage

**Spreadsheet Services:**
- Google Sheets (Sales Daily)
  - Service: Google Sheets API via gspread >=6.0.0
  - Client: `config.get_sheets_client()` (cached, thread-safe in `config.py` lines 141-147)
  - Auth: `GOOGLE_CREDENTIALS_JSON` (service account JSON)
  - Scopes: spreadsheets, drive
  - Config: `SHEETS_ID` environment variable (optional, disabled if empty)
  - Usage: Real-time sales dashboard, daily transaction logging (`sheets.py`)

**File Storage:**
- Google Drive (Backup and file sync)
  - Service: Google Drive API via google-api-python-client 2.108.0
  - Client: `config.get_drive_service()` (cached, thread-safe in `config.py` lines 133-139)
  - Auth: `GOOGLE_CREDENTIALS_JSON` (same service account)
  - Scope: drive
  - Folder: `GOOGLE_FOLDER_ID` environment variable (required)
  - Usage: Backup of memory.json, ventas.xlsx, catalog sync (`drive.py`)
  - Queue system: `cola_drive.json` - retry queue for failed uploads
  - Debounce: 2-second delay to batch rapid file uploads
  - Upload method: MediaIoBaseUpload for efficient streaming

**Local File Storage:**
- Excel workbooks (ventas.xlsx) - Sales history
  - Library: openpyxl 3.1.2
  - Format: .xlsx
  - Location: Root directory as `config.EXCEL_FILE`
  - Sheets: Monthly tabs (e.g., "Marzo 2026"), "Compras" sheet
  - Access: Read/write via `excel.py`, `routers/shared.py`

- JSON state files
  - memoria.json - Catalog, inventory, client list (git-ignored, persistent)
  - cola_drive.json - Drive upload queue (git-ignored)
  - Railway restores memoria.json from Drive at startup (`start.py` lines 47-59)

**In-Memory Cache:**
- Python dictionaries - Product catalog, inventory, client state
  - Loaded from memoria.json on startup
  - Fuzzy index: Built at boot in `fuzzy_match.py`

## Authentication & Identity

**Auth Provider:**
- Google Service Account (custom implementation)
  - Implementation: Service account JSON credentials (`GOOGLE_CREDENTIALS_JSON`)
  - Scope: Drive and Sheets APIs
  - Method: oauth2.service_account.Credentials
  - Details: Credentials stored as JSON environment variable, parsed in `config.py` lines 111-128

**Telegram Auth:**
- Token-based (Telegram Bot Token)
  - Token: `TELEGRAM_TOKEN` (environment variable)
  - Scope: Single bot instance, group/private chats
  - No user authentication - public bot

## Monitoring & Observability

**Error Tracking:**
- Not detected - No external error tracking service (Sentry, etc.)
- Local logging: Python logging module (`logging` stdlib)
- Log level configured in `start.py` (line 23-34)
- File: stdout/stderr (suitable for Railway logs)

**Logs:**
- Standard Python logging to stdout
- Modules: ferrebot, ferrebot.api, ferrebot.drive, etc.
- Approach: Structured logging with timestamps and level indicators
- Railway collects stdout/stderr automatically

**Monitoring of Services:**
- keepalive.py - Health check loop to keep dyno alive
- historico_safety_net - Background thread monitors daily close-out

## CI/CD & Deployment

**Hosting:**
- Railway.app (specified in `railway.json`, `nixpacks.toml`)
- Build system: Nixpacks
- Container: Docker (via Railway)

**Build Configuration:**
- `railway.json` - Railway deployment manifest
  - Builder: NIXPACKS
  - Build command: pip install + npm install + npm build
  - Start command: python3 start.py
  - Restart policy: ON_FAILURE (max 10 retries)

- `nixpacks.toml` - Nixpacks build stages
  - Setup: Python 3.11, Node 20
  - Install: pip packages, npm packages
  - Build: npm run build (dashboard)
  - Start: python3 start.py

**Local Development:**
- Procfile (legacy, for Heroku compatibility)
- build.sh - Build script (bash)

## Environment Configuration

**Required env vars:**
- `TELEGRAM_TOKEN` - Telegram bot token (required)
- `ANTHROPIC_API_KEY` - Claude API key (required)
- `OPENAI_API_KEY` - OpenAI API key (required)
- `GOOGLE_CREDENTIALS_JSON` - Google Service Account JSON (required)
- `GOOGLE_FOLDER_ID` - Google Drive folder ID for backups (required)

**Optional env vars:**
- `SHEETS_ID` - Google Sheets ID for daily sales (optional, functions disabled if empty)
- `WEBHOOK_URL` - Public webhook URL for Telegram (optional, empty = polling mode)
- `PORT` - Server port (default 8443 for webhook, 8001 for API; Railway sets this)
- `ADMIN_CHAT_ID` - Chat ID for admin notifications (optional, `start.py` line 132)

**Validation:**
- config.py lines 44-56: Validates all required keys at import time
- Raises SystemExit(1) if any key missing

**Secrets location:**
- Environment variables only (no .env files in repo)
- Railway: Variables set in service configuration
- Development: .env file (git-ignored, matches .gitignore)

## Webhooks & Callbacks

**Incoming:**
- Telegram webhook endpoint: POST `/{TELEGRAM_TOKEN}` (main.py webhook mode)
- REST API endpoints in `routers/` for dashboard operations
- Health check: GET `/api/health` (api.py)

**Outgoing:**
- Telegram sendMessage API calls - Notifications to users/admins
  - Example: excel-watcher notifies admin of catalog updates (`start.py` lines 136-149)
  - Endpoint: `https://api.telegram.org/bot{token}/sendMessage`
- Google Drive upload/download - Async file operations
- Google Sheets append - Daily sales transactions
- Chat completion callbacks - Claude/OpenAI streaming responses

## Data Sync & Polling

**Excel Watcher Thread:**
- Interval: 2 hours (`EXCEL_WATCH_INTERVAL` = 7200s)
- Monitors: BASE_DE_DATOS_PRODUCTOS.xlsx in Drive
- Triggers: Reimports catalog if Excel modified time changes
- Runs in: Background daemon thread (`start.py` lines 92-162)
- Notification: Posts to Telegram admin chat on import

**Historical Safety Net:**
- Interval: Hourly check at 9pm+ (21:00+)
- Purpose: Persists daily totals if /cerrar command not executed
- Runs in: Background daemon thread (`start.py` lines 165-197)

**Upload Queue:**
- Debounce: 2-second delay on file uploads
- Retry: Failed uploads queued in `cola_drive.json`
- Thread-safe: Uses threading.Lock for debounce management (`drive.py`)

---

*Integration audit: 2026-03-25*
