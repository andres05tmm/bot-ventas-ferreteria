# Migrado desde migrate_compras.py (raíz del proyecto)
# Este archivo es una copia exacta. El original se mantiene en raíz hasta que Phase 1 esté verde.
#!/usr/bin/env python3
"""
migrate_compras.py — Migra historial_compras de memoria.json a PostgreSQL.

Idempotente — seguro para re-ejecutar.
Fuente actual: memoria.json["historial_compras"] (actualmente vacio).
Si la fuente esta vacia, sale con exit 0.

Ejecutar UNA VEZ despues del deploy de Fase 4:
    railway run python migrate_compras.py
"""

# -- stdlib --
import json
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("migrate_compras")

# -- propios --
import db


def migrar():
    """Migra historial_compras de memoria.json a la tabla compras."""
    if not db.init_db():
        logger.error("DATABASE_URL no configurado")
        sys.exit(1)
    if not db.DB_DISPONIBLE:
        logger.error("DB no disponible")
        sys.exit(1)

    memoria_file = os.getenv("MEMORIA_FILE", "memoria.json")
    if not os.path.exists(memoria_file):
        logger.error("No se encontro %s", memoria_file)
        sys.exit(1)

    with open(memoria_file, encoding="utf-8") as f:
        mem = json.load(f)

    historial = mem.get("historial_compras", [])
    if not historial:
        logger.info("Nada que migrar: historial_compras vacio o ausente")
        return

    logger.info("Migrando %d registros de compras...", len(historial))
    count_ins  = 0
    count_skip = 0

    for compra in historial:
        fecha     = str(compra.get("fecha", ""))[:10] or "1970-01-01"
        hora      = str(compra.get("hora", ""))[:5] or None
        proveedor = str(compra.get("proveedor") or "")
        producto  = str(compra.get("producto", ""))
        cantidad  = float(compra.get("cantidad", 0))
        cu        = int(float(compra.get("costo_unitario", 0)))
        # JSON may use key "total" or "costo_total"
        total_val = compra.get("total") or compra.get("costo_total", 0)
        ct        = int(float(total_val))

        existing = db.query_one(
            "SELECT id FROM compras "
            "WHERE fecha=%s AND producto_nombre=%s AND cantidad=%s AND costo_unitario=%s",
            (fecha, producto, cantidad, cu)
        )
        if existing:
            count_skip += 1
        else:
            db.execute(
                """INSERT INTO compras
                   (fecha, hora, proveedor, producto_nombre, cantidad, costo_unitario, costo_total)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (fecha, hora, proveedor, producto, cantidad, cu, ct)
            )
            count_ins += 1

    logger.info("=" * 50)
    logger.info("MIGRACION COMPLETA")
    logger.info("  Compras: %d insertadas, %d omitidas.", count_ins, count_skip)
    logger.info("=" * 50)


if __name__ == "__main__":
    migrar()
