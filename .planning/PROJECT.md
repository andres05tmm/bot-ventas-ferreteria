# FerreBot — Migración a PostgreSQL

## What This Is

FerreBot es un sistema POS completo para Ferretería Punto Rojo (Cartagena, Colombia). Los vendedores registran ventas por voz o texto en Telegram, Claude AI interpreta los mensajes, y un dashboard React muestra analíticas en tiempo real. Actualmente persiste en Google Drive (JSON + Excel); el objetivo de este milestone es migrar toda la persistencia estructurada a PostgreSQL en Railway.

## Core Value

El bot debe registrar ventas sin interrupciones — si la DB falla, el bot no puede caer.

## Requirements

### Validated

- ✓ Capa de acceso a PostgreSQL (`db.py`) con ThreadedConnectionPool + 18-table schema — Validated in Phase 01: db-infra-cat-logo-inventario
- ✓ Script de migración `migrate_memoria.py` (idempotent UPSERT, ~576 productos) — Validated in Phase 01: db-infra-cat-logo-inventario
- ✓ `memoria.py` dual-write (cargar desde Postgres + guardar a JSON+Postgres, interfaz pública intacta) — Validated in Phase 01: db-infra-cat-logo-inventario
- ✓ Registro de ventas por texto y audio en Telegram — existing
- ✓ Interpretación de lenguaje natural con Claude AI (`ai.py`) — existing
- ✓ Dashboard React con 12 tabs (Resumen, Ventas Rápidas, Historial, Inventario, Caja, Gastos, Compras, Proveedores, Kardex, Resultados, Top Productos, Histórico) — existing
- ✓ Catálogo de ~576 productos con fuzzy search — existing
- ✓ Gestión de inventario, caja, gastos, fiados y cuentas por pagar — existing
- ✓ Histórico diario de ventas con desglose por método de pago — existing
- ✓ Cierre diario automatizado (`/cerrar`) — existing
- ✓ Exportación a Excel y sincronización con Google Sheets — existing
- ✓ Deploy unificado en Railway (`start.py`) — existing

### Active

- [ ] `fuzzy_match.py` cargando el índice desde Postgres
- ✓ Histórico de ventas diarias (`historico_ventas`, `historico_diario`) migrado a Postgres — Validated in Phase 02: hist-rico-gastos-caja
- ✓ Gastos y caja migrados a Postgres — Validated in Phase 02: hist-rico-gastos-caja
- ✓ Ventas registradas en Postgres (tabla `ventas` + `ventas_detalle`) en paralelo con Sheets — Validated in Phase 03: ventas
- ✓ Endpoints `/ventas/*` leyendo desde Postgres (con fallback a Excel); `_leer_ventas_postgres()` en shared.py — Validated in Phase 03: ventas
- ✓ Script `migrate_ventas.py` para importar histórico de ventas.xlsx a Postgres (idempotente) — Validated in Phase 03: ventas
- [ ] Proveedores, fiados y compras migrados a Postgres
- [ ] Export Excel generado on-demand desde Postgres (`GET /export/ventas.xlsx`)
- [ ] Eliminación de dependencias de Drive para datos estructurados (JSONs e históricos)
- [ ] `test_suite.py` pasando 1096+ tests después de cada fase

### Out of Scope

- Modificar `ai.py` o el sistema de prompts de Claude — crítico, no tocar
- Migrar fotos de facturas de Google Drive — siguen en Drive
- Cambiar la interfaz del dashboard (nombres/formatos de endpoints) — solo cambia la fuente interna
- Refactorizar `ventas_state.py` — estado en RAM, no persiste
- Cambiar el mecanismo de autenticación de Telegram

## Context

**Stack actual de persistencia (a eliminar):**
- `memoria.json` descargado de Drive al arrancar, subido en cada cambio (~151 referencias en código)
- `ventas.xlsx` con hojas por mes — ~388 referencias a operaciones Excel
- Google Sheets como buffer del día (real-time pizarra)
- `historico_ventas.json` y `historico_diario.json` en Drive

**Restricciones críticas durante migración:**
- El bot no puede caer — Railway redespliega en cada commit, cada fase debe funcionar end-to-end
- La interfaz pública de `memoria.py` (`cargar_memoria()`, `guardar_memoria()`) debe mantenerse — muchos módulos dependen de ella
- `_leer_excel_rango()` en `routers/shared.py` es el unlock crítico de Fase 3 — todos los routers la usan
- Zona horaria siempre `config.COLOMBIA_TZ` (UTC-5), fechas como strings `"YYYY-MM-DD"`, montos como enteros en pesos

**Compatibilidad durante transición:**
- Fases 1-2: algunos módulos leen de Postgres, otros de `memoria.json` — intencional
- Fase 3: ventas se escriben en Postgres Y Sheets simultáneamente hasta Fase 5
- Fase 5: Sheets se elimina, Drive solo para fotos

## Constraints

- **Tech stack:** Python 3.11, psycopg2-binary (sync, no asyncpg — bot usa threading no asyncio puro)
- **Compatibilidad:** interfaz pública de `memoria.py` no puede cambiar (firmas de función)
- **Uptime:** cero downtime — cada commit debe dejar el sistema operativo
- **Tests:** `test_suite.py` 1096+ tests deben pasar después de cada fase
- **Dependencia circular:** Drive solo para fotos de facturas al finalizar la migración

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| psycopg2 (sync) sobre asyncpg | El bot usa threading, no es puramente async; psycopg2 es más simple de integrar | — Pending |
| Migración por fases (no big-bang) | El bot no puede caer; cada fase funciona end-to-end antes de avanzar | — Pending |
| Mantener interfaz de memoria.py | ~151 referencias en código; cambiar firmas rompería todo | — Pending |
| Mantener Sheets durante Fase 3 | Fallback si Postgres falla; eliminar solo en Fase 5 cuando Postgres esté probado | — Pending |

## Evolution

Este documento evoluciona en cada transición de fase y milestone.

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
*Last updated: 2026-03-26 — Phase 03 complete (ventas write path, read path, migration script)*
