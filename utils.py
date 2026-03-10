"""
Utilidades compartidas: conversiones de fracciones, helpers de formato, parseo de precios.
Sin dependencias de otros módulos del proyecto para evitar imports circulares.

CORRECCIONES v2:
  - _normalizar centralizada aquí (eliminada la duplicada en memoria.py y excel.py)
  - parsear_precio centralizado aquí (eliminada la duplicada en ventas_state.py y callbacks.py)
  - Audio: manejo seguro de ruta antes del try/finally
"""

import unicodedata
import re
from datetime import datetime
import config

# ─────────────────────────────────────────────
# NORMALIZACIÓN DE TEXTO (única definición en todo el proyecto)
# ─────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    """
    Convierte a minúsculas y elimina tildes/diacríticos.
    Permite comparar 'Andrés' con 'andres', 'MÁLAGA' con 'malaga', etc.
    Es la definición única — importar desde aquí en todos los módulos.
    """
    return (
        unicodedata.normalize("NFD", str(texto).lower())
        .encode("ascii", "ignore")
        .decode()
    )


# ─────────────────────────────────────────────
# PARSEO DE PRECIO (única definición en todo el proyecto)
# ─────────────────────────────────────────────

def parsear_precio(val) -> float:
    """
    Convierte un valor de precio a float, manejando:
      - Strings con $ y comas (ej: "$1,500" → 1500.0)
      - Formato colombiano punto-miles (ej: "1.500" → 1500.0)
      - Formato internacional coma-miles (ej: "1,500" → 1500.0)
      - Formato mixto (ej: "1.500,50" → 1500.50 | "1,500.50" → 1500.50)
      - Ints y floats directos

    CORRECCIÓN: antes esta lógica estaba duplicada en ventas_state.py (_parsear_precio)
    y en callbacks.py (_parsear_precio). Ahora vive aquí y ambos la importan.
    """
    if isinstance(val, (int, float)):
        try:
            return float(val)
        except Exception:
            return 0.0

    val = str(val).replace("$", "").strip()

    if not val:
        return 0.0

    if "," in val and "." in val:
        # Ambos separadores presentes
        if val.rfind(".") > val.rfind(","):
            # Punto es decimal: "1,500.50" → 1500.50
            val = val.replace(",", "")
        else:
            # Coma es decimal: "1.500,50" → 1500.50
            val = val.replace(".", "").replace(",", ".")
    elif "." in val:
        partes = val.split(".")
        if len(partes) == 2 and len(partes[1]) == 3:
            # Separador de miles colombiano: "1.500" → 1500
            val = val.replace(".", "")
        # else: decimal real "4000.5" → dejar como está
    elif "," in val:
        # Solo coma como separador de miles: "1,500" → 1500
        val = val.replace(",", "")

    try:
        return float(val)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
# MAPAS DE FRACCIÓN
# ─────────────────────────────────────────────

_FRAC_A_DEC: dict[str, float] = {
    # Fracciones estándar
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

# Inverso: decimal → fracción legible
_DEC_A_FRAC: dict[float, str] = {v: k for k, v in _FRAC_A_DEC.items()}

# Tolerancia para comparación de decimales
_TOL = 0.013  # ~50 ml en un galón, suficiente para cubrir aproximaciones


def convertir_fraccion_a_decimal(valor) -> float:
    """
    Convierte fracciones a float. Soporta todos estos formatos:
      - Fraccion pura:    '1/4', '3/4', '1/3'
      - Con espacio:      '1 y 1/4', '2 1/2', '1 y 3/4'
      - Con guion:        '1-1/4', '2-1/2', '3-3/4'  <- formato comun del usuario
      - Decimal directo:  '1.25', '0.5'
      - Entero:           '2', 3
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    valor = str(valor).strip()

    if valor in _FRAC_A_DEC:
        return _FRAC_A_DEC[valor]

    if "/" in valor:
        # Formato con guion: "1-1/4", "2-3/4"
        match_guion = re.match(r'^(\d+)-(\d+/\d+)$', valor)
        if match_guion:
            entero   = float(match_guion.group(1))
            frac_str = match_guion.group(2)
            fraccion = _FRAC_A_DEC.get(frac_str) or _dividir(frac_str)
            return entero + fraccion

        # Formato con espacio: "1 y 1/4", "2 1/2", "1 y 3/4"
        if " " in valor:
            try:
                partes   = [p for p in valor.split() if p.lower() != "y"]
                entero   = float(partes[0])
                frac_str = partes[-1]
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
# TABLA DE THINNER: precio → (cantidad_decimal, fracción_legible)
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

_THINNER_KEYWORDS = ("thinner", "tiner", "tinner", "disolvente", "aguarras")


def es_thinner(nombre_producto: str) -> bool:
    """Retorna True si el nombre del producto corresponde a thinner."""
    nombre_lower = nombre_producto.lower()
    return any(k in nombre_lower for k in _THINNER_KEYWORDS)


def cantidad_thinner_por_precio(precio_pagado: float) -> tuple[float, str]:
    """
    Dado el precio que pagó el cliente por thinner, retorna (cantidad_decimal, fraccion_legible).
    Si el precio no está en la tabla, busca el más cercano.
    """
    precio_int = int(round(precio_pagado))
    if precio_int <= 0:
        return 0.0, "?"
    if precio_int in _THINNER_PRECIO_A_CANTIDAD:
        return _THINNER_PRECIO_A_CANTIDAD[precio_int]
    precio_mas_cercano = min(_THINNER_PRECIO_A_CANTIDAD.keys(), key=lambda p: abs(p - precio_int))
    return _THINNER_PRECIO_A_CANTIDAD[precio_mas_cercano]


def tabla_thinner_para_prompt() -> str:
    """Genera el texto de la tabla de thinner para incluir en el system prompt."""
    lineas = []
    for precio, (cantidad, frac) in sorted(_THINNER_PRECIO_A_CANTIDAD.items()):
        lineas.append(f"   ${precio:,} → cantidad:{cantidad:.6g} ({frac} de galón)")
    return "\n".join(lineas)


# ─────────────────────────────────────────────
# CORRECTOR DE TRANSCRIPCIÓN DE AUDIO
# ─────────────────────────────────────────────

_CORRECCIONES_AUDIO: dict[str, str] = {
    # Drywall
    "driver":    "drywall",
    "draiul":    "drywall",
    "draibol":   "drywall",
    "draiwall":  "drywall",
    "draiuol":   "drywall",
    "graihol":   "drywall",
    # Thinner
    "tiner":     "thinner",
    "tinner":    "thinner",
    # Boxer
    "boser":     "boxer",
    "vocel":     "boxer",
    "bocel":     "boxer",
    "bóxer":     "boxer",
    # Bisagra
    "bisara":    "bisagra",
    "visagra":   "bisagra",
    "bisarga":   "bisagra",
    # Puntilla
    "pontilla":  "puntilla",
    "puntia":    "puntilla",
    # Sellador
    "cejador":   "sellador",
    "sejador":   "sellador",
    # Segueta
    "cegueta":   "segueta",
    "sagueta":   "segueta",
    # Chazos
    "dos hechazos": "doce chazos",
    "hechazos":     "chazos",
    # Latecol
    "la tecol":  "latecol",
    "latecoll":  "latecol",
}



def normalizar_numeros_audio(texto: str) -> str:
    """
    Convierte números escritos en letras a dígitos para que el bypass pueda procesarlos.
    Ejemplo: "dos martillos, tres tornillos seis por uno" → "2 martillos, 3 tornillos 6x1"
    Orden: fracciones primero, luego números individuales, luego compuestos, luego "por" → "x".
    """
    import re as _re

    # ── 1. Fracciones habladas PRIMERO (antes de convertir números sueltos) ──
    # Fracciones compuestas primero, luego simples
    _FRACS = [
        (r'\bcinco octavos\b',    '5/8'),
        (r'\bsiete octavos\b',    '7/8'),
        (r'\btres octavos\b',     '3/8'),
        (r'\bun octavo\b',        '1/8'),
        (r'\btres cuartos\b',     '3/4'),
        (r'\bun cuarto\b',        '1/4'),
        (r'\btres dieciséis\b',   '3/16'),
        (r'\btres dieciseis\b',   '3/16'),
        (r'\bcinco dieciséis\b',  '5/16'),
        (r'\bcinco dieciseis\b',  '5/16'),
        (r'\bmedio\b',            '1/2'),
        (r'\bmedia\b',            '1/2'),
    ]
    for patron, valor in _FRACS:
        texto = _re.sub(patron, valor, texto, flags=_re.IGNORECASE)

    # ── 2. Números en letras → dígitos (de mayor a menor para evitar solapamientos) ──
    _NUMS = [
        (r'\bveintiuno\b','21'),(r'\bveintidós\b','22'),(r'\bveintidos\b','22'),
        (r'\bveintitrés\b','23'),(r'\bveintitres\b','23'),(r'\bveinticuatro\b','24'),
        (r'\bveinticinco\b','25'),(r'\bveintiséis\b','26'),(r'\bveintiseis\b','26'),
        (r'\bveintisiete\b','27'),(r'\bveintiocho\b','28'),(r'\bveintinueve\b','29'),
        (r'\bveinte\b','20'),(r'\btreinta\b','30'),(r'\bcuarenta\b','40'),
        (r'\bcincuenta\b','50'),(r'\bsesenta\b','60'),(r'\bsetenta\b','70'),
        (r'\bochenta\b','80'),(r'\bnoventa\b','90'),(r'\bcien\b','100'),
        (r'\bonce\b','11'),(r'\bdoce\b','12'),(r'\btrece\b','13'),
        (r'\bcatorce\b','14'),(r'\bquince\b','15'),(r'\bdiez\b','10'),
        (r'\bnueve\b','9'),(r'\bocho\b','8'),(r'\bsiete\b','7'),
        (r'\bseis\b','6'),(r'\bcinco\b','5'),(r'\bcuatro\b','4'),
        (r'\btres\b','3'),(r'\bdos\b','2'),
        (r'\buno\b','1'),(r'\buna\b','1'),(r'\bun\b','1'),
    ]
    for patron, digito in _NUMS:
        texto = _re.sub(patron, digito, texto, flags=_re.IGNORECASE)

    # ── 3. Compuestos: "30 y 4" → "34", "20 y 4" → "24" ──
    def _comp(m): return str(int(m.group(1)) + int(m.group(2)))
    texto = _re.sub(r'\b(10|20|30|40|50|60|70|80|90)\s+y\s+([1-9])\b', _comp, texto)

    # ── 4. Fracciones mixtas genéricas: "2 y 3/4" → "2-3/4" ──
    # Funciona para cualquier combinación después de convertir números en letras:
    # "uno y tres cuartos" → paso 1 "uno y 3/4" → paso 2 "1 y 3/4" → aquí "1-3/4"
    texto = _re.sub(r'\b(\d+)\s+y\s+(\d+/\d+)\b', r'\1-\2', texto)

    # ── 5. "N por M" → "NxM" (medidas de tornillo) ──
    texto = _re.sub(r'\b(\d+)\s+por\s+(\d+(?:[/-]\d+)?)\b', r'\1x\2', texto, flags=_re.IGNORECASE)

    # ── 6. Limpiar espacios múltiples ──
    texto = _re.sub(r' {2,}', ' ', texto).strip()
    return texto

def corregir_texto_audio(texto: str) -> str:
    """
    Corrige errores comunes de transcripción de Whisper antes de enviar a la IA.
    Usa IGNORECASE para no destruir mayúsculas del texto original.
    Aplica reemplazo de palabra completa (\\b) para no corromper otras palabras.
    """
    if not texto:
        return texto
    for error, correcto in _CORRECCIONES_AUDIO.items():
        texto = re.sub(rf'\b{error}\b', correcto, texto, flags=re.IGNORECASE)
    # Normalizar medidas habladas de brocas antes del regex principal
    _medidas_texto = {
        r'un octavo':           '1/8',
        r'1 octavo':            '1/8',
        r'un cuarto':           '1/4',
        r'1 cuarto':            '1/4',
        r'tres diec[ié]seis':   '3/16',
        r'cinco diec[ié]seis':  '5/16',
        r'tres treintaidós':    '3/32',
        r'cinco treintaidós':   '5/32',
        r'532':                 '5/32',
        r'316':                 '5/16',
        r'132':                 '1/32',
    }
    for patron, fraccion in _medidas_texto.items():
        texto = re.sub(
            rf'\bbroca(s?)\s+(?:de\s+)?(?!para\s+(?:metal|muro)){patron}\b',
            lambda m, f=fraccion: f'broca{m.group(1)} para metal {f}',
            texto, flags=re.IGNORECASE
        )
    # Rodillo sin especificar pulgadas -> Convencional
    import re as _re2
    texto = _re2.sub(
        r'\b(\d+)\s+rodillo(s?)\b(?!\s+(?:de\s+)?\d)',
        lambda m: f'{m.group(1)} rodillo{m.group(2)} convencional',
        texto, flags=re.IGNORECASE
    )
    # Brocas con fraccion numerica sin tipo -> para metal
    texto = re.sub(
        r'\bbroca(s?)\s+(?:de\s+)?(?!para\s+(?:metal|muro))(\d+/\d+)',
        lambda m: f'broca{m.group(1)} para metal {m.group(2)}',
        texto, flags=re.IGNORECASE
    )
    # Normalizar números en letras → dígitos para que el bypass pueda procesar audio
    texto = normalizar_numeros_audio(texto)
    return texto
