"""
Tests para migración 004_usuarios_auth.
Verifica estructura, constraints, seed data e índices.
Requiere DATABASE_URL en el entorno y que la migración ya haya sido ejecutada.
"""

# -- stdlib --
import os

# -- terceros --
import psycopg2
import pytest


# ---------------------------------------------------------------------------
# Fixture de conexión
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    database_url = os.environ["DATABASE_URL"]
    connection = psycopg2.connect(database_url)
    connection.autocommit = True
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_tabla_usuarios_existe_con_columnas(conn):
    """La tabla usuarios debe existir con todas sus columnas."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'usuarios'
        """)
        col_names = {row[0] for row in cur.fetchall()}
    assert {"id", "telegram_id", "nombre", "rol", "activo", "created_at"} <= col_names, (
        f"Faltan columnas. Encontradas: {col_names}"
    )


def test_telegram_id_constraint_unique(conn):
    """telegram_id debe tener constraint UNIQUE."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT constraint_type
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_name = kcu.table_name
            WHERE tc.table_name = 'usuarios'
              AND kcu.column_name = 'telegram_id'
              AND constraint_type = 'UNIQUE'
        """)
        row = cur.fetchone()
    assert row is not None, "No se encontró constraint UNIQUE en telegram_id"


def test_rol_default_es_vendedor(conn):
    """El valor por defecto de rol debe ser 'vendedor'."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_default
            FROM information_schema.columns
            WHERE table_name = 'usuarios' AND column_name = 'rol'
        """)
        row = cur.fetchone()
    assert row is not None, "Columna 'rol' no encontrada"
    assert "vendedor" in (row[0] or ""), f"Default de 'rol' inesperado: {row[0]}"


def test_tablas_tienen_columna_usuario_id(conn):
    """Las 4 tablas de transacciones deben tener columna usuario_id."""
    tablas = ("ventas", "gastos", "compras", "facturas_proveedores")
    for tabla in tablas:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'usuario_id'
            """, (tabla,))
            row = cur.fetchone()
        assert row is not None, f"Columna 'usuario_id' no encontrada en tabla '{tabla}'"


def test_usuario_id_es_nullable(conn):
    """usuario_id debe ser nullable para no romper inserts existentes."""
    tablas = ("ventas", "gastos", "compras", "facturas_proveedores")
    for tabla in tablas:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'usuario_id'
            """, (tabla,))
            row = cur.fetchone()
        assert row is not None, f"Columna 'usuario_id' no encontrada en '{tabla}'"
        assert row[0] == "YES", (
            f"usuario_id en '{tabla}' no es nullable — rompería inserts existentes"
        )


def test_seed_admin_andres(conn):
    """Debe existir exactamente 1 usuario admin con telegram_id=1831034712."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, nombre, rol
            FROM usuarios
            WHERE telegram_id = 1831034712 AND rol = 'admin'
        """)
        row = cur.fetchone()
    assert row is not None, "No se encontró usuario admin con telegram_id=1831034712"
    assert row[1] == "Andrés", f"Nombre esperado 'Andrés', encontrado '{row[1]}'"


def test_seed_exactamente_cuatro_vendedores(conn):
    """Deben existir exactamente 4 usuarios con rol='vendedor'."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'vendedor'")
        count = cur.fetchone()[0]
    assert count == 4, f"Se esperaban 4 vendedores, encontrados: {count}"


def test_indices_existen(conn):
    """Los 4 índices de usuario_id deben existir en pg_indexes."""
    indices_esperados = {
        "idx_ventas_usuario_id",
        "idx_gastos_usuario_id",
        "idx_compras_usuario_id",
        "idx_facturas_proveedores_usuario_id",
    }
    with conn.cursor() as cur:
        cur.execute("""
            SELECT indexname FROM pg_indexes
            WHERE indexname = ANY(%s)
        """, (list(indices_esperados),))
        encontrados = {row[0] for row in cur.fetchall()}
    faltantes = indices_esperados - encontrados
    assert not faltantes, f"Índices faltantes: {faltantes}"
