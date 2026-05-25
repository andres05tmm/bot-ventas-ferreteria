---
phase: 01-infrastructure-creation
plan: 02
subsystem: infra
tags: [cache, threading, race-condition, ai, price-cache]

requires: []
provides:
  - "ai/price_cache.py con cache TTL 5min protegido por threading.RLock"
  - "API: registrar(), get_activos(), invalidar(), limpiar_expirados()"
  - "Race condition en _precios_recientes de ai.py eliminada (contenedor seguro creado)"
affects: [02-wiring, ai.py, Phase 2 Task G]

tech-stack:
  added: []
  patterns:
    - "Namespace package submodule: ai/price_cache.py sin ai/__init__.py"
    - "threading.RLock para cache dict mutable con TTL"

key-files:
  created: [ai/price_cache.py]
  modified: []

key-decisions:
  - "threading.RLock en lugar de Lock para permitir re-entrancia si limpiar_expirados() se llama desde registrar()"
  - "API con registrar/get_activos/invalidar/limpiar_expirados — más expresiva que get_price/set_price genérico"
  - "NO ai/__init__.py — namespace package resuelve ai.price_cache sin sombrar ai.py"

patterns-established:
  - "ai/ como namespace package: subdirectorio sin __init__.py para co-existir con ai.py en raíz"
  - "Cache con lista de entradas por producto (soporte fracción + precio principal)"

requirements-completed: [PC-01, PC-02, PC-03, PC-04, PC-05]

duration: N/A
completed: 2026-03-28
---

# Plan 01-02: Task B — ai/price_cache.py Summary

**Cache RAM thread-safe con TTL 5min en `ai/price_cache.py` usando namespace package — sin sombrar `ai.py`**

## Performance

- **Duration:** N/A (implementado antes de generar PLAN.md)
- **Completed:** 2026-03-28
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- `ai/price_cache.py` creado con `threading.RLock` protegiendo todas las mutaciones del dict
- API pública: `registrar()`, `get_activos()`, `invalidar()`, `limpiar_expirados()`
- `from ai.price_cache import registrar` y `from ai import procesar_con_claude` coexisten sin conflicto
- Race condition en `_precios_recientes` de `ai.py` tiene ahora un reemplazo seguro (wiring en Fase 2)
- Sin `ai/__init__.py` — el directorio `ai/` es un namespace package

## Files Created/Modified
- `ai/price_cache.py` — cache TTL con RLock y API pública

## Decisions Made
- `threading.RLock` en lugar de `Lock` para permitir llamadas re-entrantes
- Estructura de entrada: `{"precio": float, "fraccion": str|None, "ts": float}` — soporta fracciones

## Deviations from Plan
None — implementado directamente según especificación CLAUDE.md (Tarea B).

## Issues Encountered
None. El patrón namespace package (directorio sin `__init__.py`) funciona en Python 3.11 sin configuración adicional.

## Next Phase Readiness
- Contenedor listo para que Fase 2 (Tarea G) extraiga `_precios_recientes` de `ai.py` y use `price_cache`
- `from ai.price_cache import registrar` verificado en producción

---
*Phase: 01-infrastructure-creation*
*Completed: 2026-03-28*
