"""
migrations/017_budget_tracking.py

Crea la tabla api_costo_diario para tracking de uso y costo de Claude por
vendedor y día. Permite:

  - Hard limits por vendedor/modelo/día (ej. 300 Sonnet + 1000 Haiku)
  - Reportería de costo real por vendedor
  - Debugging de qué vendedor gasta más y en qué intents

Ejecutar:
    railway run python migrations/017_budget_tracking.py
"""

# -- stdlib --
import os
import sys
import logging

# ── Asegurar que la raíz del proyecto esté en sys.path ───────────────────────
# Necesario para que "import db" funcione al ejecutar desde la raíz
# (railway run python migrations/017_budget_tracking.py).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# -- propios --
import db as _db

log = logging.getLogger("ferrebot.migrations.017")


def run():
    """Crea api_costo_diario con índices. Idempotente."""
    _db.execute(
        """
        CREATE TABLE IF NOT EXISTS api_costo_diario (
            id                    SERIAL       PRIMARY KEY,
            fecha                 DATE         NOT NULL,
            vendedor_id           BIGINT       NOT NULL,
            modelo                TEXT         NOT NULL,
            llamadas              INTEGER      NOT NULL DEFAULT 0,
            input_tokens          BIGINT       NOT NULL DEFAULT 0,
            cache_read_tokens     BIGINT       NOT NULL DEFAULT 0,
            cache_created_tokens  BIGINT       NOT NULL DEFAULT 0,
            output_tokens         BIGINT       NOT NULL DEFAULT 0,
            costo_usd             NUMERIC(12,6) NOT NULL DEFAULT 0,
            creado                TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            actualizado           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            UNIQUE (fecha, vendedor_id, modelo)
        );
        """,
        [],
    )
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS api_costo_diario_fecha_idx
            ON api_costo_diario (fecha DESC);
        """,
        [],
    )
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS api_costo_diario_vendedor_idx
            ON api_costo_diario (vendedor_id, fecha DESC);
        """,
        [],
    )
    log.info("Tabla api_costo_diario lista.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Inicializar DB si se corre directo (no viene de start.py)
    if not _db.DB_DISPONIBLE:
        _db.init_db()
    run()
