# Technology Stack

**Analysis Date:** 2026-03-28

## Languages

**Primary:**
- Python 3.11 - Bot backend, API, database operations, AI processing
- JavaScript/TypeScript - React dashboard frontend
- SQL - PostgreSQL database schema and queries

**Secondary:**
- Shell - Build and startup scripts
- YAML/TOML - Configuration files

## Runtime

**Environment:**
- Python 3.11 (specified in `.python-version`)
- Node.js 20 (specified in `nixpacks.toml`)

**Package Managers:**
- pip (Python) - installed via Nixpacks
- npm (Node.js) - installed via Nixpacks for dashboard

**Deployment Platform:**
- Railway - Nixpacks build system
- Startup: `python3 start.py` via Procfile

## Frameworks

**Backend/Bot:**
- python-telegram-bot 21.3 - Telegram bot framework with webhook support
- FastAPI 0.111.0+ - REST API for dashboard
- Uvicorn 0.29.0+ - ASGI server (runs on port 8001 as daemon thread)

**Frontend:**
- React 18.3.1 - UI framework for dashboard
- Vite 5.4.2 - Build tool and dev server (port 5173)
- Recharts 2.12.7 - Charting/visualization library

**Database:**
- PostgreSQL (on Railway) - primary data store
- psycopg2-binary 2.9.9+ - PostgreSQL sync driver (NOT asyncpg)
- ThreadedConnectionPool - thread-safe connection pooling in `db.py`

**Testing:**
- pytest - test runner (referenced in CLAUDE.md conventions)

## Key Dependencies

**Critical:**
- anthropic 0.49.0+ - Claude API client (primary AI engine)
- openai 1.40.0+ - OpenAI SDK (fallback AI, GPT)
- python-telegram-bot[webhooks] 21.3 - Telegram integration
- psycopg2-binary 2.9.9+ - PostgreSQL sync access (pool-based, no async)

**Infrastructure:**
- fastapi 0.111.0+ - REST API server
- uvicorn[standard] 0.29.0+ - ASGI server with extra dependencies
- starlette (via FastAPI) - middleware support
- python-dotenv 1.0.0+ - Environment variable loading

**Utilities:**
- openpyxl 3.1.2 - Excel file generation
- httpx 0.27.0+ - HTTP client library
- rapidfuzz 3.0.0+ - Fuzzy string matching for product search
- matplotlib - Data visualization (legacy, may be phased out)
- cloudinary - Image/file hosting for photos in facturas/abonos
- python-multipart 0.0.9 - Multipart form data handling (FastAPI uploads)

## Configuration

**Environment Variables (required):**
- `TELEGRAM_TOKEN` - Bot token from @BotFather
- `ANTHROPIC_API_KEY` - Claude API key
- `OPENAI_API_KEY` - OpenAI API key (fallback)
- `DATABASE_URL` - PostgreSQL connection string (Railway)

**Environment Variables (optional):**
- `WEBHOOK_URL` - Set to empty string to force polling mode (default)
- `PORT` - API port (default 8001 for API, 8443 for webhook)
- `MEMORIA_FILE` - Legacy JSON file path (default "memoria.json")
- `ADMIN_CHAT_IDS` - Comma-separated Telegram chat IDs for admin access

**Configuration Files:**
- `config.py` - Centralized configuration, API client initialization
- `.env` - Environment variables (git-ignored)
- `nixpacks.toml` - Railway build configuration with Node 20 + Python 3.11 setup

**Build:**
- `nixpacks.toml`:
  - Install: pip dependencies + npm dashboard dependencies
  - Build: `cd dashboard && npm run build` generates static assets
  - Start: `python3 start.py` (runs both bot and API)

## Platform Requirements

**Development:**
- Python 3.11
- Node.js 20
- PostgreSQL (or fallback in-memory mode if DATABASE_URL unset)
- Telegram bot token
- Anthropic API key
- OpenAI API key

**Production (Railway):**
- PostgreSQL instance (Railway managed)
- Environment variables configured in Railway dashboard
- Nixpacks buildpack (automatic with Railway)
- Single dyno runs both:
  - API server (FastAPI/Uvicorn, port 8001)
  - Bot (polling mode, main thread)

## Architecture Notes

**Process Model:**
- `start.py` spawns two threads:
  1. FastAPI daemon thread (port 8001) - handles API requests
  2. Main thread - Telegram bot polling loop
- Optional: Safety net background thread for daily close automation

**Database Access:**
- Synchronous psycopg2 with ThreadedConnectionPool
- 2-10 connection limit pool with 8-second query timeout
- No async/await at database layer — only at Telegram bot level

**API Architecture:**
- FastAPI serves dashboard and API endpoints
- CORS enabled for all origins (`allow_origins=["*"]`)
- Request logging middleware adds `X-Request-ID` header
- Static React build mounted at `/` for SPA serving
- OpenAPI docs at `/docs`

---

*Stack analysis: 2026-03-28*
