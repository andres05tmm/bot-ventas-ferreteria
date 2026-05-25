"""
migrations/022_documento_soporte.py
Crea la tabla documentos_soporte para el Documento Soporte en Adquisiciones
a No Obligados a Facturar (DS-NO) transmitido via MATIAS API.
Idempotente — seguro para re-ejecutar.

Ejecutar UNA VEZ:
    railway run python migrations/022_documento_soporte.py
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
logger = logging.getLogger("022_documento_soporte")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS documentos_soporte (
                    id              SERIAL PRIMARY KEY,
                    consecutivo     VARCHAR(20),
                    fecha           DATE,
                    valor           DECIMAL(12,2),
                    cude            VARCHAR(200),
                    estado_dian     VARCHAR(50),
                    cuenta_cobro_id INTEGER REFERENCES cuentas_cobro(id),
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            logger.info("✓ Tabla documentos_soporte creada (o ya existía)")

            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_documentos_soporte_fecha
                ON documentos_soporte (fecha DESC);
            """)
            logger.info("✓ Índice ix_documentos_soporte_fecha OK")

        conn.commit()
    logger.info("✅ Migración 022 completada")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
