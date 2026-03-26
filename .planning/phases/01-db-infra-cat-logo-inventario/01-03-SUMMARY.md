---
phase: 01-db-infra-cat-logo-inventario
plan: 03
subsystem: database
tags: [postgres, migration, psycopg2, memoria-json, catalogo, inventario, upsert]

# Dependency graph
requires:
  - phase: 01-01
    provides: "db.py with init_db, execute_returning, execute, query_one, query_all and uq_prod_fraccion unique index"
provides:
  - "migrate_memoria.py — idempotent one-time migration script from memoria.json to PostgreSQL"
  - "Migrates productos (CAT-01), alias (CAT-02), inventario (CAT-03), fracciones, precios_cantidad"
affects:
  - 01-04-memoria-refactor
  - 01-05-fuzzy-match

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "UPSERT pattern: ON CONFLICT (unique_col) DO UPDATE SET ... for idempotent migrations"
    - "Alias conflict logging: ON CONFLICT DO NOTHING + rowcount==0 detection for duplicate warning"
    - "Defensive alias normalization: isinstance(alias_list, str) to handle str vs list field"

key-files:
  created:
    - migrate_memoria.py
  modified: []

key-decisions:
  - "D-08: Script runs manually via `railway run python migrate_memoria.py` (not at bot startup)"
  - "D-09: All UPSERT operations make script safe to re-run multiple times"
  - "D-10: Script calls db.init_db() first; exits with sys.exit(1) if DATABASE_URL missing"
  - "Pitfall 4: Fracciones UPSERT uses ON CONFLICT (producto_id, fraccion) relying on uq_prod_fraccion index from Plan 01"
  - "Pitfall 6: Alias conflicts are logged as WARNING not errors — DO NOTHING + rowcount check"

patterns-established:
  - "Migration scripts: fail-fast on DB unavailable, UPSERT all operations, log summary counts at end"

requirements-completed: [CAT-01, CAT-02, CAT-03]

# Metrics
duration: 1min
completed: 2026-03-26
---

# Phase 01 Plan 03: Migrate memoria.json to PostgreSQL Summary

**Idempotent migration script that UPSERTs ~576 products, aliases, fracciones, precios_cantidad, and inventario from memoria.json into PostgreSQL tables**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-26T06:29:39Z
- **Completed:** 2026-03-26T06:30:43Z
- **Tasks:** 1 of 1
- **Files modified:** 1

## Accomplishments

- Created `migrate_memoria.py` with complete UPSERT migration covering all 5 table targets
- Script is idempotent — safe to re-run multiple times without duplicates
- Alias conflict detection: logs WARNING for duplicate aliases (DO NOTHING + rowcount check)
- Defensive alias normalization handles both string and list field formats in memoria.json
- Summary counts logged at end for verification of successful migration

## Task Commits

Each task was committed atomically:

1. **Task 1: Create migrate_memoria.py with complete UPSERT migration** - `1e50f89` (feat)

**Plan metadata:** committed with docs commit below.

## Files Created/Modified

- `migrate_memoria.py` — one-time migration script; run via `railway run python migrate_memoria.py` after Phase 1 deploy

## Decisions Made

- Script uses `os.getenv("MEMORIA_FILE", "memoria.json")` to allow overriding the source file path via environment
- Inventario migration does a lookup JOIN approach (query_one per product) rather than bulk INSERT — correct for ~576 items, keeps code simple
- alias_list defensively normalized: `isinstance(alias_list, str)` converts bare string to single-item list (handles inconsistent memoria.json field format)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

**Manual step required before using the bot with Postgres data:**

```bash
railway run python migrate_memoria.py
```

Run this ONCE after Phase 1 deploy and after DATABASE_URL is set in Railway. Script is idempotent so re-running is safe.

## Next Phase Readiness

- `migrate_memoria.py` ready to execute against Railway Postgres after Phase 1 deploy
- Plan 01-04 (memoria.py refactor to read from Postgres) can begin — tables will be populated after migration runs
- Plan 01-05 (fuzzy_match.py loading from Postgres) also unblocked

---
*Phase: 01-db-infra-cat-logo-inventario*
*Completed: 2026-03-26*
