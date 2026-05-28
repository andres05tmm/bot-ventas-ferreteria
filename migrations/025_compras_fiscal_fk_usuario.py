#!/usr/bin/env python3
"""
migrations/025_compras_fiscal_fk_usuario.py
Agrega la FK formal compras_fiscal.usuario_id → usuarios.id (M-02).

Contexto:
  La tabla compras_fiscal se creó (migración 010) con la columna usuario_id
  como INTEGER suelto, sin la restricción de integridad referencial que sí
  tienen ventas, gastos, compras y facturas_proveedores. Esto permite valores
  huérfanos que no corresponden a ningún usuario real.

Seguridad:
  - La FK solo valida valores NO nulos: las filas con usuario_id NULL no se ven
    afectadas (en prod las 26 filas actuales son NULL).
  - Antes de crear la restricción, se sanean posibles huérfanos poniéndolos a
    NULL para que el ADD CONSTRAINT no falle.
  - ON DELETE SET NULL: al borrar un usuario, sus compras fiscales no se pierden.
  - Idempotente: no recrea la FK si ya existe.

Ejecutar UNA VEZ:
    railway run python migrations/025_compras_fiscal_fk_usuario.py
"""
import logging
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] -- %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("025_compras_fiscal_fk_usuario")

import db as _db

_CONSTRAINT = "fk_compras_fiscal_usuario"


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── 1. Sanear huérfanos: usuario_id que no existe en usuarios ──
            cur.execute("""
                UPDATE compras_fiscal
                   SET usuario_id = NULL
                 WHERE usuario_id IS NOT NULL
                   AND usuario_id NOT IN (SELECT id FROM usuarios);
            """)
            if cur.rowcount:
                logger.info("✓ %s huérfanos saneados a NULL", cur.rowcount)
            else:
                logger.info("✓ sin huérfanos que sanear")

            # ── 2. Crear la FK solo si no existe ───────────────────────────
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                         WHERE constraint_name = 'fk_compras_fiscal_usuario'
                           AND table_name = 'compras_fiscal'
                    ) THEN
                        ALTER TABLE compras_fiscal
                            ADD CONSTRAINT fk_compras_fiscal_usuario
                            FOREIGN KEY (usuario_id)
                            REFERENCES usuarios(id)
                            ON DELETE SET NULL;
                    END IF;
                END $$;
            """)
            logger.info("✓ FK %s creada (o ya existía)", _CONSTRAINT)

        conn.commit()
        logger.info("✅ Migración 025 aplicada correctamente")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
