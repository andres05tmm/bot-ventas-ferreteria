---
phase: 01-infrastructure-creation
plan: 05
subsystem: database
tags: [services, inventory, postgres, threading, return-contract]

requires: []
provides:
  - "services/inventario_service.py con todas las funciones de inventario de memoria.py"
  - "Contrato descontar_inventario() -> (bool, str|None, float|None) preservado"
  - "cargar_inventario() lee de db directamente, sin dependencia de memoria.py"
affects: [02-wiring, Phase 2 Task H, ventas_state.py, memoria.py]

tech-stack:
  added: []
  patterns:
    - "DB-level atomicity para writes (ON CONFLICT DO UPDATE) — sin app-level lock adicional"
    - "Contrato de retorno explícito en docstring para prevenir regresiones"

key-files:
  created: [services/inventario_service.py]
  modified: []

key-decisions:
  - "cargar_inventario() lee de db directamente — rompe dependencia de memoria.cargar_memoria()"
  - "_KG_INVENTARIO_LINKS constante incluida en el módulo (no importada de memoria)"

patterns-established:
  - "Contrato de retorno documentado con ⚠️ en docstring cuando hay destructuring externo crítico"

requirements-completed: [INV-01, INV-02, INV-03, INV-04]

duration: N/A
completed: 2026-03-28
---

# Plan 01-05: Task E — services/inventario_service.py Summary

**Lógica de inventario extraída a `services/inventario_service.py` con contrato `descontar_inventario() -> (bool, str|None, float|None)` preservado**

## Performance

- **Duration:** N/A (implementado antes de generar PLAN.md)
- **Completed:** 2026-03-28
- **Tasks:** 2
- **Files modified:** 1 (creado)

## Accomplishments
- `services/inventario_service.py` con 10+ funciones de inventario
- Contrato `descontar_inventario()` preservado: `(bool, str|None, float|None)` — compatible con `ventas_state.py` línea 210
- `cargar_inventario()` lee de `db` directamente (sin `cargar_memoria()`) — INV-04 cumplido
- Writes protegidos por atomicidad PostgreSQL (`ON CONFLICT DO UPDATE`) — INV-03 cumplido
- `_KG_INVENTARIO_LINKS` constante incluida en el módulo

## Files Created/Modified
- `services/inventario_service.py` — funciones de inventario con contrato preservado

## Decisions Made
- `cargar_inventario()` usa `db.query_all()` directamente — elimina dependencia circular con `memoria.py`
- Constante `_KG_INVENTARIO_LINKS` copiada al módulo (no importada desde ningún lado)

## Deviations from Plan
None — implementado directamente según especificación CLAUDE.md (Tarea E).

## Issues Encountered
None.

## Next Phase Readiness
- Listo para que Fase 2 (Tarea H) convierta `memoria.py` en thin wrapper delegando a este servicio
- El contrato de retorno de `descontar_inventario()` debe mantenerse intacto en toda la refactorización

---
*Phase: 01-infrastructure-creation*
*Completed: 2026-03-28*
