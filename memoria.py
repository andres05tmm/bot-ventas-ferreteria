"""
Memoria persistente del bot: precios, catalogo, negocio, inventario, caja, gastos.
Usa cache en RAM para evitar lecturas repetidas del JSON.
"""

import json
import os
from datetime import datetime

import config

_cache: dict | None = None
_bloquear_subida_drive: bool = False  # True durante la sincronizacion inicial


def bloquear_subida_drive(bloquear: bool):
    global _bloquear_subida_drive
    _bloquear_subida_drive = bloquear


def cargar_memoria() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(config.MEMORIA_FILE):
        with open(config.MEMORIA_FILE, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    else:
        _cache = {
            "precios": {}, "catalogo": {}, "negocio": {},
            "notas": [], "inventario": {}, "gastos": {},
            "caja_actual": {"abierta": False},
        }
    return _cache


def guardar_memoria(memoria: dict):
    global _cache
    _cache = memoria
    with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=2)
    if not _bloquear_subida_drive:
        from drive import subir_a_drive
        subir_a_drive(config.MEMORIA_FILE)


def invalidar_cache_memoria():
    global _cache
    _cache = None


# ─────────────────────────────────────────────
# CATALOGO
# ─────────────────────────────────────────────

def buscar_producto_en_catalogo(nombre_buscado: str) -> dict | None:
    """
    Busca un producto en el catalogo por nombre (busqueda flexible).
    Retorna el dict del producto o None.
    Niveles de busqueda:
      1. Coincidencia exacta en nombre_lower
      2. Todas las palabras del termino aparecen en el nombre
      3. Al menos todas menos una aparecen
      4. Al menos UNA palabra aparece (busqueda parcial)
    """
    catalogo = cargar_memoria().get("catalogo", {})
    if not catalogo:
        return None

    nombre_lower = nombre_buscado.strip().lower()

    for prod in catalogo.values():
        if prod.get("nombre_lower") == nombre_lower:
            return prod

    palabras = [p for p in nombre_lower.split() if len(p) > 2]
    if not palabras:
        return None

    candidatos = []
    for prod in catalogo.values():
        nl = prod.get("nombre_lower", "")
        coincidencias = sum(1 for p in palabras if p in nl)
        if coincidencias == len(palabras):
            candidatos.append((3, coincidencias, len(nl), prod))
        elif len(palabras) > 1 and coincidencias >= len(palabras) - 1:
            candidatos.append((2, coincidencias, len(nl), prod))
        elif coincidencias >= 1:
            candidatos.append((1, coincidencias, len(nl), prod))

    if candidatos:
        candidatos.sort(key=lambda x: (-x[0], -x[1], x[2]))
        return candidatos[0][3]

    return None


def buscar_multiples_en_catalogo(nombre_buscado: str, limite: int = 8) -> list:
    """Retorna todos los candidatos que coincidan con el termino, ordenados por relevancia."""
    catalogo = cargar_memoria().get("catalogo", {})
    if not catalogo:
        return []

    nombre_lower = nombre_buscado.strip().lower()
    palabras = [p for p in nombre_lower.split() if len(p) > 2]
    if not palabras:
        return []

    candidatos = []
    for prod in catalogo.values():
        nl = prod.get("nombre_lower", "")
        coincidencias = sum(1 for p in palabras if p in nl)
        if coincidencias == len(palabras):
            candidatos.append((3, coincidencias, len(nl), prod))
        elif len(palabras) > 1 and coincidencias >= len(palabras) - 1:
            candidatos.append((2, coincidencias, len(nl), prod))
        elif coincidencias >= 1:
            candidatos.append((1, coincidencias, len(nl), prod))

    candidatos.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [c[3] for c in candidatos[:limite]]


def obtener_precio_para_cantidad(nombre_producto: str, cantidad_decimal: float) -> tuple[int, float]:
    """
    Dado un producto y una cantidad decimal, retorna (precio_total, precio_unidad).
    - Pinturas: usa precios_fraccion por fraccion de galon (1/4, 1/2, etc.)
    - Tornilleria: si cantidad >= 100 usa precio mayorista, si no precio unitario normal.
    - Resto: proporcional al precio_unidad.
    """
    prod = buscar_producto_en_catalogo(nombre_producto)
    if not prod:
        precios = cargar_memoria().get("precios", {})
        precio_u = precios.get(nombre_producto.strip().lower(), 0)
        return round(precio_u * cantidad_decimal), precio_u

    precio_u   = prod.get("precio_unidad", 0)
    fracciones = prod.get("precios_fraccion", {})

    # ── Tornilleria: precio por umbral de cantidad ──
    precio_x_cantidad = prod.get("precio_por_cantidad")
    if precio_x_cantidad:
        umbral = precio_x_cantidad.get("umbral", 100)
        if cantidad_decimal >= umbral:
            precio_u_aplicado = precio_x_cantidad.get("precio_sobre_umbral", precio_u)
        else:
            precio_u_aplicado = precio_x_cantidad.get("precio_bajo_umbral", precio_u)
        return round(precio_u_aplicado * cantidad_decimal), precio_u_aplicado

    # ── Pinturas: precio por fraccion de galon ──
    for frac_data in fracciones.values():
        if isinstance(frac_data, dict) and abs(frac_data.get("decimal", 0) - cantidad_decimal) < 0.01:
            return frac_data.get("precio", round(precio_u * cantidad_decimal)), precio_u

    return round(precio_u * cantidad_decimal), precio_u


def obtener_precios_como_texto() -> str:
    """Resumen compacto de precios para el system prompt."""
    memoria  = cargar_memoria()
    catalogo = memoria.get("catalogo", {})
    precios  = memoria.get("precios", {})

    if catalogo:
        lineas = []
        for prod in catalogo.values():
            sufijo = " [fraccionable]" if prod.get("precios_fraccion") else ""
            lineas.append(f"- {prod['nombre']}: ${prod['precio_unidad']:,}{sufijo}")
        return "\n".join(lineas)
    if precios:
        return "\n".join(f"- {p}: ${v:,}" for p, v in precios.items())
    return "No hay precios guardados aun."


def obtener_info_fraccion_producto(nombre_producto: str) -> str | None:
    """Retorna texto con los precios por fraccion o por cantidad de un producto."""
    prod = buscar_producto_en_catalogo(nombre_producto)
    if not prod:
        return None

    nombre = prod['nombre']
    precio_u = prod['precio_unidad']

    # Tornilleria: precio por umbral de cantidad
    pxc = prod.get("precio_por_cantidad")
    if pxc:
        umbral     = pxc.get("umbral", 100)
        p_bajo     = pxc.get("precio_bajo_umbral", precio_u)
        p_sobre    = pxc.get("precio_sobre_umbral", precio_u)
        return (
            f"{nombre}: "
            f"c/u (menos de {umbral}) = ${p_bajo:,} | "
            f"c/u (x{umbral} o más) = ${p_sobre:,}"
        )

    # Pinturas: precio por fraccion de galon
    fracs = prod.get("precios_fraccion", {})
    if not fracs:
        return f"{nombre}: unidad=${precio_u:,} (no fraccionable)"
    partes = []
    for frac_texto, fd in fracs.items():
        if isinstance(fd, dict):
            partes.append(f"{frac_texto}=${fd['precio']:,}")
    return f"{nombre}: " + " | ".join(partes)


# ─────────────────────────────────────────────
# INVENTARIO
# ─────────────────────────────────────────────

def cargar_inventario() -> dict:
    return cargar_memoria().get("inventario", {})


def guardar_inventario(inventario: dict):
    mem = cargar_memoria()
    mem["inventario"] = inventario
    guardar_memoria(mem)


def verificar_alertas_inventario() -> list[str]:
    alertas = []
    for producto, datos in cargar_inventario().items():
        if isinstance(datos, dict):
            cantidad = datos.get("cantidad", 0)
            minimo   = datos.get("minimo", 3)
            if cantidad <= minimo:
                alertas.append(f"⚠️ STOCK BAJO: {producto} — quedan {cantidad} unidades")
    return alertas


# ─────────────────────────────────────────────
# CAJA
# ─────────────────────────────────────────────

def cargar_caja() -> dict:
    return cargar_memoria().get("caja_actual", {
        "abierta": False, "fecha": None, "monto_apertura": 0,
        "efectivo": 0, "transferencias": 0, "datafono": 0,
    })


def guardar_caja(caja: dict):
    mem = cargar_memoria()
    mem["caja_actual"] = caja
    guardar_memoria(mem)


def obtener_resumen_caja() -> str:
    from excel import obtener_resumen_ventas
    caja = cargar_caja()
    if not caja.get("abierta"):
        return "La caja no esta abierta hoy."
    resumen          = obtener_resumen_ventas()
    total_ventas     = resumen["total"] if resumen else 0
    gastos_hoy       = cargar_gastos_hoy()
    total_gastos_caja = sum(g["monto"] for g in gastos_hoy if g.get("origen") == "caja")
    efectivo_esperado = caja["monto_apertura"] + caja["efectivo"] - total_gastos_caja
    return (
        f"RESUMEN DE CAJA\n"
        f"Apertura: ${caja['monto_apertura']:,.0f}\n"
        f"Ventas efectivo: ${caja['efectivo']:,.0f}\n"
        f"Transferencias: ${caja['transferencias']:,.0f}\n"
        f"Datafono: ${caja['datafono']:,.0f}\n"
        f"Total ventas: ${total_ventas:,.0f}\n"
        f"Gastos de caja: ${total_gastos_caja:,.0f}\n"
        f"Efectivo esperado en caja: ${efectivo_esperado:,.0f}"
    )


# ─────────────────────────────────────────────
# GASTOS
# ─────────────────────────────────────────────

def cargar_gastos_hoy() -> list:
    hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
    return cargar_memoria().get("gastos", {}).get(hoy, [])


def guardar_gasto(gasto: dict):
    mem = cargar_memoria()
    hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
    mem.setdefault("gastos", {}).setdefault(hoy, []).append(gasto)
    guardar_memoria(mem)


# ─────────────────────────────────────────────
# FIADOS
# ─────────────────────────────────────────────

def cargar_fiados() -> dict:
    """Retorna el dict completo de fiados: {nombre_cliente: {saldo, movimientos}}"""
    return cargar_memoria().get("fiados", {})


def guardar_fiado_movimiento(cliente: str, concepto: str, cargo: float, abono: float):
    """
    Registra un movimiento de fiado (cargo=lo que quedó debiendo, abono=lo que pagó).
    Crea el cliente en fiados si no existe.
    """
    from datetime import datetime
    mem = cargar_memoria()
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
    guardar_memoria(mem)
    return saldo_nuevo


def abonar_fiado(cliente: str, monto: float, concepto: str = "Abono") -> tuple[bool, str]:
    """
    Registra un abono a la cuenta de un cliente.
    Retorna (exito, mensaje).
    """
    mem    = cargar_memoria()
    fiados = mem.get("fiados", {})

    # Busqueda flexible del nombre
    cliente_key = None
    cliente_lower = cliente.strip().lower()
    for k in fiados:
        if k.lower() == cliente_lower or cliente_lower in k.lower() or k.lower() in cliente_lower:
            cliente_key = k
            break

    if not cliente_key:
        return False, f"No encontré a '{cliente}' en los fiados."

    saldo_nuevo = guardar_fiado_movimiento(cliente_key, concepto, cargo=0, abono=monto)
    if saldo_nuevo <= 0:
        return True, f"✅ Abono registrado. {cliente_key} quedó a paz y salvo. 🎉"
    return True, f"✅ Abono de ${monto:,.0f} registrado. {cliente_key} aún debe ${saldo_nuevo:,.0f}."


def resumen_fiados() -> str:
    """Texto con todos los clientes que deben algo."""
    fiados = cargar_fiados()
    pendientes = {k: v for k, v in fiados.items() if v.get("saldo", 0) > 0}
    if not pendientes:
        return "No hay fiados pendientes. ✅"
    lineas = ["💳 *Fiados pendientes:*\n"]
    total = 0
    for cliente, datos in sorted(pendientes.items()):
        saldo = datos["saldo"]
        total += saldo
        lineas.append(f"• {cliente}: ${saldo:,.0f}")
    lineas.append(f"\n*Total por cobrar: ${total:,.0f}*")
    return "\n".join(lineas)


def detalle_fiado_cliente(cliente: str) -> str:
    """Retorna el detalle de movimientos de un cliente."""
    fiados = cargar_fiados()
    cliente_lower = cliente.strip().lower()
    cliente_key   = None
    for k in fiados:
        if k.lower() == cliente_lower or cliente_lower in k.lower() or k.lower() in cliente_lower:
            cliente_key = k
            break
    if not cliente_key:
        return f"No encontré a '{cliente}' en los fiados."
    datos = fiados[cliente_key]
    saldo = datos.get("saldo", 0)
    movs  = datos.get("movimientos", [])
    lineas = [f"📋 Cuenta de {cliente_key} — Saldo: ${saldo:,.0f}\n"]
    for m in movs[-10:]:  # ultimos 10 movimientos
        if m["cargo"] > 0 and m["abono"] > 0:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Cargo: ${m['cargo']:,.0f} | Abono: ${m['abono']:,.0f} | Saldo: ${m['saldo']:,.0f}")
        elif m["cargo"] > 0:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Fiado: ${m['cargo']:,.0f} | Saldo: ${m['saldo']:,.0f}")
        else:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Abono: ${m['abono']:,.0f} | Saldo: ${m['saldo']:,.0f}")
    return "\n".join(lineas)
