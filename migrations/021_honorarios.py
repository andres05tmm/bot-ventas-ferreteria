"""
migrations/021_honorarios.py
Crea la tabla cuentas_cobro para el módulo de honorarios.
Idempotente — seguro para re-ejecutar.

Ejecutar UNA VEZ:
    railway run python migrations/021_honorarios.py
"""

# -- stdlib --
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
logger = logging.getLogger("021_honorarios")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── Tabla principal ────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cuentas_cobro (
                    id                  SERIAL PRIMARY KEY,
                    consecutivo         INTEGER NOT NULL UNIQUE,
                    numero_display      VARCHAR(10)  NOT NULL,
                    fecha               DATE         NOT NULL,
                    periodo             VARCHAR(30)  NOT NULL,
                    concepto            TEXT         NOT NULL,
                    valor               NUMERIC(15,2) NOT NULL,
                    pdf_bytes           BYTEA,
                    enviado_telegram    BOOLEAN DEFAULT FALSE,
                    creado_at           TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            logger.info("✓ Tabla cuentas_cobro creada (o ya existía)")

            # ── Índice para ordenar por fecha ──────────────────────────────────
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_cuentas_cobro_fecha
                ON cuentas_cobro (fecha DESC);
            """)
            logger.info("✓ Índice ix_cuentas_cobro_fecha OK")

        conn.commit()
    logger.info("✅ Migración 021 completada")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
