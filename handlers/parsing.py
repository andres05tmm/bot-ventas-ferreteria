"""
handlers/parsing.py — Parsing puro de mensajes de texto.

Funciones sin efectos secundarios: no escriben a DB, no envían mensajes,
no acceden a estado global. Solo toman texto y retornan datos estructurados.
"""

# -- stdlib --
import re


def parsear_actualizacion_masiva(mensaje: str):
    """
    Detecta un mensaje con múltiples líneas "producto = precio" o
    "producto = precio_unidad / precio_mayorista" (tornillos).
    Retorna lista de (nombre, precio, fraccion, precio_mayorista) si hay ≥2 líneas válidas.
    Retorna None si no es un mensaje de actualización masiva.
    """
    _FRACCIONES = {"1/16", "1/8", "1/4", "1/3", "3/8", "1/2", "3/4", "galon", "galon"}

    _ENCABEZADOS = {
        "actualizar precios", "update precios", "precios",
        "cambiar precios", "nuevos precios", "subir precios",
        "bajar precios", "precios nuevos", "actualizar",
        "actualizar tornillos", "tornillos",
    }

    lineas = [l.strip() for l in mensaje.strip().splitlines()]
    lineas = [l for l in lineas if l]

    # FIX: mensaje llegó como 1 sola línea con espacios en vez de \n
    # (ocurre cuando Telegram colapsa saltos de línea al pegar texto)
    if len(lineas) == 1 and "  " in lineas[0]:
        candidatos = [s.strip() for s in re.split(r"  +", lineas[0]) if s.strip()]
        if len(candidatos) >= 2:
            lineas = candidatos

    # FIX: una "línea" puede contener múltiples pares nombre=precio pegados con espacios
    # Ej: "Cinta Pele L= 17000   Cinta pele XL= 30000"
    # El regex PAT_UNO ancla al final ($) y captura el ÚLTIMO =precio como precio,
    # perdiendo todas las entradas anteriores.
    # Solución: para cada línea, detectar si hay múltiples pares y separarlos.
    _PAT_MULTI = re.compile(
        r"([^=\n]+?)\s*(?:=|:|→|->)\s*\$?\s*([\d][\d.,]*)\s*(?=\S)",
        re.UNICODE
    )
    def _expandir_linea(linea):
        """Si la línea tiene múltiples pares nombre=precio, los separa en sublíneas."""
        # Busca todos los matches de nombre=precio dentro de la línea
        matches = list(re.finditer(
            r"(.+?)\s*(?:=|:|→|->)\s*\$?\s*([\d][\d.,]*)(?=\s+\S|\s*$)",
            linea, re.UNICODE
        ))
        if len(matches) <= 1:
            return [linea]
        # Verificar que los nombres no sean vacíos y los precios sean válidos
        result = []
        for m in matches:
            nombre_part = m.group(1).strip()
            precio_part = m.group(2).strip()
            if nombre_part and precio_part:
                result.append(f"{nombre_part}= {precio_part}")
        return result if len(result) >= 2 else [linea]

    lineas_expandidas = []
    for l in lineas:
        lineas_expandidas.extend(_expandir_linea(l))
    lineas = lineas_expandidas

    # Palabras de acción que indican que la primera línea es (o empieza con) un header
    _PREFIJOS_ACCION = ("actualizar", "update", "cambiar", "subir", "bajar",
                        "nuevos", "precios", "modificar")

    if lineas:
        primera = lineas[0].lower().strip()
        primera_norm = primera.rstrip(": ")

        # Caso especial: "actualizar precios de : Producto = precio"
        # → la primera línea tiene header Y producto en la misma línea
        # Detectar: empieza con palabra de acción, contiene ':', tiene precio después
        _tiene_prefijo_accion = any(primera.startswith(p) for p in _PREFIJOS_ACCION)
        if _tiene_prefijo_accion and ":" in primera:
            # Separar en header y producto en el primer ':'
            _idx_dos_puntos = primera.index(":")
            _resto_original = lineas[0][_idx_dos_puntos + 1:].strip()
            # Si lo que queda del ':' parece un producto con precio, insertarlo
            if _resto_original and re.search(r"[=:→\->].*\d", _resto_original):
                lineas = [_resto_original] + lineas[1:]
            elif _resto_original and re.search(r"\d", _resto_original):
                lineas = [_resto_original] + lineas[1:]
            else:
                lineas = lineas[1:]  # solo header, sin producto
        else:
            # Quitar encabezado si: está en la lista conocida, O si termina en ':'
            # y no tiene número (no es una línea de precio disfrazada de encabezado)
            es_encabezado = (
                primera_norm in _ENCABEZADOS
                or (primera.endswith(":") and not re.search(r"\d", primera))
                or (primera.endswith(":") and not re.search(r"[=:→\->/].*\d", primera))
            )
            if es_encabezado:
                lineas = lineas[1:]

    if not lineas:
        return None

    def _parse_precio(s):
        """Convierte '2.500' o '2,500' o '2500' a float."""
        return float(s.replace(".", "").replace(",", ""))

    # Patrón con dos precios: <nombre> [=|:] <p1> / <p2>
    PAT_DOS = re.compile(
        r"^(.+?)\s*(?:=|:|→|->)\s*\$?\s*([\d][\d.,]*)\s*/\s*\$?\s*([\d][\d.,]*)$",
        re.UNICODE
    )
    # Patrón un precio: <nombre> [=|:] <precio>
    PAT_UNO = re.compile(
        r"^(.+?)\s*(?:=|:|→|->)\s*\$?\s*([\d][\d.,]*)$",
        re.UNICODE
    )
    # Sin separador: <nombre> <precio>
    PAT_ESP = re.compile(r"^(.+?)\s+\$?([\d][\d.,]*)$", re.UNICODE)

    resultados = []
    for linea in lineas:
        if not linea:
            continue

        precio_mayorista = None

        m = PAT_DOS.match(linea)
        if m:
            nombre_raw = m.group(1).strip().rstrip(":")
            try:
                precio = _parse_precio(m.group(2))
                precio_mayorista = _parse_precio(m.group(3))
            except ValueError:
                return None
        else:
            m = PAT_UNO.match(linea) or PAT_ESP.match(linea)
            if not m:
                return None
            nombre_raw = m.group(1).strip().rstrip(":")
            try:
                precio = _parse_precio(m.group(2))
            except ValueError:
                return None

        if precio <= 0:
            return None

        # ── GUARD: si el "nombre" empieza con un número o fracción, es una VENTA
        # con total, no una actualización de precio.
        # Ej: "348 tornillos 6x3/4= 17000" → 348 es la cantidad
        # Ej: "1/2 vinilo= 21000" → 1/2 es la cantidad
        # También "venta:" al inicio
        _nombre_check = nombre_raw.strip().lower()
        if re.match(r'^\d+[\s,]', _nombre_check):
            return None  # Empieza con cantidad entera → es venta
        if re.match(r'^\d+/\d+\s', _nombre_check):
            return None  # Empieza con fracción → es venta
        if re.match(r'^\d+-\d+/\d+\s', _nombre_check):
            return None  # Empieza con mixto (1-1/2) → es venta
        if _nombre_check.startswith(("venta:", "venta ")):
            return None  # Explícitamente una venta

        # Detectar fracción al final del nombre
        fraccion = None
        nombre_lower = nombre_raw.lower()
        for frac in _FRACCIONES:
            if nombre_lower.endswith(" " + frac):
                fraccion = frac if frac not in ("galon",) else None
                nombre_raw = nombre_raw[:-(len(frac)+1)].strip()
                break

        resultados.append((nombre_raw, precio, fraccion, precio_mayorista))

    return resultados if len(resultados) >= 2 else None
