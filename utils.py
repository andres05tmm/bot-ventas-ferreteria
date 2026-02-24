"""
Utilidades compartidas: conversiones de fracciones, helpers de formato.
Sin dependencias de otros modulos del proyecto para evitar imports circulares.
"""

from datetime import datetime
import config

# Mapas de fraccion a decimal y viceversa
_FRAC_A_DEC: dict[str, float] = {
    # Fracciones estandar
    "1/8":   0.125,
    "1/4":   0.25,
    "3/8":   0.375,
    "1/2":   0.5,
    "5/8":   0.625,
    "3/4":   0.75,
    "7/8":   0.875,
    # Fracciones extendidas (thinner y productos por mililitros)
    "1/12":  round(1/12,  6),   # ≈ 0.083333
    "1/10":  0.1,
    "1/6":   round(1/6,   6),   # ≈ 0.166667
    "1/5":   0.2,
    "3/10":  0.3,
    "1/3":   round(1/3,   6),   # ≈ 0.333333
    "2/5":   0.4,
    "5/9":   round(5/9,   6),   # ≈ 0.555556
    "3/5":   0.6,
    "2/3":   round(2/3,   6),   # ≈ 0.666667
    "7/10":  0.7,
    "4/5":   0.8,
    "5/6":   round(5/6,   6),   # ≈ 0.833333
    "9/10":  0.9,
    "19/20": 0.95,
}

# Inverso: decimal → fraccion legible
# Ordenado de mayor precision a menor para que el mas exacto gane
_DEC_A_FRAC: dict[float, str] = {v: k for k, v in _FRAC_A_DEC.items()}

# Tolerancia para comparacion de decimales
_TOL = 0.013  # ~50 ml en un galon, suficiente para cubrir aproximaciones


def convertir_fraccion_a_decimal(valor) -> float:
    """Convierte fracciones como '1/4', '1/3', '1/12', '3 y 1/4' o numeros a float."""
    if isinstance(valor, (int, float)):
        return float(valor)
    valor = str(valor).strip()
    # Buscar exacto en el mapa expandido primero
    if valor in _FRAC_A_DEC:
        return _FRAC_A_DEC[valor]
    if "/" in valor:
        # Puede ser "3 y 1/4" o "1/12" directo
        if " " in valor:
            try:
                partes  = valor.split()
                entero  = float(partes[0])
                frac_str = partes[-1]  # ultimo token con la fraccion
                fraccion = _FRAC_A_DEC.get(frac_str) or _dividir(frac_str)
                return entero + fraccion
            except Exception:
                pass
        return _dividir(valor)
    try:
        return float(valor)
    except Exception:
        return 0.0


def _dividir(texto: str) -> float:
    """Divide 'num/den' a float, retorna 0 si falla."""
    try:
        num, den = texto.split("/")
        return float(num) / float(den)
    except Exception:
        return 0.0


def decimal_a_fraccion_legible(valor: float) -> str:
    """Convierte 5.75 a '5 y 3/4', 0.25 a '1/4', 0.333 a '1/3', 3.0 a '3'."""
    entero  = int(valor)
    decimal = round(valor - entero, 6)

    fraccion_texto = ""
    mejor_diff = _TOL
    for dec, texto in _DEC_A_FRAC.items():
        diff = abs(decimal - dec)
        if diff < mejor_diff:
            mejor_diff = diff
            fraccion_texto = texto

    if entero == 0 and fraccion_texto:
        return fraccion_texto
    if fraccion_texto:
        return f"{entero} y {fraccion_texto}"
    if decimal < 0.01:
        return str(entero)
    return f"{valor:.2f}"


def obtener_nombre_hoja() -> str:
    """Retorna el nombre de la hoja Excel del mes actual, ej: 'Febrero 2026'."""
    ahora = datetime.now(config.COLOMBIA_TZ)
    return f"{config.MESES[ahora.month]} {ahora.year}"


# ─────────────────────────────────────────────
# TABLA DE THINNER: precio → (cantidad_decimal, fraccion_legible)
#
# El thinner se vende por precio pagado, no por fraccion.
# Muchos precios distintos corresponden a la misma fraccion de galon
# (diferentes calidades / thinners mezclados).
# El total cobrado es SIEMPRE el precio que dijo el cliente.
# ─────────────────────────────────────────────

_THINNER_PRECIO_A_CANTIDAD: dict[int, tuple[float, str]] = {
    3000:  (round(1/12, 6),  "1/12"),
    4000:  (0.1,              "1/10"),
    5000:  (0.125,            "1/8"),
    6000:  (round(1/6, 6),   "1/6"),
    7000:  (0.2,              "1/5"),
    8000:  (0.25,             "1/4"),
    9000:  (0.3,              "3/10"),
    10000: (round(1/3, 6),   "1/3"),
    11000: (round(1/3, 6),   "1/3"),
    12000: (0.4,              "2/5"),
    13000: (0.5,              "1/2"),
    14000: (0.5,              "1/2"),
    15000: (0.5,              "1/2"),
    16000: (round(5/9, 6),   "5/9"),
    17000: (0.6,              "3/5"),
    18000: (0.625,            "5/8"),
    19000: (round(2/3, 6),   "2/3"),
    20000: (0.75,             "3/4"),
    21000: (0.8,              "4/5"),
    22000: (round(5/6, 6),   "5/6"),
    24000: (0.9,              "9/10"),
    25000: (0.95,             "19/20"),
    26000: (1.0,              "1"),
}

# Palabras clave que identifican al thinner en el nombre del producto
_THINNER_KEYWORDS = ("thinner", "tiner", "tinner", "disolvente", "aguarras")


def es_thinner(nombre_producto: str) -> bool:
    """Retorna True si el nombre del producto corresponde a thinner."""
    nombre_lower = nombre_producto.lower()
    return any(k in nombre_lower for k in _THINNER_KEYWORDS)


def cantidad_thinner_por_precio(precio_pagado: float) -> tuple[float, str]:
    """
    Dado el precio que pago el cliente por thinner, retorna (cantidad_decimal, fraccion_legible).
    Si el precio no esta en la tabla, busca el mas cercano.
    Retorna (0.0, "?") si el precio es 0 o no se puede determinar.
    """
    precio_int = int(round(precio_pagado))
    if precio_int <= 0:
        return 0.0, "?"

    # Busqueda exacta primero
    if precio_int in _THINNER_PRECIO_A_CANTIDAD:
        return _THINNER_PRECIO_A_CANTIDAD[precio_int]

    # Buscar el precio mas cercano en la tabla
    precio_mas_cercano = min(_THINNER_PRECIO_A_CANTIDAD.keys(), key=lambda p: abs(p - precio_int))
    return _THINNER_PRECIO_A_CANTIDAD[precio_mas_cercano]


def tabla_thinner_para_prompt() -> str:
    """Genera el texto de la tabla de thinner para incluir en el system prompt."""
    lineas = []
    for precio, (cantidad, frac) in sorted(_THINNER_PRECIO_A_CANTIDAD.items()):
        lineas.append(f"   ${precio:,} → cantidad:{cantidad:.6g} ({frac} de galon)")
    return "\n".join(lineas)
