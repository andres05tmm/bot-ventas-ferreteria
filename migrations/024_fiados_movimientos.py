"""
migrations/024_fiados_movimientos.py

Crea la tabla fiados_movimientos — historial transaccional de cargos y abonos
por cliente. Antes los movimientos vivían solo en memoria (services/fiados_service
los appendaba al dict cache cargado por memoria.py) y se perdían en cada
reinicio del bot. Solo el saldo agregado (fiados.saldo_actual) sobrevivía.

Idempotente: CREATE TABLE IF NOT EXISTS. Seguro de re-ejecutar.

Ejecutar:
    railway run python migrations/024_fiados_movimientos.py
"""

# -- stdlib --
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
logger = logging.getLogger("024_fiados_movimientos")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS fiados_movimientos (
                    id               BIGSERIAL    PRIMARY KEY,
                    fiado_id         INTEGER      NOT NULL REFERENCES fiados(id) ON DELETE CASCADE,
                    fecha            DATE         NOT NULL DEFAULT CURRENT_DATE,
                    hora             TIME         NOT NULL DEFAULT (NOW()::time),
                    concepto         TEXT         NOT NULL DEFAULT '',
                    cargo            NUMERIC(15,2) NOT NULL DEFAULT 0,
                    abono            NUMERIC(15,2) NOT NULL DEFAULT 0,
                    saldo_resultante NUMERIC(15,2) NOT NULL,
                    creado_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    CHECK (cargo >= 0 AND abono >= 0)
                );
            """)
            logger.info("✓ Tabla fiados_movimientos creada (o ya existía)")

            # Índice principal: leer últimos N movimientos de un cliente.
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_fiados_mov_fiado_fecha
                    ON fiados_movimientos (fiado_id, fecha DESC, hora DESC, id DESC);
            """)
            logger.info("✓ Índice idx_fiados_mov_fiado_fecha OK")

            # Índice secundario: cleanup por antigüedad si se decide en el futuro.
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_fiados_mov_creado
                    ON fiados_movimientos (creado_at);
            """)
            logger.info("✓ Índice idx_fiados_mov_creado OK")

        conn.commit()
    logger.info("✅ Migración 024 completada")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
