# Requirements: FerreBot Refactorización

**Defined:** 2026-03-28
**Core Value:** El bot no se rompe durante la refactorización — cada commit deja `python main.py` arrancando sin errores.

---

## v1 Requirements

### Middleware

- [ ] **MW-01**: El decorador `@protegido` verifica `AUTHORIZED_CHAT_IDS` antes de ejecutar cualquier handler de Telegram
- [ ] **MW-02**: `AUTHORIZED_CHAT_IDS` vacía o ausente = permitir todos los chats (modo dev, sin breaking change)
- [ ] **MW-03**: `@protegido` usa `functools.wraps` para preservar `__name__` del handler (PTB lo inspecciona)
- [ ] **MW-04**: Rate limiter configurable por chat_id disponible en `middleware/`
- [ ] **MW-05**: `from middleware import protegido` funciona como import path único para los handlers

### PriceCache

- [ ] **PC-01**: `ai/price_cache.py` expone `get_price(product_id)`, `set_price(product_id, price)`, `invalidate_cache()`
- [ ] **PC-02**: La cache está protegida por `threading.Lock` propio (no compartido con otros módulos)
- [ ] **PC-03**: Escrituras y lecturas concurrentes desde Uvicorn threads y PTB event loop no producen `RuntimeError`
- [ ] **PC-04**: La race condition de `_precios_recientes` en `ai.py` queda eliminada al wirear la cache
- [ ] **PC-05**: `from ai.price_cache import get_price` funciona sin romper `from ai import procesar_con_claude`

### Migrations

- [ ] **MIG-01**: Todos los scripts `migrate_*.py` están en `migrations/` con `migrations/__init__.py`
- [ ] **MIG-02**: Cada script tiene guard `if __name__ == "__main__":` — no ejecuta código al importar
- [ ] **MIG-03**: Referencias a estos scripts en Procfile/start.py actualizadas si las hubiera

### CatalogoService

- [ ] **CAT-01**: `services/catalogo_service.py` contiene toda la lógica de catálogo extraída de `memoria.py`
- [ ] **CAT-02**: Importa solo de `config` y `db` — nunca de `ai`, `handlers`, ni `memoria`
- [ ] **CAT-03**: Signatures de funciones idénticas a las originales en `memoria.py`
- [ ] **CAT-04**: `logger = logging.getLogger("ferrebot.services.catalogo")`

### InventarioService

- [ ] **INV-01**: `services/inventario_service.py` contiene la lógica de inventario extraída de `memoria.py`
- [ ] **INV-02**: `descontar_inventario()` retorna exactamente `(bool, str|None, float|None)` — contrato con `ventas_state.py`
- [ ] **INV-03**: Escrituras de inventario protegidas contra concurrencia (múltiples ventas simultáneas)
- [ ] **INV-04**: Importa solo de `config` y `db`

### HandlersModulares

- [x] **HDL-01**: `handlers/comandos.py` se convierte en re-export hub — todos los nombres originales re-exportados
- [x] **HDL-02**: Los ~50 handlers están distribuidos en archivos temáticos: `cmd_ventas`, `cmd_inventario`, `cmd_clientes`, `cmd_caja`, `cmd_admin` (mínimo)
- [x] **HDL-03**: Cada handler usa `@protegido` de `from middleware import protegido`
- [x] **HDL-04**: `main.py` no requiere ningún cambio — sus imports de `handlers.comandos` siguen funcionando
- [x] **HDL-05**: No existe `with threading.Lock():` que contenga un `await` en ningún `cmd_*.py`

### AIPrompts

- [ ] **PRM-01**: `ai/prompts.py` contiene las funciones de construcción de prompts extraídas de `ai.py`
- [ ] **PRM-02**: Las funciones en `ai/prompts.py` son puras — no hacen llamadas a `db` ni `memoria`
- [ ] **PRM-03**: `ai/excel_gen.py` contiene la lógica de generación Excel extraída de `ai.py`
- [ ] **PRM-04**: `ai/excel_gen.py` importa solo `openpyxl` y `config`

### ServiciosCajaFiados

- [ ] **CAJA-01**: `services/caja_service.py` contiene la lógica de caja extraída de `memoria.py`
- [ ] **CAJA-02**: `services/fiados_service.py` contiene la lógica de fiados extraída de `memoria.py`
- [ ] **CAJA-03**: `memoria.py` es un thin wrapper que re-exporta todos sus nombres públicos originales (~151)
- [ ] **CAJA-04**: `from memoria import X` funciona para todos los callers sin ningún cambio en los callers
- [ ] **CAJA-05**: `services/` nunca importa de `memoria.py` (evita circular import)

### AILimpio

- [ ] **AI-01**: `ai.py` reducido a ~800 líneas eliminando código movido a `ai/price_cache`, `ai/prompts`, `ai/excel_gen`
- [ ] **AI-02**: `ai.py` renombrado a `ai/__init__.py` — `from ai import procesar_con_claude` sigue funcionando
- [ ] **AI-03**: No existe `ai/__init__.py` hasta que Task I se ejecute (evita shadow de `ai.py`)

### Tests

- [ ] **TST-01**: `tests/test_price_cache.py` — tests de thread safety para la cache
- [ ] **TST-02**: `tests/test_middleware.py` — tests del decorador `@protegido`
- [ ] **TST-03**: `tests/test_catalogo_service.py` y `tests/test_inventario_service.py`
- [ ] **TST-04**: `tests/test_caja_service.py` y `tests/test_fiados_service.py`
- [ ] **TST-05**: `python -m pytest tests/ -v --ignore=test_suite.py` pasa en verde
- [ ] **TST-06**: `test_suite.py` original permanece sin modificar y sigue pasando

---

## v2 Requirements

### Observabilidad

- **OBS-01**: Métricas de hit/miss ratio de price_cache
- **OBS-02**: Contador de requests bloqueados por `@protegido`
- **OBS-03**: Health endpoint que muestre estado de todos los servicios

### Auth Avanzada

- **AUTH-01**: TTL configurable para rate limiter
- **AUTH-02**: Admin bypass automático para `ADMIN_CHAT_ID` en rate limiter

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cambios funcionales al bot | Solo refactorización estructural — cero cambios de comportamiento |
| Migrar a asyncpg/async DB | Complejidad innecesaria, psycopg2 sync funciona bien |
| Dashboard React | Fuera del scope de esta refactorización |
| Tocar `db.py`, `config.py`, `main.py` | Archivos protegidos — correctos tal como están |
| OAuth / login externo para el bot | No aplica — bot interno de ferretería |
| Webhooks Telegram (migrar de polling) | Cambio de arquitectura, no parte de esta refactorización |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MW-01 a MW-05 | Phase 1 (Tarea A) | Pending |
| PC-01 a PC-05 | Phase 1 (Tarea B) | Pending |
| MIG-01 a MIG-03 | Phase 1 (Tarea C) | Pending |
| CAT-01 a CAT-04 | Phase 1 (Tarea D) | Pending |
| INV-01 a INV-04 | Phase 1 (Tarea E) | Pending |
| HDL-01 a HDL-05 | Phase 2 (Tarea F) | Pending |
| PRM-01 a PRM-04 | Phase 2 (Tarea G) | Pending |
| CAJA-01 a CAJA-05 | Phase 2 (Tarea H) | Pending |
| AI-01 a AI-03 | Phase 3 (Tarea I) | Pending |
| TST-01 a TST-06 | Paralelo (Tarea J) | Pending |

**Coverage:**
- v1 requirements: 38 total
- Mapped to phases: 38
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-28 after initialization*
