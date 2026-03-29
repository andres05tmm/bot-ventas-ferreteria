"""
services/caja_service.py — Logica de caja y gastos.
Extraido de memoria.py (Tarea H).

Imports permitidos: logging, datetime, db (lazy), config.
NUNCA importar de memoria a nivel de modulo — evita circular import.
"""

# -- stdlib --
import logging
from datetime import datetime

# -- propios --
import config

logger = logging.getLogger("ferrebot.services.caja")


# ─────────────────────────────────────────────
# CAJA — Postgres helpers privados
# ─────────────────────────────────────────────

def _guardar_gasto_postgres(gasto: dict):
    """Inserta un gasto en Postgres. No-fatal: logger.warning en caso de error."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return
        hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        hora_str = gasto.get("hora")
        _db.execute(
            """INSERT INTO gastos (fecha, hora, concepto, monto, categoria, origen)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (hoy, hora_str, gasto.get("concepto", ""), int(gasto.get("monto", 0)),
             gasto.get("categoria", "General"), gasto.get("origen", "caja"))
        )
    except Exception as e:
        logger.warning("Error guardando gasto en Postgres: %s", e)


def _guardar_caja_postgres(caja: dict):
    """UPSERT caja del dia en Postgres. No-fatal."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return
        fecha = caja.get("fecha")
        if not fecha:
            return
        _db.execute(
            """INSERT INTO caja (fecha, abierta, monto_apertura, efectivo, transferencias, datafono, cerrada_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (fecha) DO UPDATE SET
                 abierta = EXCLUDED.abierta,
                 monto_apertura = EXCLUDED.monto_apertura,
                 efectivo = EXCLUDED.efectivo,
                 transferencias = EXCLUDED.transferencias,
                 datafono = EXCLUDED.datafono,
                 cerrada_at = CASE WHEN EXCLUDED.abierta = FALSE THEN NOW() ELSE caja.cerrada_at END""",
            (fecha, caja.get("abierta", False), int(caja.get("monto_apertura", 0)),
             int(caja.get("efectivo", 0)), int(caja.get("transferencias", 0)),
             int(caja.get("datafono", 0)),
             None)
        )
    except Exception as e:
        logger.warning("Error guardando caja en Postgres: %s", e)


def _leer_caja_postgres() -> dict | None:
    """Lee el estado de caja del dia de Postgres. Retorna None si no hay datos o DB no disponible."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return None
        hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        row = _db.query_one("SELECT * FROM caja WHERE fecha = %s", (hoy,))
        if not row:
            return None
        return {
            "abierta": row["abierta"],
            "fecha": str(row["fecha"]),
            "monto_apertura": int(row["monto_apertura"]),
            "efectivo": int(row["efectivo"]),
            "transferencias": int(row["transferencias"]),
            "datafono": int(row["datafono"]),
        }
    except Exception as e:
        logger.warning("Error leyendo caja de Postgres: %s", e)
        return None


def _leer_gastos_postgres(fecha_inicio: str, fecha_fin: str) -> list[dict]:
    """Lee gastos del rango de fechas desde Postgres. Retorna lista vacia si falla."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return []
        rows = _db.query_all(
            "SELECT * FROM gastos WHERE fecha >= %s AND fecha <= %s ORDER BY fecha DESC, hora DESC",
            (fecha_inicio, fecha_fin)
        )
        return [{
            "concepto": r["concepto"],
            "monto": int(r["monto"]),
            "categoria": r.get("categoria") or "General",
            "origen": r.get("origen") or "caja",
            "hora": str(r["hora"])[:5] if r.get("hora") else "",
            "fecha": str(r["fecha"]),
        } for r in rows]
    except Exception as e:
        logger.warning("Error leyendo gastos de Postgres: %s", e)
        return []


# ─────────────────────────────────────────────
# CAJA
# ─────────────────────────────────────────────

def cargar_caja() -> dict:
    pg = _leer_caja_postgres()
    if pg is not None:
        return pg
    return {
        "abierta": False, "fecha": None, "monto_apertura": 0,
        "efectivo": 0, "transferencias": 0, "datafono": 0,
    }


def guardar_caja(caja: dict):
    import db as _db
    if not _db.DB_DISPONIBLE:
        raise RuntimeError("⚠️ Base de datos no disponible. Intenta de nuevo en un momento.")
    _guardar_caja_postgres(caja)


def obtener_resumen_caja() -> str:
    import db as _db
    caja = cargar_caja()
    if not caja.get("abierta"):
        return "La caja no está abierta hoy."
    if not _db.DB_DISPONIBLE:
        return "⚠️ Base de datos no disponible. No se puede obtener el resumen de caja ahora."
    from datetime import date as _date
    row = _db.query_one(
        "SELECT COALESCE(SUM(total), 0) AS total, COUNT(*) AS num_ventas"
        " FROM ventas WHERE fecha = %s",
        (_date.today(),),
    )
    total_ventas_hoy = int(row["total"]) if row else 0
    num_ventas_hoy   = int(row["num_ventas"]) if row else 0
    gastos_hoy        = cargar_gastos_hoy()
    total_gastos_caja = sum(g["monto"] for g in gastos_hoy if g.get("origen") == "caja")
    efectivo_esperado = caja["monto_apertura"] + caja["efectivo"] - total_gastos_caja
    return (
        f"RESUMEN DE CAJA\n"
        f"Apertura: ${caja['monto_apertura']:,.0f}\n"
        f"Ventas efectivo: ${caja['efectivo']:,.0f}\n"
        f"Transferencias: ${caja['transferencias']:,.0f}\n"
        f"Datafono: ${caja['datafono']:,.0f}\n"
        f"Total ventas hoy ({num_ventas_hoy}): ${total_ventas_hoy:,.0f}\n"
        f"Gastos de caja: ${total_gastos_caja:,.0f}\n"
        f"Efectivo esperado en caja: ${efectivo_esperado:,.0f}"
    )


# ─────────────────────────────────────────────
# GASTOS
# ─────────────────────────────────────────────

def cargar_gastos_hoy() -> list:
    import db as _db
    if not _db.DB_DISPONIBLE:
        logger.warning("DB no disponible — cargar_gastos_hoy retorna []")
        return []
    try:
        hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        return _leer_gastos_postgres(hoy, hoy) or []
    except Exception as e:
        logger.warning("Error leyendo gastos de Postgres: %s", e)
        return []


def guardar_gasto(gasto: dict):
    import db as _db
    if not _db.DB_DISPONIBLE:
        raise RuntimeError("⚠️ Base de datos no disponible. Intenta de nuevo en un momento.")
    _guardar_gasto_postgres(gasto)
