"""
services/catalogo_service.py — Lógica de catálogo extraída de memoria.py.

Funciones de búsqueda, precios y actualización del catálogo de productos.
Copias verbatim de memoria.py — sin cambios de firma ni lógica.

FASE 1 — este módulo NO está conectado a nada todavía.
Solo debe existir en disco e importar limpio.
La integración ocurre en Fase 2 (Tarea H).

Imports permitidos: logging, re, db, config, utils, alias_manager, fuzzy_match.
cargar_memoria() se importa de forma lazy dentro de las funciones para evitar
ciclo de imports (catalogo_service → memoria → catalogo_service).
NUNCA importar de ai, handlers, o memoria a nivel de módulo.

Por qué lazy y no nivel de módulo:
  memoria.py importa a config e inicia el cliente de Claude al importarse.
  Si catalogo_service importara memoria al nivel de módulo, cualquier test
  que haga `import catalogo_service` necesitaría variables de entorno reales.
  El lazy import permite mockear memoria por test sin patching complejo.

El patrón correcto para tests es el stub en sys.modules (ver tests/test_catalogo_service.py).
"""

# -- stdlib --
import logging
import re

# -- terceros --
# (ninguno — rapidfuzz se importa donde se usa, igual que en memoria.py)

# -- propios --
import config  # noqa: F401 — disponible para funciones que lo necesiten

logger = logging.getLogger("ferrebot.services.catalogo")


# ─────────────────────────────────────────────
# BÚSQUEDA EN CATÁLOGO
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
    from memoria import cargar_memoria
    catalogo = cargar_memoria().get("catalogo", {})
    if not catalogo:
        return None

    # Normalizar el término de búsqueda igual que nombre_lower del catálogo
    # (elimina °, tildes, caracteres especiales) para que "N°100" == "n100"
    from utils import _normalizar as _norm_busq
    nombre_lower = _norm_busq(nombre_buscado)

    for prod in catalogo.values():
        if prod.get("nombre_lower") == nombre_lower:
            return prod

    # Incluir tokens de ≥2 chars + dígitos solos (1,2,3...) para "Rodillo de 2" vs "Rodillo de 1"
    def _es_token_relevante_busq(p: str) -> bool:
        return len(p) >= 2 or p.isdigit()

    palabras = [p for p in nombre_lower.split() if _es_token_relevante_busq(p)]
    if not palabras:
        return None

    import re as _re_busq
    numeros_busqueda = {p for p in palabras if p.isdigit()}

    candidatos = []
    for prod in catalogo.values():
        nl = prod.get("nombre_lower", "")
        coincidencias = sum(1 for p in palabras if p in nl)
        if coincidencias == len(palabras):
            score_base = 3
        elif len(palabras) > 1 and coincidencias >= len(palabras) - 1:
            score_base = 2
        elif coincidencias >= 1:
            score_base = 1
        else:
            continue

        # Bonus si el número exacto coincide; penalizar si el número NO coincide
        # Evita "Rodillo de 2" → "Rodillo de 1"" cuando todos tienen igual score base
        nl_numeros = set(_re_busq.findall(r'\d+', nl))
        bonus_numero    = sum(1 for n in numeros_busqueda if n in nl_numeros)
        penaliz_numero  = -sum(2 for n in numeros_busqueda if n not in nl_numeros)

        # Filtro anti-match-espurio: requiere mínimo de palabras sustantivas en común
        # Ej: "cepillo de acero" NO debe matchear "Regadera" ni "Bisagra acero"
        _STOPWORDS = {"de", "el", "la", "los", "las", "un", "una", "unos", "unas",
                      "para", "con", "por", "en", "del", "al"}
        # Adjetivos descriptores que no identifican el producto — no cuentan para el umbral
        _ADJETIVOS_DESC = {"economico", "economica", "pequeno", "pequeña", "grande",
                           "simple", "corriente", "comun", "basico", "normal",
                           "plastico", "plastica", "metalico", "metalica"}
        palabras_sustantivas = [p for p in palabras if p not in _STOPWORDS and not p.isdigit()]
        palabras_identificadoras = [p for p in palabras_sustantivas if p not in _ADJETIVOS_DESC]
        if palabras_sustantivas:
            coincidencias_sustantivas = sum(1 for p in palabras_sustantivas if p in nl)
            # Con 2+ palabras identificadoras: deben coincidir al menos 2
            # Con 1 identificadora: basta con que esa 1 coincida
            minimo_requerido = 2 if len(palabras_identificadoras) >= 2 else 1
            if coincidencias_sustantivas < minimo_requerido:
                continue

        candidatos.append((score_base + bonus_numero + penaliz_numero, coincidencias, len(nl), prod))

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
    from memoria import cargar_memoria
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

    _TALLAS_MEM = {"xl", "xs", "xxl", "s", "m", "l"}
    def _es_token_relevante(p: str) -> bool:
        if len(p) > 2:
            return True
        if p.isdigit():
            return True
        if len(p) == 2 and any(c.isdigit() for c in p):
            return True
        if p in _TALLAS_MEM:
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
    # Solo typos de escritura y variantes sin tilde del mismo nombre
    "tiner":          "thinner",
    "thiner":         "thinner",
    "cunete":         "cuñete",
    "convencional":   "rodillo convencional",
    "convencionañ":   "rodillo convencional",
    "convensional":   "rodillo convencional",
    "rodillo normal": "rodillo convencional",
}


def expandir_con_alias(termino: str) -> list[str]:
    """
    Dado un término de búsqueda, retorna variantes aplicando alias de escritura.
    Ej: 'tiner' → ['tiner', 'thinner']
    """
    termino_lower = termino.lower().strip()
    variantes = [termino_lower]
    for alias_original, alias_destino in _ALIAS_SINONIMOS.items():
        if alias_original in termino_lower and alias_destino not in termino_lower:
            variante = termino_lower.replace(alias_original, alias_destino)
            variantes.append(variante)
    return variantes


def _limpiar_cantidad_inicial(query: str) -> str:
    """
    Elimina prefijos numéricos que son CANTIDADES, no tallas.
    Ej: '2 brochas de 3'  → 'brochas de 3'
        '1 brocha 2 pulgadas 4000' → 'brocha 2 pulgadas'
        '5 lijas 80'       → 'lijas 80'
    No elimina fracciones que son parte del nombre: '1/4 vinilo' → '1/4 vinilo'
    No elimina precios finales (número > 1000 al final).
    """
    import re as _re_lc
    q = query.strip()
    # Eliminar número entero inicial seguido de espacio y palabra alfabética
    # (ej: "2 brochas", "5 lijas", "1 brocha") — pero NO "1/4 vinilo" ni "2x4"
    q = _re_lc.sub(r'^(\d+)\s+(?=[a-zA-ZáéíóúÁÉÍÓÚñÑ])', '', q).strip()
    # Eliminar precio final obvio (número > 1000 al final sin contexto de medida)
    q = _re_lc.sub(r'\s+\d{4,}$', '', q).strip()
    return q


def buscar_multiples_con_alias(nombre_buscado: str, limite: int = 8) -> list:
    """
    Igual que buscar_multiples_en_catalogo pero expande el término con alias/sinónimos.
    Úsala en lugar de buscar_multiples_en_catalogo cuando el MATCH falle frecuentemente.
    """
    # Limpiar cantidad inicial antes de expandir alias
    nombre_buscado = _limpiar_cantidad_inicial(nombre_buscado)
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


# ─────────────────────────────────────────────
# PRECIOS
# ─────────────────────────────────────────────

def obtener_precio_para_cantidad(nombre_producto: str, cantidad_decimal: float) -> tuple[int, float]:
    """
    Dado un producto y una cantidad decimal, retorna (precio_total, precio_unidad).
    """
    from memoria import cargar_memoria
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
    from memoria import cargar_memoria
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
# ACTUALIZACIÓN DE PRECIOS EN CATÁLOGO
# ─────────────────────────────────────────────

def _upsert_precio_producto_postgres(clave: str, datos_prod: dict, fraccion: str = None):
    """Upsert quirúrgico de precios de un producto.
    Solo toca las filas que cambiaron — no hace sync completo del catálogo.
    Raises si PG falla.
    """
    import db as _db
    prod_row = _db.query_one("SELECT id FROM productos WHERE clave = %s", (clave,))
    if not prod_row:
        raise ValueError(f"Producto con clave '{clave}' no existe en productos")
    prod_id = prod_row["id"]

    # Actualizar precio_unidad en productos si cambió
    _db.execute(
        "UPDATE productos SET precio_unidad = %s, updated_at = NOW() WHERE id = %s",
        (datos_prod.get("precio_unidad", 0), prod_id)
    )

    # Actualizar fracción específica si se proporcionó
    if fraccion:
        datos_frac = datos_prod.get("precios_fraccion", {}).get(fraccion, {})
        if datos_frac:
            _db.execute("""
                INSERT INTO productos_fracciones (producto_id, fraccion, precio_total, precio_unitario)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (producto_id, fraccion) DO UPDATE SET
                    precio_total    = EXCLUDED.precio_total,
                    precio_unitario = EXCLUDED.precio_unitario
            """, (
                prod_id,
                fraccion,
                datos_frac.get("precio", 0),
                datos_frac.get("precio_unitario", 0),
            ))

    # Actualizar precio_por_cantidad — columnas inline en productos
    pxc = datos_prod.get("precio_por_cantidad", {})
    if pxc:
        _db.execute("""
            UPDATE productos
            SET precio_umbral       = %s,
                precio_bajo_umbral  = %s,
                precio_sobre_umbral = %s,
                updated_at          = NOW()
            WHERE id = %s
        """, (
            pxc.get("umbral", 50),
            pxc.get("precio_bajo_umbral", datos_prod.get("precio_unidad", 0)),
            pxc.get("precio_sobre_umbral", 0),
            prod_id,
        ))


def actualizar_precio_en_catalogo(nombre_producto: str, nuevo_precio: float, fraccion: str = None) -> bool:
    """
    Actualiza el precio de un producto existente en el catálogo de forma permanente.
    - Si fraccion es None: actualiza precio_unidad (galon completo / precio base).
    - Si fraccion es "1/4", "1/2", etc.: actualiza ese precio de fraccion.
    Retorna True si encontró y actualizó el producto, False si no lo encontró.
    """
    import db as _db
    import threading as _threading
    from memoria import cargar_memoria, _cache, _cache_lock

    mem      = cargar_memoria()
    catalogo = mem.get("catalogo", {})
    prod     = buscar_producto_en_catalogo(nombre_producto)

    logger.info("[PRECIO_CAT] buscar('%s') → %s | nuevo_precio=%s", nombre_producto, prod.get("nombre") if prod else "None", nuevo_precio)

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

    precio_antes = catalogo[clave].get("precio_unidad") if clave else None

    if not _db.DB_DISPONIBLE:
        raise RuntimeError("⚠️ Base de datos no disponible. Intenta de nuevo en un momento.")

    _upsert_precio_producto_postgres(clave, catalogo[clave], fraccion)
    # Actualizar cache directamente — sin guardar_memoria ni invalidar_cache_memoria
    with _cache_lock:
        if _cache is not None:
            _cache.setdefault("catalogo", {})[clave] = catalogo[clave]
            nombre_lower = prod.get("nombre_lower", nombre_producto.lower())
            precios_cache = _cache.get("precios", {})
            for k in [k for k in precios_cache if k == nombre_lower or nombre_lower in k or k in nombre_lower]:
                del precios_cache[k]
    logger.info("[PRECIO_CAT] ✅ %s: $%s → $%s (fraccion=%s)", clave, precio_antes, nuevo_precio, fraccion)
    return True
