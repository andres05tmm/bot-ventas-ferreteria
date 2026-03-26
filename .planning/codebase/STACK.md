# Technology Stack

**Analysis Date:** 2026-03-25

## Languages

**Primary:**
- Python 3.11 - Core bot and API backend (`.python-version`)
- JavaScript/JSX - React frontend dashboard (React 18.3.1)

**Secondary:**
- TypeScript-compatible patterns in some files

## Runtime

**Environment:**
- Python 3.11 (specified in `nixpacks.toml`)
- Node.js 20 (for dashboard builds)

**Package Managers:**
- `pip` for Python dependencies - `requirements.txt`
- `npm` for Node.js dependencies - `dashboard/package.json`
- Lockfiles: `package-lock.json` present in `/dashboard/`

## Frameworks

**Core Bot Framework:**
- `python-telegram-bot[webhooks]` 21.3 - Telegram bot framework with webhook support (polling fallback)

**API Framework:**
- FastAPI >=0.111.0 - REST API server (`api.py`)
- Uvicorn >=0.29.0 - ASGI server for FastAPI

**Frontend:**
- React ^18.3.1 - UI framework (`dashboard/package.json`)
- Vite ^5.4.2 - Build tool and dev server
- Recharts ^2.12.7 - Charting library for data visualization

**AI/LLM:**
- Anthropic SDK (`anthropic>=0.49.0`) - Claude API integration
- OpenAI SDK (`openai>=1.40.0`) - GPT API integration

**Database/Persistence:**
- OpenPyXL 3.1.2 - Excel file handling (`ventas.xlsx`)
- gspread >=6.0.0 - Google Sheets integration (read/write)

## Key Dependencies

**Critical:**
- `google-api-python-client` 2.108.0 - Google Drive API for file sync and backups
- `google-auth` 2.25.2 - Google authentication
- `gspread` >=6.0.0 - Google Sheets client

**Data Processing:**
- `openpyxl` 3.1.2 - Excel workbook manipulation (`ventas.xlsx`)
- `rapidfuzz` >=3.0.0 - Fuzzy string matching for product search
- `matplotlib` - Chart generation (used in handlers)

**Infrastructure:**
- `httpx` >=0.27.0 - Async HTTP client
- `python-dotenv` >=1.0.0 - Environment variable loading
- `python-multipart` >=0.0.9 - Multipart form data handling for FastAPI

## Configuration

**Environment:**
- Configuration file: `config.py` - Central configuration module
- Variables stored in environment (loaded via `python-dotenv`)
- Secret credentials: `GOOGLE_CREDENTIALS_JSON` (JSON service account key)
- Build configuration: `railway.json`, `nixpacks.toml`, `Procfile`

**Key Configuration Files:**
- `.python-version` - Python version lock (3.11)
- `requirements.txt` - Python dependencies
- `config.py` - API clients initialization, timezone (Colombia TZ), paths
- `api.py` - FastAPI app setup with CORS middleware
- `dashboard/package.json` - Node dependencies and build scripts
- `dashboard/vite.config.js` - Vite build configuration

## Platform Requirements

**Development:**
- Python 3.11 or higher
- Node.js 20+ (for dashboard)
- pip package manager
- npm or compatible package manager

**Production:**
- Railway.app deployment platform (uses Nixpacks build system)
- Docker container runtime (via Railway)
- Public HTTPS endpoint for Telegram webhook (optional - polling fallback available)

## Build & Deployment

**Build Process:**
```
1. Install Python dependencies: pip install -r requirements.txt
2. Build dashboard: cd dashboard && npm install && npm run build
3. Start application: python3 start.py (Railway)
```

**Deployment Target:**
- Railway.app with Nixpacks builder
- Start command: `python3 start.py` (`railway.json`, `start.py`)

**Process Architecture:**
- Primary: Python bot process (runs polling or webhook mode)
- Secondary: FastAPI daemon thread (port configurable, default 8001)
- Watch threads: Excel monitor (2-hour interval), historical safety net

---

*Stack analysis: 2026-03-25*
