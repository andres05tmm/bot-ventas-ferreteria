# Architecture Research: Module Decomposition

**Date:** 2026-03-28
**Domain:** FerreBot modular refactoring — target architecture and import graph

---

## Target Architecture (post-refactoring)

```
config.py          ← singleton, no imports from project
db.py              ← imports config only
middleware/        ← imports config only
  __init__.py      ← re-exports protegido, rate_limiter
  auth.py          ← @protegido decorator
  rate_limit.py    ← rate limiting logic

services/          ← imports config + db only (never ai/, never handlers/)
  __init__.py
  catalogo_service.py
  inventario_service.py
  caja_service.py
  fiados_service.py

ai/                ← imports config + db + services (never handlers/)
  __init__.py      ← re-exports procesar_con_claude, procesar_acciones (Tarea I)
  price_cache.py   ← thread-safe cache, no external deps
  prompts.py       ← pure functions, no external deps
  excel_gen.py     ← imports openpyxl, config

memoria.py         ← thin wrapper: imports from services/, re-exports all names

handlers/          ← imports config + middleware + memoria + ai + ventas_state
  __init__.py
  comandos.py      ← re-export hub (never move functions out of here until re-export line is in)
  cmd_ventas.py
  cmd_inventario.py
  cmd_clientes.py
  cmd_caja.py
  cmd_admin.py
  mensajes.py
  callbacks.py
  productos.py
  alias_handler.py

routers/           ← imports config + db + memoria + ai (8 existing routers, unchanged)
ventas_state.py    ← imports config + threading only
main.py            ← FROZEN, imports handlers.comandos
```

---

## Critical Risk: ai.py → ai/ Package Naming Collision

**Highest-risk step in the entire refactoring.**

Python cannot have both `ai.py` (module) and `ai/` (package) at the same path. Currently 5+ files do `from ai import procesar_con_claude`. When creating `ai/` package in Tarea I:

**Recommended Strategy: ai.py → ai/__init__.py**

```bash
# Tarea B: create ai/ package for price_cache only
mkdir -p ai
# ai/price_cache.py is standalone — no conflict with ai.py yet

# Tarea I: rename ai.py to ai/__init__.py
mv ai.py ai/__init__.py
# All existing "from ai import X" call sites continue working
```

**Alternative (NOT recommended):** Keep `ai.py` and use relative imports from `ai/` submodules. This creates ambiguity and has caused bugs in Python <3.3 (namespace packages). Stick with the `__init__.py` strategy.

**Verification after Tarea I:**
```bash
python -c "from ai import procesar_con_claude, procesar_acciones; print('OK')"
```

---

## Import Dependency Rules (acyclic graph)

```
Layer 0 (no deps):     config, threading, stdlib
Layer 1 (→ Layer 0):   db
Layer 2 (→ Layer 1):   services/, middleware/, ai/price_cache, ai/prompts
Layer 3 (→ Layer 2):   ai/__init__ (full), memoria (thin wrapper)
Layer 4 (→ Layer 3):   handlers/, routers/, ventas_state
Layer 5 (→ Layer 4):   main, start, api
```

**Rule: never import from a higher layer.** Services never import from handlers. ai/ never imports from handlers or routers.

---

## Circular Import Paths (existing + risk)

**Confirmed existing circulars (resolved with lazy imports):**
- `handlers/mensajes.py` ↔ `handlers/comandos.py` — lazy imports in function bodies

**Must carry this pattern into cmd_*.py files:**
```python
# cmd_ventas.py — if it needs something from cmd_clientes:
def cmd_ventas(update, context):
    from handlers.cmd_clientes import buscar_cliente  # lazy, inside function
    ...
```

**New risk after Tarea H (services ↔ memoria):**
- `memoria.py` imports from `services/`
- `services/` must NEVER import from `memoria.py`
- Verify: `python -c "from services.catalogo_service import *; from services.inventario_service import *; print('no circular')"`

---

## Zero-Side-Effects at Module Level (Phase 1 mandate)

All Phase 1 modules (A-E) must be importable with no observable side effects:

```python
# WRONG — reads env at import time:
AUTHORIZED_IDS = set(os.getenv("AUTHORIZED_CHAT_IDS", "").split(","))

# RIGHT — reads env at call time (or at first use with lazy singleton):
def _get_authorized_ids():
    raw = os.getenv("AUTHORIZED_CHAT_IDS", "")
    return set(filter(None, raw.split(",")))
```

Exception: module-level `logger = logging.getLogger("ferrebot.X")` is fine — no side effects.

---

## memoria.py Thin Wrapper (Tarea H)

18+ files import from `memoria.py`. The wrapper must cover every public symbol. Pre-Tarea H audit:

```bash
grep -r "from memoria import\|import memoria" . --include="*.py" | grep -v __pycache__
```

Wrapper template:
```python
# memoria.py (post-Tarea H)
"""
Thin wrapper — delegates to services/. All names preserved for backwards compat.
DO NOT import services directly elsewhere; use this module as the facade.
"""
from services.catalogo_service import (
    obtener_catalogo, buscar_producto, actualizar_precio,
    # ... all names
)
from services.inventario_service import (
    descontar_inventario, obtener_inventario,
    # ... all names
)
from services.caja_service import (
    registrar_movimiento_caja, obtener_resumen_caja,
    # ... all names
)
from services.fiados_service import (
    registrar_fiado, obtener_fiados_cliente,
    # ... all names
)

__all__ = [
    # enumerate every name from the original memoria.py
]
```

**Verification:** `python -c "from memoria import *; print(len(dir()))"` — count should match original.

---

## handlers/comandos.py Re-export Hub (Tarea F)

`main.py` is frozen — imports specific handler names from `handlers/comandos.py`. When splitting:

```python
# handlers/comandos.py (post-Tarea F) — re-export hub only
from handlers.cmd_ventas import cmd_ventas, cmd_ultima_venta, cmd_corregir
from handlers.cmd_inventario import cmd_inventario, cmd_agregar, cmd_precio
from handlers.cmd_clientes import cmd_clientes, cmd_nuevo_cliente
from handlers.cmd_caja import cmd_caja, cmd_resumen, cmd_corte
from handlers.cmd_admin import cmd_admin, cmd_stats, cmd_backup
# ... all ~50 handlers

__all__ = ["cmd_ventas", "cmd_ultima_venta", ...]  # complete list
```

**Order of operations per handler:**
1. Add `from handlers.cmd_X import handler_name` to `comandos.py`
2. Move handler body to `cmd_X.py`
3. Verify: `python -c "from handlers.comandos import handler_name; print('OK')"`
4. Commit

Never remove a name from `comandos.py` before step 1 is confirmed working.

---

## Build Order Rationale

**Phase 1 (A-E) — pure additions, no wiring:**
- A, B, C, D, E have no interdependencies → fully parallel
- None of Phase 1 modules are imported by existing code yet
- Risk: near zero (additive only)

**Phase 2 (F, G, H) — re-wiring:**
- F depends on A (`@protegido` must exist before cmd_*.py use it)
- G depends on B (`price_cache.py` must exist before ai/prompts.py references it)
- H depends on D+E (services must exist before memoria.py delegates to them)
- Risk: moderate (changing import structure)

**Phase 3 (I) — reduction:**
- Must start only after B+G complete (ai.py still needs price_cache and prompts to be in ai/)
- Creates the ai.py → ai/__init__.py rename
- Risk: high (naming collision if done wrong)

---

*Confidence: High — based on direct codebase inspection of import graph and task specifications*
