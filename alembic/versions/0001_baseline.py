"""baseline - esquema completo de FerreBot (estado de produccion Punto Rojo)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-28

Esta es la migracion baseline: representa el esquema COMPLETO tal como existe
hoy en produccion, capturado con pg_dump --schema-only de la BD real (28
tablas, secuencias, indices, constraints, funcion y trigger de updated_at).

El SQL vive en alembic/sql/baseline.sql (fuente de verdad fiel). Para una BD
nueva (otra ferreteria), `alembic upgrade head` ejecuta este archivo y crea todo
desde cero. En Punto Rojo NO se ejecuta: la BD ya existe y se marco con
`alembic stamp 0001_baseline`.

Se filtran los meta-comandos de psql (lineas que empiezan con backslash, como
restrict / unrestrict) que pg_dump 18 agrega y que no son SQL ejecutable. El
resto se ejecuta con exec_driver_sql para pasar el SQL crudo a psycopg2 sin que
SQLAlchemy interprete los casts de tipo (doble dos-puntos) como parametros bind.
"""
import os

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

_SQL_PATH = os.path.join(os.path.dirname(__file__), "..", "sql", "baseline.sql")
_BACKSLASH = chr(92)


def _cargar_sql() -> str:
    with open(_SQL_PATH, encoding="utf-8") as f:
        lineas = f.readlines()
    # Quitar meta-comandos de psql (empiezan con backslash): no son SQL.
    return "".join(l for l in lineas if not l.lstrip().startswith(_BACKSLASH))


def upgrade() -> None:
    sql = _cargar_sql()
    op.get_bind().exec_driver_sql(sql)


def downgrade() -> None:
    # La baseline no se revierte (no hay estado anterior al esquema inicial).
    pass
