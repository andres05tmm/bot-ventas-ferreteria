# Migrado desde migrate_fiados.py (raíz del proyecto)
# Este archivo es una copia exacta. El original se mantiene en raíz hasta que Phase 1 esté verde.
#!/usr/bin/env python3
"""
migrate_fiados.py — Migra fiados de memoria.json a PostgreSQL.

Idempotente — seguro para re-ejecutar.

Ejecutar UNA VEZ despues del deploy de Fase 4:
    railway run python migrate_fiados.py
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
logger = logging.getLogger("migrate_fiados")

# -- propios --
import db


def migrar():
    """Migra el dict fiados de memoria.json a las tablas fiados + fiados_historial."""
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

    fiados = mem.get("fiados", {})
    if not fiados:
        logger.info("Nada que migrar: fiados vacio o ausente")
        return

    logger.info("Migrando %d clientes con fiado...", len(fiados))
    count_fiados = 0
    count_movs   = 0
    skip_movs    = 0

    for nombre_cliente, datos in fiados.items():
        saldo = int(float(datos.get("saldo", 0)))

        # Get or create fiado record (idempotent by name)
        existing = db.query_one(
            "SELECT id FROM fiados WHERE nombre = %s", (nombre_cliente,)
        )
        if existing:
            fiado_id = existing["id"]
            db.execute(
                "UPDATE fiados SET deuda=%s, updated_at=NOW() WHERE id=%s",
                (saldo, fiado_id)
            )
            logger.info("  Fiado actualizado: %s (saldo=%d)", nombre_cliente, saldo)
        else:
            row = db.execute_returning(
                "INSERT INTO fiados (nombre, deuda) VALUES (%s, %s) RETURNING id",
                (nombre_cliente, saldo)
            )
            fiado_id = row["id"]
            count_fiados += 1
            logger.info("  Fiado creado: %s (saldo=%d)", nombre_cliente, saldo)

        # Migrate movimientos with check-before-insert
        for mov in datos.get("movimientos", []):
            fecha_mov = str(mov.get("fecha", ""))[:10] or "1970-01-01"
            cargo     = float(mov.get("cargo", 0))
            abono     = float(mov.get("abono", 0))
            tipo      = "cargo" if cargo > 0 else "abono"
            monto     = int(cargo if cargo > 0 else abono)
            concepto  = str(mov.get("concepto", ""))

            existing_mov = db.query_one(
                "SELECT id FROM fiados_historial "
                "WHERE fiado_id=%s AND fecha=%s AND monto=%s AND concepto=%s",
                (fiado_id, fecha_mov, monto, concepto)
            )
            if existing_mov:
                skip_movs += 1
            else:
                db.execute(
                    """INSERT INTO fiados_historial
                       (fiado_id, tipo, monto, concepto, fecha)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (fiado_id, tipo, monto, concepto, fecha_mov)
                )
                count_movs += 1

    logger.info("=" * 50)
    logger.info("MIGRACION COMPLETA")
    logger.info(
        "  Fiados creados: %d. Movimientos: %d insertados, %d omitidos.",
        count_fiados, count_movs, skip_movs
    )
    logger.info("=" * 50)


if __name__ == "__main__":
    migrar()
