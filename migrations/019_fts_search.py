"""
migrations/019_fts_search.py — Capa 3 de memoria: búsqueda histórica FTS + trigram.

Amplía la infraestructura de búsqueda full-text para que el bot pueda responder
preguntas del vendedor sobre su histórico sin mandar todo el contexto a Claude:

    "¿qué le vendí ayer a Pedro?"    → buscar en ventas_detalle
    "¿de qué hablamos con Juan?"     → buscar en conversaciones_bot
    "¿cuándo compraron drwayll?"     → tolerar typos vía pg_trgm

La migración 018 ya montó `to_tsvector('spanish', content)` sobre
conversaciones_bot. Acá completamos:

  * pg_trgm como extensión (idempotente) — permite similarity() para fuzzy
  * GIN FTS sobre ventas_detalle.producto_nombre (búsqueda semántica)
  * GIN trgm sobre ventas_detalle.producto_nombre (tolerancia a typos)
  * GIN trgm sobre conversaciones_bot.content (typos en conversaciones)

Todas las operaciones son idempotentes — la migración puede correrse N veces.

Ejecutar:
    railway run python migrations/019_fts_search.py
"""

# -- stdlib --
import os
import sys
import logging

# ── Asegurar que la raíz del proyecto esté en sys.path ───────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# -- propios --
import db as _db

log = logging.getLogger("ferrebot.migrations.019")


def run():
    """
    Crea extensión pg_trgm e índices GIN para búsqueda híbrida FTS + trigram.
    Idempotente.
    """
    # 1) Extensión pg_trgm — requiere superuser pero Railway managed PG lo permite.
    #    Si falla (permisos), registramos warning pero no abortamos: el resto
    #    de la migración (índices FTS) aún es útil.
    try:
        _db.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;", [])
        log.info("Extensión pg_trgm lista.")
    except Exception as e:
        log.warning(
            "No se pudo crear extensión pg_trgm (%s). "
            "Búsqueda fuzzy quedará deshabilitada; FTS nativo seguirá funcionando.",
            e,
        )

    # 2) Índice FTS sobre ventas_detalle.producto_nombre.
    #    Usamos 'spanish' para que stemming reconozca plurales (tornillos/tornillo)
    #    y conjugaciones (pintura/pintar).
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS ventas_detalle_producto_fts_idx
            ON ventas_detalle
            USING GIN (to_tsvector('spanish', producto_nombre));
        """,
        [],
    )
    log.info("Índice FTS sobre ventas_detalle.producto_nombre listo.")

    # 3) Índice trigram sobre ventas_detalle.producto_nombre.
    #    Tolera typos: "drwayll" encuentra "drywall". Requiere pg_trgm instalado.
    try:
        _db.execute(
            """
            CREATE INDEX IF NOT EXISTS ventas_detalle_producto_trgm_idx
                ON ventas_detalle
                USING GIN (producto_nombre gin_trgm_ops);
            """,
            [],
        )
        log.info("Índice trigram sobre ventas_detalle.producto_nombre listo.")
    except Exception as e:
        log.warning(
            "No se pudo crear índice trigram sobre ventas_detalle (%s). "
            "Búsqueda con typos quedará deshabilitada para productos.",
            e,
        )

    # 4) Índice trigram sobre conversaciones_bot.content.
    #    La migración 018 ya creó el FTS nativo; este lo complementa con fuzzy.
    try:
        _db.execute(
            """
            CREATE INDEX IF NOT EXISTS conversaciones_bot_content_trgm_idx
                ON conversaciones_bot
                USING GIN (content gin_trgm_ops);
            """,
            [],
        )
        log.info("Índice trigram sobre conversaciones_bot.content listo.")
    except Exception as e:
        log.warning(
            "No se pudo crear índice trigram sobre conversaciones_bot (%s). "
            "Búsqueda con typos quedará deshabilitada para conversaciones.",
            e,
        )

    log.info("Migración 019 completada.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not _db.DB_DISPONIBLE:
        _db.init_db()
    run()
