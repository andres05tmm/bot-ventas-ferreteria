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
