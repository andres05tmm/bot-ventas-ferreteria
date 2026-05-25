"""
migrations/020_memoria_entidades.py — Capa 4 de memoria: notas estructuradas
sobre productos, aliases y vendedores generadas por el compresor nocturno.

Cada noche a las 3 AM Colombia un job corre Haiku 4.5 sobre las conversaciones
del día que terminaron en venta registrada y genera notas tipo:

  producto:drywall 6mm   → "se pide seguido con tornillos 6x1; clientes mayoristas suelen llevar 10+"
  producto:thinner       → "subió de precio el 12 abr; vender de a galón cuando es para repintar"
  alias:tiner            → "thinner"
  vendedor:andres        → "vende drywall principalmente entre 7am y 11am"

Estas notas se inyectan en la parte dinámica del system prompt cuando el mensaje
del vendedor menciona la entidad correspondiente, dándole a Claude contexto que
no requiere mandar todo el histórico.

Esquema:
  memoria_entidades
    ├── id              SERIAL PK
    ├── tipo            TEXT  ('producto' | 'alias' | 'vendedor')
    ├── entidad_key     TEXT  (nombre normalizado lowercase, sin tildes)
    ├── nota            TEXT  (texto generado por Haiku, max ~200 chars)
    ├── confidence      REAL  (0.0–1.0; default 1.0)
    ├── fecha_generada  DATE  (día Colombia en que se generó)
    ├── vigente         BOOL  (FALSE = invalidada manualmente o reemplazada)
    └── creado_en       TIMESTAMPTZ DEFAULT NOW()

  UNIQUE(tipo, entidad_key, fecha_generada) — evita duplicados si el job
  corre dos veces el mismo día.

  INDEX (tipo, entidad_key, vigente) — lookup rápido para inyección en prompt.

Ejecutar:
    railway run python migrations/020_memoria_entidades.py
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

log = logging.getLogger("ferrebot.migrations.020")


def run():
    """
    Crea memoria_entidades + índices. Idempotente.
    """
    _db.execute(
        """
        CREATE TABLE IF NOT EXISTS memoria_entidades (
            id              SERIAL       PRIMARY KEY,
            tipo            TEXT         NOT NULL CHECK (tipo IN ('producto','alias','vendedor')),
            entidad_key     TEXT         NOT NULL,
            nota            TEXT         NOT NULL,
            confidence      REAL         NOT NULL DEFAULT 1.0,
            fecha_generada  DATE         NOT NULL,
            vigente         BOOLEAN      NOT NULL DEFAULT TRUE,
            creado_en       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            CONSTRAINT memoria_entidades_unica
                UNIQUE (tipo, entidad_key, fecha_generada)
        );
        """,
        [],
    )
    log.info("Tabla memoria_entidades lista.")

    # Lookup principal: traer notas vigentes de una entidad ordenadas por fecha
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS memoria_entidades_lookup_idx
            ON memoria_entidades (tipo, entidad_key, vigente, fecha_generada DESC);
        """,
        [],
    )
    log.info("Índice memoria_entidades_lookup_idx listo.")

    # Cleanup por antigüedad (job que purga notas > 90 días)
    _db.execute(
        """
        CREATE INDEX IF NOT EXISTS memoria_entidades_fecha_idx
            ON memoria_entidades (fecha_generada);
        """,
        [],
    )
    log.info("Índice memoria_entidades_fecha_idx listo.")

    log.info("Migración 020 completada.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not _db.DB_DISPONIBLE:
        _db.init_db()
    run()
