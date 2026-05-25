# Retrospective: FerreBot

---

## Milestone: v1.0 — Refactorización

**Shipped:** 2026-03-29
**Phases:** 4 | **Plans:** 12 | **Tasks:** 22

### What Was Built

- `@protegido` decorator + rate limiter — AUTHORIZED_CHAT_IDS fail-open, threading.Lock per chat_id
- Thread-safe price cache `ai/price_cache.py` con TTL 5min — race condition en `_precios_recientes` eliminada
- `migrations/` con 7 scripts movidos fuera de la raíz
- `services/catalogo_service.py` + `inventario_service.py` — firmas idénticas, sin imports de memoria/ai/handlers
- `handlers/cmd_*.py` (6 archivos) — handlers distribuidos con `@protegido`, `comandos.py` = re-export hub puro
- `ai/prompts.py` (1370 líneas) + `ai/excel_gen.py` (97 líneas) extraídos de ai.py
- `services/caja_service.py` + `fiados_service.py` + `memoria.py` thin wrapper (~151 nombres re-exportados)
- `ai/__init__.py` — ai.py reducido de 2685 → 1256 líneas como package propio
- 62 tests unitarios — sin credentials, sin DB, pasan en ~3.4s

### What Worked

- **Namespace package trick**: crear `ai/price_cache.py` sin `ai/__init__.py` fue crítico para evitar sombrar `ai.py` durante fases intermedias. El diseño de fases secuenciales lo hizo seguro.
- **Thin wrapper pattern**: exportar todos los nombres desde `memoria.py` sin cambiar callers fue el movimiento más seguro. Cero cambios en `main.py`, `handlers/`, `routers/`.
- **Un commit por tarea**: cada commit verificable independientemente. El bot se podía reiniciar en cualquier punto.
- **sys.modules stub en tests**: solución elegante para evitar `SystemExit(1)` de `config.py` sin modificar `config.py`.
- **Wave-based execution con GSD**: las fases 1 paralelas (5 planes) se ejecutaron sin conflictos. El modelo de waves separó dependencias correctamente.

### What Was Inefficient

- **REQUIREMENTS.md checkboxes no actualizados**: los executors no marcaron las casillas durante la ejecución — 26 de 38 quedaron `[ ]` aunque los módulos existían. Requirió revisión manual en complete-milestone.
- **ROADMAP.md con Phase 2 desincronizada**: la tabla de progreso mostró Phase 2 como "In Progress" con "0/5 plans" aunque estaba completa — datos desincronizados entre secciones del ROADMAP.
- **Fase 3 (Reduction) sobredimensionada**: ai.py quedó en 1256 líneas (objetivo era ~800). Podría haberse dividido más en Fase 2.

### Patterns Established

- Namespace packages sin `__init__.py` para coexistir con módulos raíz del mismo nombre durante refactorización gradual
- `sys.modules` stub en tests como alternativa a modificar archivos protegidos (`config.py`)
- Re-export hub pattern: convertir módulo monolítico en thin wrapper manteniendo compatibilidad total
- Contrato de retorno como test explícito: `isinstance(result, tuple) and len(result) == 3`

### Key Lessons

1. **Diseñar el orden de fases alrededor del shadow problem**: si un módulo puede sombrear otro, la fase que crea el `__init__.py` debe ser la última, no la primera.
2. **Contar símbolos antes de thin-wrapping**: `grep -r "from memoria import" . | wc -l` antes de cualquier cambio a memoria.py.
3. **REQUIREMENTS.md necesita actualización inline**: los executors deben marcar checkboxes durante ejecución, no al final — o usar una herramienta automatizada.
4. **Wave isolation funciona bien en Python puro**: sin conflictos de merge en fases paralelas porque los módulos nuevos no modificaban archivos existentes.

### Cost Observations

- Model mix: claude-sonnet-4-6 para todos los executors y verifier
- Phases: 4 phases, 12 plans, 22 tasks
- Tests: 62 passing, 0 failures — validación automática sin setup adicional

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Tests | Duration |
|-----------|--------|-------|-------|----------|
| v1.0 Refactorización | 4 | 12 | 62 | ~19 days |
