"""
bypass.py — Bypass directo Python para ventas sin llamar a Claude.

VERSIÓN 2: Soporta fracciones simples y fracciones mixtas.

TIPOS DE VENTA BYPASSEADOS:
  1. Cantidad entera:    "2 martillo"         → 2 × precio_unidad
  2. Fracción sola:      "1/2 vinilo azul t1" → precios_fraccion["1/2"]
  3. Fracción mixta:     "1-1/2 vinilo azul t1" → precio_unidad + precios_fraccion["1/2"]
  4. Mixta texto:        "1 y medio vinilo"   → precio_unidad + precios_fraccion["1/2"]
  5. Entero múltiple:    "3 vinilo azul t1"   → 3 × precio_unidad

CUÁNDO NO SE ACTIVA (va a Claude):
  - Multi-producto (comas, saltos de línea)
  - Palabras de cliente (para, fiado, a nombre...)
  - Consultas (cuánto vale, hay stock...)
  - Modificaciones (cambia, quita, borra...)
  - Tornillos con precio_por_cantidad (mayorista)
  - Fracción no existente en el catálogo

MATH FRACCIÓN MIXTA:
  1-1/2 galones = precio_unidad × 1 + precios_fraccion["1/2"]
  2-1/4 galones = precio_unidad × 2 + precios_fraccion["1/4"]
  La suma es determinista y exacta — Python nunca se equivoca.

IMPACTO:
  - ~60% de mensajes bypasseables (vs 40% sin fracciones)
  - Velocidad: 800ms → <5ms
  - Ahorro estimado: ~$11/mes (a 200 mensajes/día)
"""

import re
import logging

logger = logging.getLogger("ferrebot.bypass")

# ─────────────────────────────────────────────
# PALABRAS QUE DESHABILITAN EL BYPASS
# ─────────────────────────────────────────────

_PALABRAS_CLIENTE = {
    "para", "fiado", "a nombre", "cuenta de", "credito",
    "a credito", "de parte", "factura", "facturar",
}

_PALABRAS_CONSULTA = {
    "cuanto", "cuánto", "vale", "precio", "cuesta",
    "hay", "stock", "queda", "quedan", "inventario",
    "vendimos", "reporte", "total", "gasto", "caja",
    "ultimo", "últimos", "reciente",
}

_PALABRAS_MODIFICACION = {
    "cambia", "quita", "agrega", "borra", "elimina",
    "corrige", "modifica", "error", "equivoque",
    "cancela", "olvida",
}

# ─────────────────────────────────────────────
# MAPA DE FRACCIONES SOPORTADAS
# ─────────────────────────────────────────────

# Fracción como texto → clave en precios_fraccion
_FRAC_TEXTO_A_CLAVE = {
    # numéricas
    "1/16": "1/16",
    "1/8":  "1/8",
    "1/4":  "1/4",
    "3/8":  "3/8",
    "1/2":  "1/2",
    "3/4":  "3/4",
    # escritas
    "un octavo":   "1/8",
    "cuarto":      "1/4",
    "un cuarto":   "1/4",
    "medio":       "1/2",
    "media":       "1/2",
    "un medio":    "1/2",
    "tres cuartos":"3/4",
}

# Para cantidad mixta: texto de la parte fraccionaria → clave
_FRAC_MIXTA_PATRONES = [
    # "N-1/2", "N-1/4", "N-3/4"  (formato guion)
    (r'^(\d+)\s*-\s*(1/16|1/8|1/4|3/8|1/2|3/4)\s+(.+)$', "guion"),
    # "N y medio", "N y media", "N y cuarto", "N y tres cuartos"
    (r'^(\d+)\s+y\s+(medio|media|un medio|un cuarto|cuarto|tres cuartos|octavo|un octavo)\s+(.+)$', "texto"),
    # "N 1/2", "N 1/4" (espacio simple entre entero y fracción)
    (r'^(\d+)\s+(1/16|1/8|1/4|3/8|1/2|3/4)\s+(.+)$', "espacio"),
]

# Fracción sola al inicio
_FRAC_SOLA_PATRONES = [
    r'^(1/16|1/8|1/4|3/8|1/2|3/4)\s+(?:de\s+)?(.+)$',
    r'^(medio|media|un cuarto|tres cuartos|un octavo)\s+(?:de\s+)?(.+)$',
]

# ─────────────────────────────────────────────
# NORMALIZACIÓN
# ─────────────────────────────────────────────

def _norm(s: str) -> str:
    return (s.lower()
            .replace("á","a").replace("é","e").replace("í","i")
            .replace("ó","o").replace("ú","u").replace("ñ","n"))

def _get_precio_fraccion(prod: dict, clave: str) -> int | None:
    """Obtiene precio de una fracción del producto. Retorna None si no existe."""
    fracs = prod.get("precios_fraccion", {})
    v = fracs.get(clave)
    if v is None:
        return None
    return int(v["precio"]) if isinstance(v, dict) else int(v)

def _slug(s: str) -> str:
    """Quita comillas y caracteres especiales, deja alfanuméricos y espacios."""
    return re.sub(r'[^\w\s]', '', _norm(s)).strip()

def _buscar_producto_exacto(nombre_msg: str, catalogo: dict) -> dict | None:
    """
    Busca producto por match exacto normalizado.
    Usa slug (sin comillas ni especiales) para tolerar 'brocha de 4' == 'Brocha de 4"'.
    """
    slug_msg = _slug(nombre_msg.strip())
    for prod in catalogo.values():
        slug_prod = _slug(prod.get("nombre_lower", prod.get("nombre", "")))
        if slug_prod == slug_msg:
            return prod
    return None

# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────

def intentar_bypass_python(mensaje: str, catalogo: dict) -> tuple | None:
    """
    Intenta resolver la venta directamente en Python sin Claude.

    Retorna (texto_respuesta, venta_dict) si bypass seguro.
    Retorna None si necesita ir a Claude.
    """
    msg = mensaje.strip()
    msg_norm = _norm(msg)

    # ── Sin comas ni saltos → un solo producto ──
    if "," in msg or "\n" in msg:
        return None

    # ── Sin palabras problemáticas ──
    for palabra in _PALABRAS_CLIENTE | _PALABRAS_CONSULTA | _PALABRAS_MODIFICACION:
        if palabra in msg_norm:
            return None

    # ════════════════════════════════════════════
    # CASO 1: FRACCIÓN MIXTA  "1-1/2 vinilo azul"
    # ════════════════════════════════════════════
    for patron, tipo in _FRAC_MIXTA_PATRONES:
        m = re.match(patron, msg_norm, re.IGNORECASE)
        if not m:
            continue

        enteros_str = m.group(1)
        frac_txt    = m.group(2)
        nombre_txt  = m.group(3).strip()

        enteros = int(enteros_str)
        frac_clave = _FRAC_TEXTO_A_CLAVE.get(frac_txt, frac_txt)

        prod = _buscar_producto_exacto(nombre_txt, catalogo)
        if not prod:
            return None

        if prod.get("precio_por_cantidad"):
            return None

        precio_galon = prod.get("precio_unidad", 0)
        precio_frac  = _get_precio_fraccion(prod, frac_clave)

        if not precio_galon or not precio_frac:
            return None  # fracción no existe en catálogo → Claude

        total = (enteros * precio_galon) + precio_frac
        nombre_oficial = prod["nombre"]

        # Formato legible: "1-1/2" o "2 y medio"
        if tipo == "guion":
            cant_legible = f"{enteros}-{frac_txt}"
        else:
            cant_legible = f"{enteros} y {frac_txt}"

        venta = {
            "producto":       nombre_oficial,
            "cantidad":       enteros + _frac_a_decimal(frac_clave),
            "total":          total,
            "precio_unitario": precio_galon,
            "metodo_pago":    "",
        }
        texto = (
            f"{cant_legible} {nombre_oficial} — ${total:,.0f} "
            f"({enteros}×${precio_galon:,.0f} + {frac_clave}=${precio_frac:,.0f})"
        )
        logger.info(f"[BYPASS MIXTO] ✅ '{msg}' → {nombre_oficial} = ${total:,}")
        return texto, venta

    # ════════════════════════════════════════════
    # CASO 2: FRACCIÓN SOLA  "1/2 vinilo azul"
    # ════════════════════════════════════════════
    for patron in _FRAC_SOLA_PATRONES:
        m = re.match(patron, msg_norm, re.IGNORECASE)
        if not m:
            continue

        frac_txt   = m.group(1)
        nombre_txt = m.group(2).strip()
        # Quitar "de " al inicio si quedó
        nombre_txt = re.sub(r'^de\s+', '', nombre_txt)

        frac_clave = _FRAC_TEXTO_A_CLAVE.get(frac_txt, frac_txt)

        prod = _buscar_producto_exacto(nombre_txt, catalogo)
        if not prod:
            return None

        if prod.get("precio_por_cantidad"):
            return None

        precio_frac = _get_precio_fraccion(prod, frac_clave)
        if not precio_frac:
            return None  # fracción no en catálogo → Claude

        nombre_oficial = prod["nombre"]
        venta = {
            "producto":       nombre_oficial,
            "cantidad":       _frac_a_decimal(frac_clave),
            "total":          precio_frac,
            "precio_unitario": precio_frac,
            "metodo_pago":    "",
        }
        texto = f"{frac_clave} {nombre_oficial} — ${precio_frac:,.0f}"
        logger.info(f"[BYPASS FRAC] ✅ '{msg}' → {nombre_oficial} {frac_clave} = ${precio_frac:,}")
        return texto, venta

    # ════════════════════════════════════════════
    # CASO 3: ENTERO SIMPLE  "2 martillo"
    # ════════════════════════════════════════════
    m = re.match(r'^(\d+)\s+(.+)$', msg.strip())
    if not m:
        return None

    cantidad   = int(m.group(1))
    nombre_txt = m.group(2).strip()

    if cantidad <= 0 or cantidad > 9999:
        return None

    prod = _buscar_producto_exacto(nombre_txt, catalogo)
    if not prod:
        return None

    if prod.get("precio_por_cantidad"):
        return None

    precio = prod.get("precio_unidad", 0)
    if not precio or precio <= 0:
        return None

    total          = cantidad * precio
    nombre_oficial = prod["nombre"]

    venta = {
        "producto":       nombre_oficial,
        "cantidad":       cantidad,
        "total":          total,
        "precio_unitario": precio,
        "metodo_pago":    "",
    }
    texto = (
        f"{nombre_oficial} — ${total:,.0f}"
        if cantidad == 1
        else f"{cantidad} {nombre_oficial} — ${total:,.0f} (${precio:,.0f} c/u)"
    )
    logger.info(f"[BYPASS ENTERO] ✅ '{msg}' → {nombre_oficial} x{cantidad} = ${total:,}")
    return texto, venta


def _frac_a_decimal(clave: str) -> float:
    """Convierte clave de fracción a decimal."""
    mapa = {
        "1/16": 0.0625, "1/8": 0.125,  "1/4": 0.25,
        "3/8":  0.375,  "1/2": 0.5,    "3/4": 0.75,
    }
    return mapa.get(clave, 0.5)
