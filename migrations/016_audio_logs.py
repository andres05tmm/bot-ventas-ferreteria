"""
Migración 016: tabla audio_logs para registrar transcripciones de audio.

Permite analizar errores de Whisper y mantener el diccionario
_CORRECCIONES_AUDIO actualizado con el tiempo.
"""

import logging
import db as _db

log = logging.getLogger("ferrebot.migrations.016")


def run():
    """Crea la tabla audio_logs si no existe."""
    _db.execute(
        """
        CREATE TABLE IF NOT EXISTS audio_logs (
            id               SERIAL PRIMARY KEY,
            chat_id          BIGINT        NOT NULL,
            vendedor         TEXT          NOT NULL,
            texto_original   TEXT          NOT NULL,
            texto_corregido  TEXT          NOT NULL,
            duracion_seg     FLOAT,
            fecha            TIMESTAMPTZ   DEFAULT NOW()
        );
        """,
        []
    )
    # Índice para consultas por fecha (análisis semanal)
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS audio_logs_fecha_idx
            ON audio_logs (fecha DESC);
        """,
        []
    )
    log.info("Tabla audio_logs lista.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
