"""
migrations/023_insertar_ds5_manual.py
Inserta el registro del DS5 que no quedó guardado por el bug de FK (ya corregido).
DS5 fue transmitido exitosamente a DIAN el 2026-05-13 con CUDE confirmado.

Ejecutar UNA VEZ:
    railway run python migrations/023_insertar_ds5_manual.py
"""

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
logger = logging.getLogger("023_insertar_ds5_manual")

import db as _db

CUDE_DS5  = "f8a18d33f686fd5357d20350bf2637451e82c27ac24f97e662c3a6e7f600e5e922eee302726537fe704c19ac50bfbf16"
FECHA_DS5 = "2026-05-13"
VALOR_DS5 = 2000000.00


def run():
    # Verificar que no exista ya
    existe = _db.query_one(
        "SELECT id FROM documentos_soporte WHERE consecutivo = '5'",
    )
    if existe:
        logger.info("DS5 ya existe en documentos_soporte (id=%s) — nada que hacer.", existe["id"])
        return

    # Buscar el id real de la CC-001 (la del mes de mayo 2026)
    cc_row = _db.query_one(
        "SELECT id FROM cuentas_cobro WHERE consecutivo = 1 ORDER BY id DESC LIMIT 1",
    )
    cc_id = cc_row["id"] if cc_row else None
    if cc_id:
        logger.info("CC-001 encontrada con id=%s — vinculando.", cc_id)
    else:
        logger.warning("CC-001 no encontrada — DS5 se insertará sin FK de CC.")

    _db.execute(
        """
        INSERT INTO documentos_soporte
            (consecutivo, fecha, valor, cude, estado_dian, cuenta_cobro_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        ["5", FECHA_DS5, VALOR_DS5, CUDE_DS5, "transmitido", cc_id],
    )
    logger.info("✅ DS5 insertado en documentos_soporte — CUDE: %s…", CUDE_DS5[:20])


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
