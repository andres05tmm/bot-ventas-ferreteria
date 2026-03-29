# FerreBot — Refactorización

## What This Is

FerreBot es un bot de Telegram para Ferretería Punto Rojo (Cartagena, Colombia) que permite a vendedores registrar ventas por voz o texto usando IA (Claude). La refactorización estructural v1.0 está **completa**: los dos archivos monolíticos (`ai.py` de 2685 líneas, `handlers/comandos.py` de ~2200 líneas) y `memoria.py` fueron divididos en módulos cohesivos sin cambiar funcionalidad externa. El bot permaneció operativo en cada commit del proceso.

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
- ✓ `middleware/` — `@protegido` con AUTHORIZED_CHAT_IDS fail-open + rate limiter — v1.0
- ✓ `ai/price_cache.py` — cache thread-safe con TTL 5min, race condition eliminada — v1.0
- ✓ `migrations/` — todos los migrate_*.py en directorio dedicado con guards — v1.0
- ✓ `services/catalogo_service.py` — lógica de catálogo extraída de memoria.py — v1.0
- ✓ `services/inventario_service.py` — lógica de inventario con contrato 3-tuple preservado — v1.0
- ✓ `handlers/cmd_*.py` — comandos.py dividido en 6 archivos temáticos, re-export hub — v1.0
- ✓ `ai/prompts.py` + `ai/excel_gen.py` — prompts y Excel extraídos de ai.py — v1.0
- ✓ `services/caja_service.py` + `fiados_service.py` + thin wrapper `memoria.py` — v1.0
- ✓ `ai/__init__.py` — ai.py reducido de 2685 → 1256 líneas, convertido en package — v1.0
- ✓ `tests/` — 62 tests unitarios por módulo nuevo, cero credentials requeridas — v1.0

### Active

*(No active requirements — v1.0 refactoring complete. Add v2 goals here for next milestone.)*

### Out of Scope

- Cambios funcionales al bot — solo refactorización estructural
- Tocar `db.py`, `config.py`, `main.py` — archivos protegidos, correctos tal como están
- Migrar a asyncpg/async PostgreSQL — complejidad innecesaria
- Dashboard React — fuera del scope de esta refactorización
- OAuth / login externo para el bot — no aplica
- Webhooks Telegram (migrar de polling) — cambio de arquitectura, no parte de la refact.

## Context

**Estado actual (post v1.0):**

- `ai/__init__.py` — 1256 líneas (↓ desde 2685): motor Claude, procesar_con_claude, procesar_acciones. Delega a `ai/prompts.py`, `ai/excel_gen.py`, `ai/price_cache.py`
- `memoria.py` — thin wrapper: re-exporta ~151 nombres públicos delegando a `services/`
- `handlers/comandos.py` — re-export hub puro; lógica en 6 `cmd_*.py` temáticos
- `middleware/auth.py` — `@protegido` activo en todos los handlers
- `tests/` — 62 tests en verde, sin credentials, corre en CI
- Codebase: 63 archivos Python, ~22,500 LOC total

**Variables de entorno:**
- `AUTHORIZED_CHAT_IDS` — lista separada por coma (nueva en v1.0, Tarea A)

**Potential next focus:**
- Observabilidad: métricas hit/miss de price_cache, requests bloqueados por @protegido
- Auth avanzada: TTL configurable en rate limiter, admin bypass automático

## Constraints

- **Tech stack**: Python 3.11, python-telegram-bot 21.3, psycopg2-binary (sync) — no cambiar
- **Archivos protegidos**: `db.py`, `config.py`, `main.py` — no modificar
- **Deploy**: Railway con Nixpacks, `python3 start.py` — cada commit debe arrancar
- **Threading**: `threading.Lock` para todo estado compartido — mantener patrón existente
- **Backwards compat**: `memoria.py` sigue exportando las mismas funciones (thin wrapper estable)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Thin wrapper en memoria.py | Evita romper imports en todos los archivos que usan memoria | ✓ Funciona — ~151 nombres re-exportados sin cambiar callers |
| Fase 1 paralela completa | Las tareas A-E no tienen dependencias entre sí | ✓ Ejecutadas en paralelo sin conflictos |
| Un commit por tarea | Cada tarea es reversible y verificable independientemente | ✓ 35+ commits atómicos, bot operativo en cada uno |
| services/ en vez de modificar memoria.py directo | Separación de responsabilidades sin romper contratos | ✓ 4 services sin circular imports |
| Namespace package para ai/ (sin __init__.py en Fase 1) | Evitar shadow de ai.py mientras price_cache y prompts existían | ✓ Crítico — previno rotura de 5+ callers durante fases intermedias |
| sys.modules stub en tests | config.py hace SystemExit sin credentials | ✓ 62 tests pasan sin DATABASE_URL ni TELEGRAM_TOKEN |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-29 after v1.0 milestone complete*
