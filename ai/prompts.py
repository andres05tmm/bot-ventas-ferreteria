"""
ai/prompts.py — Construccion del system prompt de Claude.
Extraido de ai.py (Tarea G). Funciones puras de construccion de texto.
"""

# -- stdlib --
import re
import logging
import os
import json
import time as _time

# -- propios --
import config
import skill_loader
import alias_manager
import fuzzy_match
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, _normalizar

logger = logging.getLogger("ferrebot.ai.prompts")

# ─────────────────────────────────────────────
# ALIAS DE FERRETERÍA (pre-procesamiento)
# ─────────────────────────────────────────────

_ALIAS_FERRETERIA = [
    # (patrón regex, reemplazo)
    # PUNTILLAS: normalizar abreviaturas y quitar "caja de" → "puntilla X"
    (r'\bcaja[s]?\s+de\s+puntilla[s]?\b', r'puntilla'),   # "caja de puntilla" → "puntilla"
    (r'\bpuntilla[s]?\s+(.*?)\bs\.c\.?\b', r'puntilla \g<1> sin cabeza'),  # s.c → sin cabeza
    (r'\bpuntilla[s]?\s+(.*?)\bc\.c\.?\b', r'puntilla \g<1> con cabeza'),  # c.c → con cabeza
    (r'\bpuntilla[s]?\s+(.*?)\bsc\b',      r'puntilla \g<1> sin cabeza'),  # sc → sin cabeza (sin puntos)
    (r'\bpuntilla[s]?\s+(.*?)\bcc\b',      r'puntilla \g<1> con cabeza'),  # cc → con cabeza (sin puntos)
    (r'\bs\.c\.?\b', r'sin cabeza'),   # s.c genérico
    (r'\bc\.c\.?\b', r'con cabeza'),   # c.c genérico
    (r'\bsc\b(?=.*puntilla|\bpuntilla)', r'sin cabeza'),  # sc genérico cerca de puntilla
    # TORNILLOS DRYWALL: normalizar medidas para evitar confusión (6x3 vs 6x3/4)
    # Importante: estos patrones van PRIMERO para que se apliquen antes de otros
    (r'\btornillo[s]?\s*(?:de\s*)?drywall\s*(\d+)\s*[xX]\s*3\b(?!/)', r'tornillo drywall \g<1>x3'),
    (r'\bdrywall\s*(\d+)\s*[xX]\s*3\b(?!/)', r'drywall \g<1>x3'),
    (r'\b(\d+)\s*[xX]\s*3\b(?!/)\s*(?=.*(?:tornillo|drywall))', r'\g<1>x3'),
    # Rodillo sin medida → Rodillo Convencional
    # Evita que "3 rodillos" matchee "Rodillo de 1"", "Rodillo de 2"", etc.
    # Solo aplica cuando NO va seguido de una medida explícita (número o pulgadas)
    (r'\b(\d+)\s+rodillos?\b(?!\s*(?:de\s+)?\d)', lambda m: f"{m.group(1)} rodillo convencional"),
    # Pita sin color especificado → pita para carpa azul (la más vendida)
    # Solo aplica cuando NO va seguido de un color
    (r'\b(\d+)\s+(?:metros?\s+(?:de\s+)?)?pitas?\b(?!\s*(?:para\s+)?(?:carpa\s+)?(?:azul|rojo|negro|blanco|amarillo))',
        lambda m: f"{m.group(1)} pita para carpa azul"),
    # Pegaternit: normalizar variantes de escritura
    (r'\bpagaternit\b', r'pegaternit'),
    (r'\bpega\s*ternit\b', r'pegaternit'),
    (r'\bpegaeternit\b', r'pegaternit'),
    # Esmalte 3en1: normalizar variantes sin espacios
    (r'\b3en1\b', r'3 en 1'),
    (r'\b3-en-1\b', r'3 en 1'),
    # Thinner/Varsol: litro=1/4 galón (8000), botella/botellita=1/10 galón (4000).
    # Convertimos directo a precio total antes de llegar a Claude.
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellitas?\s+(?:de\s+)?thinner\b',
        lambda m: f"{int(m.group(1) or 1) * 4000} thinner" if int(m.group(1) or 1) > 1 else "thinner 4000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellitas?\s+(?:de\s+)?varsol\b',
        lambda m: f"{int(m.group(1) or 1) * 4000} varsol" if int(m.group(1) or 1) > 1 else "varsol 4000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellas?\s+(?:de\s+)?thinner\b',
        lambda m: f"{int(m.group(1) or 1) * 4000} thinner" if int(m.group(1) or 1) > 1 else "thinner 4000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellas?\s+(?:de\s+)?varsol\b',
        lambda m: f"{int(m.group(1) or 1) * 4000} varsol" if int(m.group(1) or 1) > 1 else "varsol 4000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*litros?\s+(?:de\s+)?thinner\b',
        lambda m: f"{int(m.group(1) or 1) * 8000} thinner" if int(m.group(1) or 1) > 1 else "thinner 8000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*litros?\s+(?:de\s+)?varsol\b',
        lambda m: f"{int(m.group(1) or 1) * 8000} varsol" if int(m.group(1) or 1) > 1 else "varsol 8000"),
    # Thinner/Varsol por galones (cantidades >= 1/2 galón)
    # "1-1/2 galón de thinner", "1 y medio galón de thinner", "2-1/2 galones thinner"
    (r'\b(\d+)\s*-\s*1/2\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1>.5 galones \g<2>'),
    (r'\b(\d+)\s+y\s+(?:medio|1/2)\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1>.5 galones \g<2>'),
    (r'\b(\d+)\s+(?:galon(?:es)?)\s+y\s+(?:medio|1/2)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1>.5 galones \g<2>'),
    # "medio galón de thinner", "1/2 galón thinner"
    (r'\b(?:medio|1/2)\s*(?:galon)?\s*(?:de\s*)?(thinner|varsol)\b', r'0.5 galones \g<1>'),
    # "2 galones de thinner", "1 galón thinner"
    (r'\b(\d+)\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1> galones \g<2>'),
]

def aplicar_alias_ferreteria(mensaje: str) -> str:
    r"""
    Transforma alias comunes antes de enviar a Claude.

    re.sub maneja nativamente tanto callables (lambdas) como strings con
    backreferences \g<1>/\g<2>, por lo que no se necesita lógica especial.
    """
    resultado = alias_manager.aplicar_aliases_dinamicos(mensaje)
    for patron, reemplazo in _ALIAS_FERRETERIA:
        resultado = re.sub(patron, reemplazo, resultado, flags=re.IGNORECASE)
    return resultado

# ─────────────────────────────────────────────
# PARTE ESTÁTICA DEL SYSTEM PROMPT (cacheable)
# ─────────────────────────────────────────────

def _construir_parte_estatica(memoria: dict) -> str:
    """
    Construye la parte del system prompt que NO cambia entre mensajes.
    Al ser idéntica en todas las llamadas, Anthropic la cachea automáticamente.
    """
    from memoria import obtener_precios_como_texto as _obtener_precios_como_texto

    catalogo = memoria.get("catalogo", {})

    def _linea_producto_simple(prod):
        # Solo nombre:precio_unidad — las fracciones llegan via MATCH en la parte dinámica
        # Ahorra ~1960 tokens cacheados vs incluir fracciones completas
        pxc = prod.get("precio_por_cantidad")
        if pxc:
            return f"{prod['nombre']}:{pxc['precio_bajo_umbral']}/{pxc['precio_sobre_umbral']}x{pxc['umbral']}"
        else:
            return f"{prod['nombre']}:{prod['precio_unidad']}"

    if catalogo:
        # Catálogo simplificado: precio_unidad solamente (sin fracciones)
        # Las fracciones completas se inyectan en la parte dinámica via MATCH
        # cuando el producto es mencionado en el mensaje
        categorias: dict = {}
        for prod in catalogo.values():
            cat = prod.get("categoria", "Otros")
            categorias.setdefault(cat, []).append(_linea_producto_simple(prod))
        lineas_cat = []
        for cat, items in sorted(categorias.items()):
            lineas_cat.append(f"{cat}:")
            lineas_cat.extend(items[:60])
        precios_texto = "\n".join(lineas_cat)
    else:
        precios_texto = _obtener_precios_como_texto()

    precios_fraccion_mem = memoria.get("precios_fraccion", {})
    if precios_fraccion_mem:
        lineas_frac = [
            f"{prod_key} {frac}:{precio}"
            for prod_key, fracs in precios_fraccion_mem.items()
            for frac, precio in fracs.items()
        ]
        precios_fraccion_texto = "FRACCIONES EXTRA:\n" + "\n".join(lineas_frac)
    else:
        precios_fraccion_texto = ""

    # En MODO_MATCH_ONLY: catálogo se omite del estático — llega dinámicamente via MATCH
    # o como fallback completo si MATCH no encuentra nada. Cache estable con ~1235 tokens (reglas).
    # En modo normal: catálogo simplificado (solo precio base, sin fracciones) → 26% menos tokens
    _match_only = os.getenv("MODO_MATCH_ONLY", "false").lower() == "true"

    if _match_only:
        # Solo fracciones extra si las hay — el catálogo llega en la parte dinámica
        catalogo_seccion = precios_fraccion_texto
    else:
        catalogo_seccion = (
            "CATALOGO(nombre:precio_galon_o_unidad. Fracciones exactas en MATCH):\n"
            + precios_texto
            + ("\n" + precios_fraccion_texto if precios_fraccion_texto else "")
        ) if precios_texto else precios_fraccion_texto

    negocio_json = json.dumps(memoria.get("negocio", {}), ensure_ascii=False)

    # Skills estáticos: core + precios_base (siempre necesarios, muy cacheables)
    skills_estaticos = skill_loader.obtener_skills_estaticos()

    return f"""{skills_estaticos}

INFORMACION DEL NEGOCIO: {negocio_json}

{catalogo_seccion}"""

# ─────────────────────────────────────────────
# CATÁLOGO COMPLETO PARA FOTOS (Fix 2)
# ─────────────────────────────────────────────

def _construir_catalogo_imagen(memoria: dict) -> str:
    """
    Cuando hay una imagen del cuaderno de ventas, el MATCH dinámico no puede extraer
    candidatos del texto (que solo dice 'foto de ventas'). Este helper inyecta el
    catálogo COMPLETO con TODAS las fracciones para que Claude pueda identificar
    productos y calcular cantidades desde el precio anotado.
    Solo se llama cuando imagen_b64 is not None.
    """
    catalogo = memoria.get("catalogo", {})
    if not catalogo:
        return ""
    lineas = []
    for prod in sorted(catalogo.values(), key=lambda p: p.get("nombre", "")):
        nombre   = prod["nombre"]
        precio_u = prod.get("precio_unidad", 0)
        pxc      = prod.get("precio_por_cantidad")
        fracs    = prod.get("precios_fraccion", {})
        if pxc:
            umbral  = pxc.get("umbral", 50)
            p_bajo  = pxc.get("precio_bajo_umbral", precio_u)
            p_sobre = pxc.get("precio_sobre_umbral", precio_u)
            lineas.append(f"{nombre}: normal={p_bajo}/u | x{umbral}+={p_sobre}/u")
        elif fracs:
            partes_frac = []
            for fk, fd in fracs.items():
                if isinstance(fd, dict) and "precio" in fd:
                    partes_frac.append(f"{fk}=${fd['precio']:,}")
                elif isinstance(fd, (int, float)):
                    partes_frac.append(f"{fk}=${int(fd):,}")
            if partes_frac:
                lineas.append(f"{nombre}: " + " | ".join(partes_frac))
            else:
                lineas.append(f"{nombre}: unidad=${precio_u:,}")
        else:
            lineas.append(f"{nombre}: unidad=${precio_u:,}")
    return "CATÁLOGO COMPLETO CON FRACCIONES (para foto — usa esto para identificar productos y cantidades):\n" + "\n".join(lineas)


# ─────────────────────────────────────────────
# PARTE DINÁMICA DEL SYSTEM PROMPT (por mensaje)
# ─────────────────────────────────────────────

def _construir_parte_dinamica(mensaje_usuario: str, nombre_usuario: str, memoria: dict, dashboard_mode: bool = False) -> str:
    """
    Construye la parte del system prompt que SÍ cambia entre mensajes:
    candidatos del catálogo, cliente encontrado, ventas del día, inventario, caja, etc.
    """
    # Lazy imports de funciones que permanecen en ai.py hasta Tarea I
    from ai import _pg_resumen_ventas
    from ai import _pg_todos_los_datos
    from ai import _pg_clientes_recientes
    from ai import _pg_buscar_cliente
    from ai import _get_precios_recientes_activos

    # Lazy imports de memoria (evita dependencia circular a nivel de módulo)
    from memoria import (
        buscar_producto_en_catalogo,
        buscar_multiples_en_catalogo,
        buscar_multiples_con_alias,
        cargar_inventario,
        cargar_gastos_hoy,
        obtener_resumen_caja,
    )

    # ── Resumen de ventas ──
    resumen               = _pg_resumen_ventas()
    resumen_excel_total   = resumen["total"]      if resumen else 0
    resumen_excel_cantidad = resumen["num_ventas"] if resumen else 0

    total_mes    = resumen_excel_total
    cantidad_mes = resumen_excel_cantidad

    resumen_texto = (
        f"${total_mes:,.0f} en {cantidad_mes} ventas este mes"
    ) if cantidad_mes > 0 else "Sin ventas este mes"

    # ── Datos históricos ──────────────────────────────────────────────────────
    # Dashboard: ampliar keywords y cargar más registros para análisis completo.
    # Telegram: solo cuando hay palabras clave explícitas (optimización de tokens).
    _palabras_analisis = {"cuanto","vendimos","reporte","analiz","total",
                          "resumen","estadistica","top","mas vendido",
                          "dia","semana","mes","ayer","hoy","vendio",
                          "gano","ingreso","mejor","peor","promedio",
                          "historico","registro","cuantas","cuantos"}
    _es_analisis = any(p in mensaje_usuario.lower() for p in _palabras_analisis)
    _es_dash = dashboard_mode  # activado desde procesar_con_claude/_stream cuando viene del dashboard
    if _es_analisis or _es_dash:
        try:
            _limite     = 300 if _es_dash else 200
            todos       = _pg_todos_los_datos(_limite)
            datos_texto = json.dumps(todos, ensure_ascii=False, default=str) if todos else "Sin datos aun"
        except Exception:
            datos_texto = "Sin datos aun"
    else:
        datos_texto = "(no cargado)"

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
            # Solo detectar entero si está SEPARADO de fracciones:
            # - palabras textuales: "un", "dos", "tres"...
            # - número seguido de espacio y luego "y" o palabra (no fracción)
            # Ej: "1 galón y" → sí | "1/4" → no | "24 tornillos" → no
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
        palabras_msg = _msg_lower_pre.split()
        calculos_multi = []  # lista de (prod, n_enteros, frac_key, cantidad_calc, total_calc)

        # Segmentar por producto para manejar multi-producto
        def _norm_seg(s):
            return (s.lower()
                    .replace("á","a").replace("é","e").replace("í","i")
                    .replace("ó","o").replace("ú","u").replace("ñ","n"))

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
                        # Si no, seguir buscando — puede haber un fragmento más específico
                        # adelante en el segmento que sí la tenga.
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
    # Estos casos no los cubre el bloque mixto de arriba.
    # Construimos totales determinísticos antes de que Claude los vea.
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

        # Buscar producto en el segmento
        # IMPORTANTE: solo aceptar productos con precio_por_cantidad (tornillos/chazos/mayorista)
        # Evita que "1/4" matchee "Formón de 1/4" antes de que el fallback encuentre "Chazo 1/4"
        _palabras = _seg.split()

        # Palabras que indican que el segmento NO es un tornillo/arandela mayorista
        _palabras_no_tornillo = {
            "broca", "broca_para", "lija", "esmeril", "disco", "sierra",
            "metro", "metros", "pita", "cable", "manguera", "varilla",
            "pintura", "vinilo", "esmalte", "thinner", "laca", "aerosol",
            "brocha", "rodillo", "martillo", "taladro",
        }
        _seg_words = set(_seg.split())
        _es_no_tornillo = any(w in _seg_words for w in _palabras_no_tornillo)

        _prod_encontrado = None
        if not _es_no_tornillo:
          for _largo in [4, 3, 2, 1]:
            for _i in range(len(_palabras) - _largo + 1):
                _frag = " ".join(_palabras[_i:_i+_largo])
                if len(_frag) < 3:
                    continue
                _p = buscar_producto_en_catalogo(_frag)
                if _p and _p.get("precio_por_cantidad"):  # solo productos con precio mayorista
                    _prod_encontrado = _p
                    break
            if _prod_encontrado:
                break

        # Fallback: strip leading number + normalize plurals
        # "49 chazos 1/4" → "chazos 1/4" → "chazo 1/4" → Chazo Plastico 1/4
        if not _prod_encontrado:
            _sin_numero = re.sub(r'^\d+\s*', '', _seg).strip()
            # Normalize common plurals
            _sin_numero_s = re.sub(r'\b(\w+)s\b', r'\1', _sin_numero)
            for _intento in [_sin_numero, _sin_numero_s]:
                if len(_intento) >= 3:
                    _prod_encontrado = buscar_producto_en_catalogo(_intento)
                    if _prod_encontrado:
                        break

        if not _prod_encontrado:
            continue

        _pxc = _prod_encontrado.get("precio_por_cantidad")
        _fracs = _prod_encontrado.get("precios_fraccion", {})
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
    # Puntillas tienen unidad_medida=GRM. Caja = 500 gr.
    # Formas: "300 gramos puntilla X", "$2000 de puntilla X", "media caja puntilla X"
    _PESO_CAJA_GR = 500
    _grm_lines = []
    _msg_lower = mensaje_usuario.lower()

    # Detectar si el mensaje menciona puntillas
    if "puntilla" in _msg_lower:
        for _seg in re.split(r'[,\n]+', _msg_lower):
            _seg = _seg.strip()
            if "puntilla" not in _seg:
                continue

            # Buscar el producto puntilla en este segmento
            _pprod = None
            _palabras_seg = _seg.split()
            for _largo in [5, 4, 3, 2]:
                for _ii in range(len(_palabras_seg) - _largo + 1):
                    _frag = " ".join(_palabras_seg[_ii:_ii+_largo])
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

            # Caso 1: venta por pesos ("2000 pesos", "$2000", "de a 2000")
            _m_pesos = re.search(r'(?:\$|de\s+a\s+|de\s+)?\s*(\d{3,})\s*(?:pesos?|peso|\$)?', _seg)
            _m_gramos = re.search(r'(\d+(?:\.\d+)?)\s*(?:gr(?:amos?)?|g\b)', _seg)
            _m_media = re.search(r'media\s+caja|1/2\s+caja|medio', _seg)
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
    # palabras_clave ya definida arriba con _es_keyword_relevante (incluye t1/t2/t3)

    # Detectar fracciones y cantidades mixtas mencionadas en el mensaje
    _fracs_mencionadas = set()
    _msg_lower = mensaje_usuario.lower()
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
        if token in ("1/4","1/2","3/4","1/8","1/16","3/8"):
            _fracs_mencionadas.add(token)

    # Tokenizar mensaje para detectar fracciones adyacentes a productos
    _tokens = mensaje_usuario.lower().replace(",","").split()
    _fracs_set = {"1/4","1/2","3/4","1/8","1/16","3/8","botella","litro"}

    def _linea_candidato(p: dict) -> str:
        # Formato comprimido: sin "  - ", sin "$", sin comas, fraccion relevante marcada con *
        fracs = p.get("precios_fraccion", {})
        pxc   = p.get("precio_por_cantidad")
        if fracs:
            nl = p.get("nombre_lower", "")
            palabras_prod = [w for w in nl.split() if len(w) > 3]
            frac_este_prod = None
            _tok = _msg_lower.replace(",","").split()
            for idx_t, tok in enumerate(_tok):
                if tok in _fracs_set:
                    ventana = " ".join(_tok[idx_t:idx_t+5])
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
        # tenga garantizado su candidato, sin que unos "aplasten" a otros.
        # Ej: "1/4 vinilo blanco, 1/2 laca miel, 3/4 thinner" → 3 segmentos independientes
        # Separar solo por coma. NO separar por 'y' — puede ser parte de cantidad mixta
        # Ej: '1 galón y un cuarto vinilo' NO debe partirse
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
            # Limpiar símbolos de puntuación y basura al inicio del segmento
            seg = re.sub(r'^[^\w]+', '', seg).strip()
            # Normalizar tildes usando _normalizar (ya importada desde utils)
            seg = _normalizar(seg)
            # Quitar palabras de acción y cantidades iniciales del segmento
            palabras_raw = seg.split()
            # Saltar tokens no-alfanuméricos, palabras de acción y cantidades al inicio
            while palabras_raw and (
                not re.search(r'[\w\d]', palabras_raw[0]) or
                palabras_raw[0] in _palabras_accion or
                re.match(r'^[\d/\.]+$', palabras_raw[0])
            ):
                palabras_raw = palabras_raw[1:]
            # Saltar palabras de volumen/unidad inmediatas tras la cantidad
            _unidades_volumen = {"galon", "galones", "cuarto", "cuartos", "litro", "litros",
                                  "kilo", "kilos", "gramo", "gramos", "metro", "metros",
                                  "unidad", "unidades", "caja", "cajas", "bolsa", "bolsas",
                                  "rollo", "rollos", "par", "pares", "y", "un", "una",
                                  "botella", "botellas",
                                  "medio", "media", "cuarto"}
            while palabras_raw and palabras_raw[0] in _unidades_volumen:
                palabras_raw = palabras_raw[1:]

            # Incluir: palabras del nombre del producto + números que son tallas (van DESPUÉS del nombre base)
            # Los números como "3", "80", "100" solo se incluyen si no son la primera palabra
            # (para evitar que "3 cuartos de vinilo T1" incluya "3" que matchearía T3)
            palabras_seg = []
            nombre_producto_encontrado = False
            for p in palabras_raw:
                if p in stopwords:
                    continue
                # Tokens cortos: alfanuméricos (t1,t2) y tallas (xl,xs,s,m,l)
                _TALLAS_SEG = {"xl", "xs", "xxl", "s", "m", "l"}
                if (len(p) == 2 and any(c.isdigit() for c in p)) or p in _TALLAS_SEG:
                    palabras_seg.append(p)
                    nombre_producto_encontrado = True
                elif len(p) > 2 and not p.replace('.','').replace(',','').isdigit():
                    palabras_seg.append(_stem(p))  # con stemming
                    nombre_producto_encontrado = True
                elif re.match(r'^\d+x\d+', p):  # formatos como 3x3, 8x1
                    palabras_seg.append(p)
                    nombre_producto_encontrado = True
                elif nombre_producto_encontrado and p.isdigit() and 1 <= int(p) <= 999:
                    # Número de talla SOLO después de haber encontrado el nombre del producto
                    palabras_seg.append(p)

            if not palabras_seg:
                continue

            # Detectar si el segmento es de familia con tallas → usar límite más alto
            es_familia = any(f in seg.lower() or _stem(f) in seg.lower() for f in _familias_con_tallas)
            _limite_seg = 8 if es_familia else 3

            # Palabras que no identifican un producto por sí solas (no usar en largo=1)
            _SOLO_ADJETIVOS = {"pequeno", "pequeña", "pequeño", "grande", "economico",
                                "economica", "simple", "corriente", "basico", "normal",
                                "plastico", "plastica", "metalico", "metalica", "acero",
                                "madera", "hierro", "metal", "comun", "especial"}
            # Patrón de fracción compuesta: 1-1/2, 2-1/4, 3-3/4, etc.
            # Estas son SIEMPRE cantidades, nunca nombres de producto por sí solas
            _ES_FRACCION_COMPUESTA = re.compile(r'^\d+[-]\d+/\d+$')
            # Fracciones simples como 1/2, 1/4 también pueden ser cantidades
            _ES_FRACCION_SIMPLE = re.compile(r'^\d+/\d+$')

            for largo in [4, 3, 2, 1]:
                encontrado_seg = False
                for i in range(len(palabras_seg) - largo + 1):
                    fragmento = " ".join(palabras_seg[i:i + largo])
                    if len(fragmento) < 3:
                        continue
                    # En largo=1, no buscar con palabras que son solo adjetivos/materiales
                    if largo == 1 and fragmento in _SOLO_ADJETIVOS:
                        continue
                    # En largo=1, saltar fracciones compuestas (1-1/2, 2-1/4) si hay más
                    # palabras disponibles — son cantidades, no nombres de producto
                    if largo == 1 and _ES_FRACCION_COMPUESTA.match(fragmento) and len(palabras_seg) > 1:
                        continue
                    # En largo=1, saltar fracciones simples (1/2, 1/4) si hay más palabras
                    # Y el segmento original tiene palabras no-numéricas después
                    if largo == 1 and _ES_FRACCION_SIMPLE.match(fragmento) and len(palabras_seg) > 1:
                        # Solo saltar si las otras palabras del segmento no son puramente numéricas
                        otras = [p for p in palabras_seg if p != fragmento]
                        if any(not re.match(r'^[\d/\.\-]+$', p) for p in otras):
                            continue
                    resultados = buscar_multiples_con_alias(fragmento, limite=_limite_seg)
                    primer = True
                    for prod in resultados:
                        nl = prod["nombre_lower"]
                        combinados[nl] = prod
                        if primer:
                            # El primer resultado es el mejor match — garantizarlo en la lista final
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
        # Si el mensaje menciona una medida exacta como "6x3", eliminar productos con medidas
        # que la contengan pero sean diferentes (como "6x3/4", "6x3-1/2")
        _medidas_exactas = re.findall(r'\b(\d+)\s*[xX]\s*(\d+)\b(?![/\-])', _msg_lower)
        if _medidas_exactas and ("tornillo" in _msg_lower or "drywall" in _msg_lower):
            for calibre, largo_med in _medidas_exactas:
                medida_exacta = f"{calibre}x{largo_med}"
                # Filtrar productos que tengan la medida como substring pero NO sean exactos
                # Ej: si busca "6x3", eliminar "6x3/4" y "6x3-1/2" pero mantener "6x3"
                productos_a_eliminar = []
                for nl, prod in list(combinados.items()):
                    if "tornillo" in nl or "drywall" in nl:
                        # Buscar la medida en el nombre del producto
                        medida_prod = re.search(r'(\d+)[xX](\d+(?:[/-]\d+(?:/\d+)?)?)', nl)
                        if medida_prod:
                            medida_completa = medida_prod.group(0).lower()
                            # Si la medida del producto es más larga que la buscada, es diferente
                            if medida_exacta in medida_completa and medida_completa != medida_exacta:
                                productos_a_eliminar.append(nl)
                for nl in productos_a_eliminar:
                    if nl in combinados and nl not in _candidatos_garantizados:
                        del combinados[nl]

        # 3. Ordenar: más palabras del mensaje completo en el nombre = mayor prioridad
        #    Los candidatos garantizados (mejor hit por segmento) siempre se incluyen primero.
        #    Luego se agregan hasta 25 adicionales del pool general, ordenados por relevancia.
        _garantizados_lista = list(_candidatos_garantizados.values())
        _garantizados_nls   = set(_candidatos_garantizados.keys())
        _resto = sorted(
            [p for p in combinados.values() if p["nombre_lower"] not in _garantizados_nls],
            key=lambda p: sum(1 for w in palabras_clave if w in p["nombre_lower"]),
            reverse=True
        )
        candidatos = _garantizados_lista + _resto
        candidatos = candidatos[:max(len(_garantizados_lista), 25)]

        # Filtro de relevancia: se aplica SOLO al _resto (pool global), nunca a los
        # candidatos garantizados. Un candidato garantizado ya fue validado por el
        # segmentador (tiene su propio segmento que lo respaldó) — filtrarlo aquí con
        # las palabras del mensaje completo sería incorrecto en ventas multi-producto,
        # donde el mensaje tiene muchas palabras que no pertenecen a ese candidato.
        #
        # Para el _resto: comparar contra las palabras del segmento más cercano
        # es complejo, así que se usa el mensaje completo pero con umbral ajustado:
        #   - umbral fijo de 1 hit alfab: cualquier palabra del nombre debe aparecer en
        #     algún lugar del mensaje. Esto filtra productos completamente ajenos (ej:
        #     un tornillo que entró por un número suelto) sin afectar productos legítimos.

        def _stem_simple(w):
            if w.endswith("les") and len(w) > 5: return w[:-2]
            if w.endswith("es") and len(w) > 4:  return w[:-2]
            if w.endswith("s") and len(w) > 4:   return w[:-1]
            return w

        _palabras_alfab_msg = [
            w for w in palabras_clave
            if len(w) > 2 and not w.replace("/","").replace("-","").isdigit()
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
                _lf = [f"  {_p['nombre']}:{_p.get('precio_unidad',0)} ({_s:.0f}% similar)"
                       for _p, _s in _sugs]
                info_candidatos_extra = (
                    "MATCH_DIFUSO (similares, NO exactos — pregunta cuál es):\n"
                    + "\n".join(_lf)
                )
            else:
                info_candidatos_extra = "MATCH: (sin resultados — producto no encontrado en catalogo)"
                print("[CANDIDATOS DEBUG] MATCH vacío — producto no en catálogo")

    # ── Clientes recientes ──
    clientes_recientes_texto = ""
    palabras_recientes = ["ultimo", "ultimos", "reciente", "recientes", "nuevo", "nuevos",
                          "anadido", "anadidos", "agregado", "agregados", "registrado", "registrados"]
    _msg_norm = _normalizar(mensaje_usuario)
    if any(p in _msg_norm for p in palabras_recientes) and "cliente" in _msg_norm:
        try:
            recientes = _pg_clientes_recientes(5)
            if recientes:
                lineas = []
                for c in recientes:
                    nombre = c.get("Nombre tercero", "")
                    id_c   = c.get("Identificacion", "")
                    tipo   = c.get("Tipo de identificacion", "")
                    fecha  = c.get("Fecha registro", "Sin fecha")
                    lineas.append(f"  - {nombre} ({tipo}: {id_c}) — registrado: {fecha}")
                clientes_recientes_texto = (
                    "ULTIMOS 5 CLIENTES REGISTRADOS EN EL SISTEMA:\n" + "\n".join(lineas)
                )
        except Exception as e:
            print(f"Error clientes recientes: {e}")

    # ── Búsqueda de cliente si el mensaje lo indica ──
    clientes_texto      = ""
    _indicadores_cliente = [
        "cliente", "para ", "de parte", "a nombre", "factura", "facturar",
        "a credito", "fiado", "cuenta de",
    ]
    _menciona_cliente = any(ind in mensaje_usuario.lower() for ind in _indicadores_cliente)
    if _menciona_cliente:
        try:
            # Extraer nombre despues de "para", "a nombre de", "de parte de", etc.
            _match_nombre = re.search(
                r'(?:para|a nombre de|de parte de|cuenta de)\s+([A-Za-záéíóúÁÉÍÓÚñÑ]+(?:\s+[A-Za-záéíóúÁÉÍÓÚñÑ]+){0,3})',
                mensaje_usuario, re.IGNORECASE
            )
            if _match_nombre:
                termino_cliente = _match_nombre.group(1).strip()
            else:
                palabras_cliente = [p for p in mensaje_usuario.lower().split()
                                    if len(p) > 3 and p not in stopwords]
                termino_cliente = " ".join(palabras_cliente[:4]) if palabras_cliente else ""
            if termino_cliente:
                cliente_unico, candidatos_cli = _pg_buscar_cliente(termino_cliente)

                if len(candidatos_cli) == 1:
                    c      = candidatos_cli[0]
                    nombre = c.get("Nombre tercero", "")
                    id_c   = c.get("Identificacion", "")
                    tipo   = c.get("Tipo de identificacion", "")
                    # Solo asignar si hay 2+ palabras en comun con el nombre buscado
                    palabras_buscadas    = set(_normalizar(termino_cliente).split())
                    palabras_encontradas = set(_normalizar(nombre).split())
                    coincidencias = palabras_buscadas & palabras_encontradas
                    if len(coincidencias) >= 2 or (len(palabras_buscadas) == 1 and coincidencias):
                        clientes_texto = (
                            f"CLIENTE ENCONTRADO EN EL SISTEMA (usar este directamente):\n"
                            f"  - {nombre} ({tipo}: {id_c})"
                        )
                    else:
                        # Coincidencia parcial — marcar para preguntar ANTES de confirmar
                        clientes_texto = (
                            f"CLIENTE NO IDENTIFICADO: usa exactamente \"cliente\": \"{termino_cliente}\" en el JSON. "
                            f"NO uses \"{nombre}\". El sistema preguntara si es cliente nuevo o existente."
                        )
                elif len(candidatos_cli) > 1:
                    lineas_cli = []
                    for c in candidatos_cli:
                        nombre = c.get("Nombre tercero", "")
                        id_c   = c.get("Identificacion", "")
                        tipo   = c.get("Tipo de identificacion", "")
                        lineas_cli.append(f"  - {nombre} ({tipo}: {id_c})")
                    clientes_texto = (
                        "MULTIPLES CLIENTES ENCONTRADOS — pregunta al usuario cual es:\n"
                        + "\n".join(lineas_cli)
                        + "\nEjemplo: 'Te refieres a NOMBRE1 (CC: 123) o NOMBRE2 (CC: 456)?'"
                    )
        except Exception:
            clientes_texto = ""

    # ── Inventario, caja y gastos ──
    palabras_inv     = ["inventario", "stock", "queda", "quedan", "hay", "cuanto hay", "existencia"]
    inventario_texto = (
        f"INVENTARIO ACTUAL:\n{json.dumps(cargar_inventario(), ensure_ascii=False)}"
        if any(p in mensaje_usuario.lower() for p in palabras_inv) else ""
    )

    palabras_caja_kw = ["caja", "gasto", "gastos", "apertura", "cierre", "efectivo", "cuanto hay en caja"]
    if any(p in mensaje_usuario.lower() for p in palabras_caja_kw):
        caja_texto   = f"ESTADO CAJA:\n{obtener_resumen_caja()}"
        gastos_texto = f"GASTOS DE HOY:\n{json.dumps(cargar_gastos_hoy(), ensure_ascii=False, default=str)}"
    else:
        caja_texto   = ""
        gastos_texto = ""

    aviso_drive = ""  # Drive eliminado — sistema 100% PostgreSQL

    # ── Cuentas por pagar (facturas de proveedores) ───────────────────────────
    _kw_proveedores = ["deuda", "debo", "factura", "proveedor", "abono a", "le pague",
                       "pague a", "cuanto le debo", "fac-", "pendiente", "llego mercancia",
                       "llegó", "trajo"]
    proveedores_texto = ""
    if any(k in mensaje_usuario.lower() for k in _kw_proveedores):
        try:
            from memoria import listar_facturas as _lf
            _facturas_pend = _lf(solo_pendientes=True)
            if _facturas_pend:
                _lineas_prov = []
                _total_deuda = 0.0
                for _f in _facturas_pend[:10]:  # máx 10 para no inflar el prompt
                    _lineas_prov.append(
                        f"{_f['id']} | {_f['proveedor']} | Total:{_f['total']:,.0f} | "
                        f"Pagado:{_f['pagado']:,.0f} | Pendiente:{_f['pendiente']:,.0f} | "
                        f"Fecha:{_f['fecha']} | Estado:{_f['estado']}"
                    )
                    _total_deuda += _f["pendiente"]
                proveedores_texto = (
                    "CUENTAS_POR_PAGAR (deuda total: ${:,.0f}):\n".format(_total_deuda)
                    + "\n".join(_lineas_prov)
                )
        except Exception:
            proveedores_texto = ""

    msg_l = mensaje_usuario.lower()

    # ── Acronal: precalcular total en Python ──
    acronal_calculado = ""
    _acronal_precio_kg = 13000
    _acronal_precio_medio = 7000
    # precios_fraccion esta en la RAIZ de memoria, no dentro del objeto catalogo.
    # El catalogo puede tener precio_unidad desactualizado — precios_fraccion manda.
    _frac_mem = memoria.get("precios_fraccion", {}).get("acronal", {})
    if _frac_mem:
        _v1 = _frac_mem.get("1", 0)
        _acronal_precio_kg = int(_v1) if _v1 else _acronal_precio_kg
        _vm = _frac_mem.get("1/2", 0)
        _acronal_precio_medio = int(_vm) if _vm else _acronal_precio_medio
    else:
        # fallback: precio_unidad del catalogo si no hay precios_fraccion definidos
        for _ak, _av in memoria.get("catalogo", {}).items():
            if "acronal" in _av.get("nombre_lower", ""):
                _pu = _av.get("precio_unidad", 0)
                if _pu:
                    _acronal_precio_kg = int(_pu)
                break
    if "acronal" in msg_l:
        # Normalizar "kilos y medio" -> "X.5", "medio kilo" -> "0.5"
        msg_ac = msg_l
        msg_ac = re.sub(r'(\d+)\s+(?:kilo[s]?\s+)?y\s+medio', lambda m: str(int(m.group(1))) + '.5', msg_ac)
        msg_ac = msg_ac.replace('medio kilo', '0.5').replace('kilo y medio', '1.5')
        # Buscar cantidad: "2-1/2", "2.5", "4", etc.
        # Detectar "1/2 kg" o "medio" antes del regex numerico
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

    # ── Thinner y Varsol: precalcular fraccion en Python ──
    # CASO 1: "N litros/botellas de thinner/varsol" — el alias convirtió a "N litros/botellas thinner/varsol"
    # CASO 2: "thinner/varsol 8000" (precio por fracción de galón) — tabla normal.
    # Ambos productos usan la misma tabla de precios.
    thinner_calculado = ""
    _tabla_tv = {3000:"1/12",4000:"1/10",5000:"1/8",6000:"1/6",8000:"1/4",
                 10000:"1/3",13000:"1/2",20000:"3/4",26000:"1 galon"}
    _dec_tv   = {3000:1/12,4000:0.1,5000:0.125,6000:1/6,8000:0.25,
                 10000:1/3,13000:0.5,20000:0.75,26000:1.0}

    for _producto_tv in ("thinner", "varsol"):
        if _producto_tv not in msg_l:
            continue
        _m_litros   = re.search(rf'(\d+)\s+litros?\s+{_producto_tv}', msg_l)
        _m_botellas = re.search(rf'(\d+)\s+botellas?\s+{_producto_tv}', msg_l)
        if _m_litros:
            _n = int(_m_litros.group(1))
            _total_t = _n * 8000
            thinner_calculado += (
                f"{_producto_tv.upper()} PRECALCULADO: {_n} litro{'s' if _n > 1 else ''} = "
                f"${_total_t:,} total (cantidad={_n} litros, precio_litro=8000). "
                f"USA cantidad={_n}, total={_total_t} SIN MODIFICAR.\n"
            )
        elif _m_botellas:
            _n = int(_m_botellas.group(1))
            _total_t = _n * 4000
            thinner_calculado += (
                f"{_producto_tv.upper()} PRECALCULADO: {_n} botella{'s' if _n > 1 else ''} = "
                f"${_total_t:,} total (cantidad={_n} botellas, precio_botella=4000). "
                f"USA cantidad={_n}, total={_total_t} SIN MODIFICAR.\n"
            )
        else:
            # CASO 2: precio por fracción de galón
            _m_precio = re.search(
                rf'(\d[\d\.]*)\s*(?:de\s+)?{_producto_tv}|{_producto_tv}\s+(\d[\d\.]*)', msg_l
            )
            if _m_precio:
                precio_t = int(float(_m_precio.group(1) or _m_precio.group(2)))
                if precio_t in _tabla_tv:
                    frac_t = _tabla_tv[precio_t]
                    dec_t  = _dec_tv[precio_t]
                    thinner_calculado += (
                        f"{_producto_tv.upper()} PRECALCULADO: ${precio_t:,} = {frac_t} galon "
                        f"(cantidad={dec_t:.4f}, total={precio_t}). USA EXACTAMENTE estos valores.\n"
                    )
    thinner_calculado = thinner_calculado.strip()

    # ── Tornillos drywall: precalcular precio correcto ──
    tornillo_calculado = ""
    if "drywall" in msg_l or "tornillo" in msg_l:
        tabla_drywall = {
            "6x1/2":(25,25),"6x3/4":(58,30),"6x1":(38,35),"6x1-1/4":(42,40),
            "6x1-1/2":(58,55),"6x2":(67,60),"6x2-1/2":(75,70),"6x3":(83,80),
            "8x3/4":(33,30),"8x1":(38,35),"8x1-1/2":(58,55),"8x2":(67,60),"8x3":(83,80),
            "10x1":(83,70),"10x1-1/2":(125,100),"10x2":(150,120),"10x2-1/2":(167,160),
            "10x3":(167,160),"10x3-1/2":(208,200),"10x4":(208,200),
        }
        voz_medida = [
            ("3 y medio","3-1/2"),("3 y media","3-1/2"),("3½","3-1/2"),
            ("2 y medio","2-1/2"),("2 y media","2-1/2"),
            ("1 y medio","1-1/2"),("1 y media","1-1/2"),("1 y cuarto","1-1/4"),
        ]
        # Normalizar voz a fraccion
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

    # "DATOS HISTORICOS" solo se incluye cuando hay datos reales — no enviar "(no cargado)" innecesariamente
    datos_historicos_item = f"DATOS HISTORICOS:\n{datos_texto}" if datos_texto != "(no cargado)" else ""

    # Precios recién actualizados en RAM — override del cache de Anthropic (TTL 5 min)
    precios_modificados_texto = ""
    _pm_ram = _get_precios_recientes_activos()
    if _pm_ram and palabras_clave:
        overrides = []
        for clave_pm, val in _pm_ram.items():
            nombre_pm, _, frac = clave_pm.partition("___")
            if any(p in nombre_pm for p in palabras_clave):
                if frac:
                    overrides.append(f"{nombre_pm} {frac}={val}")
                else:
                    overrides.append(f"{nombre_pm}={val}")
        if overrides:
            precios_modificados_texto = "PRECIOS ACTUALIZADOS (usar estos, ignorar el catalogo):\n" + "\n".join(overrides)

    # Regla siempre activa en multi-producto: Claude debe listar lo que no pudo registrar
    _es_multiproducto = "\n" in mensaje_usuario.strip() or mensaje_usuario.count(",") >= 2
    # La regla aplica SIEMPRE (producto único o múltiple) para que el formato ⚠️
    # sea consistente y el sistema pueda guardarlo automáticamente en /pendientes.
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

    partes = [
        p for p in [
            precios_modificados_texto,
            info_fracciones_extra,
            acronal_calculado,
            thinner_calculado,
            tornillo_calculado,
            info_candidatos_extra,
            clientes_recientes_texto,
            clientes_texto,
            f"VENTAS MES:{resumen_texto}",
            datos_historicos_item,
            inventario_texto,
            caja_texto,
            gastos_texto,
            proveedores_texto,
            aviso_drive,
            f"Vendedor:{nombre_usuario}",
            _regla_no_encontrado,
            # Skills dinámicos: solo se inyectan cuando el mensaje los necesita
            skill_loader.obtener_skills_dinamicos(mensaje_usuario),
        ] if p
    ]
    return "\n\n".join(partes)


# ─────────────────────────────────────────────
# FUNCIÓN AUXILIAR: calcular historial adaptativo
# ─────────────────────────────────────────────

def _calcular_historial(mensaje: str) -> int:
    """
    Determina cuántos mensajes de historial enviar según el contexto.
    OPTIMIZACIÓN: ventas simples solo necesitan 1 mensaje, ahorrando ~100 tokens.
    """
    msg_l = mensaje.lower().strip()

    # Respuesta corta (1-2 palabras) = probablemente respuesta a pregunta anterior
    # Necesita contexto completo para no perder la venta original
    # Ej: "blanco", "rojo", "si", "no", "2 pulgadas"
    palabras = msg_l.split()
    if len(palabras) <= 2:
        return 4

    # Necesita contexto completo (cliente, correcciones, fiados)
    if any(k in msg_l for k in ("cliente", "fiado", "para ", "a nombre",
                                 "corrig", "modific", "error", "equivoque",
                                 "cambia", "quita", "agrega")):
        return 4

    # Análisis, reportes o consultas complejas
    _kw_contexto = {"cuanto", "vendimos", "reporte", "analiz", "resumen", "estadistica",
                    "inventario", "grafica", "top", "mas vendido", "caja", "gasto"}
    if any(k in msg_l for k in _kw_contexto):
        return 4

    # Multi-producto (comas o saltos de línea)
    if "," in mensaje or mensaje.count("\n") > 0:
        return 2

    # Venta simple: solo el mensaje actual basta
    return 1


# ─────────────────────────────────────────────
# MODELOS Y SELECTOR
# ─────────────────────────────────────────────

# Modelo híbrido: Haiku para tareas rápidas, Sonnet para complejas
MODELO_HAIKU  = "claude-haiku-4-5-20251001"
MODELO_SONNET = "claude-sonnet-4-6"

def _elegir_modelo(mensaje: str) -> str:
    """
    Clasifica el mensaje del usuario para elegir Haiku (rápido/barato)
    o Sonnet (inteligente/caro).

    Sonnet: análisis, reportes, comparaciones, explicaciones, ediciones
            complejas, fiados, correcciones, mensajes multi-línea largos.
    Haiku:  ventas simples, precios, stock, saludos, gastos simples.
    """
    ml = mensaje.lower()

    # ── Siempre Sonnet ──
    _kw_sonnet = {
        # Análisis y reportes
        "analiz", "analís", "compara", "explica", "por qué", "porqué",
        "reporte", "resumen", "estadistic", "rendimiento", "tendencia",
        "recomienda", "suger", "opina", "evalua", "evalúa",
        # Consultas complejas
        "cuánto vendimos", "cuanto vendimos", "qué se vendió", "que se vendio",
        "cuánto me", "cuanto me", "cuánto va", "cuanto va", "cuánto lleva", "cuanto lleva",
        "top producto", "más vendido", "mas vendido", "menos vendido",
        "ganancias", "utilidad", "margen", "rentabil",
        "histórico", "historico", "semana pasada", "mes pasado",
        "promedio", "proyección", "proyeccion",
        # Ediciones complejas
        "modifica", "corrig", "cambia el precio", "actualiza precio",
        "elimina", "borrar consecutivo",
        # Fiados / clientes
        "fiado", "debe", "abono", "deuda", "saldo",
        "cliente nuevo", "registrar cliente",
    }
    if any(kw in ml for kw in _kw_sonnet):
        return MODELO_SONNET

    # Multi-línea o mensajes largos con complejidad
    n_lineas = mensaje.count("\n") + 1
    n_comas  = mensaje.count(",")
    if n_lineas >= 3 or (len(mensaje) > 150 and n_comas >= 2):
        return MODELO_SONNET

    # Múltiples preguntas
    if mensaje.count("?") >= 2 or mensaje.count("¿") >= 2:
        return MODELO_SONNET

    # ── Todo lo demás → Haiku ──
    return MODELO_HAIKU
