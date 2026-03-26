#!/usr/bin/env python3
"""
migrate_historico.py — Migra historico_ventas.json + historico_diario.json a la tabla
historico_ventas en PostgreSQL.

Idempotente — seguro para re-ejecutar (usa ON CONFLICT DO UPDATE).

Ejecutar UNA VEZ despues del deploy de Fase 2:
    railway run python migrate_historico.py
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
logger = logging.getLogger("migrate_historico")

# -- propios --
import db


def migrar():
    """Migra historico_ventas.json + historico_diario.json a la tabla historico_ventas en Postgres."""
    # Inicializar DB
    if not db.init_db():
        print("ERROR: DATABASE_URL no configurado o Postgres no disponible")
        sys.exit(1)

    if not db.DB_DISPONIBLE:
        print("ERROR: DATABASE_URL no configurado o Postgres no disponible")
        sys.exit(1)

    # -- Leer historico_ventas.json (fuente principal: {fecha: monto}) --
    HISTORICO_FILE = os.getenv("HISTORICO_FILE", "historico_ventas.json")
    historico = {}
    if os.path.exists(HISTORICO_FILE):
        with open(HISTORICO_FILE, encoding="utf-8") as f:
            historico = json.load(f)
        logger.info(f"historico_ventas.json: {len(historico)} fechas encontradas")
    else:
        logger.warning(f"AVISO: {HISTORICO_FILE} no encontrado -- continuando con historico_diario.json")

    # -- Leer historico_diario.json (datos enriquecidos: {fecha: {ventas, efectivo, ...}}) --
    DIARIO_FILE = "historico_diario.json"
    diario = {}
    if os.path.exists(DIARIO_FILE):
        with open(DIARIO_FILE, encoding="utf-8") as f:
            diario = json.load(f)
        logger.info(f"historico_diario.json: {len(diario)} fechas encontradas")
    else:
        logger.warning(f"AVISO: {DIARIO_FILE} no encontrado -- solo se migraran totales")

    # -- Fusionar ambas fuentes --
    # Todas las fechas que aparecen en cualquiera de los dos archivos
    todas_fechas = set(historico.keys()) | set(diario.keys())
    logger.info(f"Total fechas unicas a migrar: {len(todas_fechas)}")

    count_insert = 0
    count_update = 0

    for fecha in sorted(todas_fechas):
        monto_total = int(historico.get(fecha, 0))
        dd = diario.get(fecha, {})

        # Si diario tiene ventas y historico no, usar diario
        if monto_total == 0 and dd.get("ventas", 0) > 0:
            monto_total = int(dd["ventas"])

        # Validar fecha formato YYYY-MM-DD
        parts = fecha.split("-")
        if len(parts) != 3 or len(parts[0]) != 4:
            logger.warning(f"  SKIP fecha invalida: {fecha}")
            continue

        # Check if already exists
        existing = db.query_one("SELECT fecha FROM historico_ventas WHERE fecha = %s", (fecha,))

        db.execute(
            """INSERT INTO historico_ventas
               (fecha, ventas, efectivo, transferencia, datafono, n_transacciones, gastos, abonos_proveedores)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (fecha) DO UPDATE SET
                 ventas = EXCLUDED.ventas,
                 efectivo = EXCLUDED.efectivo,
                 transferencia = EXCLUDED.transferencia,
                 datafono = EXCLUDED.datafono,
                 n_transacciones = EXCLUDED.n_transacciones,
                 gastos = EXCLUDED.gastos,
                 abonos_proveedores = EXCLUDED.abonos_proveedores,
                 updated_at = NOW()""",
            (
                fecha,
                monto_total,
                int(dd.get("efectivo", 0)),
                int(dd.get("transferencia", 0)),
                int(dd.get("datafono", 0)),
                int(dd.get("n_transacciones", 0)),
                int(dd.get("gastos", 0)),
                int(dd.get("abonos_proveedores", 0)),
            )
        )

        if existing:
            count_update += 1
        else:
            count_insert += 1

    # -- Resumen --
    logger.info("=" * 50)
    logger.info("MIGRACION COMPLETADA")
    logger.info(f"  Insertados:  {count_insert}")
    logger.info(f"  Actualizados: {count_update}")
    logger.info(f"  Total procesado: {count_insert + count_update}")
    logger.info("=" * 50)

    # Verificar
    total_rows = db.query_one("SELECT COUNT(*) as cnt FROM historico_ventas")
    logger.info(f"Verificacion: {total_rows['cnt']} filas en historico_ventas")


if __name__ == "__main__":
    migrar()
