"""
migrations/016_bancolombia_transferencias.py

Crea la tabla bancolombia_transferencias para registrar (y deduplicar)
las notificaciones de transferencias recibidas a través de Gmail.

No almacena datos sensibles — solo el log de lo que llegó.
"""

import logging
import db as _db

log = logging.getLogger("ferrebot.migrations.016")


def run():
    """Ejecuta la migración 016."""
    log.info("Migración 016: creando tabla bancolombia_transferencias …")

    _db.execute(
        """
        CREATE TABLE IF NOT EXISTS bancolombia_transferencias (
            id                SERIAL PRIMARY KEY,
            gmail_message_id  TEXT        NOT NULL UNIQUE,
            fecha             DATE        NOT NULL,
            hora              TEXT        NOT NULL DEFAULT '',
            monto             BIGINT      NOT NULL DEFAULT 0,
            remitente         TEXT        NOT NULL DEFAULT '',
            descripcion       TEXT        NOT NULL DEFAULT '',
            tipo_transaccion  TEXT        NOT NULL DEFAULT '',
            referencia        TEXT        NOT NULL DEFAULT '',
            notificado        BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bancolombia_transferencias_fecha
            ON bancolombia_transferencias (fecha DESC)
        """
    )

    log.info("✅ Migración 016 completada")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _db.init_db()
    run()
