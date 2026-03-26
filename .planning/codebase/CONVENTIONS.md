# Conventions

**Analysis Date:** 2026-03-25

## Language & Style

**Primary Language:** Python 3.11+ (type hints used, f-strings throughout)
**Secondary:** JavaScript/JSX (React dashboard)
**Comments/Docs:** Spanish (project is for Colombian hardware store)

## Code Organization

**Import Order (consistent across modules):**
1. stdlib (`import os, json, re, logging, asyncio`)
2. Third-party (`import anthropic, gspread, openpyxl`)
3. Project modules (`import config`, `from memoria import ...`)
- Separated by blank lines with comment headers: `# -- stdlib --`, `# -- terceros --`, `# -- propios --`
- Example: `handlers/mensajes.py` lines 16-48

**Module Structure:**
- Module-level docstring with version corrections history
- Module-level constants (UPPER_SNAKE)
- Module-level logger: `logger = logging.getLogger("ferrebot.<module>")`
- Private helpers prefixed with `_`
- Public functions below

## Naming Patterns

**Python:**
- Functions: `snake_case` (`cargar_memoria`, `guardar_cliente_nuevo`)
- Telegram handlers: `comando_<name>` for commands, `manejar_<name>` for messages/events
- Private: `_underscore_prefix` (`_normalizar`, `_parsear_precio`, `_cache`)
- Constants: `UPPER_SNAKE` (`EXCEL_FILE`, `COLOMBIA_TZ`, `VERSION`)
- Config vars: `UPPER_SNAKE` matching env var names (`TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`)

**React/JSX:**
- Components: `PascalCase` with `Tab` prefix for dashboard tabs (`TabResumen`, `TabCaja`)
- Props/state: `camelCase`
- API URLs: lowercase with dashes/slashes

## Error Handling Patterns

**Try/except with graceful fallback:**
```python
try:
    resultado = operacion_principal()
except Exception as e:
    logger.warning(f"Fallo X: {e}")
    resultado = operacion_fallback()
```

**Common pattern - Sheets/Excel fallback chain:**
- Try Google Sheets first (real-time)
- Fall back to Excel (local archive)
- Log warning but don't crash

**Drive retry queue:**
- Failed uploads enqueued in `cola_drive.json`
- Retried on next successful operation
- Pattern in `drive.py`

**Broad exception catching:**
- Most handlers use `except Exception as e:` (intentionally broad for bot stability)
- Log with `logger.error()` or `logger.warning()`
- Send user-friendly message via Telegram

## Async Patterns

**Telegram handlers:** All `async def` (required by python-telegram-bot v20+)
**Blocking I/O wrapped:** `await asyncio.to_thread(blocking_func, args)`
- Used for: Excel operations, Sheets writes, Drive uploads
**Thread-safe state:** `threading.Lock()` for shared dicts (`ventas_state._estado_lock`)

## Configuration Pattern

**Single source:** `config.py` reads all env vars at import time
- Validates required keys immediately (raises SystemExit if missing)
- Google API clients created lazily with `@lru_cache` or manual cache
- Constants for Excel structure (column names, row offsets)

## Data Format Conventions

**Prices:** Colombian pesos (integer, no decimals) - `$15,000`
- Parsing handles: `$1,500`, `1.500`, `1500` formats via `utils.parsear_precio()`

**Quantities:** Support fractions (`1/4`, `1 y 1/2`, `2-3/4`)
- Conversion via `utils.convertir_fraccion_a_decimal()`
- Display via `utils.decimal_a_fraccion_legible()`

**Dates:** Colombia timezone (UTC-5), format varies by context
- Internal: `datetime.now(config.COLOMBIA_TZ)`
- Display: Spanish month names from `config.MESES`

**Product names:** Title case Spanish (`"Brocha de 2\""`, `"Tornillo Drywall 6X1"`)

## Centralization Rules

**Single definition principle:** Utility functions defined once, imported everywhere
- `utils._normalizar()` - text normalization (eliminated duplicates in memoria.py, excel.py)
- `utils.parsear_precio()` - price parsing (eliminated duplicates in ventas_state.py, callbacks.py)
- `utils.convertir_fraccion_a_decimal()` - fraction handling

**Lazy imports for circular dependency avoidance:**
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

---

*Conventions analysis: 2026-03-25*
