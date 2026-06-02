"""
Migración 017: tabla ventas_pendientes_voz (P0.3).

Persiste las ventas que quedaron ESPERANDO MÉTODO DE PAGO en el canal de voz,
keyed por session_id. La memoria (ventas_state.ventas_pendientes) sigue siendo el
camino caliente, pero se borra si el server de Railway duerme/redeploya (free
tier) — y con eso se pierde la venta a medio cobrar. Esta tabla es el respaldo
durable: cuando la app vuelve (con su session_id persistente, P0.2) consulta
GET /chat/pendiente y la recupera.

Efímera por diseño: una fila por sesión de voz activa; se borra al registrar la
venta y se limpian las viejas por TTL.
"""

import logging
import db as _db

log = logging.getLogger("ferrebot.migrations.017")


def run():
    """Crea la tabla ventas_pendientes_voz si no existe (idempotente)."""
    _db.execute(
        """
        CREATE TABLE IF NOT EXISTS ventas_pendientes_voz (
            session_id   TEXT          PRIMARY KEY,
            chat_id      BIGINT        NOT NULL,
            vendedor     TEXT,
            ventas       JSONB         NOT NULL,
            created_at   TIMESTAMPTZ   DEFAULT NOW()
        );
        """,
        [],
    )
    # Índice para la limpieza por TTL (DELETE … WHERE created_at < …).
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS ventas_pendientes_voz_created_idx
            ON ventas_pendientes_voz (created_at);
        """,
        [],
    )
    log.info("Tabla ventas_pendientes_voz lista (P0.3).")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not _db.init_db():
        log.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        raise SystemExit(1)
    run()
