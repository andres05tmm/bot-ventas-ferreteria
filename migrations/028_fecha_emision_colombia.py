#!/usr/bin/env python3
"""
migrations/028_fecha_emision_colombia.py
facturas_electronicas.fecha_emision / created_at pasan a hora Colombia (UTC-5).

Contexto:
  La tabla se creó (migración 008) con DEFAULT NOW(). Railway corre en UTC, así
  que toda factura emitida después de las 7 PM Colombia quedaba fechada al día
  siguiente. Eso desplazaba el Libro IVA y los reportes de facturación
  (ej. FPR289 emitida el 31-jul 19:08 Colombia aparecía como 01-ago).

Qué hace:
  1. Cambia el DEFAULT a NOW() AT TIME ZONE 'America/Bogota'.
  2. Convierte las filas existentes de UTC → Colombia.

Seguridad:
  - No toca numeración DIAN ni CUFEs: solo el timestamp local de reporte.
  - Idempotente: si el DEFAULT ya es Colombia, no vuelve a desplazar las filas.
  - Verificado antes de escribir: las 278 filas actuales provienen todas del
    DEFAULT NOW() en UTC (fecha_emision == created_at en todas), así que el
    desplazamiento uniforme es correcto.

Ejecutar UNA VEZ:
    railway run python migrations/028_fecha_emision_colombia.py
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
logger = logging.getLogger("028_fecha_emision_colombia")

import db as _db

_DEFAULT_COL = "timezone('America/Bogota'::text, now())"


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── 1. ¿Ya está migrada? ───────────────────────────────────────
            cur.execute("""
                SELECT column_default
                  FROM information_schema.columns
                 WHERE table_name  = 'facturas_electronicas'
                   AND column_name = 'fecha_emision'
            """)
            row = cur.fetchone()
            actual = (row["column_default"] if row else "") or ""
            if "Bogota" in actual:
                logger.info("✓ ya migrada (DEFAULT = %s) — nada que hacer", actual)
                return

            # ── 2. DEFAULT en hora Colombia ────────────────────────────────
            cur.execute("""
                ALTER TABLE facturas_electronicas
                    ALTER COLUMN fecha_emision
                        SET DEFAULT (NOW() AT TIME ZONE 'America/Bogota'),
                    ALTER COLUMN created_at
                        SET DEFAULT (NOW() AT TIME ZONE 'America/Bogota');
            """)
            logger.info("✓ DEFAULT actualizado a hora Colombia")

            # ── 3. Backfill UTC → Colombia ─────────────────────────────────
            cur.execute("""
                UPDATE facturas_electronicas
                   SET fecha_emision = fecha_emision AT TIME ZONE 'UTC'
                                                     AT TIME ZONE 'America/Bogota',
                       created_at    = created_at    AT TIME ZONE 'UTC'
                                                     AT TIME ZONE 'America/Bogota';
            """)
            logger.info("✓ %s filas convertidas de UTC a hora Colombia", cur.rowcount)

        conn.commit()
        logger.info("✅ Migración 028 aplicada correctamente")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
