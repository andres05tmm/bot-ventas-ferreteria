# Milestones

## v1.0 Refactorización (Shipped: 2026-03-29)

**Phases completed:** 4 phases, 12 plans, 22 tasks

**Key accomplishments:**

- `@protegido` decorator con AUTHORIZED_CHAT_IDS fail-open y rate limiter por chat_id usando threading.Lock
- Cache RAM thread-safe con TTL 5min en `ai/price_cache.py` usando namespace package — sin sombrar `ai.py`
- Funciones de catálogo extraídas de `memoria.py` a `services/catalogo_service.py` con firmas idénticas
- Lógica de inventario extraída a `services/inventario_service.py` con contrato `descontar_inventario() -> (bool, str|None, float|None)` preservado
- Extract prompt-building and Excel generation functions from ai.py into ai/prompts.py (1370 lines) and ai/excel_gen.py (97 lines), with lazy imports preserving ai.py byte-identical
- ai.py reduced from 2685 to 1256 lines via submodule import delegation and atomic rename to ai/__init__.py, converting ai/ from namespace package to proper Python package — all 7+ callers unchanged
- One-liner:
- 22 unit tests (12 catalogo + 10 inventario) with full mock isolation — descontar_inventario() 3-tuple contract explicitly validated
- 23 pytest unit tests covering caja_service and fiados_service fallback/DB paths, plus thin wrapper smoke tests confirming memoria.py still re-exports all caja and fiados symbols

---
