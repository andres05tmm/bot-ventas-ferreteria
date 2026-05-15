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

    existing = _db.query_one("SELECT id FROM fiados WHERE nombre = %s", (cliente,))
    if existing:
        _db.execute(
            "UPDATE fiados SET saldo_actual=%s, ultima_actualizacion=NOW(), updated_at=NOW() WHERE id=%s",
            (int(saldo_nuevo), existing["id"])
        )
    else:
        _db.execute_returning(
            "INSERT INTO fiados (nombre, saldo_actual, ultima_actualizacion) VALUES (%s, %s, NOW()) RETURNING id",
            (cliente, int(saldo_nuevo))
        )
    return saldo_nuevo


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
    """Retorna el detalle de movimientos de un cliente."""
    fiados      = cargar_fiados()
    cliente_key = _buscar_cliente_fiado(cliente, fiados)
    if not cliente_key:
        return f"No encontré a '{cliente}' en los fiados."
    datos = fiados[cliente_key]
    saldo = datos.get("saldo", 0)
    movs  = datos.get("movimientos", [])
    lineas = [f"📋 Cuenta de {cliente_key} — Saldo: ${saldo:,.0f}\n"]
    for m in movs[-10:]:  # últimos 10 movimientos
        if m["cargo"] > 0 and m["abono"] > 0:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Cargo: ${m['cargo']:,.0f} | Abono: ${m['abono']:,.0f} | Saldo: ${m['saldo']:,.0f}")
        elif m["cargo"] > 0:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Fiado: ${m['cargo']:,.0f} | Saldo: ${m['saldo']:,.0f}")
        else:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Abono: ${m['abono']:,.0f} | Saldo: ${m['saldo']:,.0f}")
    return "\n".join(lineas)
