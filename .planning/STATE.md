---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-29T13:17:29.831Z"
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 8
  completed_plans: 6
---

# Project State

## Current Position

Phase: 02 (wiring) — EXECUTING
Plan: 2 of 3
**Active phase:** Phase 2 — Wiring
**Last completed:** Plan 02-01 — Handler Split (2026-03-29)
**Next action:** Execute 02-02-PLAN.md (ai/prompts.py + ai/excel_gen.py extraction, Tarea G)

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

---

## Active Risks

| Risk | Mitigation | Status |
|------|-----------|--------|
| `ai/__init__.py` accidental en Fase 3 | Verificar `python -c "import ai; print(type(ai.procesar_con_claude))"` después de cada commit | Activo |
| `descontar_inventario()` return contract | Documetado en docstring con ⚠️; `ventas_state.py` línea 210 es el caller crítico | Activo |

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

---

## Phase 2 Readiness

Phase 1 provides (still relevant for remaining plans):

- `from ai.price_cache import registrar, get_activos` — listo para extraer `_precios_recientes` de `ai.py` (Tarea G, Plan 02-02)
- `from services.catalogo_service import *` — listo para thin-wrap `memoria.py` (Tarea H, Plan 02-03)
- `from services.inventario_service import *` — listo para thin-wrap `memoria.py` (Tarea H, Plan 02-03)
