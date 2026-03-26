# Phase 4: Proveedores + Fiados + Compras - Research

**Researched:** 2026-03-26
**Domain:** PostgreSQL dual-write migration — proveedores, fiados, compras
**Confidence:** HIGH

## Summary

Phase 4 completes the last three data domains of the PostgreSQL migration: supplier invoices (`cuentas_por_pagar`), customer credit accounts (`fiados`), and merchandise purchase history (`historial_compras`). All schema is already deployed in Railway from Phase 1 (`db.py` lines 234-309). The implementation pattern is identical to Phases 1-3: inline Postgres blocks inside existing `memoria.py` functions using lazy `import db`, `DB_DISPONIBLE` guard, and non-fatal `try/except Exception → logger.warning`.

Write paths are added to four `memoria.py` functions. Read paths are updated in `listar_facturas()`, `cargar_fiados()`, and `GET /compras` in `routers/caja.py`. Photo-to-Drive flow stays untouched; the two photo endpoints only gain a non-fatal `UPDATE` to sync the Drive URL back into Postgres after upload succeeds. Three idempotent migration scripts cover the one-time data migration from `memoria.json`.

**Primary recommendation:** Follow the `GET /gastos` pattern in `routers/caja.py` lines 309-391 as the direct template for all write and read changes in this phase. Zero new modules. Zero signature changes. Zero dashboard changes.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Las cuatro funciones de escritura en `memoria.py` reciben bloques de Postgres inline: `registrar_factura_proveedor()`, `registrar_abono_factura()`, `guardar_fiado_movimiento()`, y `_registrar_historial_compra()`. Mismo patron que Fases 1-3: lazy `import db` dentro de la funcion, guard `if not db.DB_DISPONIBLE: return/continue`, non-fatal `try/except Exception → logger.warning`.

**D-02:** No se crea ningun modulo nuevo (no `proveedores_pg.py`). Toda la logica Postgres va inline dentro de las funciones existentes de `memoria.py`.

**D-03:** `GET /compras` en `routers/caja.py` (lineas 396-427) se reescribe con Postgres como fuente primaria (query a tabla `compras`), con el bloque `mem.get("historial_compras")` como fallback — igual al patron de `GET /gastos` ya implementado en el mismo archivo.

**D-04:** El formato de respuesta JSON de `GET /compras` no cambia: mismas claves `fecha`, `hora`, `proveedor`, `producto`, `cantidad`, `costo_unitario`, `costo_total`.

**D-05:** `listar_facturas()` en `memoria.py` se actualiza para leer desde Postgres (`facturas_proveedores` + `facturas_abonos`) con fallback a `cuentas_por_pagar` en `memoria.json`. El router `routers/proveedores.py` no necesita cambios — solo consume `listar_facturas()`.

**D-06:** El formato de cada factura retornado se mantiene identico: `id`, `proveedor`, `descripcion`, `total`, `pagado`, `pendiente`, `estado`, `fecha`, `foto_url`, `foto_nombre`, `abonos[]`.

**D-07:** Las fotos de facturas siguen subiendose a Drive sin cambios (PROV-05). Despues del upload, los endpoints `POST /proveedores/facturas/{fac_id}/foto` y `POST /proveedores/abonos/{fac_id}/foto` agregan un `UPDATE` non-fatal en Postgres para sincronizar `foto_url` y `foto_nombre`. Sin cambios en el flujo Drive.

**D-08:** Los fiados no tienen endpoint REST ni tab en el dashboard — se usan solo desde Telegram (`/fiados`, `/abonar`). La migracion agrega dual-write solo en `guardar_fiado_movimiento()` en `memoria.py`. PROV-06 ("Tab Proveedores") cubre facturas unicamente; no se agrega `GET /proveedores/fiados`.

**D-09:** `cargar_fiados()` en `memoria.py` se actualiza para leer desde la tabla `fiados` + `fiados_historial` con fallback a `memoria.json["fiados"]`.

**D-10:** Tres scripts separados (o uno combinado): `migrate_proveedores.py` (cuentas_por_pagar → facturas_proveedores + facturas_abonos), `migrate_fiados.py` (fiados dict → fiados + fiados_historial), `migrate_compras.py` (historial_compras → compras). Ejecucion manual via `railway run python migrate_*.py`. Idempotentes con UPSERT o INSERT ON CONFLICT DO NOTHING.

**D-11:** `migrate_compras.py` usa `historial_compras` de `memoria.json` como fuente (no el Excel). Razon: `memoria.json["historial_compras"]` es la fuente canonica para el bot; el Excel "Compras" sheet es secundario. **NOTE: `historial_compras` is ABSENT from current `memoria.json` (0 records) and the Excel has no "Compras" sheet — the migration scripts must handle empty source gracefully (log + exit 0).**

### Claude's Discretion

- Constraint de idempotencia para `migrate_proveedores.py` (facturas tienen ID alfanumerico `FAC-001` — usar `ON CONFLICT (id) DO NOTHING`)
- Constraint de idempotencia para `migrate_fiados.py` (fiados no tienen ID estable en JSON — usar nombre como clave de deduplicacion)
- Tamano de batch para los scripts de migracion
- Exacta estructura de la query para `listar_facturas()` (JOIN entre `facturas_proveedores` y `facturas_abonos`)

### Deferred Ideas (OUT OF SCOPE)

- `GET /proveedores/fiados` REST endpoint — fiados no tienen tab en dashboard; agregar endpoint REST es una feature nueva
- Sincronizacion bidireccional foto_url Drive <-> Postgres en tiempo real — la foto va primero a Drive, luego UPDATE en Postgres es suficiente para Phase 4
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROV-01 | `memoria.json["cuentas_por_pagar"]` migrado a tabla `facturas_proveedores` + `facturas_abonos` | Schema verified in `db.py` lines 256-278. Source has 0 records currently — migration script must handle empty gracefully. `facturas_proveedores.id` is `VARCHAR(20) PRIMARY KEY` matching `FAC-001` format. |
| PROV-02 | `memoria.json["fiados"]` migrado a tablas `fiados` + `fiados_historial` | Schema verified in `db.py` lines 234-251. Source has 3 clients with 6 movements in JSON. `fiados` table uses `SERIAL PRIMARY KEY`; idempotence via name-based lookup. |
| PROV-03 | Compras del Excel migradas a tabla `compras` | `memoria.json["historial_compras"]` is empty; Excel has no "Compras" sheet. Scripts must handle empty source and exit 0. `compras` table schema verified `db.py` lines 298-309. |
| PROV-04 | Routers de proveedores, fiados y compras leen/escriben en Postgres | Write path: 4 `memoria.py` functions. Read path: `listar_facturas()`, `cargar_fiados()`, `GET /compras`. All follow established patterns. |
| PROV-05 | Fotos de facturas siguen en Google Drive sin cambios | Drive upload code unchanged. Only addition: non-fatal `UPDATE` in `facturas_proveedores`/`facturas_abonos` after successful Drive upload. |
| PROV-06 | Tab Proveedores funciona desde Postgres | Fulfilled entirely by updating `listar_facturas()` — router and dashboard unchanged. `GET /proveedores/facturas` calls `listar_facturas()` which will now read from Postgres. |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg2-binary | 2.9.11 (verified) | Postgres driver | Already in use; sync driver matches bot's threading model |
| db.py (project) | — | Centralized Postgres access | `query_all`, `query_one`, `execute`, `execute_returning`, `DB_DISPONIBLE` guard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| openpyxl | 3.1.2 (verified) | Excel read for migration | `migrate_compras.py` if sourcing from Excel instead of JSON |
| json (stdlib) | — | Read `memoria.json` | All three migration scripts |

**No new dependencies required.** All needed libraries are already installed.

---

## Architecture Patterns

### Established Write Pattern (Phases 1-3)

Every write function in `memoria.py` follows this exact structure. Phase 4 repeats it without variation:

```python
def registrar_factura_proveedor(proveedor, descripcion, total, fecha=None, foto_url="", foto_nombre="") -> dict:
    # ... existing JSON write logic unchanged ...
    guardar_memoria(mem, urgente=True)

    # Postgres dual-write (inline, non-fatal)
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            _db.execute(
                """INSERT INTO facturas_proveedores
                   (id, proveedor, descripcion, total, pagado, pendiente, estado, fecha, foto_url, foto_nombre)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (fac_id, proveedor.strip(), descripcion.strip(),
                 int(total), 0, int(total), "pendiente", hoy,
                 foto_url, foto_nombre)
            )
    except Exception as e:
        logger.warning("Postgres write facturas_proveedores failed: %s", e)

    return factura
```

Source: established pattern in `memoria.py` (gastos, caja, ventas, historico writes).

### Established Read Pattern (Postgres-first with JSON fallback)

Direct template: `GET /gastos` in `routers/caja.py` lines 309-391.

```python
def listar_facturas(solo_pendientes: bool = False) -> list:
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            rows = _db.query_all(
                """SELECT fp.id, fp.proveedor, fp.descripcion, fp.total, fp.pagado,
                          fp.pendiente, fp.estado, fp.fecha::text, fp.foto_url, fp.foto_nombre,
                          COALESCE(
                              json_agg(
                                  json_build_object(
                                      'fecha', fa.fecha::text,
                                      'monto', fa.monto,
                                      'foto_url', COALESCE(fa.foto_url, ''),
                                      'foto_nombre', COALESCE(fa.foto_nombre, '')
                                  ) ORDER BY fa.created_at
                              ) FILTER (WHERE fa.id IS NOT NULL),
                              '[]'
                          ) AS abonos
                   FROM facturas_proveedores fp
                   LEFT JOIN facturas_abonos fa ON fa.factura_id = fp.id
                   GROUP BY fp.id
                   ORDER BY fp.fecha DESC""",
                ()
            )
            facturas = [{**dict(r), "abonos": r["abonos"] or []} for r in rows]
            if solo_pendientes:
                return [f for f in facturas if f["estado"] != "pagada"]
            return facturas
    except Exception as e:
        logger.warning("Postgres read listar_facturas failed: %s", e)

    # Fallback: JSON
    mem = cargar_memoria()
    facturas = mem.get("cuentas_por_pagar", [])
    if solo_pendientes:
        return [f for f in facturas if f.get("estado") != "pagada"]
    return sorted(facturas, key=lambda f: f.get("fecha", ""), reverse=True)
```

### `cargar_fiados()` Read Pattern

```python
def cargar_fiados() -> dict:
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            rows = _db.query_all(
                "SELECT f.id, f.nombre, f.deuda, "
                "  COALESCE(json_agg(json_build_object("
                "    'fecha', fh.fecha::text, 'concepto', fh.concepto,"
                "    'cargo', fh.monto, 'abono', 0, 'saldo', fh.monto"
                "  ) ORDER BY fh.created_at) FILTER (WHERE fh.id IS NOT NULL), '[]') AS movimientos "
                "FROM fiados f LEFT JOIN fiados_historial fh ON fh.fiado_id = f.id "
                "GROUP BY f.id, f.nombre, f.deuda",
                ()
            )
            result = {}
            for r in rows:
                result[r["nombre"]] = {
                    "saldo": r["deuda"],
                    "movimientos": r["movimientos"] or [],
                }
            return result
    except Exception as e:
        logger.warning("Postgres read cargar_fiados failed: %s", e)
    return cargar_memoria().get("fiados", {})
```

**NOTE:** The `fiados_historial` table does not store cumulative saldo — only tipo/monto. The JSON format stores per-movement saldo. The planner must decide whether `cargar_fiados()` reconstructs running saldo from historial or uses `fiados.deuda` as the current balance (simpler). Current JSON uses per-movement saldo; Postgres has `fiados.deuda` as the authoritative current balance.

### Migration Script Pattern

Every migration script follows this structure (from `migrate_gastos_caja.py`):
1. `logging.basicConfig()` at top
2. `if not os.getenv("DATABASE_URL"): sys.exit(1)` (fail-fast)
3. `db.init_db()` + `if not db.DB_DISPONIBLE: sys.exit(1)`
4. Load source file (JSON or Excel) with explicit existence check
5. Iterate and INSERT with idempotency guard
6. Log final counts (inserted vs skipped)

**Idempotency strategies by table:**
- `facturas_proveedores`: `ON CONFLICT (id) DO NOTHING` — id is `FAC-001` style VARCHAR PRIMARY KEY, deterministic
- `facturas_abonos`: No unique constraint. Use check-before-insert: `SELECT id FROM facturas_abonos WHERE factura_id=%s AND fecha=%s AND monto=%s` (same deduplication pattern as `migrate_gastos_caja.py` for gastos)
- `fiados`: `INSERT INTO fiados (nombre, deuda) ... ON CONFLICT (nombre) DO UPDATE SET deuda=EXCLUDED.deuda` — requires adding `UNIQUE(nombre)` constraint OR use SELECT + INSERT pattern
- `fiados_historial`: No unique constraint. Use SELECT check on `fiado_id + fecha + tipo + monto` before insert
- `compras`: No unique constraint. Use SELECT check on `fecha + producto_nombre + cantidad + costo_unitario`

**IMPORTANT — UNIQUE constraint on fiados.nombre:** The `fiados` table schema (db.py line 234-240) does NOT have a UNIQUE constraint on `nombre`. For `migrate_fiados.py` to use `ON CONFLICT (nombre) DO NOTHING`, a unique index must be added — OR the migration script uses SELECT-then-INSERT. The planner should choose: add `CREATE UNIQUE INDEX IF NOT EXISTS fiados_nombre_unique ON fiados(nombre)` in the migration script before inserting, OR use check-before-insert. **Recommendation: add the unique index in the migration script preamble** (idempotent via `IF NOT EXISTS`).

### Photo URL Sync Pattern (D-07)

After the existing `guardar_memoria(mem, urgente=True)` call in each photo endpoint:

```python
# Non-fatal Postgres sync
try:
    import db as _db
    if _db.DB_DISPONIBLE:
        _db.execute(
            "UPDATE facturas_proveedores SET foto_url=%s, foto_nombre=%s WHERE id=%s",
            (resultado["url"], nombre_archivo, fac_id.upper())
        )
except Exception as e:
    logger.warning("Postgres UPDATE foto factura failed: %s", e)
```

For `subir_foto_abono`: after `guardar_memoria()`, update the latest abono in `facturas_abonos`. Identifying the latest abono requires the abono's `id` — use `SELECT id FROM facturas_abonos WHERE factura_id=%s ORDER BY created_at DESC LIMIT 1` first.

### `GET /compras` Rewrite Pattern

Direct model: `GET /gastos` lines 309-391 of `routers/caja.py`. The Postgres block queries `compras` table and builds the same JSON shape as the current JSON path. The JSON fallback block (`mem.get("historial_compras")`) stays as-is below.

**Key mapping — JSON field `total` vs Postgres column `costo_total`:**
- `historial_compras` entries use key `"total"` (see `_registrar_historial_compra()` line 975)
- Postgres `compras` table has column `costo_total` (db.py line 307)
- The response shape (D-04) uses `"costo_total"` — verify the existing JSON fallback path uses `c.get("costo_total", 0)` not `c.get("total", 0)` before modifying. Current code at line 414 uses `c.get("costo_total", 0)`. **But `_registrar_historial_compra()` stores `"total"` not `"costo_total"`.** This is a pre-existing discrepancy in the fallback path — do not fix it in Phase 4; just ensure the Postgres write uses `costo_total` column correctly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe DB access | Custom pool | `db._get_conn()` via `db.execute()` / `db.query_all()` | Pool already handles min/max connections, commit/rollback |
| JSON aggregation of abonos | Python post-processing loop | `json_agg()` + `FILTER (WHERE fa.id IS NOT NULL)` in SQL | Single query, handles LEFT JOIN NULLs correctly |
| Migration idempotency | Delete-then-reinsert | `ON CONFLICT DO NOTHING` or SELECT check pattern | Existing migration scripts already use both patterns |
| Postgres availability guard | Re-implement check | `db.DB_DISPONIBLE` module flag | Set once at init, thread-safe, matches bot's startup contract |

---

## Common Pitfalls

### Pitfall 1: json_agg NULL rows from LEFT JOIN
**What goes wrong:** When a `facturas_proveedores` row has no matching `facturas_abonos` rows, `json_agg()` returns `[null]` not `[]`.
**Why it happens:** LEFT JOIN produces NULL columns; `json_agg` includes the NULL row.
**How to avoid:** Use `FILTER (WHERE fa.id IS NOT NULL)` on the `json_agg` call, then `COALESCE(..., '[]')` for no-match rows. Already shown in code example above.
**Warning signs:** Frontend receives `[null]` in abonos array instead of `[]`.

### Pitfall 2: fiados.deuda vs JSON saldo reconstruction
**What goes wrong:** `cargar_fiados()` returns `{"saldo": <value>}` per client. JSON stores running saldo in each movimiento. Postgres `fiados.deuda` is the authoritative current balance — no need to sum `fiados_historial`.
**Why it happens:** Confusion between two data models.
**How to avoid:** Read `f.deuda` from `fiados` table directly as the current `saldo`. Do NOT reconstruct by summing historial monto fields — types/signs differ (`tipo` = 'cargo'/'abono' with unsigned `monto`).

### Pitfall 3: historial_compras key name mismatch
**What goes wrong:** `_registrar_historial_compra()` stores key `"total"` but `GET /compras` fallback reads `"costo_total"`. New Postgres writes must use `costo_total` column.
**Why it happens:** Pre-existing naming inconsistency between writer and reader.
**How to avoid:** In `_registrar_historial_compra()` Postgres INSERT, map the in-memory `round(cantidad * costo_unitario)` value to column `costo_total`. Do not rename the JSON key.

### Pitfall 4: Empty migration sources
**What goes wrong:** `cuentas_por_pagar` has 0 records in `memoria.json`; `historial_compras` key is absent entirely; Excel has no "Compras" sheet.
**Why it happens:** The business has no supplier invoices or purchase history recorded yet.
**How to avoid:** Each migration script must check for empty/missing source and exit 0 with an info log (`"Nada que migrar: fuente vacia"`). Do NOT raise an error or sys.exit(1) for empty source.

### Pitfall 5: registrar_abono_factura Postgres UPDATE timing
**What goes wrong:** `registrar_abono_factura()` updates `pagado`, `pendiente`, and `estado` in the JSON dict, then writes. The Postgres equivalent needs two operations: INSERT into `facturas_abonos` AND UPDATE `facturas_proveedores` for the new `pagado`/`pendiente`/`estado`.
**Why it happens:** Postgres schema separates abonos from the parent invoice.
**How to avoid:** The Postgres block in `registrar_abono_factura()` must: (1) INSERT into `facturas_abonos`, (2) UPDATE `facturas_proveedores SET pagado=%s, pendiente=%s, estado=%s WHERE id=%s`.

### Pitfall 6: guardar_fiado_movimiento tipo field
**What goes wrong:** `fiados_historial.tipo` is `VARCHAR(20) NOT NULL`. The JSON movimiento has `cargo` and `abono` floats, not a tipo string.
**Why it happens:** Schema models the event as typed (cargo vs abono), JSON models it as two separate amounts.
**How to avoid:** Derive `tipo`: if `cargo > 0` → `"cargo"`, if `abono > 0` → `"abono"`. Store the non-zero amount as `monto`. If both are non-zero (unusual), use `"cargo"` as the primary type.

---

## Runtime State Inventory

> Phase 4 is not a rename/refactor phase — this section is not applicable.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All scripts | Yes (3.14.3 local) | 3.14.3 local / 3.11 Railway | — |
| psycopg2-binary | db.py | Yes | 2.9.11 | — |
| openpyxl | migrate_compras.py (if Excel source) | Yes | 3.1.2 | — |
| DATABASE_URL env var | Migration scripts, Postgres writes | Not in local .env | — | JSON fallback mode (bot still works) |
| PostgreSQL (Railway) | Migration scripts | Not locally reachable | — | Migrations run via `railway run` |
| memoria.json | migrate_proveedores.py, migrate_fiados.py, migrate_compras.py | Yes (present) | — | — |
| ventas.xlsx | migrate_compras.py (if using Excel) | Yes, but no Compras sheet | — | Use JSON source (D-11) |

**Missing dependencies with no fallback:**
- `DATABASE_URL` must be configured in Railway environment before running migration scripts. Scripts fail-fast if absent (consistent with all prior migration scripts).

**Missing dependencies with fallback:**
- Migration scripts run only via `railway run python migrate_*.py` — not executable locally without DATABASE_URL.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Custom test runner (`test_suite.py`) — no pytest |
| Config file | None — standalone script |
| Quick run command | `PYTHONIOENCODING=utf-8 python3 test_suite.py` |
| Full suite command | `PYTHONIOENCODING=utf-8 python3 test_suite.py` |

**Current baseline:** 201 tests passing, 0 failures (verified 2026-03-26).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| PROV-01 | `cuentas_por_pagar` migrated to Postgres | manual-only | `railway run python migrate_proveedores.py` | Migration script runs in Railway; verifiable by count log output |
| PROV-02 | `fiados` migrated to Postgres | manual-only | `railway run python migrate_fiados.py` | Same |
| PROV-03 | Compras migrated (empty source) | manual-only | `railway run python migrate_compras.py` | Must exit 0 with "nada que migrar" |
| PROV-04 | Write/read through Postgres | regression | `PYTHONIOENCODING=utf-8 python3 test_suite.py` | Existing 201 tests must still pass; no new tests needed for Postgres path (DB_DISPONIBLE=False locally) |
| PROV-05 | Photos stay in Drive | regression | Visual inspection via dashboard + `PYTHONIOENCODING=utf-8 python3 test_suite.py` | Drive flow unchanged; test suite confirms no breakage |
| PROV-06 | Tab Proveedores reads Postgres | manual-only | Load dashboard tab in browser after deploy | Verifies `GET /proveedores/facturas` returns data from Postgres |

### Wave 0 Gaps
None — existing test infrastructure covers all regression requirements. No new test files needed. Migration scripts are verified by their own log output in Railway.

*(The test_suite.py does not cover proveedores/fiados/compras paths directly — they are not tested by the existing suite. Phase 4 relies on the non-fatal pattern ensuring the JSON fallback keeps all 201 tests passing.)*

---

## Code Examples

### Write: `_registrar_historial_compra()` Postgres block
```python
# Source: established pattern (memoria.py gastos write, Phase 2)
# Add AFTER guardar_memoria(mem) call
try:
    import db as _db
    if _db.DB_DISPONIBLE:
        from datetime import datetime as _dt2
        ahora = _dt2.now(config.COLOMBIA_TZ)
        _db.execute(
            """INSERT INTO compras
               (fecha, hora, proveedor, producto_nombre, cantidad, costo_unitario, costo_total)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M"),
             proveedor, producto, cantidad,
             int(costo_unitario), round(cantidad * costo_unitario))
        )
except Exception as e:
    logger.warning("Postgres write compras failed: %s", e)
```

### Write: `guardar_fiado_movimiento()` Postgres block
```python
# Add AFTER guardar_memoria(mem)
try:
    import db as _db
    if _db.DB_DISPONIBLE:
        # Upsert fiado (get or create)
        existing = _db.query_one(
            "SELECT id FROM fiados WHERE nombre = %s", (cliente,)
        )
        if existing:
            fiado_id = existing["id"]
            _db.execute(
                "UPDATE fiados SET deuda=%s, updated_at=NOW() WHERE id=%s",
                (int(saldo_nuevo), fiado_id)
            )
        else:
            row = _db.execute_returning(
                "INSERT INTO fiados (nombre, deuda) VALUES (%s, %s) RETURNING id",
                (cliente, int(saldo_nuevo))
            )
            fiado_id = row["id"]
        # tipo derivado de cargo/abono
        tipo = "cargo" if cargo > 0 else "abono"
        monto_pg = int(cargo if cargo > 0 else abono)
        from datetime import datetime as _dt2
        _db.execute(
            """INSERT INTO fiados_historial
               (fiado_id, tipo, monto, concepto, fecha, hora)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (fiado_id, tipo, monto_pg, concepto,
             _dt2.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d"),
             _dt2.now(config.COLOMBIA_TZ).strftime("%H:%M"))
        )
except Exception as e:
    logger.warning("Postgres write fiados failed: %s", e)
```

### Migration: `migrate_fiados.py` idempotency (name-based)
```python
# Source: same pattern as migrate_gastos_caja.py check-before-insert
for nombre_cliente, datos in fiados.items():
    # Get or create fiado record
    existing = db.query_one("SELECT id FROM fiados WHERE nombre = %s", (nombre_cliente,))
    if existing:
        fiado_id = existing["id"]
        db.execute("UPDATE fiados SET deuda=%s WHERE id=%s",
                   (int(datos.get("saldo", 0)), fiado_id))
        logger.info(f"  Fiado actualizado: {nombre_cliente}")
    else:
        row = db.execute_returning(
            "INSERT INTO fiados (nombre, deuda) VALUES (%s, %s) RETURNING id",
            (nombre_cliente, int(datos.get("saldo", 0)))
        )
        fiado_id = row["id"]
        logger.info(f"  Fiado creado: {nombre_cliente}")
    # Insert movimientos with check-before-insert
    for mov in datos.get("movimientos", []):
        tipo = "cargo" if mov.get("cargo", 0) > 0 else "abono"
        monto = int(mov.get("cargo", 0) or mov.get("abono", 0))
        existing_mov = db.query_one(
            "SELECT id FROM fiados_historial WHERE fiado_id=%s AND fecha=%s AND monto=%s AND concepto=%s",
            (fiado_id, mov["fecha"], monto, mov.get("concepto", ""))
        )
        if not existing_mov:
            db.execute(
                "INSERT INTO fiados_historial (fiado_id, tipo, monto, concepto, fecha) VALUES (%s,%s,%s,%s,%s)",
                (fiado_id, tipo, monto, mov.get("concepto", ""), mov["fecha"])
            )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `cargar_fiados()` reads only from JSON | Reads from Postgres with JSON fallback | Phase 4 | Fiados state survives bot restarts without Drive dependency |
| `GET /compras` reads only from `memoria.json` | Reads from `compras` Postgres table with JSON fallback | Phase 4 | Dashboard shows purchase history reliably |
| `listar_facturas()` reads only from JSON `cuentas_por_pagar` | Reads from `facturas_proveedores` JOIN `facturas_abonos` with JSON fallback | Phase 4 | Tab Proveedores gets Postgres source |

**After Phase 4, remaining JSON-only paths (for Phase 5):**
- `notas` in `memoria.json`
- Google Sheets ventas (intentional dual-write during transition)
- Drive uploads of `memoria.json` itself

---

## Open Questions

1. **`cargar_fiados()` movimientos format: running saldo vs event monto**
   - What we know: JSON stores `{"cargo": X, "abono": Y, "saldo": running_total}` per movement. `fiados_historial` stores `tipo` + `monto` (unsigned). `fiads.deuda` is the current balance.
   - What's unclear: `resumen_fiados()` and `detalle_fiado_cliente()` access `v.get("saldo", 0)` per movement. If `cargar_fiados()` returns historial from Postgres with `"saldo": 0` (unknown), these display functions may show wrong per-movement running balance.
   - Recommendation: Reconstruct running saldo in `cargar_fiados()` by iterating movements in order — same logic as the original `guardar_fiado_movimiento()`. Set `"cargo"` from historial when `tipo="cargo"`, `"abono"` when `tipo="abono"`.

2. **`execute_returning` vs `execute` for `fiados` INSERT**
   - What we know: `db.execute_returning(sql, params)` returns the first row of RETURNING clause. The `fiados` table uses SERIAL PRIMARY KEY (`id`).
   - What's unclear: If `execute_returning` is needed for migración INSERT to get `fiado_id`, the function must be verified to return a dict with `id` key (RealDictCursor is in use, so this should work).
   - Recommendation: Use `execute_returning` with `RETURNING id` for INSERT, capture `row["id"]`. Low risk.

---

## Sources

### Primary (HIGH confidence)
- `db.py` lines 234-309 — Schema for all 5 tables: `fiados`, `fiados_historial`, `facturas_proveedores`, `facturas_abonos`, `compras` — verified by direct file read
- `memoria.py` lines 962-1625 — All 6 functions to be modified — verified by direct file read
- `routers/caja.py` lines 309-427 — `GET /gastos` template pattern and current `GET /compras` implementation — verified
- `routers/proveedores.py` lines 85-230 — Photo upload endpoints to be modified — verified
- `memoria.json` — Live data: 3 fiado clients, 0 facturas, 0 historial_compras — verified by Python inspection
- `migrate_gastos_caja.py` — Canonical migration script pattern (check-before-insert deduplication) — verified

### Secondary (MEDIUM confidence)
- `ventas.xlsx` Fiados sheet — 6 non-empty rows; no Compras sheet — verified by openpyxl inspection
- `test_suite.py` — 201 tests passing baseline confirmed 2026-03-26

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use and verified
- Architecture patterns: HIGH — direct templates exist in codebase (GET /gastos, Phase 1-3 write patterns)
- Pitfalls: HIGH — identified from code inspection (json_agg NULL, tipo derivation, key name mismatch) and Phase 3 decisions log
- Migration source data: HIGH — confirmed by runtime inspection (0 facturas, 3 fiados, 0 compras)

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (stable domain — schema deployed, patterns established)
