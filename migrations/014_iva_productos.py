#!/usr/bin/env python3
"""
migrations/014_iva_productos.py
Marca todos los productos como IVA incluido al 19%.

Todos los precios de Ferretería Punto Rojo ya tienen el IVA incluido
(precio final = base + 19%). Este script actualiza la DB para reflejarlo.

Ejecutar UNA VEZ:
    railway run python migrations/014_iva_productos.py
"""
import logging, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("014_iva_productos")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("SELECT COUNT(*) AS total FROM productos")
            total = cur.fetchone()["total"]
            logger.info("Total productos en catálogo: %d", total)

            cur.execute("""
                UPDATE productos
                SET tiene_iva      = TRUE,
                    porcentaje_iva = 19
                WHERE tiene_iva = FALSE OR porcentaje_iva = 0
            """)
            actualizados = cur.rowcount
            logger.info("✓ Productos actualizados con IVA 19%%: %d", actualizados)

        conn.commit()

    # Verificar
    rows = _db.query_all("""
        SELECT tiene_iva, porcentaje_iva, COUNT(*) AS qty
        FROM productos
        GROUP BY tiene_iva, porcentaje_iva
        ORDER BY tiene_iva DESC
    """)
    logger.info("Estado final de IVA en productos:")
    for r in rows:
        logger.info("  tiene_iva=%s  porcentaje=%s%%  cantidad=%d",
                    r["tiene_iva"], r["porcentaje_iva"], r["qty"])

    logger.info("✅ Migración 014 aplicada correctamente")


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    _db.init_db()
    run()
