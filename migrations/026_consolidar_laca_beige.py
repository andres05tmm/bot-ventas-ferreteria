#!/usr/bin/env python3
"""
migrations/026_consolidar_laca_beige.py
Consolida el producto duplicado "Laca Beige" del catálogo (N-05).

Contexto:
  El catálogo tiene el mismo producto cargado dos veces, con las ventas
  repartidas entre ambos, lo que distorsiona reportes y top de productos:

    - id 441211  "Laca Catalizada Beige"  clave=laca_catalizada_beige  ACTIVO
    - id 272260  "Laca Beige Catalizada"  clave=laca_beige_catalizada   inactivo

  Ambos $107.000, unidad Galón. Se conserva el ACTIVO (441211) y se le migran
  las líneas de venta del inactivo (272260), que queda desactivado. Se agregan
  aliases para que el bot reconozca las variantes de nombre vistas en ventas.

Idempotente:
  - El UPDATE de ventas_detalle solo afecta filas que aún apunten al duplicado.
  - Los aliases se deduplican (no se repiten si ya están).
  - Reejecutar no cambia nada tras la primera corrida.

Ejecutar UNA VEZ:
    railway run python migrations/026_consolidar_laca_beige.py
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
logger = logging.getLogger("026_consolidar_laca_beige")

import db as _db

_KEEP = 441211        # "Laca Catalizada Beige" (activo)
_MERGE_FROM = 272260  # "Laca Beige Catalizada" (inactivo)
_ALIASES = ["laca beige catalizada", "laca catalizada beis"]


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── 1. Migrar líneas de venta del duplicado al producto a conservar ─
            cur.execute(
                "UPDATE ventas_detalle SET producto_id = %s WHERE producto_id = %s",
                (_KEEP, _MERGE_FROM),
            )
            logger.info("✓ %s líneas de venta migradas %s → %s",
                        cur.rowcount, _MERGE_FROM, _KEEP)

            # ── 2. Agregar aliases al producto conservado (dedup) ──────────────
            cur.execute(
                """
                UPDATE productos
                   SET aliases = (
                       SELECT array_agg(DISTINCT a)
                       FROM unnest(COALESCE(aliases, '{}') || %s::text[]) a
                   )
                 WHERE id = %s
                """,
                (_ALIASES, _KEEP),
            )
            logger.info("✓ aliases agregados a %s: %s", _KEEP, _ALIASES)

            # ── 3. Desactivar el duplicado (idempotente) ───────────────────────
            cur.execute(
                "UPDATE productos SET activo = FALSE WHERE id = %s AND activo IS DISTINCT FROM FALSE",
                (_MERGE_FROM,),
            )
            if cur.rowcount:
                logger.info("✓ producto %s desactivado", _MERGE_FROM)
            else:
                logger.info("✓ producto %s ya estaba inactivo", _MERGE_FROM)

        conn.commit()
        logger.info("✅ Migración 026 aplicada correctamente")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
