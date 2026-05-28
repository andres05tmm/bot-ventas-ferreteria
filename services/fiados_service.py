"""
services/fiados_service.py — Logica de fiados (cuentas por cobrar a clientes).
Extraido de memoria.py (Tarea H).

Imports permitidos: logging, datetime, db (lazy), config, utils.
cargar_memoria() se importa de forma lazy dentro de las funciones para evitar
ciclo de imports (fiados_service → memoria → fiados_service).
NUNCA importar de memoria a nivel de modulo.
"""

# -- stdlib --
import logging
from datetime import datetime

# -- propios --
import config
from utils import _normalizar

logger = logging.getLogger("ferrebot.services.fiados")


# ─────────────────────────────────────────────
# FIADOS
# ─────────────────────────────────────────────

def cargar_fiados() -> dict:
    """Retorna el dict completo de fiados: {nombre_cliente: {saldo, movimientos}}"""
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            rows = _db.query_all(
                "SELECT id, nombre, saldo_actual FROM fiados",
                ()
            )
            return {
                r["nombre"]: {
                    "saldo": r["saldo_actual"],
                    "movimientos": [],
                }
                for r in rows
            }
    except Exception as e:
        logger.warning("Postgres read cargar_fiados failed: %s", e)

    from memoria import cargar_memoria
    return cargar_memoria().get("fiados", {})


def _buscar_cliente_fiado(nombre: str, fiados: dict) -> str | None:
    """Busca el key del cliente en fiados de forma flexible (sin tildes, parcial)."""
    busqueda = _normalizar(nombre.strip())
    # 1. Coincidencia exacta normalizada
    for k in fiados:
        if _normalizar(k) == busqueda:
            return k
    # 2. La búsqueda está contenida en el nombre o viceversa
    for k in fiados:
        kn = _normalizar(k)
        if busqueda in kn or kn in busqueda:
            return k
    # 3. Todas las palabras de la búsqueda aparecen en el nombre
    palabras = busqueda.split()
    for k in fiados:
        kn = _normalizar(k)
        if all(p in kn for p in palabras):
            return k
    return None


def guardar_fiado_movimiento(cliente: str, concepto: str, cargo: float, abono: float):
    """
    Registra un movimiento de fiado (cargo=lo que quedó debiendo, abono=lo que pagó).
    Crea el cliente en fiados si no existe.

    H-14: el movimiento ahora se persiste en la tabla fiados_movimientos en
    la misma transacción que el UPDATE del saldo. El cache en memoria también
    se actualiza para que las lecturas inmediatas vean el cambio. Si el bot
    se reinicia, el cache se reconstruye desde la tabla (no se pierde nada).
    """
    import db as _db
    if not _db.DB_DISPONIBLE:
        raise RuntimeError("⚠️ Base de datos no disponible. Intenta de nuevo en un momento.")

    from memoria import cargar_memoria
    mem    = cargar_memoria()
    fiados = mem.setdefault("fiados", {})
    if cliente not in fiados:
        fiados[cliente] = {"saldo": 0, "movimientos": []}

    saldo_anterior = fiados[cliente]["saldo"]
    saldo_nuevo    = saldo_anterior + cargo - abono
    fiados[cliente]["saldo"] = saldo_nuevo
    fiados[cliente]["movimientos"].append({
        "fecha":    datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d"),
        "concepto": concepto,
        "cargo":    cargo,
        "abono":    abono,
        "saldo":    saldo_nuevo,
    })

    # Transacción: UPSERT del saldo + INSERT del movimiento atómicamente.
    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM fiados WHERE nombre = %s", (cliente,))
            row = cur.fetchone()
            if row:
                fiado_id = row["id"]
                cur.execute(
                    "UPDATE fiados SET saldo_actual=%s, ultima_actualizacion=NOW(), "
                    "updated_at=NOW() WHERE id=%s",
                    (int(saldo_nuevo), fiado_id),
                )
            else:
                cur.execute(
                    "INSERT INTO fiados (nombre, saldo_actual, ultima_actualizacion) "
                    "VALUES (%s, %s, NOW()) RETURNING id",
                    (cliente, int(saldo_nuevo)),
                )
                fiado_id = cur.fetchone()["id"]

            cur.execute(
                """INSERT INTO fiados_movimientos
                       (fiado_id, concepto, cargo, abono, saldo_resultante)
                   VALUES (%s, %s, %s, %s, %s)""",
                (fiado_id, concepto, cargo, abono, saldo_nuevo),
            )
        conn.commit()

    return saldo_nuevo


def listar_movimientos_cliente(fiado_id: int, limit: int = 20) -> list[dict]:
    """
    Retorna los últimos N movimientos de un fiado desde PG (no del cache).
    Útil para reconstruir el detalle del cliente después de un reinicio.
    """
    import db as _db
    if not _db.DB_DISPONIBLE:
        return []
    try:
        rows = _db.query_all(
            """SELECT fecha, hora, concepto, cargo, abono, saldo_resultante
               FROM fiados_movimientos
               WHERE fiado_id = %s
               ORDER BY fecha DESC, hora DESC, id DESC
               LIMIT %s""",
            (fiado_id, limit),
        )
        return [
            {
                "fecha":    str(r["fecha"]),
                "hora":     str(r["hora"])[:5] if r.get("hora") else "",
                "concepto": r["concepto"] or "",
                "cargo":    float(r["cargo"] or 0),
                "abono":    float(r["abono"] or 0),
                "saldo":    float(r["saldo_resultante"] or 0),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("listar_movimientos_cliente falló: %s", e)
        return []


def abonar_fiado(cliente: str, monto: float, concepto: str = "Abono") -> tuple[bool, str]:
    """
    Registra un abono a la cuenta de un cliente.
    Retorna (exito, mensaje).
    """
    from memoria import cargar_memoria
    mem    = cargar_memoria()
    fiados = mem.get("fiados", {})

    cliente_key = _buscar_cliente_fiado(cliente, fiados)

    if not cliente_key:
        return False, f"No encontré a '{cliente}' en los fiados."

    saldo_nuevo = guardar_fiado_movimiento(cliente_key, concepto, cargo=0, abono=monto)
    if saldo_nuevo <= 0:
        return True, f"✅ Abono registrado. {cliente_key} quedó a paz y salvo. 🎉"
    return True, f"✅ Abono de ${monto:,.0f} registrado. {cliente_key} aún debe ${saldo_nuevo:,.0f}."


def resumen_fiados() -> str:
    """Texto con todos los clientes que deben algo."""
    fiados     = cargar_fiados()
    pendientes = {k: v for k, v in fiados.items() if v.get("saldo", 0) > 0}
    if not pendientes:
        return "No hay fiados pendientes. ✅"
    lineas = ["💳 *Fiados pendientes:*\n"]
    total  = 0
    for cliente, datos in sorted(pendientes.items()):
        saldo = datos["saldo"]
        total += saldo
        lineas.append(f"• {cliente}: ${saldo:,.0f}")
    lineas.append(f"\n*Total por cobrar: ${total:,.0f}*")
    return "\n".join(lineas)


def detalle_fiado_cliente(cliente: str) -> str:
    """
    Retorna el detalle de movimientos de un cliente.

    H-14: ahora lee los movimientos desde PG (fiados_movimientos) en vez del
    cache de memoria, así sobreviven a reinicios del bot. Fallback al cache
    in-memory si la query falla (compatibilidad).
    """
    import db as _db
    fiados      = cargar_fiados()
    cliente_key = _buscar_cliente_fiado(cliente, fiados)
    if not cliente_key:
        return f"No encontré a '{cliente}' en los fiados."
    saldo = fiados[cliente_key].get("saldo", 0)

    # Intentar leer desde PG; si falla, usar el cache.
    movs: list[dict] = []
    if _db.DB_DISPONIBLE:
        row = _db.query_one("SELECT id FROM fiados WHERE nombre = %s", (cliente_key,))
        if row:
            movs = listar_movimientos_cliente(row["id"], limit=10)
            # PG retorna en orden DESC; invertir a ASC para mostrar cronológicamente.
            movs = list(reversed(movs))
    if not movs:
        # Fallback al cache (incluye datos legados pre-H-14 que no migraron).
        movs = fiados[cliente_key].get("movimientos", [])[-10:]

    lineas = [f"📋 Cuenta de {cliente_key} — Saldo: ${saldo:,.0f}\n"]
    for m in movs:
        if m["cargo"] > 0 and m["abono"] > 0:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Cargo: ${m['cargo']:,.0f} | Abono: ${m['abono']:,.0f} | Saldo: ${m['saldo']:,.0f}")
        elif m["cargo"] > 0:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Fiado: ${m['cargo']:,.0f} | Saldo: ${m['saldo']:,.0f}")
        else:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Abono: ${m['abono']:,.0f} | Saldo: ${m['saldo']:,.0f}")
    return "\n".join(lineas)
