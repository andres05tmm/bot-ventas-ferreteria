---
phase: 01-infrastructure-creation
plan: 01
subsystem: auth
tags: [middleware, decorator, telegram, rate-limit, threading]

requires: []
provides:
  - "@protegido async decorator con functools.wraps, verifica AUTHORIZED_CHAT_IDS (fail-open si vacía)"
  - "RateLimiter por chat_id con ventana deslizante y threading.Lock"
  - "from middleware import protegido como path único"
affects: [02-wiring, handlers/comandos.py, handlers/cmd_*.py]

tech-stack:
  added: []
  patterns:
    - "Fail-open auth: lista vacía = permitir todo (modo dev)"
    - "functools.wraps en decoradores async para preservar __name__"
    - "Rate limiting con sliding window y threading.Lock"

key-files:
  created: [middleware/__init__.py, middleware/auth.py]
  modified: []

key-decisions:
  - "rate_limiter exportado desde middleware/__init__.py además de protegido (más flexible para Fase 2)"
  - "RLock no usado (Lock suficiente; no hay re-entrancia en este módulo)"

patterns-established:
  - "Módulo standalone sin imports propios — evita circulares"
  - "Variables de entorno leídas en cada llamada (_get_authorized_ids) — cambios en Railway sin redeploy"

requirements-completed: [MW-01, MW-02, MW-03, MW-04, MW-05]

duration: N/A
completed: 2026-03-28
---

# Plan 01-01: Task A — middleware/ Summary

**`@protegido` decorator con AUTHORIZED_CHAT_IDS fail-open y rate limiter por chat_id usando threading.Lock**

## Performance

- **Duration:** N/A (implementado antes de generar PLAN.md)
- **Completed:** 2026-03-28
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Decorador `@protegido` con `functools.wraps` para preservar `__name__` (requerido por PTB 21.3)
- Rate limiter per-chat con ventana deslizante configurable via env vars
- Fail-open: lista vacía de `AUTHORIZED_CHAT_IDS` = modo dev, permite todos los chats
- `from middleware import protegido` funciona como path único

## Files Created/Modified
- `middleware/__init__.py` — re-export de `protegido` y `rate_limiter`
- `middleware/auth.py` — decorador + rate limiter con threading.Lock

## Decisions Made
- `rate_limiter` también exportado desde `__init__.py` para flexibilidad en Fase 2
- Variables de entorno leídas en cada llamada (no cacheadas) — cambios efectivos sin redeploy

## Deviations from Plan
None — implementado directamente según especificación CLAUDE.md (Tarea A).

## Issues Encountered
None.

## Next Phase Readiness
- `@protegido` listo para aplicarse a handlers en Fase 2 (Tarea F)
- `AUTHORIZED_CHAT_IDS` env var documentada en CLAUDE.md

---
*Phase: 01-infrastructure-creation*
*Completed: 2026-03-28*
