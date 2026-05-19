#!/usr/bin/env python3
"""
migrations/013_productos_iva_19.py

Todos los productos activos de la ferretería tienen IVA del 19% incluido
en el precio. Esta migración los marca correctamente en la BD para que
la facturación electrónica DIAN refleje el impuesto real.

Ejecutar UNA VEZ:
    python migrations/013_productos_iva_19.py
"""
import logging, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] -- %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("013_productos_iva_19")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # Contar productos antes del cambio
            cur.execute("SELECT COUNT(*) AS total FROM productos WHERE activo = true;")
            row = cur.fetchone()
            total = row.get("total") if isinstance(row, dict) else row[0]
            logger.info(f"Productos activos en BD: {total}")

            # Ver distribución actual
            cur.execute("""
                SELECT tiene_iva, porcentaje_iva, COUNT(*) AS cant
                FROM productos
                WHERE activo = true
                GROUP BY tiene_iva, porcentaje_iva
                ORDER BY tiene_iva, porcentaje_iva;
            """)
            rows = cur.fetchall()
            logger.info("Distribución actual de IVA en productos:")
            for r in rows:
                if isinstance(r, dict):
                    logger.info(f"  tiene_iva={r['tiene_iva']} | pct={r['porcentaje_iva']} → {r['cant']} productos")
                else:
                    logger.info(f"  tiene_iva={r[0]} | pct={r[1]} → {r[2]} productos")

            # Actualizar TODOS los productos activos a 19% IVA
            cur.execute("""
                UPDATE productos
                SET tiene_iva      = true,
                    porcentaje_iva = 19
                WHERE activo = true;
            """)
            actualizados = cur.rowcount
            logger.info(f"✓ {actualizados} productos actualizados a tiene_iva=true, porcentaje_iva=19")

        conn.commit()
        logger.info("✅ Migración 013 aplicada correctamente")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
