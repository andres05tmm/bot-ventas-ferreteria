---
phase: 04-proveedores-fiados-compras
verified: 2026-03-26T00:00:00Z
status: passed
score: 13/13 must-haves verified
gaps: []
human_verification:
  - test: "Tab Proveedores en el dashboard muestra facturas y fiados reales"
    expected: "Las tablas de facturas y clientes con fiado se renderizan con datos reales desde Postgres cuando DATABASE_URL está activo"
    why_human: "Requiere browser + base de datos Railway activa; no verificable por grep"
  - test: "Subir foto de factura via la UI actualiza foto_url en Postgres"
    expected: "Después de subir, GET /proveedores/facturas devuelve foto_url no vacío para esa factura"
    why_human: "Depende de Drive activo y DB en Railway; requiere interacción manual"
---

# Phase 04: Proveedores, Fiados y Compras — Verification Report

**Phase Goal:** Migrate proveedores, fiados, and compras data to Postgres with dual-write and Postgres-first reads — while maintaining uptime (all writes non-fatal, no public API changes).
**Verified:** 2026-03-26
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Registrar una factura de proveedor escribe en `facturas_proveedores` de Postgres (además de memoria.json) | VERIFIED | `INSERT INTO facturas_proveedores` at memoria.py:1644, inside `try/if _db.DB_DISPONIBLE/except logger.warning` block after `guardar_memoria()` |
| 2 | Registrar un abono escribe en `facturas_abonos` y actualiza pagado/pendiente/estado en `facturas_proveedores` | VERIFIED | `INSERT INTO facturas_abonos` at memoria.py:1712 and `UPDATE facturas_proveedores` at memoria.py:1717, both inside single non-fatal try block at lines 1707-1724 |
| 3 | Guardar un movimiento de fiado escribe en `fiados` (upsert) y en `fiados_historial` | VERIFIED | query_one SELECT + conditional UPDATE/INSERT at memoria.py:1343-1368; `INSERT INTO fiados_historial` at memoria.py:1362 |
| 4 | Registrar una compra escribe en la tabla `compras` | VERIFIED | `INSERT INTO compras` at memoria.py:988, non-fatal block at lines 983-997 |
| 5 | Si Postgres no está disponible, las cuatro funciones siguen escribiendo en JSON sin error | VERIFIED | All four blocks guarded by `if _db.DB_DISPONIBLE:` and wrapped in `except Exception as e: logger.warning(...)` — JSON path unchanged |
| 6 | `listar_facturas()` devuelve facturas desde `facturas_proveedores JOIN facturas_abonos` con fallback a memoria.json | VERIFIED | `SELECT fp.id, fp.proveedor...` at memoria.py:1744; `LEFT JOIN facturas_abonos fa ON fa.factura_id = fp.id` at line 1758; fallback to `cargar_memoria().get("cuentas_por_pagar", [])` at line 1775 |
| 7 | `cargar_fiados()` devuelve el dict de fiados desde Postgres con fallback a JSON | VERIFIED | `LEFT JOIN fiados_historial fh ON fh.fiado_id = f.id` at memoria.py:1273; fallback `return cargar_memoria().get("fiados", {})` at line 1293 |
| 8 | `GET /compras` devuelve compras desde la tabla `compras` de Postgres con fallback a memoria.json | VERIFIED | `SELECT fecha::text, hora::text, proveedor, producto_nombre...FROM compras` at routers/caja.py:406-408; JSON fallback retained; `"producto": prod` key mapping preserves API shape |
| 9 | Las fotos de facturas siguen subiendo a Drive sin cambios; después del upload se sincroniza `foto_url/foto_nombre` en Postgres | VERIFIED | `UPDATE facturas_proveedores SET foto_url=%s, foto_nombre=%s WHERE id=%s` at proveedores.py:139; `UPDATE facturas_abonos SET foto_url=%s, foto_nombre=%s WHERE id=%s` at proveedores.py:250; both non-fatal |
| 10 | `migrate_proveedores.py` es idempotente y migra `cuentas_por_pagar` con graceful empty | VERIFIED | `ON CONFLICT (id) DO NOTHING` at line 67; `Nada que migrar` at line 47; `sys.exit(1)` on missing DB; syntax valid |
| 11 | `migrate_fiados.py` es idempotente y migra `fiados` con graceful empty | VERIFIED | `SELECT id FROM fiados WHERE nombre = %s` at line 60 (check-before-upsert); `INSERT INTO fiados_historial` present; `Nada que migrar` at line 47; `sys.exit(1)` present; syntax valid |
| 12 | `migrate_compras.py` es idempotente y migra `historial_compras` con graceful empty | VERIFIED | `SELECT id FROM compras WHERE fecha=%s AND producto_nombre=%s...` at lines 68-70; `compra.get("total") or compra.get("costo_total", 0)` at line 64; `Nada que migrar` at line 49; `sys.exit(1)` present; syntax valid |
| 13 | Ninguna firma de función pública cambió | VERIFIED | `listar_facturas(solo_pendientes: bool = False)`, `cargar_fiados() -> dict`, `registrar_factura_proveedor(...)`, `registrar_abono_factura(...)`, `guardar_fiado_movimiento(...)`, `_registrar_historial_compra(...)` — all signatures match plan spec |

**Score:** 13/13 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `memoria.py` | Dual-write Postgres in 4 write functions; Postgres-first reads in listar_facturas() and cargar_fiados() | VERIFIED | `import db as _db` lazy-imported in all 6 blocks; substantive SQL present; functions wired through routers/proveedores.py |
| `routers/caja.py` | GET /compras with Postgres-first + JSON fallback | VERIFIED | Contains `SELECT fecha::text, hora::text, proveedor, producto_nombre` + `FROM compras`; returns `"producto": prod` to preserve API shape |
| `routers/proveedores.py` | Photo upload endpoints with non-fatal Postgres UPDATE | VERIFIED | `UPDATE facturas_proveedores SET foto_url` and `UPDATE facturas_abonos SET foto_url` both present, both non-fatal |
| `migrate_proveedores.py` | Idempotent migration, fail-fast, graceful empty | VERIFIED | `ON CONFLICT (id) DO NOTHING`; `sys.exit(1)`; `Nada que migrar`; syntax valid |
| `migrate_fiados.py` | Idempotent migration, fail-fast, graceful empty | VERIFIED | SELECT-then-branch upsert; `INSERT INTO fiados_historial`; `sys.exit(1)`; `Nada que migrar`; syntax valid |
| `migrate_compras.py` | Idempotent migration, fail-fast, graceful empty, dual-key handling | VERIFIED | Check-before-insert; handles both `"total"` and `"costo_total"`; `sys.exit(1)`; `Nada que migrar`; syntax valid |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `registrar_factura_proveedor()` | `facturas_proveedores` | `_db.execute INSERT ON CONFLICT (id) DO NOTHING` | WIRED | memoria.py:1644-1651 |
| `registrar_abono_factura()` | `facturas_abonos` + `facturas_proveedores` | `_db.execute INSERT + UPDATE` | WIRED | memoria.py:1711-1722 |
| `guardar_fiado_movimiento()` | `fiados` + `fiados_historial` | `query_one SELECT + execute UPDATE/execute_returning INSERT` | WIRED | memoria.py:1343-1368 |
| `_registrar_historial_compra()` | `compras` | `_db.execute INSERT` | WIRED | memoria.py:987-994 |
| `routers/proveedores.py GET /proveedores/facturas` | `facturas_proveedores` | `listar_facturas()` reads from Postgres | WIRED | proveedores.py:46 calls `listar_facturas()`; memoria.py:1744 queries `SELECT fp.id...` |
| `routers/caja.py GET /compras` | `compras` table | `_db.query_all` in router handler | WIRED | caja.py:405-410 |
| `subir_foto_factura` / `subir_foto_abono` | `facturas_proveedores` / `facturas_abonos` | non-fatal UPDATE after guardar_memoria | WIRED | proveedores.py:139, 250 |
| `migrate_proveedores.py` | `facturas_proveedores (id VARCHAR PK)` | INSERT ON CONFLICT DO NOTHING | WIRED | migrate_proveedores.py:67 |
| `migrate_fiados.py` | `fiados` (nombre lookup) + `fiados_historial` | SELECT id FROM fiados WHERE nombre | WIRED | migrate_fiados.py:60 |
| `migrate_compras.py` | `compras` (no unique constraint) | SELECT check on fecha+producto_nombre+cantidad+costo_unitario | WIRED | migrate_compras.py:68 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `listar_facturas()` | `rows` from `facturas_proveedores JOIN facturas_abonos` | `_db.query_all(SELECT fp.id...)` | Yes — DB query with JOIN and json_agg | FLOWING |
| `cargar_fiados()` | `rows` from `fiados JOIN fiados_historial` | `_db.query_all(SELECT f.id...)` | Yes — DB query with LEFT JOIN and saldo reconstruction | FLOWING |
| `GET /compras` | `rows` from `compras` | `_db.query_all(SELECT fecha::text...)` | Yes — DB query with date range filter | FLOWING |
| `subir_foto_factura` Postgres sync | `resultado["url"]` | Drive upload result passed directly to UPDATE | Yes — `UPDATE facturas_proveedores SET foto_url=%s WHERE id=%s` | FLOWING |

---

### Behavioral Spot-Checks

Behavioral spot-checks skipped: all entry points require active Railway PostgreSQL connection (`DATABASE_URL` not set in local environment). The code paths are fully verified at grep/AST level.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PROV-01 | Plan 03 | `memoria.json["cuentas_por_pagar"]` migrado a tablas `facturas_proveedores` + `facturas_abonos` | SATISFIED | `migrate_proveedores.py` exists, idempotent, handles empty source, `ON CONFLICT (id) DO NOTHING` |
| PROV-02 | Plan 03 | `memoria.json["fiados"]` migrado a tablas `fiados` + `fiados_historial` | SATISFIED | `migrate_fiados.py` exists, idempotent, SELECT-then-upsert, `INSERT INTO fiados_historial` |
| PROV-03 | Plan 03 | Compras del Excel migradas a tabla `compras` | SATISFIED | `migrate_compras.py` exists, check-before-insert on 4-column composite key, handles `"total"`/`"costo_total"` dual key |
| PROV-04 | Plans 01, 02 | Routers de proveedores, fiados y compras leen/escriben en Postgres | SATISFIED | All 4 write functions dual-write; `listar_facturas()` and `cargar_fiados()` Postgres-first; GET /compras Postgres-first |
| PROV-05 | Plan 02 | Fotos de facturas siguen en Google Drive sin cambios | SATISFIED | Drive upload code in proveedores.py unchanged; Postgres UPDATE added non-fatally after Drive upload |
| PROV-06 | Plan 02 | Tab Proveedores del dashboard muestra datos desde Postgres | SATISFIED (programmatic) | `routers/proveedores.py` calls `listar_facturas()` which now queries `facturas_proveedores JOIN facturas_abonos`; data path wired end-to-end |

**Orphaned requirements:** None. All 6 requirements for Phase 4 are claimed and verified.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | None found |

No TODOs, FIXMEs, placeholders, empty return stubs, or hardcoded empty values found in any of the 5 modified/created files. All four dual-write blocks and three read blocks use real SQL with proper fallback logic.

---

### Human Verification Required

#### 1. Tab Proveedores renders in browser with live data

**Test:** Open the dashboard in a browser connected to the deployed Railway instance. Navigate to the Proveedores tab.
**Expected:** Facturas table and fiados summary render rows from Postgres (not empty state).
**Why human:** Requires active browser session + Railway DATABASE_URL + live data in tables.

#### 2. Photo upload syncs foto_url to Postgres

**Test:** Upload a photo for an existing factura via the dashboard. Then call `GET /proveedores/facturas` directly.
**Expected:** The factura record in the response shows a non-empty `foto_url` matching the uploaded Drive URL.
**Why human:** Requires Drive credentials + live DB; can only be verified by running the full upload flow.

---

### Gaps Summary

No gaps found. All automated checks passed across all three plans (04-01, 04-02, 04-03).

**Plan 04-01 (write paths):** All four memoria.py write functions contain the required dual-write blocks. Each block: (a) uses lazy `import db as _db`, (b) is guarded by `if _db.DB_DISPONIBLE:`, (c) wrapped in `try/except Exception as e: logger.warning(...)`, (d) placed after `guardar_memoria()` and before `return`. JSON write path and return values are unchanged.

**Plan 04-02 (read paths):** `listar_facturas()` and `cargar_fiados()` both Postgres-first with JSON fallback. `GET /compras` Postgres-first with JSON fallback. Photo URL sync non-fatal in both `subir_foto_factura` and `subir_foto_abono`. `"producto"` key mapped correctly in GET /compras Postgres path.

**Plan 04-03 (migration scripts):** All three scripts exist, pass syntax check, contain idempotency patterns, handle empty sources gracefully (exit 0), and fail fast on missing DATABASE_URL (exit 1).

---

*Verified: 2026-03-26*
*Verifier: Claude (gsd-verifier)*
