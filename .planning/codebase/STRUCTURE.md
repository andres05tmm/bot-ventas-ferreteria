# STRUCTURE.md — Directory Layout & Organization

## Root Directory

```
bot-ventas-ferreteria/
├── config.py              # Central config, API clients, Colombia timezone
├── db.py                  # PostgreSQL connection pool (psycopg2 sync)
├── main.py                # Bot entry point, handler registration
├── start.py               # Railway launcher (bot + FastAPI daemon)
├── api.py                 # FastAPI app factory, router mounts
├── memoria.py             # Data layer: catalog, inventory, cash, credit (85 KB)
├── ai.py                  # Claude AI engine: procesar_con_claude, procesar_acciones (133 KB)
├── alias_manager.py       # Product alias CRUD (13 KB)
├── bypass.py              # Bypass/override logic (31 KB)
├── fuzzy_match.py         # Fuzzy product name matching (5 KB)
├── graficas.py            # Chart/graph generation (6 KB)
├── keepalive.py           # HTTP keepalive for Railway (6 KB)
├── skill_loader.py        # Loads domain skills from skills/
├── utils.py               # Shared utilities
├── ventas_state.py        # Thread-safe in-progress sale state
├── test_suite.py          # Custom test runner (no pytest)
│
├── handlers/              # Telegram update handlers
│   ├── comandos.py        # 50+ slash commands (~107 KB — split target)
│   ├── mensajes.py        # AI-powered sale capture (~71 KB)
│   ├── callbacks.py       # Inline keyboard callbacks (28 KB)
│   ├── productos.py       # Product browser handler (38 KB)
│   └── alias_handler.py   # Alias command handler (4 KB)
│
├── routers/               # FastAPI REST routers (mounted at /api/*)
│   ├── ventas.py          # Sales endpoints (24 KB)
│   ├── catalogo.py        # Catalog endpoints (30 KB)
│   ├── caja.py            # Cash register endpoints (19 KB)
│   ├── clientes.py        # Customer endpoints (8 KB)
│   ├── historico.py       # History endpoints (22 KB)
│   ├── proveedores.py     # Supplier endpoints (11 KB)
│   ├── reportes.py        # Reports + Excel export (16 KB)
│   ├── chat.py            # AI chat endpoints (44 KB)
│   └── shared.py          # Shared router utilities (8 KB)
│
├── skills/                # Domain knowledge .md files loaded into AI context
│   ├── core.md            # Core ferretería knowledge
│   ├── precios_base.md    # Base pricing rules
│   ├── tornillos.md       # Screws/fasteners domain
│   ├── pinturas.md        # Paints domain
│   ├── tintes.md          # Stains domain
│   ├── wayper.md          # Wayper products
│   ├── lija_esmeril.md    # Sandpaper/grinder
│   ├── thinner_varsol.md  # Solvents
│   ├── granel.md          # Bulk products
│   ├── clientes.md        # Customer handling
│   ├── foto_cuaderno.md   # Photo/notebook feature
│   └── pele.md            # Pele products
│
├── dashboard/             # React 18 + Vite frontend
│
├── _obsidian/             # Project management notes (not deployed)
│   ├── 01-Proyecto/       # Task specs (TAREA-A.md through TAREA-J.md)
│   ├── 02-Contextos/      # Context documents
│   ├── MAPA.md            # Project map
│   └── KANBAN.md          # Task tracking
│
├── migrate_*.py           # One-time DB migration scripts (7 files)
│
├── requirements.txt       # Python dependencies
├── nixpacks.toml          # Railway build config
├── railway.json           # Railway deploy config
├── Procfile               # Process definition
└── build.sh               # Build script
```

## Key Locations

| What | Where |
|------|-------|
| Bot entry point | `main.py` |
| Production launcher | `start.py` |
| FastAPI app | `api.py` |
| All Telegram commands | `handlers/comandos.py` |
| AI sale processing | `handlers/mensajes.py` + `ai.py` |
| Database queries | `db.py` + `memoria.py` |
| REST API endpoints | `routers/` |
| Domain knowledge | `skills/` |
| Task specifications | `_obsidian/01-Proyecto/TAREA-*.md` |
| Tests | `test_suite.py` |

## Naming Conventions

### Files
- `snake_case.py` for all Python modules
- `handlers/` prefix for Telegram update handlers
- `routers/` prefix for FastAPI endpoint modules
- `migrate_<entity>.py` for one-time migration scripts
- `TAREA-X.md` for task specifications (uppercase)

### Python
- Modules: `snake_case` (e.g., `alias_manager.py`)
- Functions: `snake_case` (e.g., `procesar_con_claude`)
- Private functions: `_underscore_prefix`
- Constants: `UPPER_SNAKE_CASE`
- Logger: `logger = logging.getLogger("ferrebot.<module>")`
- Classes: `PascalCase` (rare — mostly functional style)

### Import Groups (enforced in all modules)
```python
# -- stdlib --
import os, threading

# -- terceros --
from telegram import Update

# -- propios --
from config import TELEGRAM_TOKEN
```

## Dashboard Structure

```
dashboard/
├── src/
│   ├── components/        # React components
│   ├── pages/             # Route pages
│   └── main.jsx           # Entry point
├── package.json
└── vite.config.js
```

## Configuration Files

| File | Purpose |
|------|---------|
| `config.py` | Env vars, API clients, timezone |
| `nixpacks.toml` | Railway build (Python 3.11) |
| `railway.json` | Deploy settings |
| `Procfile` | `web: python3 start.py` |
| `.python-version` | `3.11` |
| `requirements.txt` | Python deps (pinned) |

## Planned Structure (Refactoring Targets)

```
middleware/                # Auth + rate limiting (Tarea A)
ai/
  price_cache.py           # Thread-safe price cache (Tarea B)
  prompts.py               # Prompt templates (Tarea G)
  excel_gen.py             # Excel generation (Tarea G)
services/
  catalogo_service.py      # (Tarea D)
  inventario_service.py    # (Tarea E)
  caja_service.py          # (Tarea H)
  fiados_service.py        # (Tarea H)
migrations/                # Moved migrate_*.py files (Tarea C)
tests/                     # Proper pytest suite (Tarea J)
handlers/
  cmd_ventas.py            # Split from comandos.py (Tarea F)
  cmd_catalogo.py
  cmd_caja.py
  cmd_clientes.py
  cmd_admin.py
```
