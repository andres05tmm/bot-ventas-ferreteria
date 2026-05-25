---
phase: quick
plan: 260401-0dm
completed: "2026-04-01"
duration: "5m"
commit: "c3c3608"
---

# Quick Task 260401-0dm: Create usuarios Auth Schema Migration Summary

## Objective
Create an idempotent PostgreSQL migration establishing user authentication schema and comprehensive test suite for role-based access control.

## Files Created

### 1. migrations/004_usuarios_auth.py (78 lines)
- **Purpose:** Idempotent async migration using asyncpg for PostgreSQL
- **Entry point:** `python migrations/004_usuarios_auth.py` (suitable for Railway `railway run`)
- **Idempotency:** All SQL statements use `IF NOT EXISTS` or `ON CONFLICT` clauses
- **Operations:**
  1. CREATE TABLE usuarios (id, telegram_id, nombre, rol, activo, created_at)
  2. ALTER TABLE ventas ADD COLUMN usuario_id (if not exists)
  3. ALTER TABLE gastos ADD COLUMN usuario_id (if not exists)
  4. ALTER TABLE compras ADD COLUMN usuario_id (if not exists)
  5. ALTER TABLE facturas_proveedores ADD COLUMN usuario_id (if not exists)
  6. CREATE INDEX idx_ventas_usuario_id (if not exists)
  7. CREATE INDEX idx_gastos_usuario_id (if not exists)
  8. CREATE INDEX idx_compras_usuario_id (if not exists)
  9. CREATE INDEX idx_facturas_proveedores_usuario_id (if not exists)
  10. INSERT 5 seed users via ON CONFLICT (telegram_id) DO NOTHING
- **Seed data (5 users):**
  - telegram_id=1831034712, nombre="Andrés", rol="admin"
  - telegram_id=1, nombre="Farid M", rol="vendedor"
  - telegram_id=2, nombre="Farid D", rol="vendedor"
  - telegram_id=3, nombre="Karolay", rol="vendedor"
  - telegram_id=4, nombre="Papá", rol="vendedor"
- **Print confirmations:** Each step prints `✓` with status message
- **Error handling:** Wrapped in try/finally to ensure connection cleanup

### 2. tests/test_004_usuarios_auth.py (147 lines)
- **Purpose:** Comprehensive test suite validating schema structure, constraints, and seeding
- **Framework:** pytest + asyncpg with async/await
- **Test count:** 8 tests
- **Fixture:** `conn` — asyncpg connection per test, async setup/teardown
- **Tests:**
  1. `test_tabla_usuarios_existe_con_columnas` — Verify all 6 columns exist with correct types
  2. `test_telegram_id_constraint_unique` — Verify UNIQUE constraint on telegram_id
  3. `test_rol_default_es_vendedor` — Verify column_default='vendedor'
  4. `test_tablas_tienen_columna_usuario_id` — Verify FK column exists in 4 transaction tables
  5. `test_usuario_id_es_nullable` — Verify is_nullable=YES (preserves existing rows)
  6. `test_seed_admin_andres` — Verify admin user (telegram_id=1831034712, nombre="Andrés")
  7. `test_seed_exactamente_cuatro_vendedores` — Verify exactly 4 vendedores seeded
  8. `test_indices_existen` — Verify all 4 performance indexes created
- **Async markers:** All tests decorated with `@pytest.mark.asyncio`
- **DB interaction:** Direct asyncpg queries to information_schema and pg_indexes
- **Error messages:** Descriptive assertion failures for debugging

## Verification Results

✓ Migration file valid Python syntax
✓ Test file valid Python syntax
✓ Both files committed atomically
✓ Commit hash: c3c3608

## Schema Summary

**usuarios table:**
- id SERIAL PRIMARY KEY
- telegram_id BIGINT UNIQUE NOT NULL
- nombre VARCHAR(100) NOT NULL
- rol VARCHAR(20) NOT NULL DEFAULT 'vendedor'
- activo BOOLEAN NOT NULL DEFAULT TRUE
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

**FK columns added:**
- ventas.usuario_id INT REFERENCES usuarios(id) [nullable, preserves existing]
- gastos.usuario_id INT REFERENCES usuarios(id) [nullable, preserves existing]
- compras.usuario_id INT REFERENCES usuarios(id) [nullable, preserves existing]
- facturas_proveedores.usuario_id INT REFERENCES usuarios(id) [nullable, preserves existing]

**Performance indexes:**
- idx_ventas_usuario_id ON ventas(usuario_id)
- idx_gastos_usuario_id ON gastos(usuario_id)
- idx_compras_usuario_id ON compras(usuario_id)
- idx_facturas_proveedores_usuario_id ON facturas_proveedores(usuario_id)

## Adherence to CLAUDE.md

- No protected files modified (db.py, config.py, main.py untouched)
- No existing functions deleted
- Backward compatible (users table is purely additive)
- Idempotent design allows safe rerunning
- Follows FerreBot migration pattern (sequential numbered scripts)

## Next Steps

Run migration on Railway:
```bash
railway run python migrations/004_usuarios_auth.py
```

Run tests locally (requires DATABASE_URL):
```bash
pytest tests/test_004_usuarios_auth.py -v
```

## Deviations from Plan

None — plan executed exactly as written.
