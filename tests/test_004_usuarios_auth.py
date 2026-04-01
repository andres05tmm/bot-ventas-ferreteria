"""
Tests para migración 004_usuarios_auth.
Verifica estructura, constraints, seed data e índices.
Requiere DATABASE_URL en el entorno y que la migración ya haya sido ejecutada.
"""

# -- stdlib --
import os

# -- terceros --
import asyncpg
import pytest


# ---------------------------------------------------------------------------
# Fixture de conexión
# ---------------------------------------------------------------------------

@pytest.fixture
async def conn():
    database_url = os.environ["DATABASE_URL"]
    connection = await asyncpg.connect(database_url)
    yield connection
    await connection.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tabla_usuarios_existe_con_columnas(conn):
    """La tabla usuarios debe existir con todas sus columnas."""
    rows = await conn.fetch("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'usuarios'
        ORDER BY ordinal_position
    """)
    col_names = {r["column_name"] for r in rows}
    assert {"id", "telegram_id", "nombre", "rol", "activo", "created_at"} <= col_names, (
        f"Faltan columnas. Encontradas: {col_names}"
    )


@pytest.mark.asyncio
async def test_telegram_id_constraint_unique(conn):
    """telegram_id debe tener constraint UNIQUE."""
    row = await conn.fetchrow("""
        SELECT constraint_type
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_name = kcu.table_name
        WHERE tc.table_name = 'usuarios'
          AND kcu.column_name = 'telegram_id'
          AND constraint_type = 'UNIQUE'
    """)
    assert row is not None, "No se encontró constraint UNIQUE en telegram_id"


@pytest.mark.asyncio
async def test_rol_default_es_vendedor(conn):
    """El valor por defecto de rol debe ser 'vendedor'."""
    row = await conn.fetchrow("""
        SELECT column_default
        FROM information_schema.columns
        WHERE table_name = 'usuarios' AND column_name = 'rol'
    """)
    assert row is not None, "Columna 'rol' no encontrada"
    assert "vendedor" in (row["column_default"] or ""), (
        f"Default de 'rol' inesperado: {row['column_default']}"
    )


@pytest.mark.asyncio
async def test_tablas_tienen_columna_usuario_id(conn):
    """Las 4 tablas de transacciones deben tener columna usuario_id."""
    tablas = ("ventas", "gastos", "compras", "facturas_proveedores")
    for tabla in tablas:
        row = await conn.fetchrow("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = $1 AND column_name = 'usuario_id'
        """, tabla)
        assert row is not None, f"Columna 'usuario_id' no encontrada en tabla '{tabla}'"


@pytest.mark.asyncio
async def test_usuario_id_es_nullable(conn):
    """usuario_id debe ser nullable para no romper inserts existentes."""
    tablas = ("ventas", "gastos", "compras", "facturas_proveedores")
    for tabla in tablas:
        row = await conn.fetchrow("""
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_name = $1 AND column_name = 'usuario_id'
        """, tabla)
        assert row is not None, f"Columna 'usuario_id' no encontrada en '{tabla}'"
        assert row["is_nullable"] == "YES", (
            f"usuario_id en '{tabla}' no es nullable — rompería inserts existentes"
        )


@pytest.mark.asyncio
async def test_seed_admin_andres(conn):
    """Debe existir exactamente 1 usuario admin con telegram_id=1831034712."""
    row = await conn.fetchrow("""
        SELECT id, nombre, rol
        FROM usuarios
        WHERE telegram_id = 1831034712 AND rol = 'admin'
    """)
    assert row is not None, "No se encontró usuario admin con telegram_id=1831034712"
    assert row["nombre"] == "Andrés", f"Nombre esperado 'Andrés', encontrado '{row['nombre']}'"


@pytest.mark.asyncio
async def test_seed_exactamente_cuatro_vendedores(conn):
    """Deben existir exactamente 4 usuarios con rol='vendedor' del seed."""
    count = await conn.fetchval("""
        SELECT COUNT(*) FROM usuarios WHERE rol = 'vendedor'
    """)
    assert count == 4, f"Se esperaban 4 vendedores, encontrados: {count}"


@pytest.mark.asyncio
async def test_indices_existen(conn):
    """Los 4 índices de usuario_id deben existir en pg_indexes."""
    indices_esperados = {
        "idx_ventas_usuario_id",
        "idx_gastos_usuario_id",
        "idx_compras_usuario_id",
        "idx_facturas_proveedores_usuario_id",
    }
    rows = await conn.fetch("""
        SELECT indexname FROM pg_indexes
        WHERE indexname = ANY($1)
    """, list(indices_esperados))
    encontrados = {r["indexname"] for r in rows}
    faltantes = indices_esperados - encontrados
    assert not faltantes, f"Índices faltantes: {faltantes}"
