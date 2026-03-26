---
phase: 03-ventas
verified: 2026-03-26T22:50:00Z
status: passed
score: 8/8 must-haves verified
gaps: []
human_verification:
  - test: "Confirm payment in Telegram triggers actual Postgres row creation (ventas + ventas_detalle)"
    expected: "Row visible in DB after bot flow completes in production"
    why_human: "Requires live Railway environment with DATABASE_URL set and a real Telegram payment confirmation flow"
  - test: "Run /cerrar and verify Postgres receives all synced ventas"
    expected: "ventas table row count increases by number of Sheets entries synced"
    why_human: "Requires live bot session with open sales in Google Sheets"
  - test: "Dashboard /ventas/semana returns data sourced from Postgres (fuente field or confirmed via DB)"
    expected: "Response comes from Postgres when DB_DISPONIBLE=True"
    why_human: "Requires Railway environment; cannot simulate DB_DISPONIBLE=True locally without DATABASE_URL"
  - test: "railway run python migrate_ventas.py executes against real ventas.xlsx"
    expected: "Prints summary with sheets_count > 0, ventas_count > 0, no fatal errors"
    why_human: "Requires Railway CLI and access to ventas.xlsx with real data in production"
---

# Phase 3: Ventas Verification Report

**Phase Goal:** Migrate all ventas (sales) writes and reads to Postgres — payment confirmation writes to ventas+ventas_detalle, dashboard endpoints read from Postgres with Excel fallback, and historical data from ventas.xlsx is importable via migrate_ventas.py.
**Verified:** 2026-03-26T22:50:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Confirmar pago en Telegram escribe la venta en tablas ventas y ventas_detalle de Postgres | VERIFIED | `ventas_state.py` lines 234-276: full INSERT INTO ventas + ventas_detalle block with DB_DISPONIBLE guard and non-fatal except |
| 2 | /cerrar sincroniza ventas de Sheets a Postgres ademas de Excel (triple-write) | VERIFIED | `handlers/comandos.py` lines 1193-1282: `_sync_ventas_postgres()` inner function wrapped in `asyncio.to_thread`, called after Drive upload |
| 3 | Si Postgres falla, la venta igual queda en Sheets/Excel — bot no cae | VERIFIED | Both Postgres blocks use `except Exception as e: logger.warning(...)` — non-fatal. Sheets/Excel writes happen before Postgres block |
| 4 | Endpoints /ventas/semana, /ventas/top, /ventas/top2, /ventas/resumen read historical ventas from Postgres instead of Excel | VERIFIED | `routers/ventas.py` lines 101-103, 114-116, 180-184, 201-205, 323-325: all four endpoints call `_leer_ventas_postgres()` first with `_leer_excel_rango()` fallback |
| 5 | /ventas/hoy keeps Sheets as primary source for today, uses Postgres as fallback instead of Excel | VERIFIED | `routers/ventas.py` lines 39-68: Sheets primary (line 42), Postgres fallback (lines 51-59), Excel last resort (lines 61-68). `fuente = "postgres_fallback"` label confirmed |
| 6 | Dashboard receives identical JSON format from all ventas endpoints (no frontend changes needed) | VERIFIED | `_leer_ventas_postgres()` in `routers/shared.py` lines 209-225 produces identical dict structure to `_leer_excel_rango()` with all 14 keys matching exactly including `"codigo_producto": ""` |
| 7 | Historical sales from ventas.xlsx are imported into ventas + ventas_detalle tables in Postgres | VERIFIED | `migrate_ventas.py` (308 lines): reads all monthly sheets via `openpyxl`, groups by consecutivo+fecha, INSERT INTO ventas + ventas_detalle |
| 8 | The migration script is idempotent — safe to re-run without creating duplicates | VERIFIED | `migrate_ventas.py` lines 225-231: `SELECT id FROM ventas WHERE consecutivo = %s AND fecha = %s` check-then-skip before each INSERT |

**Score:** 8/8 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `ventas_state.py` | INSERT INTO ventas + ventas_detalle on payment confirm | VERIFIED | Lines 234-276: items_para_pg collected in for loop, full Postgres INSERT block with DB_DISPONIBLE guard, execute_returning for ventas header, execute for each detail line |
| `handlers/comandos.py` | Triple-write Postgres block in comando_cerrar_dia | VERIFIED | Lines 1193-1282: `_sync_ventas_postgres()` inner function, idempotent check-then-insert, asyncio.to_thread wrapper, non-fatal exception handling at both inner and outer levels |
| `routers/shared.py` | `_leer_ventas_postgres()` function | VERIFIED | Lines 156-230: full SQL JOIN query on ventas + ventas_detalle, WHERE clause builders for dias/mes_actual, identical dict format to _leer_excel_rango, returns None on failure |
| `routers/ventas.py` | Updated endpoints using Postgres-first reads | VERIFIED | 7 occurrences of `_leer_ventas_postgres` (line 22 import + 6 call sites in ventas_semana, ventas_top, ventas_resumen x2, ventas_top2, ventas_hoy) |
| `migrate_ventas.py` | One-time migration script for historical ventas from Excel to Postgres | VERIFIED | 308 lines, fail-fast guard, db.init_db(), openpyxl.load_workbook, column detection mirrors _leer_excel_rango, idempotency, summary output, no asyncio import |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `ventas_state.py::registrar_ventas_con_metodo` | `db.execute_returning` | lazy `import db as _db` inside function | WIRED | Line 236: `import db as _db`, line 251: `_db.execute_returning("""INSERT INTO ventas ... RETURNING id""", ...)` |
| `handlers/comandos.py::_sync_ventas_postgres` | `db.execute_returning` | lazy `import db as _db` inside inner function | WIRED | Line 1195: `import db as _db`, line 1236: `_db.execute_returning("""INSERT INTO ventas ... RETURNING id""", ...)` |
| `routers/shared.py::_leer_ventas_postgres` | `db.query_all` | lazy `import db as _db` | WIRED | Line 165: `import db as _db`, line 206: `rows = _db.query_all(sql, params if params else None)` |
| `routers/ventas.py` | `routers/shared.py::_leer_ventas_postgres` | explicit import | WIRED | Line 22: `from routers.shared import (_hoy, _hace_n_dias, _leer_excel_rango, _leer_ventas_postgres, ...)` |
| `migrate_ventas.py` | `db.execute_returning` | direct `import db` | WIRED | Line 35: `import db`, line 252: `db.execute_returning("""INSERT INTO ventas ... RETURNING id""", ...)` |
| `migrate_ventas.py` | `ventas.xlsx` | openpyxl | WIRED | Line 157: `wb = openpyxl.load_workbook(excel_file, read_only=True, data_only=True)` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `routers/ventas.py::ventas_semana` | `ventas` | `_leer_ventas_postgres(dias=7)` -> `_db.query_all(SELECT ... FROM ventas v JOIN ventas_detalle d ...)` | Yes — SQL JOIN with real DB query | FLOWING |
| `routers/ventas.py::ventas_hoy` | `filtradas` | `sheets_leer_ventas_del_dia()` primary; `_leer_ventas_postgres(dias=1)` fallback | Yes — Sheets primary, real DB query as fallback | FLOWING |
| `routers/ventas.py::ventas_resumen` | `ventas_sem`, `ventas_mes` | `_leer_ventas_postgres(dias=7)` and `_leer_ventas_postgres(mes_actual=True)` | Yes — SQL with date filters | FLOWING |
| `ventas_state.py::registrar_ventas_con_metodo` | `items_para_pg` | populated during `for venta in ventas:` loop, written to DB after | Yes — live transaction data from bot state | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| migrate_ventas.py has valid Python syntax | `python -c "import ast; ast.parse(open('migrate_ventas.py').read()); print('syntax ok')"` | `syntax ok` | PASS |
| migrate_ventas.py is 308 lines (>= 80 required) | `wc -l migrate_ventas.py` | `308` | PASS |
| No asyncio in migrate_ventas.py | `grep asyncio migrate_ventas.py` | (no output) | PASS |
| ventas router imports _leer_ventas_postgres | `grep -c "_leer_ventas_postgres" routers/ventas.py` | `7` | PASS |
| All 5 task commits present in git log | `git log --oneline fdc5080 f8e342a 2708968 69652f9 f4cdb65` | All 5 found | PASS |

Step 7b: Behavioral spot-checks run. Cannot test actual API responses without a live server with DATABASE_URL set — those deferred to human verification.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| VEN-01 | 03-01-PLAN.md | Confirmación de pago escribe venta en tabla ventas + ventas_detalle (en paralelo con Sheets durante transición) | SATISFIED | `ventas_state.py` lines 234-276: INSERT INTO ventas + ventas_detalle after payment confirmation callback |
| VEN-02 | 03-01-PLAN.md | /cerrar copia ventas de Sheets → Postgres (en lugar de Sheets → Excel) | SATISFIED | `handlers/comandos.py` lines 1193-1282: _sync_ventas_postgres() called via asyncio.to_thread after Excel save |
| VEN-03 | 03-02-PLAN.md | _leer_excel_rango() en routers/shared.py reemplazada por query a ventas + ventas_detalle | SATISFIED | `routers/shared.py` lines 156-230: `_leer_ventas_postgres()` added as replacement; `_leer_excel_rango()` retained as fallback |
| VEN-04 | 03-02-PLAN.md | Endpoints /ventas/hoy, /ventas/historial leen desde Postgres | SATISFIED | `routers/ventas.py`: ventas_hoy uses Postgres as fallback (line 53); ventas_semana/top/top2/resumen use Postgres as primary (lines 101, 114, 180, 201, 323) |
| VEN-05 | 03-03-PLAN.md | Script de migración importa ventas históricas del Excel a Postgres | SATISFIED | `migrate_ventas.py` 308 lines: reads all monthly sheets, idempotent insert with consecutivo+fecha dedup |
| VEN-06 | 03-02-PLAN.md | Dashboard muestra ventas desde Postgres (mismos formatos de respuesta JSON) | SATISFIED | `_leer_ventas_postgres()` returns identical 14-key dict structure to `_leer_excel_rango()` including `"codigo_producto": ""`; zero frontend changes needed |

No orphaned requirements found — all 6 VEN-* IDs declared in plan frontmatter and accounted for.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `routers/shared.py` | 37, 42 | `return []` | Info | Legitimate error fallbacks in `_leer_excel_rango()` when Excel file missing/unreadable — not stubs |
| `routers/shared.py` | 267, 271, 274 | `return []` | Info | Legitimate error fallbacks in `_leer_excel_compras()` — not phase-3 code, not stubs |

No blocker or warning anti-patterns found in phase-3 code. All `return []` hits are in Excel fallback helpers (pre-existing code), not in new Postgres paths.

---

### Human Verification Required

The following items cannot be verified programmatically — they require a live Railway environment with `DATABASE_URL` set.

#### 1. Payment Confirmation Creates Postgres Rows

**Test:** Send a product message via Telegram, confirm payment method
**Expected:** New row in `ventas` table with correct consecutivo, fecha, vendedor, metodo_pago, total; corresponding rows in `ventas_detalle`
**Why human:** Requires live Railway environment + Telegram bot session

#### 2. /cerrar Triple-Write Verification

**Test:** Open caja, record 2-3 sales via Telegram, run `/cerrar`
**Expected:** All sales appear in Postgres `ventas` + `ventas_detalle` after command completes; `/cerrar` log shows "Postgres /cerrar: N ventas synced"
**Why human:** Requires live bot session with Sheets data

#### 3. Dashboard Reads from Postgres (Not Excel)

**Test:** Query `GET /ventas/semana` when Postgres has data
**Expected:** Response data matches Postgres rows, not Excel; verify by inserting a test row in DB that doesn't exist in Excel
**Why human:** Requires Railway environment with `DB_DISPONIBLE=True`

#### 4. Migration Script End-to-End Run

**Test:** `railway run python migrate_ventas.py` in production
**Expected:** Prints "Migration complete" summary with `sheets_count > 0`, `ventas_count > 0`, `detalle_count > 0`; subsequent run shows all rows in `skipped_count` (idempotency)
**Why human:** Requires Railway CLI and production `ventas.xlsx` with real data

---

### Gaps Summary

None. All 8 observable truths verified, all 5 artifacts exist and are substantive (not stubs), all 6 key links wired with real data flow, all 6 VEN-* requirements satisfied. The automated checks are comprehensive — only live-environment integration tests remain as human verification items, which is expected for a DB migration phase.

---

_Verified: 2026-03-26T22:50:00Z_
_Verifier: Claude (gsd-verifier)_
