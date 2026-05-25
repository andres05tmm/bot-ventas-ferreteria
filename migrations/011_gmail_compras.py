#!/usr/bin/env python3
"""
migrations/011_gmail_compras.py
Agrega la columna gmail_message_id a compras_fiscal para:
  1. Idempotencia: evitar registrar dos veces el mismo email
  2. Trazabilidad: saber qué registros vinieron de Gmail vs manuales
  3. Índice: búsqueda rápida por message_id en cada webhook

Ejecutar UNA VEZ en Railway:
    railway run python migrations/011_gmail_compras.py
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
logger = logging.getLogger("011_gmail_compras")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── 1. Columna gmail_message_id en compras_fiscal ─────────────────
            cur.execute("""
                ALTER TABLE compras_fiscal
                    ADD COLUMN IF NOT EXISTS gmail_message_id VARCHAR(200);
            """)
            logger.info("✓ compras_fiscal: columna gmail_message_id agregada")

            # ── 2. Índice único para idempotencia ─────────────────────────────
            # UNIQUE parcial: solo aplica cuando gmail_message_id no es NULL,
            # así los registros manuales (gmail_message_id=NULL) no se bloquean.
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_compras_fiscal_gmail_msg
                    ON compras_fiscal(gmail_message_id, producto_nombre)
                    WHERE gmail_message_id IS NOT NULL;
            """)
            logger.info("✓ índice único idx_compras_fiscal_gmail_msg creado")

            # ── 3. Índice para queries de estado/auditoría ────────────────────
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_compras_fiscal_gmail_not_null
                    ON compras_fiscal(created_at DESC)
                    WHERE gmail_message_id IS NOT NULL;
            """)
            logger.info("✓ índice de auditoría Gmail creado")

        conn.commit()
        logger.info("✅ Migración 011 aplicada correctamente")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
