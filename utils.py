"""
Utilidades compartidas: conversiones de fracciones, helpers de formato.
Sin dependencias de otros modulos del proyecto para evitar imports circulares.
"""

from datetime import datetime
import config

# Mapas de fraccion a decimal y viceversa
_FRAC_A_DEC: dict[str, float] = {
    "1/8": 0.125, "1/4": 0.25, "3/8": 0.375, "1/2": 0.5,
    "5/8": 0.625, "3/4": 0.75, "7/8": 0.875,
}
_DEC_A_FRAC: dict[float, str] = {v: k for k, v in _FRAC_A_DEC.items()}


def convertir_fraccion_a_decimal(valor) -> float:
    """Convierte fracciones como '1/4', '1/2', '3 y 1/4' o numeros a float."""
    if isinstance(valor, (int, float)):
        return float(valor)
    valor = str(valor).strip()
    if valor in _FRAC_A_DEC:
        return _FRAC_A_DEC[valor]
    if "/" in valor:
        try:
            num, den = valor.split("/")
            return float(num) / float(den)
        except Exception:
            pass
    if " " in valor:
        try:
            partes = valor.split()
            entero  = float(partes[0])
            fraccion = convertir_fraccion_a_decimal(partes[1])
            return entero + fraccion
        except Exception:
            pass
    try:
        return float(valor)
    except Exception:
        return 0.0


def decimal_a_fraccion_legible(valor: float) -> str:
    """Convierte 5.75 a '5 y 3/4', 0.25 a '1/4', 3.0 a '3'."""
    entero  = int(valor)
    decimal = valor - entero
    fraccion_texto = ""
    for dec, texto in _DEC_A_FRAC.items():
        if abs(decimal - dec) < 0.05:
            fraccion_texto = texto
            break
    if entero == 0 and fraccion_texto:
        return fraccion_texto
    if fraccion_texto:
        return f"{entero} y {fraccion_texto}"
    if decimal < 0.05:
        return str(entero)
    return f"{valor:.2f}"


def obtener_nombre_hoja() -> str:
    """Retorna el nombre de la hoja Excel del mes actual, ej: 'Febrero 2026'."""
    ahora = datetime.now(config.COLOMBIA_TZ)
    return f"{config.MESES[ahora.month]} {ahora.year}"
