#!/usr/bin/env python3
"""
migrations/012_ferrebot_config.py
Crea la tabla ferrebot_config para almacenar configuración clave-valor del sistema.

Uso actual:
  - gmail_last_history_id: último historyId de Gmail procesado exitosamente.
    Permite que el webhook use el rango correcto entre notificaciones,
    incluso tras reinicios del servicio en Railway.

Ejecutar UNA VEZ en Railway:
    railway run python migrations/012_ferrebot_config.py
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
logger = logging.getLogger("012_ferrebot_config")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ferrebot_config (
                    clave       VARCHAR(100) PRIMARY KEY,
                    valor       TEXT,
                    updated_at  TIMESTAMP DEFAULT NOW()
                );
            """)
            logger.info("✓ tabla ferrebot_config creada (o ya existía)")

        conn.commit()
        logger.info("✅ Migración 012 aplicada correctamente")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
