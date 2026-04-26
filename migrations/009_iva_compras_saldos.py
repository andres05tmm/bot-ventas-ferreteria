#!/usr/bin/env python3
"""
migrations/009_iva_compras_saldos.py
Agrega soporte de IVA en compras y saldos bimestrales.

Ejecutar UNA VEZ:
    railway run python migrations/009_iva_compras_saldos.py
"""
import logging, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] -- %(message)s", stream=sys.stdout)
logger = logging.getLogger("009_iva_compras_saldos")

import db as _db

def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # 1. Columnas IVA en compras
            cur.execute("""
                ALTER TABLE compras
                    ADD COLUMN IF NOT EXISTS incluye_iva BOOLEAN  DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS tarifa_iva  INTEGER  DEFAULT 0;
            """)
            logger.info("✓ compras: columnas incluye_iva, tarifa_iva agregadas")

            # 2. usuario_id (por si alguna versión no la tiene)
            cur.execute("""
                ALTER TABLE compras
                    ADD COLUMN IF NOT EXISTS usuario_id INTEGER;
            """)
            logger.info("✓ compras: columna usuario_id verificada")

            # 3. Tabla de saldos bimestrales IVA
            cur.execute("""
                CREATE TABLE IF NOT EXISTS iva_saldos_bimestrales (
                    año               INTEGER  NOT NULL,
                    bimestre          INTEGER  NOT NULL CHECK (bimestre BETWEEN 1 AND 6),
                    iva_ventas        BIGINT   DEFAULT 0,
                    iva_compras       BIGINT   DEFAULT 0,
                    saldo_anterior    BIGINT   DEFAULT 0,
                    iva_neto          BIGINT   DEFAULT 0,
                    estado            VARCHAR(20) DEFAULT 'borrador',
                    fecha_declaracion DATE,
                    observaciones     TEXT,
                    cerrado_at        TIMESTAMP,
                    PRIMARY KEY (año, bimestre)
                );
            """)
            logger.info("✓ tabla iva_saldos_bimestrales creada")

        conn.commit()
        logger.info("✅ Migración 009 aplicada correctamente")

if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
