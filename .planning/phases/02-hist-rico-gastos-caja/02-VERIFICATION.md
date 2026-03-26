---
phase: 02-hist-rico-gastos-caja
verified: 2026-03-26T20:10:00Z
status: human_needed
score: 4/4 success criteria verified
re_verification: true
  previous_status: gaps_found
  previous_score: 2/4
  gaps_closed:
    - "GET /historico/ventas, /historico/diario, /historico/resumen all read from Postgres first (HIS-01, HIS-02, HIS-03)"
    - "Drive uploads of historico JSON/Excel fully eliminated from routers/historico.py (HIS-04)"
    - "migrate_historico.py created — migrates historico_ventas.json + historico_diario.json to historico_ventas table (HIS-01)"
    - "_sync_historico_hoy() writes enriched daily data to Postgres via _guardar_diario_postgres (HIS-02)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Navigate to Tab Historico in dashboard with DB available"
    expected: "Tab loads historical sales data from Postgres (not from JSON file)"
    why_human: "Requires running frontend + backend with active DB connection; cannot verify Postgres is actually returning rows without live Railway environment"
  - test: "Execute /cerrar command in Telegram bot on Railway"
    expected: "No Drive upload of historico JSON files occurs after daily close"
    why_human: "Requires active Railway deployment, Telegram token, and Drive credentials to observe that the eliminated upload paths are not triggered"
---

# Phase 2: Historico + Gastos + Caja — Verification Report

**Phase Goal:** Los datos operativos del dia (gastos, caja) y el historico de ventas diarias viven en Postgres y el tab Historico del dashboard los muestra desde alli
**Verified:** 2026-03-26T20:10:00Z
**Status:** human_needed (all automated checks pass; 2 items require running deployment to confirm end-to-end behavior)
**Re-verification:** Yes — after gap closure via 02-02-PLAN.md

## Goal Achievement

### Success Criteria from ROADMAP.md

| # | Success Criterion | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | Tab Historico muestra historico de ventas desde Postgres | VERIFIED | _leer_historico() at line 578 reads _leer_historico_postgres() first; historico_diario_get() at line 728 reads _leer_diario_postgres() first; dashboard tab calls /historico/ventas and /historico/diario |
| 2 | Registrar un gasto escribe en tabla gastos de Postgres | VERIFIED (no regression) | memoria.py guardar_gasto() at line 1229 calls _guardar_gasto_postgres(); syntax OK |
| 3 | Abrir y cerrar caja escribe el estado en tabla caja de Postgres | VERIFIED (no regression) | memoria.py guardar_caja() at line 1177 calls _guardar_caja_postgres(); syntax OK |
| 4 | Subidas a Drive de historico JSON ya no ocurren tras cierre diario | VERIFIED | grep for subir_a_drive_urgente in routers/historico.py returns 0 matches; _guardar_historico() comment at line 634 confirms elimination; _sync_historico_hoy() comment at line 208 confirms elimination |

**Score:** 4/4 success criteria verified

---

### Observable Truths (02-01 plan — all verified, regression checks pass)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Registrar un gasto desde el dashboard escribe en la tabla gastos de Postgres | VERIFIED | _guardar_gasto_postgres at memoria.py:1066; called from guardar_gasto at line 1229; syntax OK |
| 2 | GET /caja devuelve estado de caja leyendo desde Postgres cuando DB disponible | VERIFIED | query_one at routers/caja.py:39; JSON fallback preserved |
| 3 | GET /gastos devuelve gastos del periodo leyendo desde Postgres cuando DB disponible | VERIFIED | query_all pattern in routers/caja.py; JSON fallback preserved |
| 4 | Abrir caja desde dashboard escribe en tabla caja de Postgres | VERIFIED | _guardar_caja_postgres at memoria.py:1084; called from guardar_caja at line 1177 |
| 5 | Cerrar caja desde dashboard escribe en tabla caja de Postgres | VERIFIED | same path as above |
| 6 | Gastos historicos de memoria.json migrados a tabla gastos | VERIFIED | migrate_gastos_caja.py INSERT INTO gastos confirmed; syntax OK |
| 7 | Estado de caja de memoria.json migrado a tabla caja | VERIFIED | migrate_gastos_caja.py UPSERT of caja_actual confirmed |
| 8 | Si Postgres falla, todo sigue funcionando con JSON fallback | VERIFIED | all helpers non-fatal; routers fall back to open(config.MEMORIA_FILE) |

### Observable Truths (02-02 plan — gap closure)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /historico/ventas returns data from Postgres historico_ventas table when DB available | VERIFIED | _leer_historico() line 584 calls _leer_historico_postgres(); query_all("SELECT fecha, ventas FROM historico_ventas ORDER BY fecha") at line 241 |
| 2 | GET /historico/diario returns enriched daily data from Postgres historico_ventas table when DB available | VERIFIED | historico_diario_get() line 736 calls _leer_diario_postgres(); query_all with SELECT * FROM historico_ventas at lines 256-265 |
| 3 | GET /historico/resumen returns monthly summaries from Postgres when DB available | VERIFIED | historico_resumen() line 712 calls _leer_historico() which reads Postgres first; inherits Postgres-first path |
| 4 | _sync_historico_hoy() writes daily close to Postgres historico_ventas table | VERIFIED | _guardar_diario_postgres called at lines 199-207; INSERT INTO historico_ventas via _guardar_diario_postgres at line 302 |
| 5 | _guardar_historico() dual-writes to Postgres and JSON (no Drive upload of historico JSON) | VERIFIED | _guardar_historico_postgres called at line 624; comment at line 634 confirms Drive eliminated; 0 subir_a_drive_urgente calls remain |
| 6 | Drive upload of historico_ventas.json, historico_diario.json, historico_ventas.xlsx eliminated from _guardar_historico and _sync_historico_hoy | VERIFIED | grep subir_a_drive_urgente in routers/historico.py = 0 results; grep subir_a_drive in routers/historico.py = 0 results |
| 7 | migrate_historico.py migrates both historico_ventas.json and historico_diario.json into historico_ventas table | VERIFIED | File exists at repo root; syntax OK; contains INSERT INTO historico_ventas, ON CONFLICT (fecha) DO UPDATE, reads both JSON files, summary print with count_insert/count_update |
| 8 | If Postgres fails, all historico endpoints fall back to JSON/Drive path | VERIFIED | _leer_historico_postgres returns {} on exception; _leer_historico falls through to Excel/JSON/Drive at lines 589-614; _guardar_historico_postgres has try/except with logger.warning at line 300 |

**Score:** 16/16 plan truths verified (8 from 02-01, 8 from 02-02)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `memoria.py` | Postgres dual-write for gastos and caja | VERIFIED | _guardar_gasto_postgres (line 1066), _guardar_caja_postgres (line 1084); syntax OK (regression) |
| `memoria.py` | Postgres read for caja | VERIFIED | _leer_caja_postgres (line 1112); called from cargar_caja() at line 1163 (regression) |
| `routers/caja.py` | Postgres-first reads for /caja and /gastos | VERIFIED | db.query_one at line 39; JSON fallback at lines 103-105 (regression) |
| `migrate_gastos_caja.py` | One-time migration script for gastos and caja | VERIFIED | 114 lines; syntax OK (regression) |
| `routers/historico.py` | 4 Postgres helpers + Postgres-first reads + Drive upload elimination | VERIFIED | _leer_historico_postgres (235), _leer_diario_postgres (248), _guardar_historico_postgres (283), _guardar_diario_postgres (302); all wired; 0 Drive uploads; syntax OK |
| `migrate_historico.py` | One-time migration for historico_ventas.json + historico_diario.json | VERIFIED | Exists at repo root; syntax OK; INSERT INTO historico_ventas; ON CONFLICT (fecha) DO UPDATE; reads both JSON sources; summary prints |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| memoria.py:guardar_gasto | db.execute | _guardar_gasto_postgres | WIRED | Line 1074: _db.execute INSERT INTO gastos (regression) |
| memoria.py:guardar_caja | db.execute | _guardar_caja_postgres | WIRED | Line 1093: _db.execute INSERT INTO caja ON CONFLICT (regression) |
| routers/caja.py:caja() | db.query_one | direct Postgres read | WIRED | Line 39: query_one SELECT * FROM caja WHERE fecha (regression) |
| routers/caja.py:gastos() | db.query_all | direct Postgres read | WIRED | query_all SELECT FROM gastos WHERE fecha (regression) |
| routers/historico.py:_leer_historico | db.query_all | _leer_historico_postgres | WIRED | Line 584 calls _leer_historico_postgres(); line 241 runs SELECT fecha, ventas FROM historico_ventas |
| routers/historico.py:_guardar_historico | db.execute | _guardar_historico_postgres | WIRED | Line 624 calls _guardar_historico_postgres(); line 291 runs INSERT INTO historico_ventas ON CONFLICT |
| routers/historico.py:_sync_historico_hoy | db.execute | _guardar_diario_postgres | WIRED | Lines 199-207 call _guardar_diario_postgres(); line 302 has INSERT INTO historico_ventas ON CONFLICT |
| routers/historico.py:historico_diario_get | db.query_all | _leer_diario_postgres | WIRED | Line 736 calls _leer_diario_postgres(); queries SELECT * FROM historico_ventas |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| routers/caja.py GET /caja | caja_row | query_one("SELECT * FROM caja WHERE fecha = %s") | Yes — parametric SQL | FLOWING (regression) |
| routers/caja.py GET /gastos | rows | query_all("SELECT...FROM gastos WHERE fecha >= %s") | Yes — parametric SQL with date range | FLOWING (regression) |
| routers/historico.py GET /historico/ventas | data | _leer_historico_postgres -> query_all("SELECT fecha, ventas FROM historico_ventas ORDER BY fecha") | Yes — parametric SQL, returns all rows | FLOWING |
| routers/historico.py GET /historico/diario | pg_diario | _leer_diario_postgres -> query_all("SELECT * FROM historico_ventas ...") | Yes — parametric SQL | FLOWING |
| routers/historico.py GET /historico/resumen | data | _leer_historico() -> _leer_historico_postgres() | Yes — inherits Postgres-first path | FLOWING |
| dashboard/src/tabs/TabHistoricoVentas.jsx | fetch result | /historico/ventas and /historico/diario endpoints | Endpoints now serve Postgres data | FLOWING (endpoint-level) |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| memoria.py syntax valid | python -c "import ast; ast.parse(open('memoria.py', encoding='utf-8').read())" | syntax OK | PASS |
| routers/caja.py syntax valid | python -c "import ast; ast.parse(open('routers/caja.py', encoding='utf-8').read())" | syntax OK | PASS |
| migrate_gastos_caja.py syntax valid | python -c "import ast; ast.parse(open('migrate_gastos_caja.py', encoding='utf-8').read())" | syntax OK | PASS |
| routers/historico.py syntax valid | python -c "import ast; ast.parse(open('routers/historico.py', encoding='utf-8').read())" | syntax OK | PASS |
| migrate_historico.py syntax valid | python -c "import ast; ast.parse(open('migrate_historico.py', encoding='utf-8').read())" | syntax OK | PASS |
| migrate_historico.py has UPSERT patterns | grep -c "INSERT INTO historico_ventas\|ON CONFLICT.*fecha.*DO UPDATE" migrate_historico.py | 2 matches | PASS |
| Zero Drive upload calls in historico.py | grep -c "subir_a_drive_urgente" routers/historico.py | 0 | PASS |
| Zero subir_a_drive calls in historico.py | grep "subir_a_drive" routers/historico.py | no output | PASS |
| Gap-closure commits in git | git log --oneline 0dc0a02 8f0d9cd | Both commits found | PASS |
| All 4 Postgres helpers defined in historico.py | grep -n "_leer_historico_postgres\|_leer_diario_postgres\|_guardar_historico_postgres\|_guardar_diario_postgres" routers/historico.py | Lines 235, 248, 283, 302 | PASS |
| All 4 helpers are called (wired) | same grep for call sites | Lines 199, 584, 624, 736, 836, 951 | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| GAS-01 | 02-01-PLAN | Gastos de memoria.json["gastos"] migrados a tabla gastos | SATISFIED | migrate_gastos_caja.py iterates all gastos entries with deduplication |
| GAS-02 | 02-01-PLAN | Nuevo registro de gastos escribe en Postgres | SATISFIED | guardar_gasto() dual-writes via _guardar_gasto_postgres() |
| CAJ-01 | 02-01-PLAN | Estado de caja de memoria.json["caja_actual"] migrado a tabla caja | SATISFIED | migrate_gastos_caja.py UPSERT of caja_actual |
| CAJ-02 | 02-01-PLAN | Apertura/cierre de caja escribe en Postgres | SATISFIED | guardar_caja() dual-writes via _guardar_caja_postgres() |
| HIS-01 | 02-02-PLAN | Script migra historico_ventas.json + historico_diario.json a tabla historico_ventas | SATISFIED | migrate_historico.py exists, syntax OK, reads both JSON files, UPSERTs to historico_ventas with ON CONFLICT (fecha) DO UPDATE |
| HIS-02 | 02-02-PLAN | _sync_historico_hoy() escribe el cierre diario en Postgres | SATISFIED | _guardar_diario_postgres called at lines 199-207 inside _sync_historico_hoy; INSERT INTO historico_ventas with all enriched fields |
| HIS-03 | 02-02-PLAN | Tab Historico del dashboard muestra datos desde Postgres | SATISFIED (programmatic) | _leer_historico() and historico_diario_get() both read Postgres first; dashboard tab calls these endpoints; end-to-end behavior needs human verification |
| HIS-04 | 02-02-PLAN | Subidas a Drive de archivos JSON de historico eliminadas | SATISFIED | 0 subir_a_drive_urgente calls in routers/historico.py; all eliminated paths marked with HIS-04 comments |

**REQUIREMENTS.md status:** All 8 requirements marked [x] Complete (lines 29-36) and all 8 tracked as "Complete" in the requirements table (lines 104-111).

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | - | - | - | - |

Scan covered: routers/historico.py (full, modified), migrate_historico.py (full, new), memoria.py (lines 1060-1232), routers/caja.py (full), migrate_gastos_caja.py (full). No TODO/FIXME, no empty returns, no placeholder text detected in phase-modified code.

---

## Human Verification Required

### 1. Tab Historico loads from Postgres

**Test:** With DATABASE_URL set and rows in historico_ventas table, open the dashboard Tab Historico (navigate to the Historico tab in the React dashboard).
**Expected:** Historical daily sales data appears, sourced from Postgres. Confirm by checking that data matches what was inserted via migrate_historico.py, not just what is in the local historico_ventas.json file.
**Why human:** Requires active Railway deployment with live DATABASE_URL. The programmatic check confirms the code path reaches Postgres, but cannot confirm rows are actually returned without a live DB connection.

### 2. Daily close does not upload historico JSON to Drive

**Test:** Execute /cerrar command in a Telegram conversation with the deployed bot.
**Expected:** The bot closes the day and no historico JSON file (historico_ventas.json, historico_diario.json, historico_ventas.xlsx) is uploaded to Google Drive. Check Drive folder after command completes.
**Why human:** Requires Railway deployment, Telegram token, and Drive credentials to observe upload behavior. Code-level verification confirms the upload calls are absent, but Drive upload absence must be confirmed in a real deployment.

---

## Gaps Summary

No automated gaps remain. All 8 requirements are implemented and verified at the code level.

The phase is complete pending human confirmation of two end-to-end behaviors (Postgres data appearing in the dashboard tab, and Drive uploads confirmed absent in production). These human checks cannot be automated without a live deployment environment.

**Re-verification results:**
- Previous score: 2/4 success criteria (gaps_found)
- Current score: 4/4 success criteria (human_needed)
- Gaps closed: HIS-01, HIS-02, HIS-03, HIS-04 — all implemented by 02-02 execution (commits 0dc0a02, 8f0d9cd)
- Regressions: None — GAS-01, GAS-02, CAJ-01, CAJ-02 artifacts all pass regression checks

---

_Verified: 2026-03-26T20:10:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification: Yes (previous status: gaps_found, previous score: 2/4)_
