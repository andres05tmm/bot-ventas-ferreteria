#!/usr/bin/env python3
"""
migrations/011_notas_electronicas.py
Extiende facturas_electronicas para soportar notas crédito y débito DIAN.

En vez de crear una tabla nueva, se agregan tres columnas a la tabla existente:
  - tipo            VARCHAR(20)  → 'factura' | 'nota_credito' | 'nota_debito'
  - razon_id        SMALLINT     → ID de razón DIAN (solo notas)
  - factura_cufe_ref VARCHAR(200) → CUFE de la factura original (solo notas)

Las filas existentes quedan con tipo='factura' por DEFAULT.
Idempotente — seguro para re-ejecutar.

Ejecutar UNA VEZ desde la raíz del proyecto:
    railway run python migrations/011_notas_electronicas.py
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
logger = logging.getLogger("011_notas_electronicas")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── Extender facturas_electronicas ────────────────────────────────
            cur.execute("""
                ALTER TABLE facturas_electronicas
                    ADD COLUMN IF NOT EXISTS tipo
                        VARCHAR(20) NOT NULL DEFAULT 'factura',
                    ADD COLUMN IF NOT EXISTS razon_id
                        SMALLINT,
                    ADD COLUMN IF NOT EXISTS factura_cufe_ref
                        VARCHAR(200);
            """)
            logger.info("✓ facturas_electronicas: columnas tipo, razon_id, factura_cufe_ref agregadas")

            # Índice para filtrar notas por tipo y por factura de referencia
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_facturas_tipo "
                "ON facturas_electronicas(tipo);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_facturas_cufe_ref "
                "ON facturas_electronicas(factura_cufe_ref);"
            )
            logger.info("✓ índices adicionales creados")

        conn.commit()
        logger.info("✅ Migración 011 notas electrónicas aplicada correctamente")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    _db.init_db()
    run()
