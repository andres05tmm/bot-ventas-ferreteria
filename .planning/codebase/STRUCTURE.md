# Codebase Structure

**Analysis Date:** 2026-03-25

## Directory Layout

```
bot-ventas-ferreteria/
├── main.py              # Telegram bot entry (webhook/polling)
├── start.py             # Railway unified launcher (bot + API + watchers)
├── api.py               # FastAPI app initialization
├── config.py            # Central configuration, env vars, Google clients
├── requirements.txt     # Python dependencies
├── Procfile             # Railway processes (web + worker)
├── README.md            # Project documentation
│
├── handlers/            # Telegram message + command handlers
│   ├── __init__.py
│   ├── comandos.py      # 50+ command handlers (/ventas, /buscar, /caja, etc.)
│   ├── mensajes.py      # Message text parsing + AI-powered sales capture
│   ├── callbacks.py     # Inline button responses (payment, client selection)
│   ├── productos.py     # Product browser + inventory management
│   └── alias_handler.py # Alias utilities
│
├── routers/             # FastAPI endpoint implementations (8 routers)
│   ├── __init__.py
│   ├── shared.py        # Centralized helpers (_hoy, _hace_n_dias, Excel reader)
│   ├── ventas.py        # /ventas/*, /venta-rapida (sales listing)
│   ├── catalogo.py      # /catalogo/*, /productos/*, /inventario/* (catalog)
│   ├── caja.py          # /caja/*, /gastos/*, /compras/* (cash box)
│   ├── clientes.py      # /clientes/* (client management)
│   ├── reportes.py      # /kardex, /resultados, /proyeccion (analytics)
│   ├── historico.py     # /historico/* (daily closure)
│   ├── chat.py          # /chat/* (AI chat endpoint)
│   └── proveedores.py   # /proveedores/* (suppliers)
│
├── dashboard/           # React + Vite frontend
│   ├── package.json     # Node dependencies (React 18, Recharts)
│   ├── vite.config.js   # Vite build config
│   ├── index.html       # HTML entry
│   ├── public/          # Static assets (manifest.json, sw.js)
│   └── src/
│       ├── App.jsx      # Main component (12 tabs)
│       ├── main.jsx     # React entry
│       ├── components/
│       │   ├── shared.jsx       # Theme context (light/dark)
│       │   └── ChatWidget.jsx   # AI chat widget
│       └── tabs/        # Dashboard tabs (12 components)
│           ├── TabResumen.jsx          # Summary KPIs + 7-day chart
│           ├── TabTopProductos.jsx     # Top 10 by quantity
│           ├── TabInventario.jsx       # Full catalog with stock alerts
│           ├── TabHistorial.jsx        # Daily sales table
│           ├── TabCaja.jsx             # Cash box operations
│           ├── TabGastos.jsx           # Expenses
│           ├── TabCompras.jsx          # Purchases
│           ├── TabKardex.jsx           # Kardex (inventory movement)
│           ├── TabResultados.jsx       # Daily results
│           ├── TabVentasRapidas.jsx    # Quick sales entry
│           ├── TabHistoricoVentas.jsx  # Historical sales
│           └── TabProveedores.jsx      # Supplier management
│
├── ai.py                # Claude + OpenAI for NLP parsing, product matching
├── memoria.py           # In-memory cache: catalog, prices, inventory, expenses
├── excel.py             # openpyxl operations (ventas.xlsx monthly sheets)
├── sheets.py            # Google Sheets real-time pizarra (Ventas del Dia)
├── drive.py             # Drive upload/download + debounce + retry queue
├── ventas_state.py      # In-flight state: pending_ventas, clientes_en_proceso
├── fuzzy_match.py       # Flexible product search
├── precio_sync.py       # Price synchronization from external Excel
├── utils.py             # Helper functions (decimal conversion, normalization)
├── skill_loader.py      # Plugin/skill loader
│
├── memoria.json         # Persistent state (catalog, prices, inventory)
├── ventas.xlsx          # Monthly sales archive
├── logo.png             # Ferreteria logo
│
└── .planning/           # GSD planning documents
    └── codebase/        # Codebase analysis documents
```

## Directory Purposes

**handlers/** - Telegram message + command processing
- Purpose: Receive updates from Telegram, route to appropriate handler, send responses
- Contains: Message parsers, command processors, callback handlers
- Key files: `comandos.py` (large, 50+ commands), `mensajes.py` (AI sales capture)
- Imported by: `main.py` (registered via Application.add_handler)

**routers/** - FastAPI business logic
- Purpose: Implement REST endpoints for dashboard + external clients
- Contains: CRUD operations, analytics, reporting
- Shared helpers: `shared.py` (_hoy, _hace_n_dias, _leer_excel_rango, _to_float)
- Imported by: `api.py` (registered via app.include_router)

**dashboard/** - React frontend
- Purpose: Web UI for analytics, quick sales, inventory
- 12 tabs covering sales, inventory, cash, expenses, suppliers
- Built with Vite, served as static files from `api.py`
- API proxy: Environment variable VITE_API_URL (defaults to same origin)

## Key File Locations

**Entry Points:**
- `main.py` - Telegram bot (webhook/polling)
- `start.py` - Railway unified launcher (bot + API + watchers)
- `api.py` - FastAPI app initialization
- `dashboard/src/App.jsx` - React main component

**Configuration:**
- `config.py` - Environment variables, Google clients, constants
- `requirements.txt` - Python dependencies
- `dashboard/package.json` - Node dependencies
- `Procfile` - Railway process definitions

**Core Logic:**
- `handlers/comandos.py` - 50+ Telegram commands
- `handlers/mensajes.py` - Message parsing + AI sales capture
- `ai.py` - Claude + OpenAI NLP processing
- `memoria.py` - In-memory state management

**Persistence:**
- `excel.py` - Excel read/write operations
- `sheets.py` - Google Sheets integration
- `drive.py` - Google Drive sync
- `ventas_state.py` - In-flight sale state

**Testing:**
- `test_suite.py` - Custom test runner (no framework)

## Naming Conventions

**Files:**
- `snake_case.py` - Python modules
- `PascalCase.jsx` - React components (Tab prefix for dashboard tabs)
- `lowercase-dash.js` - Config files (vite.config.js)

**Functions:**
- `snake_case()` - Regular functions
- `_private_function()` - Internal helpers (prefix _)
- `async def comando_*()` - Telegram command handlers (prefix comando_)
- `async def manejar_*()` - Telegram message handlers (prefix manejar_)
- `router.get("/path")` - FastAPI endpoints (use decorators)

**Variables:**
- `snake_case` - Local variables
- `CONSTANT_NAMES` - Constants (config values)
- `_cache` - Module-level cache (prefix _)

## Where to Add New Code

**New Command:**
1. Implement in `handlers/comandos.py` as `async def comando_name(update, context)`
2. Register in `main.py` via `app.add_handler(CommandHandler("name", comando_name))`

**New API Endpoint:**
1. Create new router file in `routers/` if new domain, else add to existing
2. Import shared helpers from `routers/shared.py`
3. Register in `api.py` via `app.include_router(router)`

**New Dashboard Tab:**
1. Create `dashboard/src/tabs/TabNewFeature.jsx`
2. Import in `dashboard/src/App.jsx`
3. Add to TABS constant and TAB_ICONS

**New State Field:**
1. Add to memoria.json structure (initialize in `memoria.cargar_memoria()`)
2. Implement getter/setter in `memoria.py`
3. Call `guardar_memoria()` on write (triggers Drive sync)

---

*Structure analysis: 2026-03-25*
