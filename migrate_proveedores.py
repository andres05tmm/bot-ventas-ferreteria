#!/usr/bin/env python3
"""
migrate_proveedores.py — Migra cuentas_por_pagar de memoria.json a PostgreSQL.

Idempotente — seguro para re-ejecutar.

Ejecutar UNA VEZ despues del deploy de Fase 4:
    railway run python migrate_proveedores.py
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
logger = logging.getLogger("migrate_proveedores")

# -- propios --
import db


def migrar():
    """Migra cuentas_por_pagar de memoria.json a facturas_proveedores + facturas_abonos."""
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

    facturas = mem.get("cuentas_por_pagar", [])
    if not facturas:
        logger.info("Nada que migrar: cuentas_por_pagar vacio o ausente")
        return

    logger.info("Migrando %d facturas...", len(facturas))
    count_fac = 0
    skip_fac  = 0
    count_abo = 0
    skip_abo  = 0

    for factura in facturas:
        fac_id = str(factura.get("id", "")).upper()
        if not fac_id:
            logger.warning("Factura sin id — omitida: %s", factura)
            skip_fac += 1
            continue

        db.execute(
            """INSERT INTO facturas_proveedores
               (id, proveedor, descripcion, total, pagado, pendiente, estado, fecha, foto_url, foto_nombre)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            (
                fac_id,
                str(factura.get("proveedor", "")).strip(),
                str(factura.get("descripcion", "")).strip(),
                int(float(factura.get("total", 0))),
                int(float(factura.get("pagado", 0))),
                int(float(factura.get("pendiente", 0))),
                str(factura.get("estado", "pendiente")),
                str(factura.get("fecha", ""))[:10] or "1970-01-01",
                str(factura.get("foto_url", "")),
                str(factura.get("foto_nombre", "")),
            )
        )
        # Verify insertion (ON CONFLICT DO NOTHING skips on duplicate)
        existing_check = db.query_one(
            "SELECT id FROM facturas_proveedores WHERE id = %s", (fac_id,)
        )
        if existing_check:
            count_fac += 1
        else:
            skip_fac += 1

        # Migrate abonos with check-before-insert
        for abono in factura.get("abonos", []):
            fecha_abo = str(abono.get("fecha", ""))[:10] or "1970-01-01"
            monto_abo = int(float(abono.get("monto", 0)))
            existing_abo = db.query_one(
                "SELECT id FROM facturas_abonos WHERE factura_id=%s AND fecha=%s AND monto=%s",
                (fac_id, fecha_abo, monto_abo)
            )
            if existing_abo:
                skip_abo += 1
            else:
                db.execute(
                    """INSERT INTO facturas_abonos (factura_id, monto, fecha, foto_url, foto_nombre)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (fac_id, monto_abo, fecha_abo,
                     str(abono.get("foto_url", "")),
                     str(abono.get("foto_nombre", "")))
                )
                count_abo += 1

    logger.info("=" * 50)
    logger.info("MIGRACION COMPLETA")
    logger.info(
        "  Facturas: %d insertadas, %d omitidas. Abonos: %d insertados, %d omitidos.",
        count_fac, skip_fac, count_abo, skip_abo
    )
    logger.info("=" * 50)


if __name__ == "__main__":
    migrar()
