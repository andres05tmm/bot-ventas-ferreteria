#!/usr/bin/env python3
"""
migrate_gastos_caja.py — Migra gastos y caja_actual de memoria.json a PostgreSQL.

Idempotente — seguro para re-ejecutar.

Ejecutar UNA VEZ despues del deploy de Fase 2:
    railway run python migrate_gastos_caja.py
"""

# -- stdlib --
import json
import logging
import os
import sys

# Configurar logging basico para ver output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("migrate_gastos_caja")

# -- propios --
import db


def migrar():
    """Migra gastos y caja_actual de memoria.json a las tablas PostgreSQL."""
    # Inicializar DB
    if not db.init_db():
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    if not db.DB_DISPONIBLE:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    # Leer memoria.json
    memoria_file = os.getenv("MEMORIA_FILE", "memoria.json")
    if not os.path.exists(memoria_file):
        logger.error(f"No se encontro {memoria_file}")
        sys.exit(1)

    with open(memoria_file, encoding="utf-8") as f:
        mem = json.load(f)

    # ── Migrar gastos ─────────────────────────────────────────────────────────
    gastos_dict = mem.get("gastos", {})
    # gastos_dict format: {"2026-03-20": [{"concepto":..., "monto":..., "categoria":..., "origen":..., "hora":...}], ...}

    count_gastos = 0
    count_skip   = 0
    total_gastos = sum(len(v) for v in gastos_dict.values())
    logger.info(f"Migrando gastos: {total_gastos} registros en {len(gastos_dict)} dias...")

    for fecha, lista in gastos_dict.items():
        for gasto in lista:
            concepto = gasto.get("concepto", "")
            monto    = int(gasto.get("monto", 0))
            # Deduplication: check if a gasto with same fecha+concepto+monto already exists
            existing = db.query_one(
                "SELECT id FROM gastos WHERE fecha = %s AND concepto = %s AND monto = %s",
                (fecha, concepto, monto)
            )
            if not existing:
                db.execute(
                    """INSERT INTO gastos (fecha, hora, concepto, monto, categoria, origen)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (fecha, gasto.get("hora"), concepto, monto,
                     gasto.get("categoria", "General"),
                     gasto.get("origen", "caja"))
                )
                count_gastos += 1
            else:
                count_skip += 1

    logger.info(f"Gastos migrados: {count_gastos} (omitidos por duplicado: {count_skip})")

    # ── Migrar caja_actual ────────────────────────────────────────────────────
    caja = mem.get("caja_actual", {})
    if caja and caja.get("fecha"):
        db.execute(
            """INSERT INTO caja (fecha, abierta, monto_apertura, efectivo, transferencias, datafono)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (fecha) DO UPDATE SET
                 abierta = EXCLUDED.abierta,
                 monto_apertura = EXCLUDED.monto_apertura,
                 efectivo = EXCLUDED.efectivo,
                 transferencias = EXCLUDED.transferencias,
                 datafono = EXCLUDED.datafono""",
            (caja["fecha"], caja.get("abierta", False),
             int(caja.get("monto_apertura", 0)),
             int(caja.get("efectivo", 0)),
             int(caja.get("transferencias", 0)),
             int(caja.get("datafono", 0)))
        )
        logger.info(f"Caja migrada: fecha={caja['fecha']}, abierta={caja.get('abierta')}")
    else:
        logger.info("Caja: sin datos para migrar (caja_actual vacio o sin fecha)")

    # ── Resumen final ─────────────────────────────────────────────────────────
    logger.info("=" * 50)
    logger.info("MIGRACION COMPLETA")
    logger.info(f"  Gastos insertados: {count_gastos}")
    logger.info(f"  Gastos omitidos:   {count_skip}")
    caja_info = caja.get("fecha", "ninguna") if caja else "ninguna"
    logger.info(f"  Caja fecha:        {caja_info}")
    logger.info("=" * 50)


if __name__ == "__main__":
    migrar()
