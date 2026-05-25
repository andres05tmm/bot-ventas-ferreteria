---
phase: 02-wiring
plan: 01
subsystem: handlers
tags: [python, telegram-bot, middleware, auth, refactoring]

# Dependency graph
requires:
  - phase: 01-infrastructure-creation
    provides: middleware.protegido decorator, services/, ai/price_cache
provides:
  - handlers/cmd_ventas.py with 8 handlers decorated with @protegido
  - handlers/cmd_inventario.py with 11 public handlers + 5 private helpers
  - handlers/cmd_clientes.py with 4 handlers
  - handlers/cmd_caja.py with 3 handlers
  - handlers/cmd_proveedores.py with upload_foto_cloudinary + 5 handlers
  - handlers/cmd_admin.py with 4 handlers
  - handlers/comandos.py converted to 48-line re-export hub with __all__
affects: [handlers, main, mensajes, auth-gating]

# Tech tracking
tech-stack:
  added: []
  patterns: ["@protegido decorator applied to all public Telegram handlers", "re-export hub pattern for backward compat while splitting monolith"]

key-files:
  created:
    - handlers/cmd_ventas.py
    - handlers/cmd_inventario.py
    - handlers/cmd_clientes.py
    - handlers/cmd_caja.py
    - handlers/cmd_proveedores.py
    - handlers/cmd_admin.py
  modified:
    - handlers/comandos.py

key-decisions:
  - "manejar_flujo_agregar_producto and manejar_mensaje_precio excluded from @protegido — called from mensajes.py, not registered in main.py"
  - "upload_foto_cloudinary excluded from @protegido — helper function, not a command handler"
  - "Hub file kept at 48 lines with explicit __all__ for contract clarity"
  - "conversational flows kept importable from comandos.py hub so mensajes.py needs no changes"

patterns-established:
  - "All Telegram command handlers decorated with @protegido from middleware"
  - "Private helpers (underscore-prefixed) and conversational flow functions excluded from @protegido"
  - "Re-export hub in comandos.py provides backward-compat while modules are extracted"

requirements-completed: [HDL-01, HDL-02, HDL-03, HDL-04, HDL-05]

# Metrics
duration: 9min
completed: 2026-03-29
---

# Phase 2 Plan 01: Handler Split Summary

**Split 2450-line handlers/comandos.py into 6 themed cmd_*.py modules with @protegido on all 39 public handlers, converting comandos.py to a 48-line re-export hub**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-29T14:47:04Z
- **Completed:** 2026-03-29T14:56:32Z
- **Tasks:** 2
- **Files modified:** 7 (6 created + 1 rewritten)

## Accomplishments

- Created 6 themed handler modules with correct @protegido decoration on all 39 public handlers
- Preserved conversational flows (manejar_flujo_agregar_producto, manejar_mensaje_precio) without @protegido so mensajes.py requires zero changes
- Replaced 2450-line monolith with 48-line re-export hub — main.py unchanged, all imports resolve
- Verified no `await` inside `threading.Lock` blocks in any cmd_*.py file

## Task Commits

1. **Task 1: Create 6 cmd_*.py files with handlers and @protegido** - `6688e02` (feat)
2. **Task 2: Convert comandos.py to re-export hub and verify main.py** - `75d7a35` (refactor)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `handlers/cmd_ventas.py` - 8 handlers: inicio, ventas, borrar, pendientes, grafica, manejar_callback_grafica, cerrar_dia, reset_ventas
- `handlers/cmd_inventario.py` - 11 public handlers + 5 private helpers: buscar, precios, inventario, inv, stock, ajuste, compra, margenes, agregar_producto, actualizar_precio, actualizar_catalogo + conversational flows
- `handlers/cmd_clientes.py` - 4 handlers: clientes, nuevo_cliente, fiados, abono
- `handlers/cmd_caja.py` - 3 handlers: caja, gastos, dashboard
- `handlers/cmd_proveedores.py` - upload_foto_cloudinary helper + 5 handlers: factura, abonar, deudas, facturas, borrar_factura
- `handlers/cmd_admin.py` - 4 handlers: consistencia, exportar_precios, keepalive, modelo
- `handlers/comandos.py` - Rewritten as 48-line re-export hub with __all__ listing 38 names

## Decisions Made

- Excluded `manejar_flujo_agregar_producto` and `manejar_mensaje_precio` from @protegido — these are conversational flows called from mensajes.py, not registered in main.py as CommandHandlers
- Excluded `upload_foto_cloudinary` from @protegido — it's a pure helper function called programmatically, not a Telegram command handler
- Hub file uses explicit `__all__` with 38 names for contract clarity and IDE tooling

## Deviations from Plan

None - plan executed exactly as written. Handler map from TAREA-F.md was used directly without re-analysis.

## Issues Encountered

- Python 3.14 changed `ast.Constant.s` attribute to `.value` — affected verification scripts only, not production code
- config.py requires env vars to initialize, so import-based verification used file-level checks instead

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 39 handlers auth-gated with @protegido (fail-open if AUTHORIZED_CHAT_IDS empty)
- handlers/comandos.py hub ready — main.py imports unchanged
- handlers/mensajes.py imports of conversational flows still work via the hub
- Ready for Plan 02-02: ai/prompts.py + ai/excel_gen.py extraction (Tarea G)
- Ready for Plan 02-03: services/caja_service + fiados_service + thin wrapper memoria.py (Tarea H)

## Self-Check: PASSED

- handlers/cmd_ventas.py: FOUND
- handlers/cmd_inventario.py: FOUND
- handlers/cmd_clientes.py: FOUND
- handlers/cmd_caja.py: FOUND
- handlers/cmd_proveedores.py: FOUND
- handlers/cmd_admin.py: FOUND
- handlers/comandos.py (48-line hub): FOUND
- Commit 6688e02 (feat: create 6 cmd_*.py): FOUND
- Commit 75d7a35 (refactor: convert comandos.py to hub): FOUND

---
*Phase: 02-wiring*
*Completed: 2026-03-29*
