"""
Memoria persistente del bot: precios, catalogo, negocio, inventario, caja, gastos.
Usa cache en RAM para evitar lecturas repetidas del JSON.
"""

import json
import os
from datetime import datetime

import config

_cache: dict | None = None


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
    from drive import subir_a_drive
    subir_a_drive(config.MEMORIA_FILE)


def invalidar_cache_memoria():
    """Fuerza recarga desde disco en la proxima llamada a cargar_memoria()."""
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
    Usa precios de fraccion si existen; si no, proporcional.
    """
    prod = buscar_producto_en_catalogo(nombre_producto)
    if not prod:
        precios = cargar_memoria().get("precios", {})
        precio_u = precios.get(nombre_producto.strip().lower(), 0)
        return round(precio_u * cantidad_decimal), precio_u

    precio_u   = prod.get("precio_unidad", 0)
    fracciones = prod.get("precios_fraccion", {})
    for frac_data in fracciones.values():
        if abs(frac_data.get("decimal", 0) - cantidad_decimal) < 0.01:
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
    """Retorna texto con los precios por fraccion de un producto."""
    prod = buscar_producto_en_catalogo(nombre_producto)
    if not prod:
        return None
    fracs = prod.get("precios_fraccion", {})
    if not fracs:
        return f"{prod['nombre']}: unidad=${prod['precio_unidad']:,} (no fraccionable)"
    partes = [f"unidad=${prod['precio_unidad']:,}"]
    for frac_texto, fd in fracs.items():
        partes.append(f"{frac_texto}=${fd['precio']:,}")
    return f"{prod['nombre']}: " + " | ".join(partes)


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
