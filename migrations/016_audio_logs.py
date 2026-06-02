"""
Migración 016: tabla audio_logs para registrar transcripciones de audio.

Permite analizar errores de Whisper y mantener el diccionario
_CORRECCIONES_AUDIO actualizado con el tiempo.

P0.1 (diagnóstico asistente de voz): se EXTIENDE audio_logs con columnas de
telemetría por turno del canal de voz. Las columnas nuevas son nullable para
no romper el INSERT existente del bot (chat_id, vendedor, texto_*). Una fila
por etapa (transcribir / chat), correlacionadas por turn_id.
"""

import logging
import db as _db

log = logging.getLogger("ferrebot.migrations.016")


# Columnas de telemetría de voz (P0.1). Todas nullable e idempotentes.
_COLUMNAS_VOZ: list[tuple[str, str]] = [
    ("canal",               "TEXT"),       # "" = dashboard/bot, "voz" = asistente
    ("turn_id",             "TEXT"),       # UUID por turno: une fila STT + fila chat
    ("session_id",          "TEXT"),       # sesión de voz (solo lo tiene /chat)
    ("no_speech_prob",      "FLOAT"),      # promedio de segmentos de Whisper
    ("descartado_silencio", "BOOLEAN"),    # True si se descartó como silencio/alucinación
    ("modelo",              "TEXT"),       # "haiku" | "sonnet" (riel interno de ai/)
    ("riel",                "TEXT"),       # R2 | R2-precio | CONFIRM-VOZ | ninguno
    ("latencia_stt_ms",     "INTEGER"),    # latencia de transcripción
    ("latencia_claude_ms",  "INTEGER"),    # latencia de Claude
    ("pendiente",           "BOOLEAN"),    # True si el turno dejó venta pendiente
    ("resultado",           "TEXT"),       # transcrito|silencio|error|respuesta|venta_registrada|pendiente_pago|consulta
]


def run():
    """Crea la tabla audio_logs si no existe y agrega las columnas de telemetría."""
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

    # ── Telemetría de voz (P0.1): columnas nuevas, idempotentes ──────────────
    for _col, _tipo in _COLUMNAS_VOZ:
        _db.execute(
            f"ALTER TABLE audio_logs ADD COLUMN IF NOT EXISTS {_col} {_tipo};",
            []
        )
    # Índice para consultar la telemetría de voz por turno y por fecha.
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS audio_logs_turn_id_idx
            ON audio_logs (turn_id);
        """,
        []
    )
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS audio_logs_canal_fecha_idx
            ON audio_logs (canal, fecha DESC);
        """,
        []
    )
    log.info("Tabla audio_logs lista (con telemetría de voz P0.1).")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not _db.init_db():
        log.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        raise SystemExit(1)
    run()
