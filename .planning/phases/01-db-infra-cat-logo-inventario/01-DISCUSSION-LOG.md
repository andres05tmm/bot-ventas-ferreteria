# Phase 1: DB Infra + Catálogo + Inventario - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 01-db-infra-cat-logo-inventario
**Areas discussed:** Schema deployment, Fallback depth, guardar_memoria() strategy, migrate_memoria.py trigger

---

## Schema Deployment

| Option | Description | Selected |
|--------|-------------|----------|
| Auto al arrancar | db.py ejecuta CREATE TABLE IF NOT EXISTS al iniciar — cero pasos manuales | ✓ |
| Manual vía Railway console | Copiar SQL de MIGRATION.md y ejecutar una sola vez | |
| Script separado setup_db.py | Script independiente que se corre una sola vez | |

**User's choice:** Auto al arrancar
**Notes:** db.py maneja la creación del schema. Railway redespliega y el schema aparece solo.

---

## Fallback Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Solo check al arrancar | Flag global DB_DISPONIBLE — toda la sesión en un modo, sin overhead por query | ✓ |
| Reintento por query | Cada llamada a db.py atrapa la excepción y usa cache RAM como fallback | |

**User's choice:** Solo check al arrancar
**Notes:** Simple y predecible. El modo se determina una vez al arranque.

---

## guardar_memoria() Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Doble escritura Postgres + JSON/Drive | Escribe en Postgres Y sigue subiendo a Drive — máximo fallback durante migración | ✓ |
| Solo Postgres (si disponible) | Si DB_DISPONIBLE, omite JSON/Drive — corte más limpio pero Drive queda desactualizado | |

**User's choice:** Doble escritura
**Notes:** Drive sigue siendo fuente de verdad durante Fase 1. Máxima seguridad durante la migración.

---

## migrate_memoria.py Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Manual vía Railway shell | `railway run python migrate_memoria.py` — control total, verificable | ✓ |
| Auto si tabla vacía | db.py detecta 0 filas y ejecuta migración al arrancar | |

**User's choice:** Manual vía Railway shell
**Notes:** Flujo explícito: (1) deploy código, (2) railway run migrate, (3) verificar /precios e /inventario.

---

## Claude's Discretion

- Tamaño del pool de conexiones (mínimo/máximo)
- Timeout y reintentos del pool
- API exacta del context manager en db.py
- Normalización de campos nulos al migrar

## Deferred Ideas

- Migración automática si tabla vacía — descartado, preferido control manual
- Observabilidad (logging queries lentas, health check, métricas) — v2 requirements
