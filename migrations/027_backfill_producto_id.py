#!/usr/bin/env python3
"""
migrations/027_backfill_producto_id.py
Backfill de ventas_detalle.producto_id por nombre exacto (N-02).

Contexto:
  El 46% de las líneas de venta históricas (218/474) tienen producto_id NULL,
  arrastrado por data de marzo cuando el bot aún no resolvía el producto contra
  el catálogo. La lógica de inserción ya está sana (mayo: 2% NULL), así que esto
  es un backfill de datos viejos, no un fix de código.

  203 de esas 218 líneas casan de forma INEQUÍVOCA con un producto por nombre
  exacto (lower+trim). Solo se resuelven esas; las 15 restantes son nombres
  libres/typos sin match único y se dejan como están.

Seguridad:
  - Solo toca filas con producto_id IS NULL (idempotente).
  - Solo asigna cuando el nombre mapea a UN único producto (sin ambigüedad):
    nombres con más de un producto se excluyen vía HAVING count(*) = 1.

Ejecutar UNA VEZ (idealmente después de 026_consolidar_laca_beige.py):
    railway run python migrations/027_backfill_producto_id.py
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
logger = logging.getLogger("027_backfill_producto_id")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ventas_detalle d
                   SET producto_id = m.pid
                  FROM (
                      SELECT lower(trim(nombre)) AS pn, min(id) AS pid
                      FROM productos
                      GROUP BY lower(trim(nombre))
                      HAVING count(*) = 1
                  ) m
                 WHERE d.producto_id IS NULL
                   AND d.producto_nombre IS NOT NULL
                   AND lower(trim(d.producto_nombre)) = m.pn
            """)
            logger.info("✓ %s líneas resueltas (producto_id asignado)", cur.rowcount)

            cur.execute(
                "SELECT count(*) AS n FROM ventas_detalle WHERE producto_id IS NULL"
            )
            restantes = cur.fetchone()["n"]
            logger.info("✓ líneas con producto_id NULL restantes: %s", restantes)

        conn.commit()
        logger.info("✅ Migración 027 aplicada correctamente")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
