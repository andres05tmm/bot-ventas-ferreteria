"""
Memoria persistente del bot: precios, catálogo, negocio, inventario, caja, gastos.
Usa cache en RAM para evitar lecturas repetidas del JSON.

CORRECCIONES v2:
  - Docstring movido ANTES del import (antes estaba después, Python no lo reconocía)
  - _normalizar eliminada de aquí — se importa de utils (era duplicado con lógica distinta)

CORRECCIONES v3:
  - cargar_memoria() lee catálogo e inventario desde Postgres cuando DB_DISPONIBLE=True (CAT-04)
  - guardar_memoria() dual-write: JSON+Drive Y Postgres (D-06, D-07)
  - Lazy import de db dentro de funciones para evitar importación circular (Pitfall 1 en RESEARCH.md)
  - Firmas públicas cargar_memoria() y guardar_memoria() sin cambios (151 referencias externas)
"""

import logging
import json
import os
import threading
from datetime import datetime

import config
from utils import _normalizar  # única definición centralizada

logger = logging.getLogger("ferrebot.memoria")

_cache: dict | None = None
_bloquear_subida_drive: bool = False  # True durante la sincronización inicial
_cache_lock = threading.Lock()        # Protege _cache en entornos multi-hilo


def bloquear_subida_drive(bloquear: bool):
    global _bloquear_subida_drive
    _bloquear_subida_drive = bloquear


def _leer_catalogo_postgres(db_module) -> dict:
    """Reconstruye memoria["catalogo"] desde Postgres.
    La estructura dict es IDENTICA a la que tenia el JSON."""
    productos = db_module.query_all("SELECT * FROM productos WHERE activo = TRUE")
    fracciones = db_module.query_all("SELECT * FROM productos_fracciones")
    precios_cant = db_module.query_all("SELECT * FROM productos_precio_cantidad")
    aliases = db_module.query_all("SELECT * FROM productos_alias")

    # Indexar por producto_id para joins eficientes en Python
    frac_by_prod = {}
    for f in fracciones:
        frac_by_prod.setdefault(f["producto_id"], []).append(f)

    pxc_by_prod = {}
    for p in precios_cant:
        pxc_by_prod[p["producto_id"]] = p

    alias_by_prod = {}
    for a in aliases:
        alias_by_prod.setdefault(a["producto_id"], []).append(a["alias"])

    catalogo = {}
    for p in productos:
        prod_dict = {
            "nombre": p["nombre"],
            "nombre_lower": p["nombre_lower"],
            "categoria": p["categoria"] or "",
            "precio_unidad": p["precio_unidad"],
            "unidad_medida": p["unidad_medida"] or "Unidad",
        }
        # Codigo (si existe)
        if p.get("codigo"):
            prod_dict["codigo"] = p["codigo"]
        # Fracciones
        if p["id"] in frac_by_prod:
            prod_dict["precios_fraccion"] = {
                f["fraccion"]: {
                    "precio": f["precio_total"],
                    "precio_unitario": f["precio_unitario"],
                }
                for f in frac_by_prod[p["id"]]
            }
        # Precio por cantidad
        if p["id"] in pxc_by_prod:
            pxc = pxc_by_prod[p["id"]]
            prod_dict["precio_por_cantidad"] = {
                "umbral": pxc["umbral"],
                "precio_bajo_umbral": pxc["precio_bajo_umbral"],
                "precio_sobre_umbral": pxc["precio_sobre_umbral"],
            }
        # Alias
        if p["id"] in alias_by_prod:
            prod_dict["alias"] = alias_by_prod[p["id"]]

        catalogo[p["clave"]] = prod_dict

    return catalogo


def _leer_inventario_postgres(db_module) -> dict:
    """Reconstruye memoria["inventario"] desde Postgres."""
    rows = db_module.query_all("""
        SELECT i.cantidad, i.minimo, i.unidad, p.clave
        FROM inventario i
        JOIN productos p ON p.id = i.producto_id
    """)
    inventario = {}
    for r in rows:
        inventario[r["clave"]] = {
            "cantidad": float(r["cantidad"]) if r["cantidad"] is not None else 0,
            "minimo": float(r["minimo"]) if r["minimo"] is not None else 0,
            "unidad": r["unidad"] or "Unidad",
        }
    return inventario


def _cargar_desde_postgres() -> dict:
    """Construye el dict de memoria con catalogo e inventario desde Postgres.
    Campos no migrados (gastos, caja, notas, negocio) se cargan del JSON local."""
    import db as _db
    # Cargar estructura base desde JSON si existe (para campos que aun no migran)
    if os.path.exists(config.MEMORIA_FILE):
        with open(config.MEMORIA_FILE, "r", encoding="utf-8") as f:
            base = json.load(f)
    else:
        base = {
            "precios": {}, "catalogo": {}, "negocio": {},
            "notas": [], "inventario": {}, "gastos": {},
            "caja_actual": {"abierta": False},
        }

    # Sobreescribir catalogo e inventario con datos de Postgres
    base["catalogo"] = _leer_catalogo_postgres(_db)
    base["inventario"] = _leer_inventario_postgres(_db)
    return base


def cargar_memoria() -> dict:
    global _cache
    with _cache_lock:
        if _cache is not None:
            return _cache
        # Intentar cargar desde Postgres si disponible
        import db as _db
        if _db.DB_DISPONIBLE:
            _cache = _cargar_desde_postgres()
        else:
            # Fallback: comportamiento anterior exacto
            if os.path.exists(config.MEMORIA_FILE):
                with open(config.MEMORIA_FILE, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
            else:
                _cache = {
                    "precios": {}, "catalogo": {}, "negocio": {},
                    "notas": [], "inventario": {}, "gastos": {},
                    "caja_actual": {"abierta": False},
                }
        return _cache


def _sincronizar_catalogo_postgres(catalogo: dict, db_module):
    """Sincroniza catalogo dict a Postgres via UPSERT (D-06, D-07)."""
    for clave, prod in catalogo.items():
        row = db_module.execute_returning("""
            INSERT INTO productos (clave, nombre, nombre_lower, categoria, precio_unidad, unidad_medida)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (clave) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                nombre_lower = EXCLUDED.nombre_lower,
                precio_unidad = EXCLUDED.precio_unidad,
                unidad_medida = EXCLUDED.unidad_medida,
                updated_at = NOW()
            RETURNING id
        """, (
            clave,
            prod.get("nombre", ""),
            prod.get("nombre_lower", prod.get("nombre", "").lower()),
            prod.get("categoria", ""),
            prod.get("precio_unidad", 0),
            prod.get("unidad_medida", "Unidad"),
        ))
        if not row:
            continue
        prod_id = row["id"]

        # Fracciones: delete + insert (simpler than individual UPSERTs)
        db_module.execute("DELETE FROM productos_fracciones WHERE producto_id = %s", (prod_id,))
        for frac, datos in prod.get("precios_fraccion", {}).items():
            db_module.execute("""
                INSERT INTO productos_fracciones (producto_id, fraccion, precio_total, precio_unitario)
                VALUES (%s, %s, %s, %s)
            """, (prod_id, frac, datos.get("precio", 0), datos.get("precio_unitario", 0)))

        # Precio por cantidad
        pxc = prod.get("precio_por_cantidad", {})
        if pxc:
            db_module.execute("""
                INSERT INTO productos_precio_cantidad (producto_id, umbral, precio_bajo_umbral, precio_sobre_umbral)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (producto_id) DO UPDATE SET
                    umbral = EXCLUDED.umbral,
                    precio_bajo_umbral = EXCLUDED.precio_bajo_umbral,
                    precio_sobre_umbral = EXCLUDED.precio_sobre_umbral
            """, (
                prod_id,
                pxc.get("umbral", 50),
                pxc.get("precio_bajo_umbral", prod.get("precio_unidad", 0)),
                pxc.get("precio_sobre_umbral", 0),
            ))

        # Alias
        for alias_str in prod.get("alias", []):
            if alias_str and isinstance(alias_str, str) and alias_str.strip():
                db_module.execute("""
                    INSERT INTO productos_alias (producto_id, alias)
                    VALUES (%s, %s)
                    ON CONFLICT (alias) DO NOTHING
                """, (prod_id, alias_str.strip()))


def _sincronizar_inventario_postgres(inventario: dict, db_module):
    """Sincroniza inventario dict a Postgres via UPSERT (D-06, D-07)."""
    for clave, datos in inventario.items():
        prod_row = db_module.query_one("SELECT id FROM productos WHERE clave = %s", (clave,))
        if not prod_row:
            continue
        db_module.execute("""
            INSERT INTO inventario (producto_id, cantidad, minimo, unidad, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (producto_id) DO UPDATE SET
                cantidad = EXCLUDED.cantidad,
                minimo = EXCLUDED.minimo,
                unidad = EXCLUDED.unidad,
                updated_at = NOW()
        """, (
            prod_row["id"],
            datos.get("cantidad", 0),
            datos.get("minimo", 0),
            datos.get("unidad", "Unidad"),
        ))


def guardar_memoria(memoria: dict, urgente: bool = False):
    """
    Guarda memoria en disco y sincroniza a Postgres.
    urgente=True: parámetro mantenido por compatibilidad con callers existentes.
    urgente=False: comportamiento idéntico (Drive eliminado en Fase 5).
    """
    global _cache
    with _cache_lock:
        _cache = memoria
        with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
            json.dump(memoria, f, ensure_ascii=False, indent=2)
    # Sincronizacion adicional a Postgres (si disponible) — D-06
    import db as _db
    if _db.DB_DISPONIBLE:
        try:
            _sincronizar_catalogo_postgres(memoria.get("catalogo", {}), _db)
            _sincronizar_inventario_postgres(memoria.get("inventario", {}), _db)
        except Exception as e:
            logger.warning(f"Error sincronizando a Postgres (no critico): {e}")


def invalidar_cache_memoria():
    global _cache
    with _cache_lock:
        _cache = None
    # Reconstruir índice fuzzy para que productos nuevos sean encontrables
    try:
        from fuzzy_match import construir_indice
        mem = cargar_memoria()
        construir_indice(mem.get("catalogo", {}))
    except Exception:
        pass


# ─────────────────────────────────────────────
# CATÁLOGO
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


def obtener_precio_para_cantidad(nombre_producto: str, cantidad_decimal: float) -> tuple[int, float]:
    """
    Dado un producto y una cantidad decimal, retorna (precio_total, precio_unidad).
    """
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
# INVENTARIO
# ─────────────────────────────────────────────

def cargar_inventario() -> dict:
    return cargar_memoria().get("inventario", {})


def guardar_inventario(inventario: dict):
    mem = cargar_memoria()
    mem["inventario"] = inventario
    guardar_memoria(mem)


def verificar_alertas_inventario() -> list[str]:
    alertas = []
    for producto, datos in cargar_inventario().items():
        if isinstance(datos, dict):
            cantidad = datos.get("cantidad", 0)
            minimo   = datos.get("minimo", 3)
            if cantidad <= minimo:
                alertas.append(f"⚠️ STOCK BAJO: {producto} — quedan {cantidad} unidades")
    return alertas


def _normalizar_clave_inventario(nombre: str) -> str:
    """Normaliza el nombre del producto para usar como clave en inventario."""
    return _normalizar(nombre).strip().lower()


def registrar_conteo_inventario(nombre_producto: str, cantidad: float, minimo: float = 5, unidad: str = "unidades") -> tuple[bool, str]:
    """
    Registra o actualiza el conteo de un producto en inventario.
    Busca primero en el catálogo para usar el nombre correcto.
    Retorna (éxito, mensaje).
    """
    inventario = cargar_inventario()
    
    # Buscar producto en catálogo para usar nombre oficial
    producto_catalogo = buscar_producto_en_catalogo(nombre_producto)
    if producto_catalogo:
        nombre_oficial = producto_catalogo.get("nombre", nombre_producto)
    else:
        nombre_oficial = nombre_producto.strip()
    
    clave = _normalizar_clave_inventario(nombre_oficial)
    
    # Verificar si ya existe con otra clave similar
    clave_existente = buscar_clave_inventario(nombre_producto)
    if clave_existente and clave_existente != clave:
        clave = clave_existente
        nombre_oficial = inventario[clave].get("nombre_original", nombre_oficial)
    
    inventario[clave] = {
        "nombre_original": nombre_oficial,
        "cantidad": round(cantidad, 4),
        "minimo": minimo,
        "unidad": unidad,
        "fecha_conteo": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    guardar_inventario(inventario)
    
    return True, f"✅ Registrado: {nombre_oficial} — {cantidad} {unidad}"


def buscar_clave_inventario(termino: str) -> str | None:
    """
    Busca un producto en inventario de forma flexible.
    Retorna la clave del inventario si encuentra coincidencia.
    """
    inventario = cargar_inventario()
    if not inventario:
        return None
    
    termino_lower = _normalizar_clave_inventario(termino)
    
    # 1. Coincidencia exacta con clave
    if termino_lower in inventario:
        return termino_lower
    
    # 2. Coincidencia exacta con nombre_original
    for clave, datos in inventario.items():
        if isinstance(datos, dict):
            nombre_orig = datos.get("nombre_original", "").lower()
            if nombre_orig == termino_lower:
                return clave
    
    # 3. Búsqueda por palabras
    palabras = [p for p in termino_lower.split() if len(p) > 2]
    if not palabras:
        return None
    
    mejores = []
    for clave, datos in inventario.items():
        if isinstance(datos, dict):
            nombre_orig = datos.get("nombre_original", clave).lower()
            texto_busqueda = f"{clave} {nombre_orig}"
            coincidencias = sum(1 for p in palabras if p in texto_busqueda)
            if coincidencias == len(palabras):
                mejores.append((3, coincidencias, len(clave), clave))
            elif coincidencias >= len(palabras) - 1 and len(palabras) > 1:
                mejores.append((2, coincidencias, len(clave), clave))
            elif coincidencias >= 1:
                mejores.append((1, coincidencias, len(clave), clave))
    
    if mejores:
        mejores.sort(key=lambda x: (-x[0], -x[1], x[2]))
        return mejores[0][3]
    
    return None


# ── Wayper: conversión kg ↔ unidades ────────────────────────────────────────
# Tabla de redirección de inventario para productos "vendidos diferente a como se almacenan".
# Formato: nombre_producto_lower → (clave_inventario, factor)
#   factor = multiplicador sobre la cantidad vendida para obtener la cantidad a descontar.
#   Waypers: 1 kg vendido = 12 unidades descontadas  (factor 12)
#   Carbonato: 1 kg vendido = 1 kg descontado de la bolsa (factor 1)
_KG_INVENTARIO_LINKS: dict[str, tuple[str, float]] = {
    "wayper blanco":   ("wayper_blanco_unidad",  12.0),
    "wayper de color": ("wayper_de_color_unidad", 12.0),
    # Carbonato x Kg descuenta de la bolsa de 25 kg (inventario en kg)
    "carbonato x kg":  ("carbonato_x_25_kg",       1.0),
}

def _resolver_wayper_inventario(nombre_producto: str, cantidad: float) -> tuple[str | None, float]:
    """
    Para productos vendidos de forma distinta a como se almacenan, redirige
    al inventario real y aplica el factor de conversión correspondiente.
    Retorna (clave_inventario, cantidad_a_descontar) o (None, cantidad) si no aplica.
    """
    nombre_lower = nombre_producto.lower().strip()
    for nombre_ref, (clave_inv, factor) in _KG_INVENTARIO_LINKS.items():
        if nombre_lower == nombre_ref or nombre_lower.startswith(nombre_ref):
            if "unidad" not in nombre_lower:
                return clave_inv, round(cantidad * factor, 4)
    return None, cantidad


def descontar_inventario(nombre_producto: str, cantidad: float) -> tuple[bool, str | None, float | None]:
    """
    Descuenta cantidad del inventario si el producto está registrado.
    Para waypers vendidos por kg, convierte automáticamente a unidades (1 kg = 12 und).
    Retorna (descontado, alerta_stock_bajo, cantidad_restante).
    Si el producto no está en inventario, retorna (False, None, None).
    """
    # Wayper por kg → convertir a unidades y buscar inventario de unidades
    clave_wayper, cantidad_real = _resolver_wayper_inventario(nombre_producto, cantidad)
    if clave_wayper:
        inventario = cargar_inventario()
        if clave_wayper in inventario:
            cantidad = cantidad_real
            # Continuar con la clave de unidades directamente
            datos = inventario.get(clave_wayper, {})
            if isinstance(datos, dict):
                cantidad_actual = datos.get("cantidad", 0)
                cantidad_nueva  = max(0, round(cantidad_actual - cantidad, 4))
                datos["cantidad"]     = cantidad_nueva
                datos["ultima_venta"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                guardar_inventario(inventario)
                minimo = datos.get("minimo", 5)
                nombre = datos.get("nombre_original", clave_wayper)
                unidad = datos.get("unidad", "unidades")
                alerta = None
                if cantidad_nueva <= minimo:
                    alerta = f"⚠️ Stock bajo: {nombre} — quedan {cantidad_nueva:.0f} {unidad}"
                return True, alerta, cantidad_nueva
        # No hay inventario de unidades registrado → intentar con la clave original
    
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        return False, None, None
    
    inventario = cargar_inventario()
    datos = inventario.get(clave, {})
    
    if not isinstance(datos, dict):
        return False, None, None
    
    cantidad_actual = datos.get("cantidad", 0)
    cantidad_nueva = max(0, round(cantidad_actual - cantidad, 4))
    datos["cantidad"] = cantidad_nueva
    datos["ultima_venta"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    guardar_inventario(inventario)
    
    minimo = datos.get("minimo", 5)
    nombre = datos.get("nombre_original", clave)
    unidad = datos.get("unidad", "unidades")
    
    alerta = None
    if cantidad_nueva <= minimo:
        alerta = f"⚠️ Stock bajo: {nombre} — quedan {cantidad_nueva} {unidad}"
    
    return True, alerta, cantidad_nueva


def ajustar_inventario(nombre_producto: str, ajuste: float) -> tuple[bool, str]:
    """
    Ajusta el inventario sumando o restando cantidad.
    ajuste puede ser positivo (+10) o negativo (-5).
    Retorna (éxito, mensaje).
    """
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        return False, f"❌ Producto no encontrado en inventario: {nombre_producto}"
    
    inventario = cargar_inventario()
    datos = inventario.get(clave, {})
    
    cantidad_anterior = datos.get("cantidad", 0)
    cantidad_nueva = max(0, round(cantidad_anterior + ajuste, 4))
    datos["cantidad"] = cantidad_nueva
    datos["ultimo_ajuste"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    guardar_inventario(inventario)
    
    nombre = datos.get("nombre_original", clave)
    unidad = datos.get("unidad", "unidades")
    signo = "+" if ajuste > 0 else ""
    
    return True, f"✅ Ajustado: {nombre}\n   {cantidad_anterior} {signo}{ajuste} = {cantidad_nueva} {unidad}"


def buscar_productos_inventario(termino: str = None, limite: int = 50) -> list[dict]:
    """
    Busca productos en inventario. Si no hay término, retorna todos.
    Retorna lista de dicts con info del producto.
    """
    inventario = cargar_inventario()
    resultados = []
    
    for clave, datos in inventario.items():
        if not isinstance(datos, dict):
            continue
        
        if termino:
            termino_lower = termino.lower()
            nombre_orig = datos.get("nombre_original", clave).lower()
            if termino_lower not in clave and termino_lower not in nombre_orig:
                # Verificar palabras individuales
                palabras = termino_lower.split()
                texto = f"{clave} {nombre_orig}"
                if not any(p in texto for p in palabras):
                    continue
        
        resultados.append({
            "clave": clave,
            "nombre": datos.get("nombre_original", clave),
            "cantidad": datos.get("cantidad", 0),
            "minimo": datos.get("minimo", 5),
            "unidad": datos.get("unidad", "unidades"),
            "fecha_conteo": datos.get("fecha_conteo", ""),
        })
    
    # Ordenar por nombre
    resultados.sort(key=lambda x: x["nombre"].lower())
    return resultados[:limite]


def registrar_compra(nombre_producto: str, cantidad: float, costo_unitario: float, proveedor: str = None) -> tuple[bool, str, dict]:
    """
    Registra una compra de mercancía:
    - Suma cantidad al inventario
    - Actualiza costo promedio ponderado
    - Guarda proveedor (usa el último si no se especifica)
    - Registra en historial de compras
    Retorna (éxito, mensaje, datos_para_excel).
    """
    inventario = cargar_inventario()
    
    # Buscar producto en catálogo
    producto_catalogo = buscar_producto_en_catalogo(nombre_producto)
    if producto_catalogo:
        nombre_oficial = producto_catalogo.get("nombre", nombre_producto)
    else:
        nombre_oficial = nombre_producto.strip()
    
    # Buscar si ya existe en inventario
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        clave = _normalizar_clave_inventario(nombre_oficial)
    
    # Obtener datos actuales o crear nuevo
    datos = inventario.get(clave, {})
    if not isinstance(datos, dict):
        datos = {}
    
    cantidad_anterior = datos.get("cantidad", 0)
    costo_anterior = datos.get("costo_promedio", costo_unitario)
    
    # Determinar proveedor: usar el especificado o el último registrado
    if proveedor:
        proveedor_final = proveedor.strip()
    else:
        proveedor_final = datos.get("ultimo_proveedor", "—")
    
    # Calcular costo promedio ponderado
    # (cantidad_anterior * costo_anterior + cantidad_nueva * costo_nuevo) / cantidad_total
    cantidad_total = cantidad_anterior + cantidad
    if cantidad_total > 0:
        costo_promedio = round(
            (cantidad_anterior * costo_anterior + cantidad * costo_unitario) / cantidad_total
        )
    else:
        costo_promedio = costo_unitario
    
    # Actualizar inventario
    datos["nombre_original"] = nombre_oficial
    datos["cantidad"] = round(cantidad_total, 4)
    datos["costo_promedio"] = costo_promedio
    datos["ultima_compra"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    datos["ultimo_costo"] = costo_unitario
    datos["ultimo_proveedor"] = proveedor_final
    if "minimo" not in datos:
        datos["minimo"] = 5
    if "unidad" not in datos:
        datos["unidad"] = "unidades"
    
    inventario[clave] = datos
    guardar_inventario(inventario)
    
    # Registrar en historial de compras (para reportes)
    _registrar_historial_compra(nombre_oficial, cantidad, costo_unitario, proveedor_final)
    
    total_compra = round(cantidad * costo_unitario)
    
    proveedor_txt = f"   🏪 Proveedor: {proveedor_final}\n" if proveedor_final != "—" else ""
    
    mensaje = (
        f"✅ Compra registrada:\n"
        f"   📦 +{cantidad} {nombre_oficial}\n"
        f"   📊 Inventario: {cantidad_anterior} → {cantidad_total}\n"
        f"   💰 Costo: ${costo_unitario:,.0f} c/u (${total_compra:,.0f} total)\n"
        f"{proveedor_txt}"
        f"   📈 Costo promedio: ${costo_promedio:,.0f}"
    )
    
    datos_excel = {
        "producto": nombre_oficial,
        "cantidad": cantidad,
        "costo_unitario": costo_unitario,
        "costo_total": total_compra,
        "proveedor": proveedor_final,
    }
    
    return True, mensaje, datos_excel


def _registrar_historial_compra(producto: str, cantidad: float, costo_unitario: float, proveedor: str = "—"):
    """Guarda la compra en el historial para reportes."""
    mem = cargar_memoria()
    if "historial_compras" not in mem:
        mem["historial_compras"] = []
    
    mem["historial_compras"].append({
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "hora": datetime.now().strftime("%H:%M"),
        "proveedor": proveedor,
        "producto": producto,
        "cantidad": cantidad,
        "costo_unitario": costo_unitario,
        "total": round(cantidad * costo_unitario),
    })
    
    # Mantener solo últimos 500 registros
    if len(mem["historial_compras"]) > 500:
        mem["historial_compras"] = mem["historial_compras"][-500:]

    guardar_memoria(mem)
    # Postgres dual-write (non-fatal — D-01/D-02)
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            _db.execute(
                """INSERT INTO compras
                   (fecha, hora, proveedor, producto_nombre, cantidad, costo_unitario, costo_total)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d"),
                 datetime.now(config.COLOMBIA_TZ).strftime("%H:%M"),
                 proveedor, producto, cantidad,
                 int(costo_unitario), round(cantidad * costo_unitario))
            )
    except Exception as e:
        logger.warning("Postgres write compras failed: %s", e)


def obtener_costo_producto(nombre_producto: str) -> float | None:
    """Obtiene el costo promedio de un producto del inventario."""
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        return None
    
    inventario = cargar_inventario()
    datos = inventario.get(clave, {})
    return datos.get("costo_promedio")


def calcular_margen(nombre_producto: str, precio_venta: float) -> dict | None:
    """
    Calcula el margen de ganancia de un producto.
    Retorna dict con costo, margen_valor, margen_porcentaje o None.
    """
    costo = obtener_costo_producto(nombre_producto)
    if costo is None or costo == 0:
        return None
    
    margen_valor = precio_venta - costo
    margen_porcentaje = round((margen_valor / precio_venta) * 100, 1)
    
    return {
        "costo": costo,
        "precio_venta": precio_venta,
        "margen_valor": margen_valor,
        "margen_porcentaje": margen_porcentaje,
    }


def obtener_resumen_margenes(limite: int = 20) -> list[dict]:
    """
    Obtiene productos con su margen calculado.
    Requiere que el producto tenga costo_promedio y precio en catálogo.
    """
    inventario = cargar_inventario()
    catalogo = cargar_memoria().get("catalogo", {})
    
    resultados = []
    
    for clave, datos in inventario.items():
        if not isinstance(datos, dict):
            continue
        
        costo = datos.get("costo_promedio")
        if not costo:
            continue
        
        nombre = datos.get("nombre_original", clave)
        
        # Buscar precio de venta en catálogo
        producto_cat = buscar_producto_en_catalogo(nombre)
        if not producto_cat:
            continue
        
        precio_venta = producto_cat.get("precio_unidad", 0)
        if not precio_venta or precio_venta <= costo:
            continue
        
        margen_valor = precio_venta - costo
        margen_porcentaje = round((margen_valor / precio_venta) * 100, 1)
        
        resultados.append({
            "nombre": nombre,
            "costo": costo,
            "precio_venta": precio_venta,
            "margen_valor": margen_valor,
            "margen_porcentaje": margen_porcentaje,
            "cantidad": datos.get("cantidad", 0),
        })
    
    # Ordenar por margen porcentaje descendente
    resultados.sort(key=lambda x: -x["margen_porcentaje"])
    return resultados[:limite]


# ─────────────────────────────────────────────
# CAJA — Postgres helpers privados
# ─────────────────────────────────────────────

def _guardar_gasto_postgres(gasto: dict):
    """Inserta un gasto en Postgres. No-fatal: logger.warning en caso de error."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return
        hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        hora_str = gasto.get("hora")
        _db.execute(
            """INSERT INTO gastos (fecha, hora, concepto, monto, categoria, origen)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (hoy, hora_str, gasto.get("concepto", ""), int(gasto.get("monto", 0)),
             gasto.get("categoria", "General"), gasto.get("origen", "caja"))
        )
    except Exception as e:
        logger.warning("Error guardando gasto en Postgres: %s", e)


def _guardar_caja_postgres(caja: dict):
    """UPSERT caja del dia en Postgres. No-fatal."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return
        fecha = caja.get("fecha")
        if not fecha:
            return
        _db.execute(
            """INSERT INTO caja (fecha, abierta, monto_apertura, efectivo, transferencias, datafono, cerrada_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (fecha) DO UPDATE SET
                 abierta = EXCLUDED.abierta,
                 monto_apertura = EXCLUDED.monto_apertura,
                 efectivo = EXCLUDED.efectivo,
                 transferencias = EXCLUDED.transferencias,
                 datafono = EXCLUDED.datafono,
                 cerrada_at = CASE WHEN EXCLUDED.abierta = FALSE THEN NOW() ELSE caja.cerrada_at END""",
            (fecha, caja.get("abierta", False), int(caja.get("monto_apertura", 0)),
             int(caja.get("efectivo", 0)), int(caja.get("transferencias", 0)),
             int(caja.get("datafono", 0)),
             None)
        )
    except Exception as e:
        logger.warning("Error guardando caja en Postgres: %s", e)


def _leer_caja_postgres() -> dict | None:
    """Lee el estado de caja del dia de Postgres. Retorna None si no hay datos o DB no disponible."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return None
        hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        row = _db.query_one("SELECT * FROM caja WHERE fecha = %s", (hoy,))
        if not row:
            return None
        return {
            "abierta": row["abierta"],
            "fecha": str(row["fecha"]),
            "monto_apertura": int(row["monto_apertura"]),
            "efectivo": int(row["efectivo"]),
            "transferencias": int(row["transferencias"]),
            "datafono": int(row["datafono"]),
        }
    except Exception as e:
        logger.warning("Error leyendo caja de Postgres: %s", e)
        return None


def _leer_gastos_postgres(fecha_inicio: str, fecha_fin: str) -> list[dict]:
    """Lee gastos del rango de fechas desde Postgres. Retorna lista vacia si falla."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return []
        rows = _db.query_all(
            "SELECT * FROM gastos WHERE fecha >= %s AND fecha <= %s ORDER BY fecha DESC, hora DESC",
            (fecha_inicio, fecha_fin)
        )
        return [{
            "concepto": r["concepto"],
            "monto": int(r["monto"]),
            "categoria": r.get("categoria") or "General",
            "origen": r.get("origen") or "caja",
            "hora": str(r["hora"])[:5] if r.get("hora") else "",
            "fecha": str(r["fecha"]),
        } for r in rows]
    except Exception as e:
        logger.warning("Error leyendo gastos de Postgres: %s", e)
        return []


# ─────────────────────────────────────────────
# CAJA
# ─────────────────────────────────────────────

def cargar_caja() -> dict:
    pg = _leer_caja_postgres()
    if pg is not None:
        return pg
    return cargar_memoria().get("caja_actual", {
        "abierta": False, "fecha": None, "monto_apertura": 0,
        "efectivo": 0, "transferencias": 0, "datafono": 0,
    })


def guardar_caja(caja: dict):
    mem = cargar_memoria()
    mem["caja_actual"] = caja
    guardar_memoria(mem)
    try:
        _guardar_caja_postgres(caja)
    except Exception as e:
        logger.warning("Error dual-write caja Postgres: %s", e)


def obtener_resumen_caja() -> str:
    from excel import obtener_ventas_hoy_excel
    caja = cargar_caja()
    if not caja.get("abierta"):
        return "La caja no está abierta hoy."
    resumen_hoy       = obtener_ventas_hoy_excel()
    total_ventas_hoy  = resumen_hoy["total"]
    num_ventas_hoy    = resumen_hoy["num_ventas"]
    gastos_hoy        = cargar_gastos_hoy()
    total_gastos_caja = sum(g["monto"] for g in gastos_hoy if g.get("origen") == "caja")
    efectivo_esperado = caja["monto_apertura"] + caja["efectivo"] - total_gastos_caja
    return (
        f"RESUMEN DE CAJA\n"
        f"Apertura: ${caja['monto_apertura']:,.0f}\n"
        f"Ventas efectivo: ${caja['efectivo']:,.0f}\n"
        f"Transferencias: ${caja['transferencias']:,.0f}\n"
        f"Datafono: ${caja['datafono']:,.0f}\n"
        f"Total ventas hoy ({num_ventas_hoy}): ${total_ventas_hoy:,.0f}\n"
        f"Gastos de caja: ${total_gastos_caja:,.0f}\n"
        f"Efectivo esperado en caja: ${efectivo_esperado:,.0f}"
    )


# ─────────────────────────────────────────────
# GASTOS
# ─────────────────────────────────────────────

def cargar_gastos_hoy() -> list:
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
            gastos = _leer_gastos_postgres(hoy, hoy)
            if gastos is not None:
                return gastos
    except Exception as e:
        logger.warning("Error leyendo gastos de Postgres: %s", e)
    hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
    return cargar_memoria().get("gastos", {}).get(hoy, [])


def guardar_gasto(gasto: dict):
    mem = cargar_memoria()
    hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
    mem.setdefault("gastos", {}).setdefault(hoy, []).append(gasto)
    guardar_memoria(mem)
    try:
        _guardar_gasto_postgres(gasto)
    except Exception as e:
        logger.warning("Error dual-write gasto Postgres: %s", e)


# ─────────────────────────────────────────────
# FIADOS
# ─────────────────────────────────────────────

def cargar_fiados() -> dict:
    """Retorna el dict completo de fiados: {nombre_cliente: {saldo, movimientos}}"""
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            rows = _db.query_all(
                """SELECT f.id, f.nombre, f.deuda,
                          COALESCE(
                              json_agg(
                                  json_build_object(
                                      'fecha', fh.fecha::text,
                                      'concepto', fh.concepto,
                                      'cargo', CASE WHEN fh.tipo='cargo' THEN fh.monto ELSE 0 END,
                                      'abono', CASE WHEN fh.tipo='abono' THEN fh.monto ELSE 0 END,
                                      'saldo', 0
                                  ) ORDER BY fh.created_at
                              ) FILTER (WHERE fh.id IS NOT NULL),
                              '[]'
                          ) AS movimientos
                   FROM fiados f
                   LEFT JOIN fiados_historial fh ON fh.fiado_id = f.id
                   GROUP BY f.id, f.nombre, f.deuda""",
                ()
            )
            result = {}
            for r in rows:
                movimientos = r["movimientos"] if r["movimientos"] else []
                # Reconstruct running saldo for each movement
                saldo_acumulado = 0
                for mov in movimientos:
                    saldo_acumulado += mov["cargo"] - mov["abono"]
                    mov["saldo"] = saldo_acumulado
                result[r["nombre"]] = {
                    "saldo": r["deuda"],
                    "movimientos": movimientos,
                }
            return result
    except Exception as e:
        logger.warning("Postgres read cargar_fiados failed: %s", e)

    return cargar_memoria().get("fiados", {})


def _buscar_cliente_fiado(nombre: str, fiados: dict) -> str | None:
    """Busca el key del cliente en fiados de forma flexible (sin tildes, parcial)."""
    busqueda = _normalizar(nombre.strip())
    # 1. Coincidencia exacta normalizada
    for k in fiados:
        if _normalizar(k) == busqueda:
            return k
    # 2. La búsqueda está contenida en el nombre o viceversa
    for k in fiados:
        kn = _normalizar(k)
        if busqueda in kn or kn in busqueda:
            return k
    # 3. Todas las palabras de la búsqueda aparecen en el nombre
    palabras = busqueda.split()
    for k in fiados:
        kn = _normalizar(k)
        if all(p in kn for p in palabras):
            return k
    return None


def guardar_fiado_movimiento(cliente: str, concepto: str, cargo: float, abono: float):
    """
    Registra un movimiento de fiado (cargo=lo que quedó debiendo, abono=lo que pagó).
    Crea el cliente en fiados si no existe.
    """
    mem    = cargar_memoria()
    fiados = mem.setdefault("fiados", {})
    if cliente not in fiados:
        fiados[cliente] = {"saldo": 0, "movimientos": []}

    saldo_anterior = fiados[cliente]["saldo"]
    saldo_nuevo    = saldo_anterior + cargo - abono
    fiados[cliente]["saldo"] = saldo_nuevo
    fiados[cliente]["movimientos"].append({
        "fecha":    datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d"),
        "concepto": concepto,
        "cargo":    cargo,
        "abono":    abono,
        "saldo":    saldo_nuevo,
    })
    guardar_memoria(mem)
    # Postgres dual-write: upsert fiado + insert historial (non-fatal — D-01/D-02)
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            # Get or create the fiado record
            existing = _db.query_one(
                "SELECT id FROM fiados WHERE nombre = %s", (cliente,)
            )
            if existing:
                fiado_id = existing["id"]
                _db.execute(
                    "UPDATE fiados SET deuda=%s, updated_at=NOW() WHERE id=%s",
                    (int(saldo_nuevo), fiado_id)
                )
            else:
                row = _db.execute_returning(
                    "INSERT INTO fiados (nombre, deuda) VALUES (%s, %s) RETURNING id",
                    (cliente, int(saldo_nuevo))
                )
                fiado_id = row["id"]
            # Derive tipo from cargo/abono values
            tipo = "cargo" if cargo > 0 else "abono"
            monto_pg = int(cargo if cargo > 0 else abono)
            _db.execute(
                """INSERT INTO fiados_historial
                   (fiado_id, tipo, monto, concepto, fecha, hora)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (fiado_id, tipo, monto_pg, concepto,
                 datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d"),
                 datetime.now(config.COLOMBIA_TZ).strftime("%H:%M"))
            )
    except Exception as e:
        logger.warning("Postgres write fiados failed: %s", e)
    return saldo_nuevo


def abonar_fiado(cliente: str, monto: float, concepto: str = "Abono") -> tuple[bool, str]:
    """
    Registra un abono a la cuenta de un cliente.
    Retorna (exito, mensaje).
    """
    mem    = cargar_memoria()
    fiados = mem.get("fiados", {})

    cliente_key = _buscar_cliente_fiado(cliente, fiados)

    if not cliente_key:
        return False, f"No encontré a '{cliente}' en los fiados."

    saldo_nuevo = guardar_fiado_movimiento(cliente_key, concepto, cargo=0, abono=monto)
    if saldo_nuevo <= 0:
        return True, f"✅ Abono registrado. {cliente_key} quedó a paz y salvo. 🎉"
    return True, f"✅ Abono de ${monto:,.0f} registrado. {cliente_key} aún debe ${saldo_nuevo:,.0f}."


def resumen_fiados() -> str:
    """Texto con todos los clientes que deben algo."""
    fiados     = cargar_fiados()
    pendientes = {k: v for k, v in fiados.items() if v.get("saldo", 0) > 0}
    if not pendientes:
        return "No hay fiados pendientes. ✅"
    lineas = ["💳 *Fiados pendientes:*\n"]
    total  = 0
    for cliente, datos in sorted(pendientes.items()):
        saldo = datos["saldo"]
        total += saldo
        lineas.append(f"• {cliente}: ${saldo:,.0f}")
    lineas.append(f"\n*Total por cobrar: ${total:,.0f}*")
    return "\n".join(lineas)


def detalle_fiado_cliente(cliente: str) -> str:
    """Retorna el detalle de movimientos de un cliente."""
    fiados      = cargar_fiados()
    cliente_key = _buscar_cliente_fiado(cliente, fiados)
    if not cliente_key:
        return f"No encontré a '{cliente}' en los fiados."
    datos = fiados[cliente_key]
    saldo = datos.get("saldo", 0)
    movs  = datos.get("movimientos", [])
    lineas = [f"📋 Cuenta de {cliente_key} — Saldo: ${saldo:,.0f}\n"]
    for m in movs[-10:]:  # últimos 10 movimientos
        if m["cargo"] > 0 and m["abono"] > 0:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Cargo: ${m['cargo']:,.0f} | Abono: ${m['abono']:,.0f} | Saldo: ${m['saldo']:,.0f}")
        elif m["cargo"] > 0:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Fiado: ${m['cargo']:,.0f} | Saldo: ${m['saldo']:,.0f}")
        else:
            lineas.append(f"  {m['fecha']} | {m['concepto']} | Abono: ${m['abono']:,.0f} | Saldo: ${m['saldo']:,.0f}")
    return "\n".join(lineas)


# ─────────────────────────────────────────────
# GESTION DE CATALOGO DESDE EXCEL
# ─────────────────────────────────────────────

# Categorias que se venden por fracciones de galon
_CATEGORIAS_CON_FRACCIONES = {
    "2 pinturas y disolventes",
    "4 impermeabilizantes y materiales de construcción",
    "4 impermeabilizantes y materiales de construccion",
}

# Palabras clave de productos que se venden por fracciones
_KEYWORDS_FRACCIONES = (
    "vinilo", "laca", "esmalte", "sellador", "base", "imprimante",
    "impermeabilizante", "thinner", "disolvente", "barniz", "aceite",
)

# Tornillos drywall — tienen precio especial por volumen (umbral 50)
_KEYWORDS_PRECIO_UMBRAL = ("tornillo drywall",)


def _es_producto_con_fracciones(nombre: str, categoria: str) -> bool:
    n = nombre.lower()
    c = categoria.lower()
    if c in _CATEGORIAS_CON_FRACCIONES:
        return True
    return any(k in n for k in _KEYWORDS_FRACCIONES)


def _es_tornillo_drywall(nombre: str) -> bool:
    n = nombre.lower()
    return all(k in n for k in ("tornillo", "drywall"))


def actualizar_precio_en_catalogo(nombre_producto: str, nuevo_precio: float, fraccion: str = None) -> bool:
    """
    Actualiza el precio de un producto existente en el catálogo de forma permanente.
    - Si fraccion es None: actualiza precio_unidad (galon completo / precio base).
    - Si fraccion es "1/4", "1/2", etc.: actualiza ese precio de fraccion.
    Retorna True si encontró y actualizó el producto, False si no lo encontró.
    """
    import logging as _log_cat
    _log = _log_cat.getLogger("ferrebot.memoria")

    mem      = cargar_memoria()
    catalogo = mem.get("catalogo", {})
    prod     = buscar_producto_en_catalogo(nombre_producto)

    _log.info("[PRECIO_CAT] buscar('%s') → %s | nuevo_precio=%s", nombre_producto, prod.get("nombre") if prod else "None", nuevo_precio)

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

    mem["catalogo"] = catalogo

    # Limpiar precio viejo de "precios" simples si existe
    precios = mem.get("precios", {})
    nombre_lower = prod.get("nombre_lower", nombre_producto.lower())
    claves_borrar = [k for k in precios if k == nombre_lower or nombre_lower in k or k in nombre_lower]
    for k in claves_borrar:
        del precios[k]
    mem["precios"] = precios

    # urgente=True: sube a Drive sin debounce para evitar pérdida si el container
    # se reinicia antes de que expire el timer de 2s del debounce normal.
    precio_antes = catalogo[clave].get("precio_unidad") if clave else None
    guardar_memoria(mem, urgente=True)
    invalidar_cache_memoria()
    _log.info("[PRECIO_CAT] ✅ %s: $%s → $%s (fraccion=%s)", clave, precio_antes, nuevo_precio, fraccion)
    return True


def importar_catalogo_desde_excel(ruta_excel: str) -> dict:
    """
    Lee BASE_DE_DATOS_PRODUCTOS.xlsx e importa todos los productos al catálogo.
    Delega a precio_sync que maneja correctamente:
      - Campo "decimal" SIEMPRE presente en precios_fraccion.
      - Pinturas/Impermeabilizantes: total = col_value × decimal_real.
      - Tornillería Cat 3: precio_por_cantidad con umbral=50.
      - Ferretería con cols extra: precios_fraccion directos.
    """
    from precio_sync import importar_catalogo_desde_excel as _importar
    return _importar(ruta_excel)

# ─────────────────────────────────────────────
# SINCRONIZACIÓN DE PRECIO → BASE_DE_DATOS_PRODUCTOS.xlsx
# ─────────────────────────────────────────────

def actualizar_precio_en_excel_drive(
    nombre_producto: str,
    nuevo_precio: float,
    fraccion: str = None,
) -> tuple[bool, str]:
    """
    DEPRECATED — mantenida por compatibilidad con código existente.
    Ahora delega a precio_sync.actualizar_precio() que usa cola serializada.
    """
    from precio_sync import actualizar_precio as _ap
    return _ap(nombre_producto, nuevo_precio, fraccion)


# ─────────────────────────────────────────────────────────────────────────────
# CUENTAS POR PAGAR (facturas de proveedores)
# ─────────────────────────────────────────────────────────────────────────────

def _siguiente_id_factura(mem: dict) -> str:
    """Genera el próximo ID secuencial: FAC-001, FAC-002, ..."""
    facturas = mem.get("cuentas_por_pagar", [])
    if not facturas:
        return "FAC-001"
    # Extraer números existentes
    import re as _re
    nums = []
    for f in facturas:
        m = _re.match(r"FAC-(\d+)", f.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    siguiente = max(nums) + 1 if nums else 1
    return f"FAC-{siguiente:03d}"


def registrar_factura_proveedor(
    proveedor: str,
    descripcion: str,
    total: float,
    fecha: str = None,
    foto_url: str = "",
    foto_nombre: str = "",
) -> dict:
    """
    Registra una nueva factura de proveedor en memoria.json.
    Retorna el dict de la factura creada.
    """
    from datetime import datetime as _dt
    mem = cargar_memoria()
    if "cuentas_por_pagar" not in mem:
        mem["cuentas_por_pagar"] = []

    fac_id = _siguiente_id_factura(mem)
    hoy    = fecha or _dt.now(import_config_tz()).strftime("%Y-%m-%d")

    factura = {
        "id":          fac_id,
        "proveedor":   proveedor.strip(),
        "descripcion": descripcion.strip(),
        "total":       float(total),
        "pagado":      0.0,
        "pendiente":   float(total),
        "estado":      "pendiente",   # pendiente | parcial | pagada
        "fecha":       hoy,
        "foto_url":    foto_url,
        "foto_nombre": foto_nombre,
        "abonos":      [],             # historial de abonos
    }
    mem["cuentas_por_pagar"].append(factura)
    guardar_memoria(mem, urgente=True)
    # Postgres dual-write (non-fatal, inline — D-01/D-02)
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            _db.execute(
                """INSERT INTO facturas_proveedores
                   (id, proveedor, descripcion, total, pagado, pendiente, estado, fecha, foto_url, foto_nombre)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (fac_id, proveedor.strip(), descripcion.strip(),
                 int(float(total)), 0, int(float(total)), "pendiente", hoy,
                 foto_url, foto_nombre)
            )
    except Exception as e:
        logger.warning("Postgres write facturas_proveedores failed: %s", e)
    return factura


def registrar_abono_factura(
    fac_id: str,
    monto: float,
    fecha: str = None,
    foto_url: str = "",
    foto_nombre: str = "",
) -> dict:
    """
    Registra un abono a una factura existente.
    Actualiza pagado/pendiente/estado.
    Retorna {"ok": True/False, "factura": {...}, "error": "..."}
    """
    from datetime import datetime as _dt
    mem = cargar_memoria()
    facturas = mem.get("cuentas_por_pagar", [])

    factura = next((f for f in facturas if f["id"].upper() == fac_id.upper()), None)
    if not factura:
        return {"ok": False, "error": f"Factura {fac_id} no encontrada"}

    hoy = fecha or _dt.now(import_config_tz()).strftime("%Y-%m-%d")

    abono = {
        "fecha":       hoy,
        "monto":       float(monto),
        "foto_url":    foto_url,
        "foto_nombre": foto_nombre,
    }
    factura["abonos"].append(abono)
    factura["pagado"]    = round(factura["pagado"] + monto, 2)
    factura["pendiente"] = round(factura["total"] - factura["pagado"], 2)

    if factura["pendiente"] <= 0:
        factura["estado"] = "pagada"
        factura["pendiente"] = 0.0
    elif factura["pagado"] > 0:
        factura["estado"] = "parcial"

    # También registrar en gastos del día como abono a proveedor
    hoy_gastos = mem.setdefault("gastos", {}).setdefault(hoy, [])
    hoy_gastos.append({
        "concepto":  f"Abono {fac_id} - {factura['proveedor']}",
        "monto":     float(monto),
        "categoria": "abono_proveedor",
        "origen":    "proveedor",
        "hora":      _dt.now(import_config_tz()).strftime("%H:%M"),
        "fac_id":    fac_id,
    })

    guardar_memoria(mem, urgente=True)
    # Postgres dual-write: INSERT abono + UPDATE factura (non-fatal — D-01/D-02)
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            _db.execute(
                """INSERT INTO facturas_abonos (factura_id, monto, fecha, foto_url, foto_nombre)
                   VALUES (%s, %s, %s, %s, %s)""",
                (fac_id.upper(), int(float(monto)), hoy, foto_url, foto_nombre)
            )
            _db.execute(
                """UPDATE facturas_proveedores
                   SET pagado=%s, pendiente=%s, estado=%s
                   WHERE id=%s""",
                (int(round(factura["pagado"])), int(round(max(factura["pendiente"], 0))),
                 factura["estado"], fac_id.upper())
            )
    except Exception as e:
        logger.warning("Postgres write registrar_abono_factura failed: %s", e)
    return {"ok": True, "factura": factura}


def import_config_tz():
    """Helper para no importar config a nivel de módulo aquí."""
    try:
        import config as _c
        return _c.COLOMBIA_TZ
    except Exception:
        import pytz
        return pytz.timezone("America/Bogota")


def listar_facturas(solo_pendientes: bool = False) -> list:
    """Retorna la lista de facturas, opcionalmente solo las no pagadas."""
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            rows = _db.query_all(
                """SELECT fp.id, fp.proveedor, fp.descripcion, fp.total, fp.pagado,
                          fp.pendiente, fp.estado, fp.fecha::text, fp.foto_url, fp.foto_nombre,
                          COALESCE(
                              json_agg(
                                  json_build_object(
                                      'fecha', fa.fecha::text,
                                      'monto', fa.monto,
                                      'foto_url', COALESCE(fa.foto_url, ''),
                                      'foto_nombre', COALESCE(fa.foto_nombre, '')
                                  ) ORDER BY fa.created_at
                              ) FILTER (WHERE fa.id IS NOT NULL),
                              '[]'
                          ) AS abonos
                   FROM facturas_proveedores fp
                   LEFT JOIN facturas_abonos fa ON fa.factura_id = fp.id
                   GROUP BY fp.id
                   ORDER BY fp.fecha DESC""",
                ()
            )
            facturas = [
                {**dict(r), "abonos": r["abonos"] if r["abonos"] else []}
                for r in rows
            ]
            if solo_pendientes:
                return [f for f in facturas if f["estado"] != "pagada"]
            return facturas
    except Exception as e:
        logger.warning("Postgres read listar_facturas failed: %s", e)

    # Fallback: JSON
    mem = cargar_memoria()
    facturas = mem.get("cuentas_por_pagar", [])
    if solo_pendientes:
        return [f for f in facturas if f.get("estado") != "pagada"]
    return sorted(facturas, key=lambda f: f.get("fecha", ""), reverse=True)
