#!/usr/bin/env python3
"""
migrations/029_iva_productos_faltantes.py
Marca con IVA 19% los productos que quedaron con tiene_iva = FALSE.

Contexto:
  El catálogo tiene 645 productos: 631 con IVA 19% y 14 con tiene_iva = FALSE
  y porcentaje_iva = 0. No son bienes excluidos — son ferretería corriente
  (remachadora, candado, cabo de pala, vinilo, lima…), quedaron así por omisión
  al cargarlos. Efecto: sus líneas salían facturadas a la DIAN sin IVA y el
  Libro IVA no las contaba como IVA generado.

Qué hace:
  UPDATE productos SET tiene_iva = TRUE, porcentaje_iva = 19
   WHERE NOT (tiene_iva AND porcentaje_iva > 0)

  Incluye el producto inactivo 'Laca Beige Catalizada' para que quede correcto
  si alguna vez se reactiva.

Alcance:
  - Solo afecta facturas FUTURAS. Las ya emitidas a la DIAN no se reescriben:
    el XML transmitido es inmutable, corregirlas requeriría nota crédito.
  - emitir_factura() lee tiene_iva/porcentaje_iva de la tabla productos en cada
    emisión, así que no hay caché que invalidar ni servicio que reiniciar.
  - Idempotente: si no queda ninguno sin IVA, no hace nada.

Ejecutar UNA VEZ:
    railway run python migrations/029_iva_productos_faltantes.py
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
logger = logging.getLogger("029_iva_productos_faltantes")

import db as _db

_SIN_IVA = "NOT (tiene_iva AND porcentaje_iva > 0)"


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute(f"SELECT id, nombre, activo FROM productos WHERE {_SIN_IVA} ORDER BY nombre")
            pendientes = cur.fetchall()
            if not pendientes:
                logger.info("✓ todos los productos ya tienen IVA — nada que hacer")
                return

            for p in pendientes:
                logger.info("  · %s%s", p["nombre"], "" if p["activo"] else "  (inactivo)")

            cur.execute(f"""
                UPDATE productos
                   SET tiene_iva = TRUE, porcentaje_iva = 19
                 WHERE {_SIN_IVA}
            """)
            logger.info("✓ %s productos actualizados a IVA 19%%", cur.rowcount)

        conn.commit()
        logger.info("✅ Migración 029 aplicada correctamente")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
