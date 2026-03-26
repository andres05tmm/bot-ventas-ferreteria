---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Phase 4 context gathered (assumptions mode)
last_updated: "2026-03-26T23:14:41.756Z"
last_activity: 2026-03-26
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 8
  completed_plans: 8
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** El bot debe registrar ventas sin interrupciones — si la DB falla, el bot no puede caer.
**Current focus:** Phase 03 — ventas

## Current Position

Phase: 4
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-03-26

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 2 | 2 tasks | 4 files |
| Phase 01 P02 | 180 | 2 tasks | 1 files |
| Phase 01-db-infra-cat-logo-inventario P03 | 1 | 1 tasks | 1 files |
| Phase 02 P01 | 600 | 2 tasks | 3 files |
| Phase 02 P02 | 3 | 2 tasks | 2 files |
| Phase 03 P03 | 80 | 1 tasks | 1 files |
| Phase 03 P02 | 142 | 2 tasks | 2 files |
| Phase 03-ventas P01 | 3 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- psycopg2 (sync) sobre asyncpg: el bot usa threading, no asyncio puro
- Migración por fases (no big-bang): cada fase funciona end-to-end antes de avanzar
- Mantener interfaz de memoria.py: ~151 referencias en código; no cambiar firmas
- Mantener Sheets durante Fase 3: fallback si Postgres falla; eliminar en Fase 5
- [Phase 01]: db.py uses ThreadedConnectionPool with lazy psycopg2 import inside init_db() — prevents import errors and is thread-safe
- [Phase 01]: DATABASE_URL not added to _CLAVES_REQUERIDAS — optional env var, bot runs in JSON mode if absent (D-05)
- [Phase 01]: init_db() called before _restaurar_memoria() in start.py — ensures DB_DISPONIBLE set before first cargar_memoria() call (D-03)
- [Phase 01]: db imported lazily inside functions in memoria.py (not top-level) to avoid circular import
- [Phase 01]: Postgres write in guardar_memoria is non-fatal (except Exception + logger.warning) — bot cannot fall
- [Phase 01]: cargar_memoria overlays catalogo+inventario from Postgres on JSON base (unmigrated fields: gastos, caja, notas stay in JSON)
- [Phase 01]: D-08/D-09/D-10: migrate_memoria.py runs manually via railway run; all UPSERTs make it idempotent; fails fast if DATABASE_URL missing
- [Phase 01]: [Phase 01]: Alias conflicts in migration logged as WARNING (DO NOTHING + rowcount==0) not errors — preserves first-registered alias owner
- [Phase 02]: lazy import db inside helpers (not top-level) — same pattern as 01-02, prevents circular import
- [Phase 02]: migrate_gastos_caja.py deduplicates gastos by fecha+concepto+monto (no unique constraint in gastos table)
- [Phase 02]: Drive uploads of historico JSON/Excel eliminated: Postgres replaces Drive as source of truth for historico data
- [Phase 02]: migrate_historico.py merges historico_ventas.json totals + historico_diario.json enriched breakdown into historico_ventas table
- [Phase 03]: cliente_id set to None during ventas migration — FK resolution unreliable against live catalog
- [Phase 03]: alias_usado mapped directly from alias column in ventas migration, None if column absent
- [Phase 03]: _leer_ventas_postgres returns None (not []) on DB unavailability so callers can distinguish 'no data' from 'DB unavailable' for fallback logic
- [Phase 03]: ventas_hoy uses three-tier fallback: Sheets (primary) -> Postgres -> Excel (last resort); all other read endpoints use two-tier: Postgres -> Excel
- [Phase 03-ventas]: items_para_pg collected during existing for loop in registrar_ventas_con_metodo to avoid re-iterating ventas list
- [Phase 03-ventas]: check-then-insert pattern in /cerrar (not UPSERT) because ventas schema lacks UNIQUE constraint on consecutivo

### Pending Todos

None yet.

### Blockers/Concerns

- _leer_excel_rango() en routers/shared.py es el unlock crítico de Phase 3 — todos los routers la usan; planificar su reemplazo con cuidado
- El schema completo debe desplegarse en Railway antes de ejecutar Phase 1 (SQL en MIGRATION.md)

## Session Continuity

Last session: 2026-03-26T23:14:41.743Z
Stopped at: Phase 4 context gathered (assumptions mode)
Resume file: .planning/phases/04-proveedores-fiados-compras/04-CONTEXT.md
