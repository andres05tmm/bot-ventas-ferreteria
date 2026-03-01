"""
Memoria persistente del bot: precios, catálogo, negocio, inventario, caja, gastos.
Usa cache en RAM para evitar lecturas repetidas del JSON.

CORRECCIONES v2:
  - Docstring movido ANTES del import (antes estaba después, Python no lo reconocía)
  - _normalizar eliminada de aquí — se importa de utils (era duplicado con lógica distinta)
"""

import logging
import json
import os
import threading
from datetime import datetime

import config
from utils import _normalizar  # única definición centralizada

_cache: dict | None = None
_bloquear_subida_drive: bool = False  # True durante la sincronización inicial
_cache_lock = threading.Lock()        # Protege _cache en entornos multi-hilo


def bloquear_subida_drive(bloquear: bool):
    global _bloquear_subida_drive
    _bloquear_subida_drive = bloquear


def cargar_memoria() -> dict:
    global _cache
    with _cache_lock:
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
    with _cache_lock:
        _cache = memoria
        with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
            json.dump(memoria, f, ensure_ascii=False, indent=2)
    if not _bloquear_subida_drive:
        from drive import subir_a_drive
        subir_a_drive(config.MEMORIA_FILE)


def invalidar_cache_memoria():
    global _cache
    with _cache_lock:
        _cache = None


# ─────────────────────────────────────────────
# CATÁLOGO
# ─────────────────────────────────────────────

def buscar_producto_en_catalogo(nombre_buscado: str) -> dict | None:
    """
    Busca un producto en el catálogo por nombre (búsqueda flexible).
    Retorna el dict del producto o None.
    Niveles de búsqueda:
      1. Coincidencia exacta en nombre_lower
      2. Todas las palabras del término aparecen en el nombre
      3. Al menos todas menos una aparecen
      4. Al menos UNA palabra aparece (búsqueda parcial)
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


def _stem_palabra(w: str) -> str:
    """Stemming mínimo: quita 's' final para plurales (lijas→lija, discos→disco)."""
    return w[:-1] if w.endswith("s") and len(w) > 4 else w


def buscar_multiples_en_catalogo(nombre_buscado: str, limite: int = 8) -> list:
    """Retorna todos los candidatos que coincidan con el término, ordenados por relevancia.
    Incluye stemming de plurales y bonus de score para números exactos (tallas).
    """
    catalogo = cargar_memoria().get("catalogo", {})
    if not catalogo:
        return []

    nombre_lower = nombre_buscado.strip().lower()
    # Incluir palabras largas (>2 chars) Y números de cualquier longitud para scoring de tallas
    palabras_raw = [p for p in nombre_lower.split() if len(p) > 2 or p.isdigit()]
    if not palabras_raw:
        return []

    # Separar palabras normales de números/tallas para scoring diferenciado
    palabras_variantes = []
    numeros_busqueda = set()
    for p in palabras_raw:
        stem = _stem_palabra(p)
        palabras_variantes.append((p, stem))
        if p.isdigit():
            numeros_busqueda.add(p)

    candidatos = []
    for prod in catalogo.values():
        nl = prod.get("nombre_lower", "")
        coincidencias = sum(1 for (orig, stem) in palabras_variantes if orig in nl or stem in nl)
        total = len(palabras_variantes)
        # Bonus: si el número exacto de la búsqueda aparece en el nombre → prioridad alta
        # Usa regex para extraer números del nombre_lower (maneja n°80, 3", etc.)
        import re as _re_mem
        nl_numeros = set(_re_mem.findall(r'\d+', nl))
        bonus_numero = sum(1 for n in numeros_busqueda if n in nl_numeros)
        score_base = 0
        if coincidencias == total:
            score_base = 3
        elif total > 1 and coincidencias >= total - 1:
            score_base = 2
        elif coincidencias >= 1:
            score_base = 1
        if score_base > 0:
            candidatos.append((score_base + bonus_numero, coincidencias, len(nl), prod))

    candidatos.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [c[3] for c in candidatos[:limite]]


def obtener_precio_para_cantidad(nombre_producto: str, cantidad_decimal: float) -> tuple[int, float]:
    """
    Dado un producto y una cantidad decimal, retorna (precio_total, precio_unidad).
    """
    prod = buscar_producto_en_catalogo(nombre_producto)
    if not prod:
        precios  = cargar_memoria().get("precios", {})
        precio_u = precios.get(nombre_producto.strip().lower(), 0)
        return round(precio_u * cantidad_decimal), precio_u

    precio_u   = prod.get("precio_unidad", 0)
    fracciones = prod.get("precios_fraccion", {})

    precio_x_cantidad = prod.get("precio_por_cantidad")
    if precio_x_cantidad:
        umbral = precio_x_cantidad.get("umbral", 100)
        if cantidad_decimal >= umbral:
            precio_u_aplicado = precio_x_cantidad.get("precio_sobre_umbral", precio_u)
        else:
            precio_u_aplicado = precio_x_cantidad.get("precio_bajo_umbral", precio_u)
        return round(precio_u_aplicado * cantidad_decimal), precio_u_aplicado

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
    return "No hay precios guardados aún."


def obtener_info_fraccion_producto(nombre_producto: str) -> str | None:
    """Retorna texto con los precios por fracción o por cantidad de un producto."""
    prod = buscar_producto_en_catalogo(nombre_producto)
    if not prod:
        return None

    nombre   = prod['nombre']
    precio_u = prod['precio_unidad']

    pxc = prod.get("precio_por_cantidad")
    if pxc:
        umbral  = pxc.get("umbral", 100)
        p_bajo  = pxc.get("precio_bajo_umbral", precio_u)
        p_sobre = pxc.get("precio_sobre_umbral", precio_u)
        return (
            f"{nombre}: "
            f"c/u (menos de {umbral}) = ${p_bajo:,} | "
            f"c/u (x{umbral} o más) = ${p_sobre:,}"
        )

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
        return "La caja no está abierta hoy."
    resumen           = obtener_resumen_ventas()
    total_ventas      = resumen["total"] if resumen else 0
    gastos_hoy        = cargar_gastos_hoy()
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
    guardar_memoria(mem)
    return saldo_nuevo


def abonar_fiado(cliente: str, monto: float, concepto: str = "Abono") -> tuple[bool, str]:
    """
    Registra un abono a la cuenta de un cliente.
    Retorna (exito, mensaje).
    """
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


# ─────────────────────────────────────────────
# GESTION DE CATALOGO DESDE EXCEL
# ─────────────────────────────────────────────

# Categorias que se venden por fracciones de galon
_CATEGORIAS_CON_FRACCIONES = {
    "2 pinturas y disolventes",
    "4 impermeabilizantes y materiales de construcción",
    "4 impermeabilizantes y materiales de construccion",
}

# Palabras clave de productos que se venden por fracciones
_KEYWORDS_FRACCIONES = (
    "vinilo", "laca", "esmalte", "sellador", "base", "imprimante",
    "impermeabilizante", "thinner", "disolvente", "barniz", "aceite",
)

# Tornillos drywall — tienen precio especial por volumen (umbral 50)
_KEYWORDS_PRECIO_UMBRAL = ("tornillo drywall",)


def _es_producto_con_fracciones(nombre: str, categoria: str) -> bool:
    n = nombre.lower()
    c = categoria.lower()
    if c in _CATEGORIAS_CON_FRACCIONES:
        return True
    return any(k in n for k in _KEYWORDS_FRACCIONES)


def _es_tornillo_drywall(nombre: str) -> bool:
    n = nombre.lower()
    return all(k in n for k in ("tornillo", "drywall"))


def actualizar_precio_en_catalogo(nombre_producto: str, nuevo_precio: float, fraccion: str = None) -> bool:
    """
    Actualiza el precio de un producto existente en el catálogo de forma permanente.
    - Si fraccion es None: actualiza precio_unidad (galon completo / precio base).
    - Si fraccion es "1/4", "1/2", etc.: actualiza ese precio de fraccion.
    Retorna True si encontró y actualizó el producto, False si no lo encontró.
    """
    mem      = cargar_memoria()
    catalogo = mem.get("catalogo", {})
    prod     = buscar_producto_en_catalogo(nombre_producto)

    if not prod:
        # Guardar en precios simples como fallback
        mem.setdefault("precios", {})[nombre_producto.lower()] = nuevo_precio
        guardar_memoria(mem)
        return False

    # Encontrar la clave exacta en el catálogo
    clave = None
    for k, v in catalogo.items():
        if v.get("nombre_lower") == prod.get("nombre_lower"):
            clave = k
            break

    if not clave:
        return False

    # Si la fraccion coincide con el inicio del nombre del producto (ej: "1/2 Cunete")
    # es parte del nombre, NO una fraccion real — ignorar y actualizar precio_unidad
    nombre_prod = catalogo[clave].get("nombre", "")
    fraccion_en_nombre = fraccion and nombre_prod.startswith(fraccion)
    tiene_fracciones_reales = bool(catalogo[clave].get("precios_fraccion")) and not fraccion_en_nombre

    if fraccion and tiene_fracciones_reales:
        catalogo[clave]["precios_fraccion"][fraccion] = {"precio": round(nuevo_precio)}
    else:
        catalogo[clave]["precio_unidad"] = round(nuevo_precio)
        # Limpiar cualquier precios_fraccion corrupto si la fraccion era parte del nombre
        if fraccion_en_nombre:
            catalogo[clave]["precios_fraccion"] = {}
        if catalogo[clave].get("precio_por_cantidad"):
            catalogo[clave]["precio_por_cantidad"]["precio_bajo_umbral"] = round(nuevo_precio)

    mem["catalogo"] = catalogo
    guardar_memoria(mem)
    invalidar_cache_memoria()
    return True


def importar_catalogo_desde_excel(ruta_excel: str) -> dict:
    """
    Lee BASE_DE_DATOS_PRODUCTOS.xlsx e importa todos los productos al catálogo en memoria.
    Retorna {"importados": N, "omitidos": N, "errores": [...]}
    """
    import openpyxl
    try:
        wb = openpyxl.load_workbook(ruta_excel, data_only=True)
        ws = wb['Datos']
    except Exception as e:
        return {"importados": 0, "omitidos": 0, "errores": [str(e)]}

    mem      = cargar_memoria()
    catalogo = mem.get("catalogo", {})

    importados = 0
    omitidos   = 0
    errores    = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        try:
            nombre    = str(row[1] or "").strip()
            categoria = str(row[3] or "").strip()
            p_unidad  = row[16]   # COL 17 — precio 1 unidad / galon
            p_075     = row[17]   # COL 18 — precio unitario para 3/4
            p_05      = row[18]   # COL 19 — precio unitario para 1/2
            p_025     = row[19]   # COL 20 — precio unitario para 1/4
            p_013     = row[20]   # COL 21 — precio unitario para 1/8
            p_006     = row[21]   # COL 22 — precio unitario para 1/16

            if not nombre or nombre == "nan":
                omitidos += 1
                continue
            if not p_unidad or not isinstance(p_unidad, (int, float)) or p_unidad <= 0:
                omitidos += 1
                continue

            nombre_lower = _normalizar(nombre)
            clave        = nombre_lower.replace(" ", "_")

            prod_base = {
                "nombre":      nombre,
                "nombre_lower": nombre_lower,
                "categoria":   categoria,
                "precio_unidad": round(float(p_unidad)),
            }

            if _es_tornillo_drywall(nombre):
                # Precio especial cuando compra >= 50 unidades
                precio_x50 = round(float(p_075)) if p_075 and isinstance(p_075, (int, float)) and p_075 > 0 else round(float(p_unidad))
                prod_base["precio_por_cantidad"] = {
                    "umbral":               50,
                    "precio_bajo_umbral":   round(float(p_unidad)),
                    "precio_sobre_umbral":  precio_x50,
                }

            elif _es_producto_con_fracciones(nombre, categoria):
                # Calcular precios totales por fraccion multiplicando precio_unitario x fraccion
                fracs = {}
                if p_075 and isinstance(p_075, (int, float)) and p_075 > 0:
                    fracs["3/4"]  = {"precio": round(float(p_075) * 0.75)}
                if p_05 and isinstance(p_05, (int, float)) and p_05 > 0:
                    fracs["1/2"]  = {"precio": round(float(p_05)  * 0.5)}
                if p_025 and isinstance(p_025, (int, float)) and p_025 > 0:
                    fracs["1/4"]  = {"precio": round(float(p_025) * 0.25)}
                if p_013 and isinstance(p_013, (int, float)) and p_013 > 0:
                    fracs["1/8"]  = {"precio": round(float(p_013) * 0.125)}
                if p_006 and isinstance(p_006, (int, float)) and p_006 > 0:
                    fracs["1/16"] = {"precio": round(float(p_006) * 0.0625)}
                if fracs:
                    prod_base["precios_fraccion"] = fracs

            catalogo[clave] = prod_base
            importados += 1

        except Exception as e:
            errores.append(f"{row[1]}: {e}")

    mem["catalogo"] = catalogo
    guardar_memoria(mem)
    invalidar_cache_memoria()

    return {"importados": importados, "omitidos": omitidos, "errores": errores[:10]}
