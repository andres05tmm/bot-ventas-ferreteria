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
    "fiado", "a nombre", "cuenta de", "credito",
    "a credito", "de parte", "factura", "facturar",
    "abono", "abonó", "abono de", "pago de", "pagó",
    "debe", "saldo", "deuda",
}

# "para" se revisa por separado: solo bloquea si va seguido de mayúscula o nombre
# "bandeja para rodillo" ✅  |  "2 tornillos para Juan" ❌
import re as _re_para
_PATRON_PARA_CLIENTE = _re_para.compile(r'\bpara\s+[a-záéíóúñ]{3,}', _re_para.IGNORECASE)

_PALABRAS_CONSULTA = {
    "cuanto", "cuánto", "vale", "precio", "cuesta",
    "hay", "stock", "queda", "quedan", "inventario",
    "vendimos", "reporte", "total", "gasto",
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
    """Normaliza para comparación: quita especiales, normaliza plurales y fracciones."""
    s = _norm(s)
    # Preservar fracciones ANTES de limpiar especiales: "1/4"→"1_4", "3/8"→"3_8"
    # Sin esto, _slug("chazos 1/4") → "chazo 14" que no matchea "chazo plastico 14"
    s = re.sub(r'\b(\d+)/(\d+)\b', r'\1_\2', s)
    # Plurales
    s = re.sub(r'\btornillos\b', 'tornillo', s)
    s = re.sub(r'\bpuntillas\b', 'puntilla', s)
    s = re.sub(r'\bchazos\b',    'chazo',    s)
    s = re.sub(r'\bplasticos\b', 'plastico', s)
    # Plurales genéricos: quitar 's' o 'es' final si el producto existe sin él
    s = re.sub(r'\b(\w{4,})es\b', r'\1', s)
    s = re.sub(r'\b(\w{4,})s\b',  r'\1', s)
    # Quitar 'de' suelto: "chazo de 3/8" → "chazo 3/8"
    s = re.sub(r'\s+de\s+', ' ', s)
    # Normalizar fracción con espacio: "8x2 1/2" → "8x2-1_2"
    s = re.sub(r'(\d+x\d+)\s+(1/2|1/4|3/4|1/8)', r'\1-\2', s)
    return re.sub(r'[^\w\s]', '', s).strip()
def _buscar_producto_exacto(nombre_msg: str, catalogo: dict) -> dict | None:
    """
    Busca producto por match exacto normalizado (slug).
    En caso de múltiples coincidencias parciales, retorna el más específico (nombre más largo).
    """
    slug_msg = _slug(nombre_msg.strip())
    # 1. Match exacto
    for prod in catalogo.values():
        slug_prod = _slug(prod.get("nombre_lower", prod.get("nombre", "")))
        if slug_prod == slug_msg:
            return prod
    # 2. Coincidencia por palabras — todas las palabras del mensaje están en el producto
    # Ej: msg="chazo 1_4" → words={"chazo","1_4"} ⊆ "chazo plastico 1_4" → ✅
    # Ej: msg="lija 80" → words={"lija","80"} ⊆ "Lija N°80" → ✅
    words_msg = set(slug_msg.split())
    if not words_msg:
        return None
    candidatos = []
    for prod in catalogo.values():
        slug_prod = _slug(prod.get("nombre_lower", prod.get("nombre", "")))
        if not slug_prod:
            continue
        words_prod = set(slug_prod.split())
        # Todas las palabras del mensaje deben estar en el producto
        if words_msg.issubset(words_prod):
            candidatos.append((len(slug_prod), prod))
    if candidatos:
        # Preferir el producto más específico (más palabras) que aún contenga todas las del msg
        candidatos.sort(key=lambda x: x[0])
        return candidatos[0][1]
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

    # ════════════════════════════════════════════
    # CASO 0: MULTI-LÍNEA — solo tornillos/puntillas/chazos
    # Si TODAS las líneas son cantidad + producto bypasseable,
    # resolvemos en Python sin Claude.
    # ════════════════════════════════════════════
    if "\n" in msg:
        resultado = _intentar_bypass_multilinea(msg, catalogo)
        if resultado is not None:
            return resultado
        return None  # multi-línea con productos no bypasseables → Claude

    # ── Con comas → intentar multi-producto por comas ──
    if "," in msg:
        resultado = _intentar_bypass_multilinea(msg.replace(",", "\n"), catalogo)
        if resultado is not None:
            return resultado
        return None

    # ── Sin palabras problemáticas ──
    # "caja" se bloquea solo si NO va con puntilla (evita bloquear "caja puntilla X")
    for palabra in _PALABRAS_CLIENTE | _PALABRAS_CONSULTA | _PALABRAS_MODIFICACION:
        if palabra in msg_norm:
            if palabra == "caja" and "puntilla" in msg_norm:
                continue  # "caja puntilla X" es venta, no consulta
            return None
    # Nota: "para" se verifica más abajo, después de intentar encontrar el producto
    # (para no bloquear "bandeja para rodillo", "rieles para gaveta", etc.)

    # ════════════════════════════════════════════
    # CASO 0B: PUNTILLAS POR GRAMOS / PESOS / CAJA
    # Patrones: "2000 de puntilla 1 sc" | "300 gramos puntilla 2"
    #           "caja puntilla 1 sc"    | "media caja puntilla 2"
    #           "1/4 caja puntilla 2"
    # ════════════════════════════════════════════
    _PESO_CAJA_GR = 500

    # Solo actuar si el mensaje menciona puntilla
    if "puntilla" in msg_norm:

        # Helper local: buscar puntilla en fragmento de texto
        def _buscar_puntilla(texto: str):
            frag = re.sub(r'^(caja|cajas|gramos?|gr|de|media|medio|cuarto|mitad)\s+', '', texto.strip())
            # Expandir abreviaciones comunes de puntillas
            frag = re.sub(r'\bsc\b', 'sin cabeza', frag)
            frag = re.sub(r'\bcc\b', 'con cabeza', frag)
            frag = re.sub(r'\bsin\s*cab\.?\b', 'sin cabeza', frag)
            frag = re.sub(r'\bcon\s*cab\.?\b', 'con cabeza', frag)
            # Intentar búsqueda exacta primero
            prod = _buscar_producto_exacto(frag, catalogo)
            if prod and "puntilla" in prod.get("nombre", "").lower():
                return prod
            # Fallback: buscar entre puntillas del catálogo por palabras clave
            palabras = set(_norm(frag).split())
            mejores = []
            for p in catalogo.values():
                if "puntilla" not in p.get("nombre", "").lower():
                    continue
                nombre_n = set(_norm(p.get("nombre_lower", p.get("nombre", ""))).replace('"', '').split())
                coincide = palabras & nombre_n
                if coincide:
                    mejores.append((len(coincide), len(nombre_n), p))
            if mejores:
                mejores.sort(key=lambda x: (-x[0], x[1]))
                return mejores[0][2]
            return None

        # ── Caso A: por pesos "$2000 de puntilla X" o "2000 de puntilla X" ──
        m_pesos = re.match(
            r'^\$?(\d{3,})\s+(?:pesos?\s+)?de\s+(?:la\s+|las\s+)?(puntilla.+)$',
            msg_norm
        )
        if not m_pesos:
            # también: "de a 2000 puntilla X"
            m_pesos = re.match(r'^de\s+a\s+(\d{3,})\s+(puntilla.+)$', msg_norm)

        if m_pesos:
            pesos = int(m_pesos.group(1))
            nombre_frag = m_pesos.group(2)
            prod = _buscar_puntilla(nombre_frag)
            if prod and prod.get("unidad_medida", "").upper() == "GRM":
                precio_caja = prod.get("precio_unidad", 0)
                precio_gr   = precio_caja / _PESO_CAJA_GR
                gramos      = round(pesos / precio_gr, 1)
                nombre_oficial = prod["nombre"]
                venta = {"producto": nombre_oficial, "cantidad": gramos, "total": pesos, "metodo_pago": ""}
                texto = f"{gramos:g} gr {nombre_oficial} — ${pesos:,.0f}"
                logger.info(f"[BYPASS PUNTILLA $] '{msg}' → {gramos}gr = ${pesos:,}")
                return texto, venta

        # ── Caso B: por gramos "300 gramos puntilla X" / "300gr puntilla X" ──
        m_gramos = re.match(r'^(\d+(?:\.\d+)?)\s*gr(?:amos?)?\s+(puntilla.+)$', msg_norm)
        if m_gramos:
            gramos = float(m_gramos.group(1))
            nombre_frag = m_gramos.group(2)
            prod = _buscar_puntilla(nombre_frag)
            if prod and prod.get("unidad_medida", "").upper() == "GRM":
                precio_caja = prod.get("precio_unidad", 0)
                precio_gr   = precio_caja / _PESO_CAJA_GR
                total       = round(gramos * precio_gr)
                nombre_oficial = prod["nombre"]
                venta = {"producto": nombre_oficial, "cantidad": gramos, "total": total, "metodo_pago": ""}
                texto = f"{gramos:g} gr {nombre_oficial} — ${total:,.0f}"
                logger.info(f"[BYPASS PUNTILLA GR] '{msg}' → {gramos}gr = ${total:,}")
                return texto, venta

        # ── Caso C: N cajas "caja puntilla X" / "2 cajas puntilla X" / "1 caja de puntillas X" ──
        # Patrón: (N cajas? | caja) [de] puntilla(s) X
        m_caja = re.match(
            r'^(?:(\d+)\s+)?(?:una?\s+)?cajas?\s+(?:de\s+)?(?:las?\s+|los?\s+)?(puntillas?.+)$',
            msg_norm
        )
        if m_caja:
            n_cajas     = int(m_caja.group(1)) if m_caja.group(1) else 1
            nombre_frag = m_caja.group(2)
            prod = _buscar_puntilla(nombre_frag)
            if prod and prod.get("unidad_medida", "").upper() == "GRM":
                precio_caja    = prod.get("precio_unidad", 0)
                nombre_oficial = prod["nombre"]
                gramos_total   = float(_PESO_CAJA_GR * n_cajas)
                total          = precio_caja * n_cajas
                label          = f"{n_cajas} caja{'s' if n_cajas > 1 else ''}" if n_cajas > 1 else "Caja"
                venta = {"producto": nombre_oficial, "cantidad": gramos_total, "total": total, "metodo_pago": ""}
                texto = f"{label} {nombre_oficial} ({int(gramos_total)} gr) — ${total:,.0f}"
                logger.info(f"[BYPASS PUNTILLA CAJA] '{msg}' → {n_cajas} cajas={gramos_total}gr = ${total:,}")
                return texto, venta

        # ── Caso D: fracciones "media caja puntilla X" / "1/4 caja puntilla X" ──
        _FRAC_CAJA = [
            (r'^(?:media|medio|1/2)\s+(?:caja\s+)?(puntilla.+)$', 0.5),
            (r'^(?:un?\s+)?cuarto\s+(?:de\s+)?(?:caja\s+)?(puntilla.+)$', 0.25),
            (r'^1/4\s+(?:de\s+)?(?:caja\s+)?(puntilla.+)$', 0.25),
            (r'^3/4\s+(?:de\s+)?(?:caja\s+)?(puntilla.+)$', 0.75),
        ]
        for patron_fc, fraccion in _FRAC_CAJA:
            m_fc = re.match(patron_fc, msg_norm)
            if m_fc:
                nombre_frag = m_fc.group(1)
                prod = _buscar_puntilla(nombre_frag)
                if prod and prod.get("unidad_medida", "").upper() == "GRM":
                    precio_caja    = prod.get("precio_unidad", 0)
                    gramos         = round(_PESO_CAJA_GR * fraccion, 1)
                    total          = round(precio_caja * fraccion)
                    nombre_oficial = prod["nombre"]
                    frac_label     = {0.5: "Media caja", 0.25: "1/4 caja", 0.75: "3/4 caja"}.get(fraccion, f"{fraccion} caja")
                    venta = {"producto": nombre_oficial, "cantidad": gramos, "total": total, "metodo_pago": ""}
                    texto = f"{frac_label} {nombre_oficial} ({gramos:g} gr) — ${total:,.0f}"
                    logger.info(f"[BYPASS PUNTILLA FRAC] '{msg}' → {gramos}gr = ${total:,}")
                    return texto, venta

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

    cantidad_raw = int(m.group(1))
    nombre_txt   = m.group(2).strip()

    # ── Conversión de unidades: docenas, gruesas ──
    _UNIDADES = {
        "docenas": 12, "docena": 12,
        "medias docenas": 6, "media docena": 6,
        "gruesas": 144, "gruesa": 144,
    }
    cantidad = cantidad_raw
    for unidad, factor in _UNIDADES.items():
        patron_u = r'^' + unidad + r'\s+'
        if re.match(patron_u, nombre_txt, re.IGNORECASE):
            cantidad   = cantidad_raw * factor
            nombre_txt = re.sub(patron_u, '', nombre_txt, flags=re.IGNORECASE).strip()
            break

    if cantidad <= 0 or cantidad > 99999:
        return None

    prod = _buscar_producto_exacto(nombre_txt, catalogo)
    if not prod:
        # Si no encontramos el producto Y el mensaje tiene "para nombre", es un cliente
        if _PATRON_PARA_CLIENTE.search(msg_norm):
            return None
        return None

    precio = _precio_segun_cantidad(prod, cantidad)
    if not precio or precio <= 0:
        return None

    total          = cantidad * precio
    nombre_oficial = prod["nombre"]
    es_mayorista   = (
        prod.get("precio_por_cantidad")
        and cantidad >= prod["precio_por_cantidad"].get("umbral", 50)
    )

    venta = {
        "producto":       nombre_oficial,
        "cantidad":       cantidad,
        "total":          total,
        "precio_unitario": precio,
        "metodo_pago":    "",
    }
    if cantidad == 1:
        texto = f"{nombre_oficial} — ${total:,.0f}"
    elif es_mayorista:
        texto = f"{cantidad} {nombre_oficial} — ${total:,.0f} (${precio:,.0f} c/u 🏭)"
    else:
        texto = f"{cantidad} {nombre_oficial} — ${total:,.0f} (${precio:,.0f} c/u)"
    logger.info(f"[BYPASS ENTERO] ✅ '{msg}' → {nombre_oficial} x{cantidad} = ${total:,}" + (" [mayorista]" if es_mayorista else ""))
    return texto, venta


def _frac_a_decimal(clave: str) -> float:
    """Convierte clave de fracción a decimal."""
    mapa = {
        "1/16": 0.0625, "1/8": 0.125,  "1/4": 0.25,
        "3/8":  0.375,  "1/2": 0.5,    "3/4": 0.75,
    }
    return mapa.get(clave, 0.5)

def _precio_segun_cantidad(prod: dict, cantidad: float) -> int:
    """Retorna el precio unitario correcto según cantidad (mayorista, fracción o normal)."""
    ppc = prod.get("precio_por_cantidad")
    if ppc:
        umbral = ppc.get("umbral", 50)
        if cantidad >= umbral:
            return int(ppc["precio_sobre_umbral"])
        else:
            return int(ppc["precio_bajo_umbral"])
    # Precio fraccionado: si la cantidad es una fracción conocida y el producto
    # tiene precios_fraccion, devolver el precio de esa fracción
    fracs = prod.get("precios_fraccion", {})
    if fracs and 0 < cantidad < 1:
        _DEC_A_FRAC = {
            0.75: "3/4", 0.5: "1/2", 0.25: "1/4",
            0.125: "1/8", 0.0625: "1/16", 0.1: "1/10",
        }
        clave = _DEC_A_FRAC.get(round(cantidad, 4))
        if clave and clave in fracs:
            fv = fracs[clave]
            return int(fv["precio"] if isinstance(fv, dict) else fv)
    return int(prod.get("precio_unidad", 0))



# ─────────────────────────────────────────────
# BYPASS MULTI-LÍNEA (tornillos, puntillas, chazos, productos simples)
# ─────────────────────────────────────────────

# Categorías que el bypass multi-línea puede resolver sin Claude
_PALABRAS_MULTILINEA_OK = {
    "tornillo", "tornillos", "puntilla", "puntillas",
    "chazo", "chazos", "drywall", "broca", "brocas",
}

# Encabezados que se ignoran (no son líneas de producto)
_ENCABEZADOS = re.compile(
    r'^(ventas?|venta|productos?|items?|fecha|marzo|abril|mayo|junio|julio|'
    r'agosto|septiembre|octubre|noviembre|diciembre|enero|febrero|'
    r'lunes|martes|miercoles|jueves|viernes|sabado|domingo|'
    # Fecha tipo "1/4", "12/3" — solo si va seguida de espacio+año o fin de línea
    # NO si va seguida de texto alfabético (sería fracción de producto)
    r'\d{1,2}/\d{1,2}(?:/\d{2,4})?(?:\s*$|\s+\d{4})|\d{4})',
    re.IGNORECASE
)

def _intentar_bypass_multilinea(mensaje: str, catalogo: dict) -> tuple | None:
    """
    Intenta resolver un mensaje multi-línea en Python.
    
    Reglas:
    - Ignora líneas de encabezado (fechas, "Ventas", etc.)
    - Cada línea de producto debe ser: "N nombre" (cantidad entera + producto)
    - Si TODAS las líneas son bypasseables → resuelve y retorna resultado
    - Si cualquier línea no es bypasseable → retorna None (va a Claude)
    """
    lineas = [l.strip() for l in mensaje.splitlines() if l.strip()]
    
    lineas_producto = []
    for linea in lineas:
        # Saltar encabezados y líneas muy cortas
        if _ENCABEZADOS.match(linea) or len(linea) < 3:
            continue
        # Saltar líneas con precio incluido (tiene $ → precio manual, va a Claude)
        if "$" in linea:
            return None
        lineas_producto.append(linea)

    if not lineas_producto:
        return None

    # Verificar que todas las líneas son "N producto" bypasseable
    items_resueltos = []
    for linea in lineas_producto:
        # Palabras problemáticas
        linea_norm = _norm(linea)
        for palabra in _PALABRAS_CLIENTE | _PALABRAS_MODIFICACION:
            if palabra in linea_norm:
                return None

        # Patrón: cantidad + nombre
        # Acepta: enteros (3), fracciones (1/4, 3/4) y mixtos (1-1/2, 2-1/4)
        m = re.match(
            r'^(\d+[\-−]\d+/\d+|\d+/\d+|\d+)\s+(.+)$',
            linea.strip()
        )
        if not m:
            return None

        cantidad_str = m.group(1).strip()
        nombre_txt   = _norm(m.group(2).strip())

        # Parsear cantidad (entero, fracción o mixto)
        _FRAC_MAP = {"1/2":0.5,"1/4":0.25,"3/4":0.75,"1/8":0.125,"1/16":0.0625,"2/3":0.667,"1/3":0.333}
        if "/" in cantidad_str:
            # Fracción mixta: "1-1/2" o "2-1/4"
            _mf = re.match(r"^(\d+)[\-−](\d+/\d+)$", cantidad_str)
            if _mf:
                _frac_val = _FRAC_MAP.get(_mf.group(2), 0)
                cantidad_raw = int(_mf.group(1)) + _frac_val
            else:
                cantidad_raw = _FRAC_MAP.get(cantidad_str, 0)
        else:
            cantidad_raw = int(cantidad_str)

        if not cantidad_raw:
            return None

        # Aplicar aliases dinámicos (corrige typos: drwayll→drywall, tiner→thinner, etc.)
        try:
            import alias_manager as _am
            nombre_txt = _norm(_am.aplicar_aliases_dinamicos(nombre_txt))
        except Exception:
            pass

        # Conversión docenas/gruesas
        cantidad = cantidad_raw
        for unidad, factor in [("docenas", 12), ("docena", 12),
                                 ("medias docenas", 6), ("media docena", 6),
                                 ("gruesas", 144), ("gruesa", 144)]:
            patron_u = r'^' + unidad + r'\s+'
            if re.match(patron_u, nombre_txt, re.IGNORECASE):
                cantidad = cantidad_raw * factor
                nombre_txt = re.sub(patron_u, '', nombre_txt, flags=re.IGNORECASE).strip()
                break

        prod = _buscar_producto_exacto(nombre_txt, catalogo)
        if not prod:
            # Fallback: fuzzy search desde memoria
            try:
                from memoria import buscar_producto_en_catalogo
                prod = buscar_producto_en_catalogo(nombre_txt)
            except Exception:
                prod = None

        # ── Caso especial: "N caja puntilla X" → convertir cantidad a gramos ──
        _PESO_CAJA_GR_MULTI = 500
        _m_caja_multi = re.match(
            r'^(?:una?\s+)?cajas?\s+(?:de\s+)?(puntilla.+)$',
            nombre_txt, re.IGNORECASE
        )
        _total_grm_override = None  # precio total precalculado para GRM por cajas
        if _m_caja_multi:
            nombre_sin_caja = _m_caja_multi.group(1).strip()
            try:
                from memoria import buscar_producto_en_catalogo as _bpc
                _prod_grm = _bpc(nombre_sin_caja)
            except Exception:
                _prod_grm = None
            if _prod_grm and _prod_grm.get("unidad_medida", "").upper() == "GRM":
                prod = _prod_grm
                # N cajas → N × 500 gramos
                cantidad = float(_PESO_CAJA_GR_MULTI * cantidad_raw)
                # Total = precio_caja × N_cajas (NO precio_caja × gramos)
                _total_grm_override = _prod_grm.get("precio_unidad", 0) * cantidad_raw

        if not prod:
            return None  # no encontrado ni exacto ni fuzzy → Claude

        precio = _precio_segun_cantidad(prod, cantidad)
        if not precio or precio <= 0:
            return None

        # Para GRM por cajas: usar total precalculado para evitar precio_unidad × gramos
        if _total_grm_override is not None:
            total = _total_grm_override
            precio = int(_total_grm_override / cantidad) if cantidad > 0 else precio  # precio por gramo
        elif 0 < cantidad < 1:
            # Fracción: precio ya es el precio DE esa fracción (no multiplicar)
            fracs = prod.get("precios_fraccion", {})
            _DEC_A_FRAC = {0.75:"3/4", 0.5:"1/2", 0.25:"1/4", 0.125:"1/8", 0.0625:"1/16"}
            clave = _DEC_A_FRAC.get(round(cantidad, 4))
            if clave and clave in fracs:
                fv = fracs[clave]
                total = int(fv["precio"] if isinstance(fv, dict) else fv)
            else:
                total = round(cantidad * prod.get("precio_unidad", 0))
        else:
            total = cantidad * precio
        es_mayorista = (
            prod.get("precio_por_cantidad")
            and cantidad >= prod["precio_por_cantidad"].get("umbral", 50)
        )
        items_resueltos.append({
            "producto":        prod["nombre"],
            "cantidad":        cantidad,
            "precio_unitario": precio,
            "total":           total,
            "es_mayorista":    es_mayorista,
            "es_grm":          prod.get("unidad_medida", "").upper() == "GRM",
        })

    if not items_resueltos:
        return None

    # Construir respuesta y venta multi-producto
    total_general = sum(i["total"] for i in items_resueltos)
    lineas_texto = []
    for i in items_resueltos:
        sufijo = " 🏭" if i["es_mayorista"] else ""
        if i.get("es_grm"):
            cant_label = f"{int(i['cantidad'])} gr"
        else:
            cant_label = str(int(i["cantidad"])) if float(i["cantidad"]).is_integer() else str(i["cantidad"])
        lineas_texto.append(
            f"• {cant_label} {i['producto']} — ${i['total']:,.0f} "
            f"(${i['precio_unitario']:,.0f} c/u{sufijo})"
        )
    lineas_texto.append(f"\n💰 Total: ${total_general:,.0f}")
    lineas_texto.append("¿Cómo fue el pago?")

    texto = "\n".join(lineas_texto)

    # Venta multi-producto: lista de items
    venta = {
        "multi": True,
        "items": items_resueltos,
        "total": total_general,
        "metodo_pago": "",
    }

    logger.info(
        f"[BYPASS MULTI] ✅ {len(items_resueltos)} productos = ${total_general:,}"
    )
    return texto, venta
