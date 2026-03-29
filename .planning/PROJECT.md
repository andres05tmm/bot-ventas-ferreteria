# FerreBot — Refactorización

## What This Is

FerreBot es un bot de Telegram para Ferretería Punto Rojo (Cartagena, Colombia) que permite a vendedores registrar ventas por voz o texto usando IA (Claude). Esta iniciativa es una refactorización estructural: dividir archivos monolíticos (`ai.py` de 2685 líneas, `handlers/comandos.py` de ~2200 líneas) en módulos pequeños y cohesivos, sin cambiar funcionalidad externa. El bot debe permanecer operativo en cada commit del proceso.

## Core Value

El bot no se rompe durante la refactorización — cada commit deja `python main.py` arrancando sin errores.

## Requirements

### Validated

- ✓ Bot recibe ventas por voz (Whisper) y texto, procesa con Claude — existing
- ✓ Dashboard React muestra analíticas via FastAPI (8 routers) — existing
- ✓ PostgreSQL en Railway con pool de conexiones thread-safe — existing
- ✓ Estado de ventas en curso protegido con threading.Lock — existing
- ✓ Comandos Telegram (50+) en handlers/comandos.py — existing
- ✓ Sistema de skills .md con conocimiento ferretero — existing

### Active

- [ ] `middleware/` — autenticación por AUTHORIZED_CHAT_IDS + rate limiting (`@protegido`)
- [ ] `ai/price_cache.py` — cache de precios thread-safe extraído de ai.py
- [ ] `migrations/` — mover scripts migrate_*.py a directorio dedicado
- [ ] `services/catalogo_service.py` — lógica de catálogo extraída de memoria.py
- [ ] `services/inventario_service.py` — lógica de inventario extraída de memoria.py
- [ ] `handlers/cmd_*.py` — dividir comandos.py en archivos temáticos con `@protegido`
- [ ] `ai/prompts.py` + `ai/excel_gen.py` — extraer prompts y generación Excel de ai.py
- [ ] `services/caja_service.py` + `fiados_service.py` + thin wrapper `memoria.py`
- [x] `ai.py` reducido de 2685 → 1256 líneas, convertido en `ai/__init__.py` package — Validated in Phase 03: reduction
- [ ] `tests/` — tests unitarios por módulo nuevo

### Out of Scope

- Cambios funcionales al bot — solo refactorización estructural
- Tocar `db.py`, `config.py`, `main.py` — están correctos
- Migrar a asyncpg/async PostgreSQL — complejidad innecesaria ahora
- Dashboard React — fuera del scope de esta refactorización

## Context

**Arquitectura actual:**
- `ai.py` (2685 líneas): motor Claude, procesar_con_claude, procesar_acciones, Excel gen, price cache
- `memoria.py`: catálogo, inventario, caja, fiados — será thin wrapper delegando a services/
- `handlers/comandos.py` (~2200 líneas): 50+ comandos, sin auth centralizada
- Sin middleware de auth — cualquier chat_id puede usar el bot actualmente

**Plan de tareas (ya definido en `_obsidian/01-Proyecto/TAREA-X.md`):**
- Fase 1 (paralelo): Tareas A, B, C, D, E — infraestructura nueva sin tocar nada existente
- Fase 2 (tras Fase 1): Tareas F, G, H — usar la infraestructura creada
- Fase 3 (al final): Tarea I — limpiar ai.py una vez extraídos sus módulos
- Paralelo con todo: Tarea J — tests unitarios

**Variables de entorno nuevas requeridas:**
- `AUTHORIZED_CHAT_IDS` — lista separada por coma, introducida en Tarea A

## Constraints

- **Tech stack**: Python 3.11, python-telegram-bot 21.3, psycopg2-binary (sync) — no cambiar
- **Archivos protegidos**: `db.py`, `config.py`, `main.py` — no modificar
- **Deploy**: Railway con Nixpacks, `python3 start.py` — cada commit debe arrancar
- **Threading**: `threading.Lock` para todo estado compartido — mantener patrón existente
- **Backwards compat**: `memoria.py` sigue exportando las mismas funciones durante toda la refactorización (thin wrapper)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Thin wrapper en memoria.py | Evita romper imports en todos los archivos que usan memoria | — Pending |
| Fase 1 paralela completa | Las tareas A-E no tienen dependencias entre sí | — Pending |
| Un commit por tarea | Cada tarea es reversible y verificable independientemente | — Pending |
| services/ en vez de modificar memoria.py directo | Separación de responsabilidades sin romper contratos | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-29 after Phase 03 (reduction) complete*
