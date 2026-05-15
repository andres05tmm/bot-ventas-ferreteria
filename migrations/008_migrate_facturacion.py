#!/usr/bin/env python3
"""
migrations/008_migrate_facturacion.py
Agrega soporte de facturación electrónica DIAN (MATIAS API).
Idempotente — seguro para re-ejecutar.

Ejecutar UNA VEZ desde la raíz del proyecto:
    railway run python migrations/008_migrate_facturacion.py
"""
import logging
import os
import sys

# ── Asegurar que la raíz del proyecto esté en sys.path ───────────────────────
# Necesario para que "import db" funcione al ejecutar desde raíz
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] -- %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("008_migrate_facturacion")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── 1. Columnas de factura en ventas ──────────────────────────────
            cur.execute("""
                ALTER TABLE ventas
                    ADD COLUMN IF NOT EXISTS factura_numero  VARCHAR(30),
                    ADD COLUMN IF NOT EXISTS factura_cufe    VARCHAR(200),
                    ADD COLUMN IF NOT EXISTS factura_estado  VARCHAR(20) DEFAULT 'sin_factura',
                    ADD COLUMN IF NOT EXISTS facturada_at    TIMESTAMP;
            """)
            logger.info("✓ ventas: columnas de factura agregadas")

            # ── 2. Campos fiscales en clientes ────────────────────────────────
            cur.execute("""
                ALTER TABLE clientes
                    ADD COLUMN IF NOT EXISTS regimen_fiscal  VARCHAR(30) DEFAULT 'no_responsable_iva',
                    ADD COLUMN IF NOT EXISTS municipio_dian  INTEGER     DEFAULT 149;
            """)
            logger.info("✓ clientes: campos fiscales DIAN agregados")

            # ── 3. IVA en productos (mayoría ferretería = FALSE/excluido) ─────
            cur.execute("""
                ALTER TABLE productos
                    ADD COLUMN IF NOT EXISTS tiene_iva      BOOLEAN DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS porcentaje_iva INTEGER DEFAULT 0;
            """)
            logger.info("✓ productos: campos IVA agregados")

            # ── 4. Tabla log de facturas electrónicas ─────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS facturas_electronicas (
                    id             SERIAL PRIMARY KEY,
                    venta_id       INTEGER REFERENCES ventas(id) ON DELETE SET NULL,
                    numero         VARCHAR(30) NOT NULL,
                    cufe           VARCHAR(200),
                    fecha_emision  TIMESTAMP DEFAULT NOW(),
                    estado         VARCHAR(20) DEFAULT 'emitida',
                    cliente_nombre VARCHAR(300),
                    total          INTEGER,
                    error_msg      TEXT,
                    created_at     TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_facturas_venta "
                "ON facturas_electronicas(venta_id);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_facturas_cufe "
                "ON facturas_electronicas(cufe);"
            )
            logger.info("✓ tabla facturas_electronicas creada")

        conn.commit()
        logger.info("✅ Migración 008 facturación aplicada correctamente")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    _db.init_db()
    run()
