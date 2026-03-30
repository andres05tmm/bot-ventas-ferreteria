"""
ai/prompt_products.py — Precálculos de productos para el system prompt.

Matching de catálogo y cálculo de precios para productos con reglas especiales:
  - Candidatos del catálogo (sección MATCH) — la más grande (~300 líneas)
  - Fracciones mixtas (galones parciales)
  - Tornillos (precio mayorista)
  - Puntillas (precio por gramos y por pesos)
  - Pinturas: Acronal, Thinner, Varsol (fracciones de galón)
  - Precios recién modificados (override del cache de Anthropic)
  - Regla multi-producto

Retorna strings ya formateados listos para incluir en el system prompt.

TODOS los imports de memoria, ai y db son LAZY (dentro de función).
"""

# -- stdlib --
import re
import logging

# -- propios --
import fuzzy_match
from utils import _normalizar

logger = logging.getLogger("ferrebot.ai.prompt_products")


def construir_seccion_match(
    mensaje_usuario: str,
    nombre_usuario: str,
    memoria: dict,
) -> str:
    """
    Retorna el bloque con precálculos de fracciones, tornillos, puntillas y
    candidatos del catálogo (sección MATCH) para el mensaje actual.

    Incluye las funciones anidadas:
      _es_keyword_relevante, _extraer_cantidad_mixta, _norm_seg,
      _linea_candidato, _stem, _stem_simple, _es_relevante_resto
    """
    # Lazy imports — evita ciclos con memoria
    from memoria import (
        buscar_producto_en_catalogo,
        buscar_multiples_en_catalogo,
        buscar_multiples_con_alias,
    )

    stopwords = {"que", "del", "los", "las", "una", "uno", "con", "por", "para", "como",
                 "fue", "son", "precio", "vale", "cuesta", "cuanto", "la", "el", "de", "en",
                 "galon", "galones", "litro", "litros", "kilo", "kilos", "metro", "metros",
                 "pulgada", "pulgadas", "unidad", "unidades",
                 "botella", "botellas",
                 "vendi", "vendo", "vendimos", "dame", "quiero", "necesito", "par",
                 # palabras de cantidad fraccionaria — no son nombre de producto
                 "y", "un", "cuarto", "medio", "media", "octavo", "tres"}

    def _es_keyword_relevante(p: str) -> bool:
        """Determina si una palabra debe incluirse como keyword de búsqueda."""
        if p in stopwords:
            return False
        if len(p) > 2:
            return True
        if p.isdigit():
            return True
        # Incluir códigos de variante de 2 chars: t1, t2, t3, x1, 6x, 8x, etc.
        _TALLAS_PC = {"xl", "xs", "xxl", "s", "m", "l"}
        if (len(p) == 2 and any(c.isdigit() for c in p)) or p in _TALLAS_PC:
            return True
        return False

    # Si el mensaje es un prompt de modificación, extraer solo la instrucción del usuario
    # para evitar que el JSON de la venta actual contamine el matching de productos
    _msg_para_candidatos = mensaje_usuario
    _sep_instruccion = "El vendedor quiere modificarla con esta instrucción:"
    if _sep_instruccion in _msg_para_candidatos:
        _msg_para_candidatos = _msg_para_candidatos.split(_sep_instruccion, 1)[1]
    # También limpiar fragmentos JSON residuales (líneas con { } o "clave": valor)
    import re as _re_cand
    _lineas_limpias = [
        l for l in _msg_para_candidatos.splitlines()
        if not _re_cand.match(r'^\s*[\[{"]', l.strip())
    ]
    _msg_para_candidatos = " ".join(_lineas_limpias)

    palabras_clave = [p for p in _msg_para_candidatos.lower().split() if _es_keyword_relevante(p)]
    info_fracciones_extra = ""

    # Mapa decimal → fracción para buscar precio especial
    _dec_a_frac = {0.5: "1/2", 0.25: "1/4", 0.75: "3/4", 0.125: "1/8", 0.0625: "1/16"}
    _frac_a_dec = {"1/2": 0.5, "1/4": 0.25, "3/4": 0.75, "1/8": 0.125, "1/16": 0.0625}

    def _extraer_cantidad_mixta(msg: str):
        """
        Extrae (n_enteros, frac_key, cantidad_total) del mensaje.
        Maneja todas las formas: '2 y medio', '2-1/2', '1.5', '2.5 galones', etc.
        Retorna (None, None, None) si no encuentra cantidad mixta.
        """
        m = msg.lower()

        # Forma decimal: 2.5, 1.5, 3.5 (producida por alias)
        match_dec = re.search(r'(\d+)\.5\b', m)
        if match_dec:
            enteros = int(match_dec.group(1))
            return enteros, "1/2", enteros + 0.5

        match_dec25 = re.search(r'(\d+)\.25\b', m)
        if match_dec25:
            enteros = int(match_dec25.group(1))
            return enteros, "1/4", enteros + 0.25

        match_dec75 = re.search(r'(\d+)\.75\b', m)
        if match_dec75:
            enteros = int(match_dec75.group(1))
            return enteros, "3/4", enteros + 0.75

        # Forma escrita: "2 y medio", "2 y media", "2-1/2", "2 1/2"
        map_frac_texto = {
            r'y\s+medio': "1/2", r'y\s+media': "1/2", r'y\s+un\s+medio': "1/2",
            r'(?<!\d)1/2': "1/2",
            r'y\s+cuarto': "1/4", r'y\s+un\s+cuarto': "1/4", r'(?<!\d)1/4': "1/4",
            r'tres\s+cuartos': "3/4", r'(?<!\d)3/4': "3/4",
            r'y\s+octavo': "1/8", r'y\s+un\s+octavo': "1/8", r'(?<!\d)1/8': "1/8",
        }
        map_enteros_texto = {
            r'\bun\b(?!\s*/)': 1, r'\buno\b': 1,
            r'\b1\b(?!\s*/)': 1,
            r'\bdos\b': 2, r'\b2\b(?!\s*/)': 2,
            r'\btres\b': 3, r'\b3\b(?!\s*/)': 3,
            r'\bcuatro\b': 4, r'\b4\b(?!\s*/)': 4,
            r'\bcinco\b': 5, r'\b5\b(?!\s*/)': 5,
        }

        # Patrón especial N-1/frac: "2-1/2", "3-1/4", etc. — extraer N directamente
        match_guion = re.search(r'\b(\d+)-1/(\d+)', m)
        if match_guion:
            enteros  = int(match_guion.group(1))
            divisor  = int(match_guion.group(2))
            frac_map = {2: "1/2", 4: "1/4", 8: "1/8"}
            frac_g   = frac_map.get(divisor)
            if frac_g:
                return enteros, frac_g, enteros + _frac_a_dec[frac_g]

        # Detectar si hay fracciones o cantidades mixtas en el mensaje
        _patrones_con_y = [
            r'y\s+medio', r'y\s+media', r'y\s+un\s+medio',
            r'y\s+cuarto', r'y\s+un\s+cuarto',
            r'tres\s+cuartos',
            r'y\s+octavo', r'y\s+un\s+octavo',
        ]
        _patrones_fraccion_numerica = [
            (r'(?<!\d)1/2', "1/2"), (r'(?<!\d)3/4', "3/4"),
            (r'(?<!\d)1/4', "1/4"), (r'(?<!\d)1/8', "1/8"),
        ]

        frac_key = None
        # Primero buscar fracciones con "y" (garantizado mixto)
        for pat, v in map_frac_texto.items():
            if pat in _patrones_con_y and re.search(pat, m):
                frac_key = v
                break

        # Si no encontró con "y", buscar fracción numérica SOLO si hay un entero antes
        if not frac_key:
            for pat, v in _patrones_fraccion_numerica:
                match_frac = re.search(pat, m)
                if match_frac:
                    # Verificar que haya un número entero ANTES de la fracción
                    texto_antes = m[:match_frac.start()].strip()
                    if re.search(r'\b[1-9]\d*\s+(?:galon|galones|litro|litros|y)\s*$', texto_antes):
                        frac_key = v
                        break

        if not frac_key:
            return None, None, None

        n_enteros = next((v for pat, v in map_enteros_texto.items() if re.search(pat, m)), None)
        if not n_enteros:
            return None, None, None

        return n_enteros, frac_key, n_enteros + _frac_a_dec[frac_key]

    # Detectar si hay fracciones o decimales mixtos en el mensaje
    _msg_lower_pre = mensaje_usuario.lower()
    _tiene_mixto = any(p in _msg_lower_pre for p in
                       ["1/4", "1/2", "3/4", "1/8", "1/16", "cuarto", "medio", "mitad",
                        "octavo", ".5", ".25", ".75"])

    if _tiene_mixto:
        calculos_multi = []  # lista de (prod, n_enteros, frac_key, cantidad_calc, total_calc)

        # Segmentar por producto para manejar multi-producto
        def _norm_seg(s):
            return (s.lower()
                    .replace("á", "a").replace("é", "e").replace("í", "i")
                    .replace("ó", "o").replace("ú", "u").replace("ñ", "n"))

        _segs = re.split(r'[,\n]+', mensaje_usuario.lower())

        for seg in _segs:
            seg = _norm_seg(seg).strip()
            if not seg:
                continue
            # Buscar producto con fracciones en este segmento
            palabras_seg = seg.split()
            # Extraer fracción una sola vez por segmento (no depende del producto)
            n_enteros, frac_key, cantidad_calc = _extraer_cantidad_mixta(seg)

            for largo in [4, 3, 2]:
                encontrado_seg = False
                for i in range(len(palabras_seg) - largo + 1):
                    fragmento = " ".join(palabras_seg[i:i + largo])
                    prod      = buscar_producto_en_catalogo(fragmento)
                    if prod and prod.get("precios_fraccion"):
                        fracs = prod.get("precios_fraccion", {})
                        # Solo usar este producto si tiene la fracción que necesitamos.
                        if n_enteros and frac_key and frac_key in fracs:
                            # Precio del galón: fracs["1"] si existe, sino precio_unidad
                            if "1" in fracs:
                                p_galon = fracs["1"]["precio"] if isinstance(fracs.get("1"), dict) else fracs.get("1", 0)
                            else:
                                p_galon = prod.get("precio_unidad", 0)
                            p_frac = fracs[frac_key]["precio"] if isinstance(fracs.get(frac_key), dict) else fracs.get(frac_key, 0)
                            if p_galon and p_frac:
                                total_calc = p_galon * n_enteros + p_frac
                                calculos_multi.append((prod["nombre"], n_enteros, frac_key, cantidad_calc, total_calc, p_galon, p_frac))
                                encontrado_seg = True
                                break  # producto correcto encontrado para este segmento
                        # Producto encontrado pero sin la fracción requerida → seguir buscando
                if encontrado_seg:
                    break

        if calculos_multi:
            lineas = []
            for nombre, n_ent, frac, cant, total, p_gal, p_fr in calculos_multi:
                lineas.append(
                    f"{nombre}: cantidad={cant}, total={total} "
                    f"({n_ent}x${p_gal:,} + {frac}=${p_fr:,})"
                )
            info_fracciones_extra = (
                "TOTALES PRECALCULADOS (USA EXACTAMENTE, NO recalcules):\n"
                + "\n".join(lineas)
            )
            print(f"[PRECALCULADO DEBUG]\n{info_fracciones_extra}")
        else:
            print("[PRECALCULADO DEBUG] No se generó precalculado para este mensaje")

    # ── Precalcular tornillos mayorista ──────────────────────────────────────
    _lineas_pre_extra = []
    _segs_pre = re.split(r'[,\n]+', mensaje_usuario.lower())
    for _seg in _segs_pre:
        _seg = _seg.strip()
        if not _seg:
            continue
        # Extraer cantidad entera del segmento (primer número)
        _m_cant = re.match(r'^[^\d]*(\d+)', _seg)
        if not _m_cant:
            continue
        _cant = int(_m_cant.group(1))

        # IMPORTANTE: solo aceptar productos con precio_por_cantidad (tornillos/chazos/mayorista)
        _palabras_no_tornillo = {
            "broca", "broca_para", "lija", "esmeril", "disco", "sierra",
            "metro", "metros", "pita", "cable", "manguera", "varilla",
            "pintura", "vinilo", "esmalte", "thinner", "laca", "aerosol",
            "brocha", "rodillo", "martillo", "taladro",
        }
        _palabras_seg_t = _seg.split()
        _seg_words = set(_palabras_seg_t)
        _es_no_tornillo = any(w in _seg_words for w in _palabras_no_tornillo)

        _prod_encontrado = None
        if not _es_no_tornillo:
            for _largo in [4, 3, 2, 1]:
                for _i in range(len(_palabras_seg_t) - _largo + 1):
                    _frag = " ".join(_palabras_seg_t[_i:_i + _largo])
                    if len(_frag) < 3:
                        continue
                    _p = buscar_producto_en_catalogo(_frag)
                    if _p and _p.get("precio_por_cantidad"):  # solo productos con precio mayorista
                        _prod_encontrado = _p
                        break
                if _prod_encontrado:
                    break

        # Fallback: strip leading number + normalize plurals
        if not _prod_encontrado:
            _sin_numero = re.sub(r'^\d+\s*', '', _seg).strip()
            _sin_numero_s = re.sub(r'\b(\w+)s\b', r'\1', _sin_numero)
            for _intento in [_sin_numero, _sin_numero_s]:
                if len(_intento) >= 3:
                    _prod_encontrado = buscar_producto_en_catalogo(_intento)
                    if _prod_encontrado:
                        break

        if not _prod_encontrado:
            continue

        _pxc = _prod_encontrado.get("precio_por_cantidad")
        _nombre = _prod_encontrado["nombre"]

        # Tornillos/mayorista: calcular precio correcto según umbral
        if _pxc and _cant > 0:
            _umbral = _pxc.get("umbral", 50)
            _p_bajo = _pxc.get("precio_bajo_umbral", 0)
            _p_sobre = _pxc.get("precio_sobre_umbral", 0)
            if _p_bajo and _p_sobre:
                _precio_u = _p_sobre if _cant >= _umbral else _p_bajo
                _total = _cant * _precio_u
                _tier = f"mayorista x{_umbral}+" if _cant >= _umbral else "normal"
                _lineas_pre_extra.append(
                    f"{_nombre}: cantidad={_cant}, precio_unit={_precio_u}({_tier}), total={_total}"
                )

    if _lineas_pre_extra:
        _bloque_pre = (
            "TOTALES PRECALCULADOS (USA EXACTAMENTE, NO recalcules):\n"
            + "\n".join(_lineas_pre_extra)
        )
        if info_fracciones_extra:
            info_fracciones_extra += "\n" + _bloque_pre
        else:
            info_fracciones_extra = _bloque_pre
        print(f"[PRECALCULADO EXTRA]\n{_bloque_pre}")

    # ── Precalcular puntillas por gramos / por pesos ────────────────────────
    _PESO_CAJA_GR = 500
    _grm_lines = []
    _msg_lower = mensaje_usuario.lower()

    if "puntilla" in _msg_lower:
        for _seg in re.split(r'[,\n]+', _msg_lower):
            _seg = _seg.strip()
            if "puntilla" not in _seg:
                continue

            _pprod = None
            _palabras_seg_p = _seg.split()
            for _largo in [5, 4, 3, 2]:
                for _ii in range(len(_palabras_seg_p) - _largo + 1):
                    _frag = " ".join(_palabras_seg_p[_ii:_ii + _largo])
                    if "puntilla" in _frag:
                        _pp = buscar_producto_en_catalogo(_frag)
                        if _pp and _pp.get("unidad_medida", "").upper() == "GRM":
                            _pprod = _pp
                            break
                if _pprod:
                    break

            if not _pprod:
                continue

            _precio_caja = _pprod.get("precio_unidad", 0)
            if not _precio_caja:
                continue
            _precio_gr = _precio_caja / _PESO_CAJA_GR  # pesos por gramo

            _m_pesos  = re.search(r'(?:\$|de\s+a\s+|de\s+)?\s*(\d{3,})\s*(?:pesos?|peso|\$)?', _seg)
            _m_gramos = re.search(r'(\d+(?:\.\d+)?)\s*(?:gr(?:amos?)?|g\b)', _seg)
            _m_media  = re.search(r'media\s+caja|1/2\s+caja|medio', _seg)
            _m_cuarto = re.search(r'cuarto\s+caja|1/4\s+caja', _seg)
            _m_caja_n = re.search(r'(\d+)\s+cajas?\b', _seg)
            _m_caja   = re.search(r'\bcaja\b', _seg) and not _m_media and not _m_cuarto

            if _m_gramos:
                _gr = float(_m_gramos.group(1))
                _total = round(_gr * _precio_gr)
                _grm_lines.append(
                    f"{_pprod['nombre']}: cantidad={_gr}gr, total=${_total} "
                    f"(usa cantidad={_gr}, NO otro número)"
                )
            elif _m_media:
                _gr = _PESO_CAJA_GR / 2
                _total = round(_precio_caja / 2)
                _grm_lines.append(
                    f"{_pprod['nombre']}: media caja={_gr}gr, total=${_total} "
                    f"(usa cantidad={_gr}, NO 0.5 ni 1)"
                )
            elif _m_cuarto:
                _gr = _PESO_CAJA_GR / 4
                _total = round(_precio_caja / 4)
                _grm_lines.append(
                    f"{_pprod['nombre']}: 1/4 caja={_gr}gr, total=${_total} "
                    f"(usa cantidad={_gr}, NO 0.25 ni 1)"
                )
            elif _m_pesos:
                _pesos = int(_m_pesos.group(1))
                if 500 <= _pesos <= 200000:  # rango razonable de venta
                    _gr = round(_pesos / _precio_gr, 1)
                    _grm_lines.append(
                        f"{_pprod['nombre']}: ${_pesos} → {_gr}gr (${_precio_gr:.1f}/gr), total=${_pesos} "
                        f"(usa cantidad={_gr})"
                    )
            elif _m_caja:
                _n_cajas = int(_m_caja_n.group(1)) if _m_caja_n else 1
                _gr_total = _PESO_CAJA_GR * _n_cajas
                _total = _precio_caja * _n_cajas
                _grm_lines.append(
                    f"{_pprod['nombre']}: {_n_cajas} caja(s)={_gr_total}gr, total=${_total} "
                    f"(IMPORTANTE: usa cantidad={_gr_total}, NO {_n_cajas})"
                )

    if _grm_lines:
        _bloque_grm = (
            "TOTALES PRECALCULADOS PUNTILLAS (USA EXACTAMENTE, NO recalcules):\n"
            + "\n".join(_grm_lines)
        )
        if info_fracciones_extra:
            info_fracciones_extra += "\n" + _bloque_grm
        else:
            info_fracciones_extra = _bloque_grm
        print(f"[PRECALCULADO PUNTILLAS GRM]\n{_bloque_grm}")

    # ── Candidatos del catálogo para este mensaje específico ──
    info_candidatos_extra = ""

    # Detectar fracciones y cantidades mixtas mencionadas en el mensaje
    _fracs_mencionadas = set()
    _mapa_palabras = {
        "cuarto": "1/4", "un cuarto": "1/4",
        "medio": "1/2",  "media": "1/2",  "un medio": "1/2",
        "octavo": "1/8", "un octavo": "1/8",
        "tres cuartos": "3/4",
        "botella": "botella", "botellas": "botella",
        "litro": "litro",    "litros": "litro",
    }
    for palabra, frac in _mapa_palabras.items():
        if palabra in _msg_lower:
            _fracs_mencionadas.add(frac)
    for token in _msg_lower.split():
        if token in ("1/4", "1/2", "3/4", "1/8", "1/16", "3/8"):
            _fracs_mencionadas.add(token)

    _fracs_set = {"1/4", "1/2", "3/4", "1/8", "1/16", "3/8", "botella", "litro"}

    def _linea_candidato(p: dict) -> str:
        # Formato comprimido: sin "  - ", sin "$", sin comas, fraccion relevante marcada con *
        fracs = p.get("precios_fraccion", {})
        pxc   = p.get("precio_por_cantidad")
        if fracs:
            nl = p.get("nombre_lower", "")
            palabras_prod = [w for w in nl.split() if len(w) > 3]
            frac_este_prod = None
            _tok = _msg_lower.replace(",", "").split()
            for idx_t, tok in enumerate(_tok):
                if tok in _fracs_set:
                    ventana = " ".join(_tok[idx_t:idx_t + 5])
                    if any(pp in ventana for pp in palabras_prod):
                        frac_este_prod = tok
                        break
            lineas_frac = []
            # Siempre incluir precio_unidad como "1=X" primero — es el precio del
            # galón/unidad completa. Sin esto, Claude no puede calcular fracciones
            # mixtas como "1 galón y un cuarto" porque no tiene el precio base.
            precio_unidad = p.get("precio_unidad", 0)
            if precio_unidad:
                marca_1 = "*" if frac_este_prod == "1" else ""
                lineas_frac.append(f"1={precio_unidad}{marca_1}")
            for k, v in fracs.items():
                if k == "1":
                    continue  # evitar duplicar si ya está en precios_fraccion
                precio = v['precio'] if isinstance(v, dict) else v
                marca = "*" if k == frac_este_prod else ""
                lineas_frac.append(f"{k}={precio}{marca}")
            return f"{p['nombre']}:" + "|".join(lineas_frac)
        elif pxc:
            return f"{p['nombre']}:{pxc['precio_bajo_umbral']}/{pxc['precio_sobre_umbral']}x{pxc['umbral']}"
        else:
            return f"{p['nombre']}:{p['precio_unidad']}"

    if palabras_clave:
        # FIX MULTI-PRODUCTO: segmentar el mensaje por producto para que cada uno
        # tenga garantizado su candidato.
        _segmentos_raw = re.split(r'[,\n]+', mensaje_usuario.lower())
        _segmentos = []
        for seg in _segmentos_raw:
            seg = seg.strip()
            if len(seg) > 3:
                _segmentos.append(seg)

        combinados = {}
        _candidatos_garantizados = {}  # nl → prod: el mejor hit por segmento, siempre incluido

        # Familias donde hay múltiples tallas/variantes — necesitamos límite más alto
        _familias_con_tallas = {"brocha", "rodillo", "lija", "disco", "tornillo", "chazo",
                                 "tuerca", "arandela", "bisagra", "candado", "manguera",
                                 "lampara", "foco", "cable", "codo", "tee", "reduccion"}

        # Palabras de acción al inicio del mensaje que no son producto
        _palabras_accion = {"vendi", "vende", "vendí", "vender", "cobré", "cobre", "cobrar",
                             "dame", "deme", "dar", "quiero", "necesito", "compre", "compré"}

        # Stemming mínimo: quitar 's' final para que "lijas"→"lija", "discos"→"disco"
        def _stem(w):
            if w.endswith("les") and len(w) > 5:
                return w[:-2]   # aerosoles → aerosol
            if w.endswith("es") and len(w) > 4:
                return w[:-2]
            if w.endswith("s") and len(w) > 4:
                return w[:-1]   # tornillos → tornillo
            return w

        # 1. Buscar candidato por cada segmento de producto (garantiza uno por producto)
        for seg in _segmentos:
            seg = re.sub(r'^[^\w]+', '', seg).strip()
            seg = _normalizar(seg)
            palabras_raw = seg.split()
            while palabras_raw and (
                not re.search(r'[\w\d]', palabras_raw[0]) or
                palabras_raw[0] in _palabras_accion or
                re.match(r'^[\d/\.]+$', palabras_raw[0])
            ):
                palabras_raw = palabras_raw[1:]
            _unidades_volumen = {"galon", "galones", "cuarto", "cuartos", "litro", "litros",
                                  "kilo", "kilos", "gramo", "gramos", "metro", "metros",
                                  "unidad", "unidades", "caja", "cajas", "bolsa", "bolsas",
                                  "rollo", "rollos", "par", "pares", "y", "un", "una",
                                  "botella", "botellas",
                                  "medio", "media", "cuarto"}
            while palabras_raw and palabras_raw[0] in _unidades_volumen:
                palabras_raw = palabras_raw[1:]

            palabras_seg = []
            nombre_producto_encontrado = False
            for p in palabras_raw:
                if p in stopwords:
                    continue
                _TALLAS_SEG = {"xl", "xs", "xxl", "s", "m", "l"}
                if (len(p) == 2 and any(c.isdigit() for c in p)) or p in _TALLAS_SEG:
                    palabras_seg.append(p)
                    nombre_producto_encontrado = True
                elif len(p) > 2 and not p.replace('.', '').replace(',', '').isdigit():
                    palabras_seg.append(_stem(p))  # con stemming
                    nombre_producto_encontrado = True
                elif re.match(r'^\d+x\d+', p):  # formatos como 3x3, 8x1
                    palabras_seg.append(p)
                    nombre_producto_encontrado = True
                elif nombre_producto_encontrado and p.isdigit() and 1 <= int(p) <= 999:
                    palabras_seg.append(p)

            if not palabras_seg:
                continue

            es_familia = any(f in seg.lower() or _stem(f) in seg.lower() for f in _familias_con_tallas)
            _limite_seg = 8 if es_familia else 3

            _SOLO_ADJETIVOS = {"pequeno", "pequeña", "pequeño", "grande", "economico",
                                "economica", "simple", "corriente", "basico", "normal",
                                "plastico", "plastica", "metalico", "metalica", "acero",
                                "madera", "hierro", "metal", "comun", "especial"}
            _ES_FRACCION_COMPUESTA = re.compile(r'^\d+[-]\d+/\d+$')
            _ES_FRACCION_SIMPLE = re.compile(r'^\d+/\d+$')

            for largo in [4, 3, 2, 1]:
                encontrado_seg = False
                for i in range(len(palabras_seg) - largo + 1):
                    fragmento = " ".join(palabras_seg[i:i + largo])
                    if len(fragmento) < 3:
                        continue
                    if largo == 1 and fragmento in _SOLO_ADJETIVOS:
                        continue
                    if largo == 1 and _ES_FRACCION_COMPUESTA.match(fragmento) and len(palabras_seg) > 1:
                        continue
                    if largo == 1 and _ES_FRACCION_SIMPLE.match(fragmento) and len(palabras_seg) > 1:
                        otras = [p for p in palabras_seg if p != fragmento]
                        if any(not re.match(r'^[\d/\.\-]+$', p) for p in otras):
                            continue
                    resultados = buscar_multiples_con_alias(fragmento, limite=_limite_seg)
                    primer = True
                    for prod in resultados:
                        nl = prod["nombre_lower"]
                        combinados[nl] = prod
                        if primer:
                            _candidatos_garantizados[nl] = prod
                            primer = False
                            print(f"[SEG DEBUG] seg='{seg[:30]}' frag='{fragmento}' garantizado='{prod['nombre']}'")
                        encontrado_seg = True
                    if encontrado_seg:
                        break
                if encontrado_seg:
                    break

        # 2. Búsqueda global adicional (fragmentos del mensaje completo)
        for largo in [4, 3, 2]:
            for i in range(len(palabras_clave) - largo + 1):
                frag_exact = " ".join(palabras_clave[i:i + largo])
                if len(frag_exact) < 4:
                    continue
                for prod in buscar_multiples_en_catalogo(frag_exact, limite=1):
                    if frag_exact in prod["nombre_lower"]:
                        combinados[prod["nombre_lower"]] = prod

        # 2.5 FILTRO TORNILLOS: evitar confusión entre medidas similares (6x3 vs 6x3/4)
        _medidas_exactas = re.findall(r'\b(\d+)\s*[xX]\s*(\d+)\b(?![/\-])', _msg_lower)
        if _medidas_exactas and ("tornillo" in _msg_lower or "drywall" in _msg_lower):
            for calibre, largo_med in _medidas_exactas:
                medida_exacta = f"{calibre}x{largo_med}"
                productos_a_eliminar = []
                for nl, prod in list(combinados.items()):
                    if "tornillo" in nl or "drywall" in nl:
                        medida_prod = re.search(r'(\d+)[xX](\d+(?:[/-]\d+(?:/\d+)?)?)', nl)
                        if medida_prod:
                            medida_completa = medida_prod.group(0).lower()
                            if medida_exacta in medida_completa and medida_completa != medida_exacta:
                                productos_a_eliminar.append(nl)
                for nl in productos_a_eliminar:
                    if nl in combinados and nl not in _candidatos_garantizados:
                        del combinados[nl]

        # 3. Ordenar: candidatos garantizados primero, luego pool adicional por relevancia
        _garantizados_lista = list(_candidatos_garantizados.values())
        _garantizados_nls   = set(_candidatos_garantizados.keys())
        _resto = sorted(
            [p for p in combinados.values() if p["nombre_lower"] not in _garantizados_nls],
            key=lambda p: sum(1 for w in palabras_clave if w in p["nombre_lower"]),
            reverse=True
        )
        candidatos = _garantizados_lista + _resto
        candidatos = candidatos[:max(len(_garantizados_lista), 25)]

        def _stem_simple(w):
            if w.endswith("les") and len(w) > 5: return w[:-2]
            if w.endswith("es") and len(w) > 4:  return w[:-2]
            if w.endswith("s") and len(w) > 4:   return w[:-1]
            return w

        _palabras_alfab_msg = [
            w for w in palabras_clave
            if len(w) > 2 and not w.replace("/", "").replace("-", "").isdigit()
        ]

        def _es_relevante_resto(prod_nombre_lower):
            """Filtro para candidatos del pool global (no garantizados).
            Exige al menos 1 palabra alfabética del nombre en el mensaje completo."""
            if not _palabras_alfab_msg:
                return True
            nl = _normalizar(prod_nombre_lower)
            return any(
                _normalizar(w) in nl or _stem_simple(_normalizar(w)) in nl
                for w in _palabras_alfab_msg
            )

        # Garantizados: pasan siempre. Resto: pasan solo si son relevantes.
        candidatos = (
            _garantizados_lista +
            [p for p in _resto if _es_relevante_resto(p.get("nombre_lower", ""))]
        )

        if candidatos:
            lineas = [_linea_candidato(p) for p in candidatos]
            info_candidatos_extra = "MATCH:\n" + "\n".join(lineas)
            print(f"[CANDIDATOS DEBUG]\n{info_candidatos_extra}")
        else:
            _frag_fuzzy = " ".join(palabras_clave[:4]) if palabras_clave else ""
            _sugs = fuzzy_match.buscar_fuzzy(_frag_fuzzy) if _frag_fuzzy else []
            if _sugs:
                _lf = [f"  {_p['nombre']}:{_p.get('precio_unidad', 0)} ({_s:.0f}% similar)"
                       for _p, _s in _sugs]
                info_candidatos_extra = (
                    "MATCH_DIFUSO (similares, NO exactos — pregunta cuál es):\n"
                    + "\n".join(_lf)
                )
            else:
                info_candidatos_extra = "MATCH: (sin resultados — producto no encontrado en catalogo)"
                print("[CANDIDATOS DEBUG] MATCH vacío — producto no en catálogo")

    partes = [p for p in [info_fracciones_extra, info_candidatos_extra] if p]
    return "\n\n".join(partes)


def construir_precalculos_especiales(
    mensaje_usuario: str,
    memoria: dict,
) -> str:
    """
    Retorna texto con precálculos de productos especiales:
    Acronal, Thinner, Varsol, tornillos drywall, precios modificados y regla multi-producto.
    """
    # Lazy import — evita ciclo con ai/__init__.py
    from ai import _get_precios_recientes_activos

    msg_l = mensaje_usuario.lower()
    partes = []

    # ── Acronal: precalcular total en Python ──
    acronal_calculado = ""
    _acronal_precio_kg = 13000
    _acronal_precio_medio = 7000
    _frac_mem = memoria.get("precios_fraccion", {}).get("acronal", {})
    if _frac_mem:
        _v1 = _frac_mem.get("1", 0)
        _acronal_precio_kg = int(_v1) if _v1 else _acronal_precio_kg
        _vm = _frac_mem.get("1/2", 0)
        _acronal_precio_medio = int(_vm) if _vm else _acronal_precio_medio
    else:
        for _ak, _av in memoria.get("catalogo", {}).items():
            if "acronal" in _av.get("nombre_lower", ""):
                _pu = _av.get("precio_unidad", 0)
                if _pu:
                    _acronal_precio_kg = int(_pu)
                break
    if "acronal" in msg_l:
        msg_ac = msg_l
        msg_ac = re.sub(r'(\d+)\s+(?:kilo[s]?\s+)?y\s+medio', lambda m: str(int(m.group(1))) + '.5', msg_ac)
        msg_ac = msg_ac.replace('medio kilo', '0.5').replace('kilo y medio', '1.5')
        if re.search(r'(?:^|\s)(?:1/2|medio)\s*(?:kilo[s]?|kg)?\s*(?:de\s+)?acronal|acronal\s*(?:1/2|medio)', msg_ac):
            acronal_calculado = f"ACRONAL PRECALCULADO: 0.5kg = ${_acronal_precio_medio:,} (precio especial). USA cantidad=0.5, total={_acronal_precio_medio} EXACTAMENTE."
            continue_ac = False
        else:
            continue_ac = True
        m_ac = re.search(r'([\d]+(?:[.,]\d+)?(?:-1/2|-1/4)?)\s*(?:kilo[s]?|kg)?\s*(?:de\s+)?acronal|acronal\s*(?:kilo[s]?|kg)?\s*([\d]+(?:[.,]\d+)?(?:-1/2|-1/4)?)', msg_ac) if continue_ac else None
        if m_ac:
            raw = (m_ac.group(1) or m_ac.group(2) or '').strip()
            raw = raw.replace(',', '.').replace('-1/2', '.5').replace('-1/4', '.25')
            try:
                kg = float(raw)
                enteros = int(kg)
                medio   = kg - enteros
                if abs(medio - 0.5) < 0.01:
                    total_ac = enteros * _acronal_precio_kg + _acronal_precio_medio
                elif abs(medio - 0.25) < 0.01:
                    total_ac = enteros * _acronal_precio_kg + round(_acronal_precio_medio / 2)
                else:
                    total_ac = round(kg * _acronal_precio_kg)
                acronal_calculado = (
                    f"ACRONAL PRECALCULADO: {kg}kg = ${total_ac:,} "
                    f"(1kg={_acronal_precio_kg},1/2kg={_acronal_precio_medio}). "
                    f"CRITICO: USA cantidad={kg}, total={total_ac} SIN MODIFICAR. PROHIBIDO recalcular."
                )
            except Exception:
                pass
    if acronal_calculado:
        partes.append(acronal_calculado)

    # ── Thinner y Varsol: precalcular fraccion en Python ──
    _tabla_tv = {3000: "1/12", 4000: "1/10", 5000: "1/8", 6000: "1/6", 8000: "1/4",
                 10000: "1/3", 13000: "1/2", 20000: "3/4", 26000: "1 galon"}
    _dec_tv   = {3000: 1/12, 4000: 0.1, 5000: 0.125, 6000: 1/6, 8000: 0.25,
                 10000: 1/3, 13000: 0.5, 20000: 0.75, 26000: 1.0}

    thinner_lineas = []
    for _producto_tv in ("thinner", "varsol"):
        if _producto_tv not in msg_l:
            continue
        _m_litros   = re.search(rf'(\d+)\s+litros?\s+{_producto_tv}', msg_l)
        _m_botellas = re.search(rf'(\d+)\s+botellas?\s+{_producto_tv}', msg_l)
        if _m_litros:
            _n = int(_m_litros.group(1))
            _total_t = _n * 8000
            thinner_lineas.append(
                f"{_producto_tv.upper()} PRECALCULADO: {_n} litro{'s' if _n > 1 else ''} = "
                f"${_total_t:,} total (cantidad={_n} litros, precio_litro=8000). "
                f"USA cantidad={_n}, total={_total_t} SIN MODIFICAR."
            )
        elif _m_botellas:
            _n = int(_m_botellas.group(1))
            _total_t = _n * 4000
            thinner_lineas.append(
                f"{_producto_tv.upper()} PRECALCULADO: {_n} botella{'s' if _n > 1 else ''} = "
                f"${_total_t:,} total (cantidad={_n} botellas, precio_botella=4000). "
                f"USA cantidad={_n}, total={_total_t} SIN MODIFICAR."
            )
        else:
            _m_precio = re.search(
                rf'(\d[\d\.]*)\s*(?:de\s+)?{_producto_tv}|{_producto_tv}\s+(\d[\d\.]*)', msg_l
            )
            if _m_precio:
                precio_t = int(float(_m_precio.group(1) or _m_precio.group(2)))
                if precio_t in _tabla_tv:
                    frac_t = _tabla_tv[precio_t]
                    dec_t  = _dec_tv[precio_t]
                    thinner_lineas.append(
                        f"{_producto_tv.upper()} PRECALCULADO: ${precio_t:,} = {frac_t} galon "
                        f"(cantidad={dec_t:.4f}, total={precio_t}). USA EXACTAMENTE estos valores."
                    )
    if thinner_lineas:
        partes.append("\n".join(thinner_lineas))

    # ── Tornillos drywall: precalcular precio correcto ──
    tornillo_calculado = ""
    if "drywall" in msg_l or "tornillo" in msg_l:
        tabla_drywall = {
            "6x1/2": (25, 25), "6x3/4": (58, 30), "6x1": (38, 35), "6x1-1/4": (42, 40),
            "6x1-1/2": (58, 55), "6x2": (67, 60), "6x2-1/2": (75, 70), "6x3": (83, 80),
            "8x3/4": (33, 30), "8x1": (38, 35), "8x1-1/2": (58, 55), "8x2": (67, 60), "8x3": (83, 80),
            "10x1": (83, 70), "10x1-1/2": (125, 100), "10x2": (150, 120), "10x2-1/2": (167, 160),
            "10x3": (167, 160), "10x3-1/2": (208, 200), "10x4": (208, 200),
        }
        voz_medida = [
            ("3 y medio", "3-1/2"), ("3 y media", "3-1/2"), ("3½", "3-1/2"),
            ("2 y medio", "2-1/2"), ("2 y media", "2-1/2"),
            ("1 y medio", "1-1/2"), ("1 y media", "1-1/2"), ("1 y cuarto", "1-1/4"),
        ]
        msg_norm = msg_l
        for voz, frac in voz_medida:
            msg_norm = msg_norm.replace(voz, frac)
        m = re.search(r'(\d+)\s+tornillo[s]?\s+drywall\s+(\d+)\s+[xXpor]+\s+([\d\-/½]+)', msg_norm)
        if m:
            cant   = int(m.group(1))
            cal    = m.group(2)
            medida = m.group(3).strip()
            key    = f"{cal}x{medida}"
            if key in tabla_drywall:
                p1, p2 = tabla_drywall[key]
                precio_u = p1 if cant < 50 else p2
                total_t  = cant * precio_u
                tornillo_calculado = (
                    f"TORNILLO PRECALCULADO: {cant} TORNILLO DRYWALL {cal.upper()}X{medida.upper()} "
                    f"({'<' if cant < 50 else '>='} 50 uds → ${precio_u}/u) = total {total_t}. "
                    f"USA EXACTAMENTE estos valores."
                )
    if tornillo_calculado:
        partes.append(tornillo_calculado)

    # ── Precios recién actualizados en RAM — override del cache de Anthropic (TTL 5 min) ──
    precios_modificados_texto = ""
    _pm_ram = _get_precios_recientes_activos()
    # Recomputar palabras_clave mínimo para filtrar overrides relevantes
    _palabras_kw = [p for p in mensaje_usuario.lower().split() if len(p) > 2]
    if _pm_ram and _palabras_kw:
        overrides = []
        for clave_pm, val in _pm_ram.items():
            nombre_pm, _, frac = clave_pm.partition("___")
            if any(p in nombre_pm for p in _palabras_kw):
                if frac:
                    overrides.append(f"{nombre_pm} {frac}={val}")
                else:
                    overrides.append(f"{nombre_pm}={val}")
        if overrides:
            precios_modificados_texto = "PRECIOS ACTUALIZADOS (usar estos, ignorar el catalogo):\n" + "\n".join(overrides)
    if precios_modificados_texto:
        partes.append(precios_modificados_texto)

    # ── Regla multi-producto ──
    _es_multiproducto = "\n" in mensaje_usuario.strip() or mensaje_usuario.count(",") >= 2
    _regla_no_encontrado = (
        "REGLA MULTI-PRODUCTO: Para CADA producto en el mensaje, verifica si existe en el MATCH. "
        "Registra con [VENTA] SOLO los que SÍ encontraste con buena coincidencia. "
        "Si un producto NO tiene match claro en el catálogo (o el match es dudoso/diferente), "
        "NO lo registres y agrégalo a una línea final: "
        "⚠️ No encontré en catálogo: [nombre(s)]. "
        "NUNCA omitas en silencio productos no encontrados ni uses matches dudosos."
        if _es_multiproducto else
        "Si el MATCH está vacío o no coincide con el producto pedido, responde EXACTAMENTE: "
        "⚠️ No encontré en catálogo: [nombre del producto]. "
        "NUNCA uses otra frase como 'No tengo X' o 'X no está disponible'."
    )
    partes.append(_regla_no_encontrado)

    return "\n\n".join(partes)
