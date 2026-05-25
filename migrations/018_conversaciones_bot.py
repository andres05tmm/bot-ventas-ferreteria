"""
migrations/018_conversaciones_bot.py

Crea la tabla conversaciones_bot — Capa 1 de memoria del bot.

Persiste cada turno (user / assistant) por chat_id para sobrevivir restarts
de Railway y permitir hidratar el historial en caliente. La in-memory cache
de ventas_state.historiales sigue siendo la fuente primaria; la DB solo se
usa para hidratar cuando la cache está vacía y para auditoría.

Esquema diseñado pensando en Capa 3 (FTS5/Postgres FTS) — la columna
content_tsv tiene un GIN index sobre to_tsvector('spanish', content) para
búsquedas por palabras clave en el histórico de conversaciones.

Ejecutar:
    railway run python migrations/018_conversaciones_bot.py
"""

# -- stdlib --
import os
import sys
import logging

# ── Asegurar que la raíz del proyecto esté en sys.path ───────────────────────
# Necesario para que "import db" funcione al ejecutar desde la raíz
# (railway run python migrations/018_conversaciones_bot.py).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# -- propios --
import db as _db

log = logging.getLogger("ferrebot.migrations.018")


def run():
    """
    Crea conversaciones_bot con índices. Idempotente — se puede correr N veces.
    """
    _db.execute(
        """
        CREATE TABLE IF NOT EXISTS conversaciones_bot (
            id              BIGSERIAL    PRIMARY KEY,
            chat_id         BIGINT       NOT NULL,
            vendedor_id     BIGINT,
            role            TEXT         NOT NULL CHECK (role IN ('user','assistant','system')),
            content         TEXT         NOT NULL,
            modelo          TEXT,
            tokens_input    INTEGER,
            tokens_output   INTEGER,
            creado          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );
        """,
        [],
    )

    # Índice principal: leer los últimos N turnos de un chat (hidratación)
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS conversaciones_bot_chat_creado_idx
            ON conversaciones_bot (chat_id, creado DESC);
        """,
        [],
    )

    # Índice secundario: jobs de cleanup por antigüedad
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS conversaciones_bot_creado_idx
            ON conversaciones_bot (creado);
        """,
        [],
    )

    # Índice FTS: búsqueda full-text en español sobre el content.
    # Lo usaremos en Capa 3 para que el bot pueda recordar conversaciones viejas
    # ("¿qué le vendí ayer a Pedro?") sin tirar todas las filas a Claude.
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS conversaciones_bot_content_fts_idx
            ON conversaciones_bot
            USING GIN (to_tsvector('spanish', content));
        """,
        [],
    )

    # Índice por vendedor para reportería ("¿con qué vendedores conversó más?")
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS conversaciones_bot_vendedor_idx
            ON conversaciones_bot (vendedor_id, creado DESC)
            WHERE vendedor_id IS NOT NULL;
        """,
        [],
    )

    log.info("Tabla conversaciones_bot lista (con índices y FTS).")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Inicializar DB si se corre directo (no viene de start.py)
    if not _db.DB_DISPONIBLE:
        _db.init_db()
    run()
