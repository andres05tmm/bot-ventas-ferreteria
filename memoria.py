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


def guardar_memoria(memoria: dict, urgente: bool = False):
    """
    Guarda memoria en disco y sube a Drive.
    urgente=True: sube inmediatamente sin debounce (para cambios de precio/catálogo).
    urgente=False: sube con debounce 2s (para ventas, que pueden ser ráfagas).
    """
    global _cache
    with _cache_lock:
        _cache = memoria
        with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
            json.dump(memoria, f, ensure_ascii=False, indent=2)
    if not _bloquear_subida_drive:
        if urgente:
            from drive import subir_a_drive_urgente
            subir_a_drive_urgente(config.MEMORIA_FILE)
        else:
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
    """Retorna candidatos que coincidan con el término, ordenados por relevancia.
    Umbral estricto para evitar falsos positivos:
    - 1 palabra:  debe aparecer exactamente en el nombre
    - 2 palabras: ambas deben aparecer (100%)
    - 3+ palabras: al menos 2 deben aparecer
    Las palabras de unidad (pulgada, metro, kilo...) son opcionales y no cuentan para el umbral.
    """
    catalogo = cargar_memoria().get("catalogo", {})
    if not catalogo:
        return []

    import re as _re_mem

    # Normalizar tildes y ñ para búsqueda tolerante
    def _norm(s: str) -> str:
        return (s.lower()
                .replace("ñ","n").replace("á","a").replace("é","e")
                .replace("í","i").replace("ó","o").replace("ú","u"))

    nombre_lower = _norm(nombre_buscado.strip())

    def _es_token_relevante(p: str) -> bool:
        if len(p) > 2:
            return True
        if p.isdigit():
            return True
        if len(p) == 2 and any(c.isdigit() for c in p):
            return True
        return False

    # Palabras de unidad: opcionales, no cuentan para el umbral mínimo
    _UNIDADES = {"pulgada", "pulgadas", "metros", "metro", "centimetro", "centimetros",
                 "litro", "litros", "kilo", "kilos", "gramo", "gramos",
                 "galon", "galones", "unidad", "unidades"}

    _STOPWORDS = {"que", "del", "los", "las", "una", "uno", "con", "por",
                  "para", "como", "fue", "son", "de", "en", "la", "el",
                  "vendi", "vendo", "dame", "quiero", "necesito"}

    palabras_raw = [p for p in nombre_lower.split()
                    if _es_token_relevante(p) and p not in _STOPWORDS]
    if not palabras_raw:
        return []

    palabras_producto = [p for p in palabras_raw if p not in _UNIDADES]
    palabras_unidad   = [p for p in palabras_raw if p in _UNIDADES]

    total_producto = len(palabras_producto)
    if total_producto == 0:
        return []

    # Umbral mínimo de coincidencias sobre palabras_producto
    if total_producto == 1:
        min_hits = 1      # 100%
    elif total_producto == 2:
        min_hits = 2      # 100%
    else:
        min_hits = 2      # al menos 2 de 3+

    numeros_busqueda = {p for p in palabras_producto if p.isdigit()}

    candidatos = []
    for prod in catalogo.values():
        nl = _norm(prod.get("nombre_lower", ""))
        coincidencias = sum(
            1 for p in palabras_producto
            if p in nl or _stem_palabra(p) in nl
        )
        if coincidencias < min_hits:
            continue

        # Bonus por número exacto de talla/medida
        nl_numeros = set(_re_mem.findall(r'\d+', prod.get("nombre_lower","")))
        bonus_numero = sum(1 for n in numeros_busqueda if n in nl_numeros)

        # Penalización: si el producto empieza con fracción (ej: "1/2 cuñete")
        # pero el usuario NO mencionó fracción, bajar prioridad
        nl_orig = prod.get("nombre_lower", "")
        penalizacion = -1 if (_re_mem.match(r'^[\d/]+\s', nl_orig)
                               and not any(f in nombre_lower for f in ["1/2","1/4","3/4","1/8","medio","mitad"])) else 0

        # Score base: más coincidencias = mejor
        if coincidencias == total_producto:
            score_base = 3
        elif coincidencias >= total_producto - 1:
            score_base = 2
        else:
            score_base = 1

        candidatos.append((score_base + bonus_numero + penalizacion, coincidencias, len(nl), prod))

    candidatos.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [c[3] for c in candidatos[:limite]]


# ─────────────────────────────────────────────
# ALIAS / SINÓNIMOS DE BÚSQUEDA
# ─────────────────────────────────────────────

# Mapa de sinónimos: palabra que dice el usuario → palabra que está en el catálogo
_ALIAS_SINONIMOS = {
    "imprimante":     "primario",
    "primante":       "primario",
    "primate":        "primario",    # error Whisper frecuente
    "tiner":          "thinner",
    "thiner":         "thinner",     # typo frecuente
    "cunete":         "cuñete",      # sin tilde
    "pintura":        "vinilo",
    "pinturas":       "vinilo",
    "lija":           "lija",
    "lijas":          "lija",
    "silicona":       "silicona",
    "silicon":        "silicona",
    "cinta masking":  "cinta enmascarar",
    "masking":        "cinta enmascarar",
    "enmascarar":     "cinta enmascarar",
    "vinipel":        "cinta",
    "esquinero":      "perfil",
    "angelina":       "lana de vidrio",
    "fibra vidrio":   "lana de vidrio",
    "emplaste":       "masilla",
    "empaste":        "masilla",
    "palustre":       "llana",
    "boquillera":     "masilla",
    "sika":           "impermeabilizante",
    "impermeabilizante": "impermeabilizante",
    # Rodillo convencional
    "convencional":   "rodillo convencional",
    "convencionañ":   "rodillo convencional",  # typo común
    "convensional":   "rodillo convencional",  # typo común
    "rodillo normal": "rodillo convencional",
}


def expandir_con_alias(termino: str) -> list[str]:
    """
    Dado un término de búsqueda, retorna variantes aplicando alias conocidos.
    Ej: 'imprimante blanco' → ['imprimante blanco', 'primario blanco']
    """
    termino_lower = termino.lower().strip()
    variantes = [termino_lower]
    for alias_original, alias_destino in _ALIAS_SINONIMOS.items():
        if alias_original in termino_lower and alias_destino not in termino_lower:
            variante = termino_lower.replace(alias_original, alias_destino)
            variantes.append(variante)
    return variantes


def buscar_multiples_con_alias(nombre_buscado: str, limite: int = 8) -> list:
    """
    Igual que buscar_multiples_en_catalogo pero expande el término con alias/sinónimos.
    Úsala en lugar de buscar_multiples_en_catalogo cuando el MATCH falle frecuentemente.
    """
    variantes = expandir_con_alias(nombre_buscado)
    vistos = set()
    resultados_combinados = []
    for variante in variantes:
        for prod in buscar_multiples_en_catalogo(variante, limite=limite):
            nl = prod.get("nombre_lower", "")
            if nl not in vistos:
                vistos.add(nl)
                resultados_combinados.append(prod)
    return resultados_combinados[:limite]


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


def _normalizar_clave_inventario(nombre: str) -> str:
    """Normaliza el nombre del producto para usar como clave en inventario."""
    return _normalizar(nombre).strip().lower()


def registrar_conteo_inventario(nombre_producto: str, cantidad: float, minimo: float = 5, unidad: str = "unidades") -> tuple[bool, str]:
    """
    Registra o actualiza el conteo de un producto en inventario.
    Busca primero en el catálogo para usar el nombre correcto.
    Retorna (éxito, mensaje).
    """
    inventario = cargar_inventario()
    
    # Buscar producto en catálogo para usar nombre oficial
    producto_catalogo = buscar_producto_en_catalogo(nombre_producto)
    if producto_catalogo:
        nombre_oficial = producto_catalogo.get("nombre", nombre_producto)
    else:
        nombre_oficial = nombre_producto.strip()
    
    clave = _normalizar_clave_inventario(nombre_oficial)
    
    # Verificar si ya existe con otra clave similar
    clave_existente = buscar_clave_inventario(nombre_producto)
    if clave_existente and clave_existente != clave:
        clave = clave_existente
        nombre_oficial = inventario[clave].get("nombre_original", nombre_oficial)
    
    inventario[clave] = {
        "nombre_original": nombre_oficial,
        "cantidad": round(cantidad, 4),
        "minimo": minimo,
        "unidad": unidad,
        "fecha_conteo": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    guardar_inventario(inventario)
    
    return True, f"✅ Registrado: {nombre_oficial} — {cantidad} {unidad}"


def buscar_clave_inventario(termino: str) -> str | None:
    """
    Busca un producto en inventario de forma flexible.
    Retorna la clave del inventario si encuentra coincidencia.
    """
    inventario = cargar_inventario()
    if not inventario:
        return None
    
    termino_lower = _normalizar_clave_inventario(termino)
    
    # 1. Coincidencia exacta con clave
    if termino_lower in inventario:
        return termino_lower
    
    # 2. Coincidencia exacta con nombre_original
    for clave, datos in inventario.items():
        if isinstance(datos, dict):
            nombre_orig = datos.get("nombre_original", "").lower()
            if nombre_orig == termino_lower:
                return clave
    
    # 3. Búsqueda por palabras
    palabras = [p for p in termino_lower.split() if len(p) > 2]
    if not palabras:
        return None
    
    mejores = []
    for clave, datos in inventario.items():
        if isinstance(datos, dict):
            nombre_orig = datos.get("nombre_original", clave).lower()
            texto_busqueda = f"{clave} {nombre_orig}"
            coincidencias = sum(1 for p in palabras if p in texto_busqueda)
            if coincidencias == len(palabras):
                mejores.append((3, coincidencias, len(clave), clave))
            elif coincidencias >= len(palabras) - 1 and len(palabras) > 1:
                mejores.append((2, coincidencias, len(clave), clave))
            elif coincidencias >= 1:
                mejores.append((1, coincidencias, len(clave), clave))
    
    if mejores:
        mejores.sort(key=lambda x: (-x[0], -x[1], x[2]))
        return mejores[0][3]
    
    return None


def descontar_inventario(nombre_producto: str, cantidad: float) -> tuple[bool, str | None, float | None]:
    """
    Descuenta cantidad del inventario si el producto está registrado.
    Retorna (descontado, alerta_stock_bajo, cantidad_restante).
    Si el producto no está en inventario, retorna (False, None, None).
    """
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        return False, None, None
    
    inventario = cargar_inventario()
    datos = inventario.get(clave, {})
    
    if not isinstance(datos, dict):
        return False, None, None
    
    cantidad_actual = datos.get("cantidad", 0)
    cantidad_nueva = max(0, round(cantidad_actual - cantidad, 4))
    datos["cantidad"] = cantidad_nueva
    datos["ultima_venta"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    guardar_inventario(inventario)
    
    minimo = datos.get("minimo", 5)
    nombre = datos.get("nombre_original", clave)
    unidad = datos.get("unidad", "unidades")
    
    alerta = None
    if cantidad_nueva <= minimo:
        alerta = f"⚠️ Stock bajo: {nombre} — quedan {cantidad_nueva} {unidad}"
    
    return True, alerta, cantidad_nueva


def ajustar_inventario(nombre_producto: str, ajuste: float) -> tuple[bool, str]:
    """
    Ajusta el inventario sumando o restando cantidad.
    ajuste puede ser positivo (+10) o negativo (-5).
    Retorna (éxito, mensaje).
    """
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        return False, f"❌ Producto no encontrado en inventario: {nombre_producto}"
    
    inventario = cargar_inventario()
    datos = inventario.get(clave, {})
    
    cantidad_anterior = datos.get("cantidad", 0)
    cantidad_nueva = max(0, round(cantidad_anterior + ajuste, 4))
    datos["cantidad"] = cantidad_nueva
    datos["ultimo_ajuste"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    guardar_inventario(inventario)
    
    nombre = datos.get("nombre_original", clave)
    unidad = datos.get("unidad", "unidades")
    signo = "+" if ajuste > 0 else ""
    
    return True, f"✅ Ajustado: {nombre}\n   {cantidad_anterior} {signo}{ajuste} = {cantidad_nueva} {unidad}"


def buscar_productos_inventario(termino: str = None, limite: int = 50) -> list[dict]:
    """
    Busca productos en inventario. Si no hay término, retorna todos.
    Retorna lista de dicts con info del producto.
    """
    inventario = cargar_inventario()
    resultados = []
    
    for clave, datos in inventario.items():
        if not isinstance(datos, dict):
            continue
        
        if termino:
            termino_lower = termino.lower()
            nombre_orig = datos.get("nombre_original", clave).lower()
            if termino_lower not in clave and termino_lower not in nombre_orig:
                # Verificar palabras individuales
                palabras = termino_lower.split()
                texto = f"{clave} {nombre_orig}"
                if not any(p in texto for p in palabras):
                    continue
        
        resultados.append({
            "clave": clave,
            "nombre": datos.get("nombre_original", clave),
            "cantidad": datos.get("cantidad", 0),
            "minimo": datos.get("minimo", 5),
            "unidad": datos.get("unidad", "unidades"),
            "fecha_conteo": datos.get("fecha_conteo", ""),
        })
    
    # Ordenar por nombre
    resultados.sort(key=lambda x: x["nombre"].lower())
    return resultados[:limite]


def registrar_compra(nombre_producto: str, cantidad: float, costo_unitario: float, proveedor: str = None) -> tuple[bool, str, dict]:
    """
    Registra una compra de mercancía:
    - Suma cantidad al inventario
    - Actualiza costo promedio ponderado
    - Guarda proveedor (usa el último si no se especifica)
    - Registra en historial de compras
    Retorna (éxito, mensaje, datos_para_excel).
    """
    inventario = cargar_inventario()
    
    # Buscar producto en catálogo
    producto_catalogo = buscar_producto_en_catalogo(nombre_producto)
    if producto_catalogo:
        nombre_oficial = producto_catalogo.get("nombre", nombre_producto)
    else:
        nombre_oficial = nombre_producto.strip()
    
    # Buscar si ya existe en inventario
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        clave = _normalizar_clave_inventario(nombre_oficial)
    
    # Obtener datos actuales o crear nuevo
    datos = inventario.get(clave, {})
    if not isinstance(datos, dict):
        datos = {}
    
    cantidad_anterior = datos.get("cantidad", 0)
    costo_anterior = datos.get("costo_promedio", costo_unitario)
    
    # Determinar proveedor: usar el especificado o el último registrado
    if proveedor:
        proveedor_final = proveedor.strip()
    else:
        proveedor_final = datos.get("ultimo_proveedor", "—")
    
    # Calcular costo promedio ponderado
    # (cantidad_anterior * costo_anterior + cantidad_nueva * costo_nuevo) / cantidad_total
    cantidad_total = cantidad_anterior + cantidad
    if cantidad_total > 0:
        costo_promedio = round(
            (cantidad_anterior * costo_anterior + cantidad * costo_unitario) / cantidad_total
        )
    else:
        costo_promedio = costo_unitario
    
    # Actualizar inventario
    datos["nombre_original"] = nombre_oficial
    datos["cantidad"] = round(cantidad_total, 4)
    datos["costo_promedio"] = costo_promedio
    datos["ultima_compra"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    datos["ultimo_costo"] = costo_unitario
    datos["ultimo_proveedor"] = proveedor_final
    if "minimo" not in datos:
        datos["minimo"] = 5
    if "unidad" not in datos:
        datos["unidad"] = "unidades"
    
    inventario[clave] = datos
    guardar_inventario(inventario)
    
    # Registrar en historial de compras (para reportes)
    _registrar_historial_compra(nombre_oficial, cantidad, costo_unitario, proveedor_final)
    
    total_compra = round(cantidad * costo_unitario)
    
    proveedor_txt = f"   🏪 Proveedor: {proveedor_final}\n" if proveedor_final != "—" else ""
    
    mensaje = (
        f"✅ Compra registrada:\n"
        f"   📦 +{cantidad} {nombre_oficial}\n"
        f"   📊 Inventario: {cantidad_anterior} → {cantidad_total}\n"
        f"   💰 Costo: ${costo_unitario:,.0f} c/u (${total_compra:,.0f} total)\n"
        f"{proveedor_txt}"
        f"   📈 Costo promedio: ${costo_promedio:,.0f}"
    )
    
    datos_excel = {
        "producto": nombre_oficial,
        "cantidad": cantidad,
        "costo_unitario": costo_unitario,
        "costo_total": total_compra,
        "proveedor": proveedor_final,
    }
    
    return True, mensaje, datos_excel


def _registrar_historial_compra(producto: str, cantidad: float, costo_unitario: float, proveedor: str = "—"):
    """Guarda la compra en el historial para reportes."""
    mem = cargar_memoria()
    if "historial_compras" not in mem:
        mem["historial_compras"] = []
    
    mem["historial_compras"].append({
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "hora": datetime.now().strftime("%H:%M"),
        "proveedor": proveedor,
        "producto": producto,
        "cantidad": cantidad,
        "costo_unitario": costo_unitario,
        "total": round(cantidad * costo_unitario),
    })
    
    # Mantener solo últimos 500 registros
    if len(mem["historial_compras"]) > 500:
        mem["historial_compras"] = mem["historial_compras"][-500:]
    
    guardar_memoria(mem)


def obtener_costo_producto(nombre_producto: str) -> float | None:
    """Obtiene el costo promedio de un producto del inventario."""
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        return None
    
    inventario = cargar_inventario()
    datos = inventario.get(clave, {})
    return datos.get("costo_promedio")


def calcular_margen(nombre_producto: str, precio_venta: float) -> dict | None:
    """
    Calcula el margen de ganancia de un producto.
    Retorna dict con costo, margen_valor, margen_porcentaje o None.
    """
    costo = obtener_costo_producto(nombre_producto)
    if costo is None or costo == 0:
        return None
    
    margen_valor = precio_venta - costo
    margen_porcentaje = round((margen_valor / precio_venta) * 100, 1)
    
    return {
        "costo": costo,
        "precio_venta": precio_venta,
        "margen_valor": margen_valor,
        "margen_porcentaje": margen_porcentaje,
    }


def obtener_resumen_margenes(limite: int = 20) -> list[dict]:
    """
    Obtiene productos con su margen calculado.
    Requiere que el producto tenga costo_promedio y precio en catálogo.
    """
    inventario = cargar_inventario()
    catalogo = cargar_memoria().get("catalogo", {})
    
    resultados = []
    
    for clave, datos in inventario.items():
        if not isinstance(datos, dict):
            continue
        
        costo = datos.get("costo_promedio")
        if not costo:
            continue
        
        nombre = datos.get("nombre_original", clave)
        
        # Buscar precio de venta en catálogo
        producto_cat = buscar_producto_en_catalogo(nombre)
        if not producto_cat:
            continue
        
        precio_venta = producto_cat.get("precio_unidad", 0)
        if not precio_venta or precio_venta <= costo:
            continue
        
        margen_valor = precio_venta - costo
        margen_porcentaje = round((margen_valor / precio_venta) * 100, 1)
        
        resultados.append({
            "nombre": nombre,
            "costo": costo,
            "precio_venta": precio_venta,
            "margen_valor": margen_valor,
            "margen_porcentaje": margen_porcentaje,
            "cantidad": datos.get("cantidad", 0),
        })
    
    # Ordenar por margen porcentaje descendente
    resultados.sort(key=lambda x: -x["margen_porcentaje"])
    return resultados[:limite]


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
        # Producto no en catalogo — no guardar en precios simples, solo retornar False
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

    _FRAC_A_DECIMAL = {
        "1": 1.0, "3/4": 0.75, "1/2": 0.5, "1/4": 0.25,
        "1/8": 0.125, "1/16": 0.0625, "1/3": 0.333, "1/6": 0.167,
    }
    if fraccion and tiene_fracciones_reales:
        # Preservar campo 'decimal' y 'etiqueta' para consistencia con catálogo importado de Excel
        decimal_val = _FRAC_A_DECIMAL.get(fraccion, 0.0)
        entrada_frac = {"precio": round(nuevo_precio)}
        if decimal_val:
            entrada_frac["decimal"] = decimal_val
        # Preservar etiqueta existente si la hay
        frac_existente = catalogo[clave]["precios_fraccion"].get(fraccion, {})
        if isinstance(frac_existente, dict) and "etiqueta" in frac_existente:
            entrada_frac["etiqueta"] = frac_existente["etiqueta"]
        catalogo[clave]["precios_fraccion"][fraccion] = entrada_frac
        # Si la fraccion actualizada es "1" (= unidad completa), sincronizar precio_unidad también
        if fraccion == "1":
            catalogo[clave]["precio_unidad"] = round(nuevo_precio)
            if catalogo[clave].get("precio_por_cantidad"):
                catalogo[clave]["precio_por_cantidad"]["precio_bajo_umbral"] = round(nuevo_precio)
    else:
        catalogo[clave]["precio_unidad"] = round(nuevo_precio)
        # Sincronizar precios_fraccion["1"] (= unidad completa) con precio_unidad
        # Garantiza que ambos campos siempre estén iguales → sin desincronización futura
        fracs = catalogo[clave].get("precios_fraccion", {})
        if fracs and "1" in fracs:
            frac1 = fracs["1"]
            if isinstance(frac1, dict):
                frac1["precio"] = round(nuevo_precio)
            else:
                fracs["1"] = {"precio": round(nuevo_precio), "decimal": 1.0}
        # Limpiar cualquier precios_fraccion corrupto si la fraccion era parte del nombre
        if fraccion_en_nombre:
            catalogo[clave]["precios_fraccion"] = {}
        if catalogo[clave].get("precio_por_cantidad"):
            catalogo[clave]["precio_por_cantidad"]["precio_bajo_umbral"] = round(nuevo_precio)

    mem["catalogo"] = catalogo

    # Limpiar precio viejo de "precios" simples si existe
    precios = mem.get("precios", {})
    nombre_lower = prod.get("nombre_lower", nombre_producto.lower())
    claves_borrar = [k for k in precios if k == nombre_lower or nombre_lower in k or k in nombre_lower]
    for k in claves_borrar:
        del precios[k]
    mem["precios"] = precios

    # urgente=True: sube a Drive sin debounce para evitar pérdida si el container
    # se reinicia antes de que expire el timer de 2s del debounce normal.
    guardar_memoria(mem, urgente=True)
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

    # Limpiar el catálogo antes de importar para evitar duplicados entre
    # el formato viejo (claves legacy como "2vinilodt1blanco") y el nuevo
    # (snake_case como "vinilo_davinci_t1_blanco"). Si no se limpia, cada
    # ejecución de /catalogo acumula ambas versiones del mismo producto.
    catalogo = {}

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
                # Las columnas tienen el precio UNITARIO aplicable a esa fraccion.
                # El precio total = precio_columna x fraccion
                # Ej: col 1/2 = 52000 → precio total 1/2 galon = 52000 x 0.5 = 26000
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
