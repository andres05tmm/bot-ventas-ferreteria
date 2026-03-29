---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-29T19:02:54.778Z"
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 9
  completed_plans: 9
---

# Project State

## Current Position

Phase: 4
Plan: Not started
**Active phase:** Phase 3 — DONE
**Last completed:** Plan 03-01 — ai.py reduced 2685→1256 lines, renamed to ai/__init__.py (2026-03-29)
**Next action:** All refactoring phases complete. Phase 4 (tests) or done.

---

## Phase Completion Log

### Phase 1: Infrastructure Creation ✓ (2026-03-28)

All 5 tasks implemented before PLAN.md artifacts were generated. Completed retroactively documented.

**What shipped:**

- `middleware/auth.py` + `middleware/__init__.py` — `@protegido` decorator con AUTHORIZED_CHAT_IDS fail-open y rate limiter por chat_id
- `ai/price_cache.py` — cache RAM thread-safe con TTL 5min usando threading.RLock (sin ai/__init__.py)
- `migrations/` — 7 scripts migrate_*.py movidos con nombres 001-007 y guards __main__
- `services/catalogo_service.py` — funciones de catálogo extraídas de memoria.py, firmas idénticas
- `services/inventario_service.py` — funciones de inventario, contrato descontar_inventario() preservado

---

## Key Decisions

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-28 | `ai/` como namespace package sin `__init__.py` | Si existiera `ai/__init__.py`, Python sombrea `ai.py` y rompe 6+ call sites de `from ai import procesar_con_claude` |
| 2026-03-28 | `threading.RLock` en price_cache.py | Re-entrancia segura si limpiar_expirados() se llama desde dentro de la misma operación |
| 2026-03-28 | `cargar_inventario()` lee de db directamente | Evita dependencia circular inventario_service → memoria → inventario_service |
| 2026-03-28 | `rate_limiter` exportado además de `protegido` desde middleware | Flexibilidad para Fase 2 sin cambiar el __init__.py |
| 2026-03-29 | `manejar_flujo_agregar_producto` y `manejar_mensaje_precio` excluidos de `@protegido` | Son flujos conversacionales llamados desde mensajes.py, no command handlers registrados en main.py |
| 2026-03-29 | Re-export hub en `comandos.py` mantiene backward compat | main.py y mensajes.py no necesitan cambios mientras se divide el monolito |
| 2026-03-29 | Lazy imports en `_construir_parte_dinamica` para `ai._pg_*` y `memoria.*` | Evita dependencia circular — ai.py importa memoria al top level, ai/prompts.py no puede importar ai al top level |
| 2026-03-29 | `ai.py` queda byte-identical hasta Tarea I | Extracciones son copias aditivas; borrado solo en Fase 3 cuando todo esté verificado |
| 2026-03-29 | Tasks 1+2 committed atomically (03-01) | `from ai.X import` in ai.py fails while ai.py is a file — rename must happen with edits in same commit |
| 2026-03-29 | Absolute imports kept in ai/__init__.py | `from ai.prompts import` (not relative) matches existing codebase convention |

---

## Active Risks

| Risk | Mitigation | Status |
|------|-----------|--------|
| `ai/__init__.py` accidental en Fase 3 | Verificar `python -c "import ai; print(type(ai.procesar_con_claude))"` después de cada commit | RESOLVED — Fase 3 completa |
| `descontar_inventario()` return contract | Documetado en docstring con ⚠️; `ventas_state.py` línea 210 es el caller crítico | Activo |

---

## Phase 3 Progress

### Plan 03-01: AI Module Reduction + Rename ✓ (2026-03-29)

**What shipped:**

- `ai/__init__.py` (was `ai.py`) — reduced from 2685 to 1256 lines via submodule import delegation
- Stripped: _ALIAS_FERRETERIA, all prompt-building functions, _calcular_historial, MODELO_HAIKU/SONNET, _elegir_modelo, editar_excel_con_claude, generar_excel_personalizado
- Added: `from ai.prompts import`, `from ai.excel_gen import`, `from ai.price_cache import`
- Atomic `git mv ai.py ai/__init__.py` — ai/ is now a proper Python package
- All callers unchanged — zero modifications to handlers/mensajes, callbacks, routers/chat, keepalive, test_suite

---

## Phase 2 Progress

### Plan 02-01: Handler Split ✓ (2026-03-29)

**What shipped:**

- `handlers/cmd_ventas.py` — 8 handlers con @protegido
- `handlers/cmd_inventario.py` — 11 public handlers + 5 private helpers
- `handlers/cmd_clientes.py` — 4 handlers
- `handlers/cmd_caja.py` — 3 handlers
- `handlers/cmd_proveedores.py` — upload_foto_cloudinary + 5 handlers
- `handlers/cmd_admin.py` — 4 handlers
- `handlers/comandos.py` — re-export hub de 48 líneas con __all__ de 38 nombres

### Plan 02-03: Caja/Fiados Services + Thin Wrapper ✓ (2026-03-29)

**What shipped:**

- `services/caja_service.py` — cargar_caja, guardar_caja, obtener_resumen_caja, cargar_gastos_hoy, guardar_gasto + 4 private helpers
- `services/fiados_service.py` — cargar_fiados, guardar_fiado_movimiento, abonar_fiado, resumen_fiados, detalle_fiado_cliente + _buscar_cliente_fiado
- `memoria.py` — thin wrapper 2147→1120 lines, re-exports all 41 public symbols from services/
- Zero callers changed — all 60+ call sites continue working unchanged

---

### Plan 02-02: AI Prompts + Excel Extraction ✓ (2026-03-29)

**What shipped:**

- `ai/prompts.py` — 1370 líneas: _ALIAS_FERRETERIA, aplicar_alias_ferreteria, _construir_parte_estatica, _construir_catalogo_imagen, _construir_parte_dinamica (toda la lógica de matching de productos), _calcular_historial, MODELO_HAIKU, MODELO_SONNET, _elegir_modelo
- `ai/excel_gen.py` — 97 líneas: generar_excel_personalizado, editar_excel_con_claude
- `ai.py` byte-identical — borrado en Tarea I (Fase 3)
- `ai/__init__.py` NO creado — namespace package preservado

---

## Phase 2 Readiness

Phase 1 provides (still relevant for remaining plans):

- `from ai.price_cache import registrar, get_activos` — listo para extraer `_precios_recientes` de `ai.py` (Tarea G, Plan 02-02)
- `from services.catalogo_service import *` — listo para thin-wrap `memoria.py` (Tarea H, Plan 02-03)
- `from services.inventario_service import *` — listo para thin-wrap `memoria.py` (Tarea H, Plan 02-03)
