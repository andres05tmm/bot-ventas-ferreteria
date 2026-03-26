# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** El bot debe registrar ventas sin interrupciones — si la DB falla, el bot no puede caer.
**Current focus:** Phase 1 — DB Infra + Catálogo + Inventario

## Current Position

Phase: 1 of 5 (DB Infra + Catálogo + Inventario)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-03-25 — Roadmap created, phases derived from MIGRATION.md

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

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- psycopg2 (sync) sobre asyncpg: el bot usa threading, no asyncio puro
- Migración por fases (no big-bang): cada fase funciona end-to-end antes de avanzar
- Mantener interfaz de memoria.py: ~151 referencias en código; no cambiar firmas
- Mantener Sheets durante Fase 3: fallback si Postgres falla; eliminar en Fase 5

### Pending Todos

None yet.

### Blockers/Concerns

- _leer_excel_rango() en routers/shared.py es el unlock crítico de Phase 3 — todos los routers la usan; planificar su reemplazo con cuidado
- El schema completo debe desplegarse en Railway antes de ejecutar Phase 1 (SQL en MIGRATION.md)

## Session Continuity

Last session: 2026-03-25
Stopped at: Roadmap created — listo para planificar Phase 1
Resume file: None
