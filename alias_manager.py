"""
alias_manager.py — Gestión dinámica de aliases de ferretería.

Separa los aliases SIMPLES (palabra → palabra/frase) del código Python.
Se guardan en la tabla `aliases` de PostgreSQL y se cachean en RAM.

Los aliases COMPLEJOS (regex con lógica) siguen en _ALIAS_FERRETERIA de ai.py.

COMANDOS TELEGRAM:
  /alias pagaternit pegaternit        → agrega alias
  /alias ver                          → lista todos
  /alias borrar pagaternit            → elimina alias
  /alias test "2 esmaltes"            → prueba cómo queda el mensaje
"""

import re
import logging
import threading

import db

logger = logging.getLogger("ferrebot.alias")

# Aliases PREDETERMINADOS — siempre activos, no se pueden borrar con /alias
# Solo términos coloquiales muy comunes que el bypass necesita resolver
_ALIASES_DEFAULT: dict[str, str] = {
    # ── Solventes ─────────────────────────────────────────────
    "tiner":        "thinner",
    "tinner":       "thinner",
    "barsol":       "varsol",
    "barso":        "varsol",
    # ── Sellantes / impermeabilizantes ────────────────────────
    "sellador":     "sellante",
    "pagaternit":   "pegaternit",
    "pega ternit":  "pegaternit",
    # ── Carbonato ─────────────────────────────────────────────
    "cal":          "carbonato x kg",
    # ── Enchufes ──────────────────────────────────────────────
    "cofelca":         "enchufe cofelca",
    "enchufe cofelca": "enchufe cofelca",
    # ── Vinilo ICO ────────────────────────────────────────────
    "vinilo ico":      "vinilo ico blanco",
    "ico blanco":      "vinilo ico blanco",
    "ico":             "vinilo ico blanco",
    # ── Abreviaciones de puntillas ────────────────────────────
    "cc":   "con cabeza",
    "sc":   "sin cabeza",
    # ── Tirafondo ─────────────────────────────────────────────
    "tirafondo":       "tornillo tirafondo",
    "tira fondo":      "tornillo tirafondo",
    # ── Cemento ───────────────────────────────────────────────
    "cemente gris": "cemento gris",
    # "cemento" solo (sin color) → gris por defecto, pero NO si dice "blanco"
    # Esto se maneja en el bot con el alias dinámico — NO poner alias genérico aquí
    # para evitar que "cemento blanco" se convierta en "cemento gris"
    # ── Cuñetes ───────────────────────────────────────────────
    "cunete t1":                   "cuñete vinilo tipo 1 davinci",
    "cuñete t1":                   "cuñete vinilo tipo 1 davinci",
    "cunete t2":                   "cuñete vinilo t 2",
    "cuñete t2":                   "cuñete vinilo t 2",
    "cunete vinilo blanco t1":     "cuñete vinilo tipo 1 davinci",
    "cuñete vinilo blanco t1":     "cuñete vinilo tipo 1 davinci",
    "cunete vinilo t1":            "cuñete vinilo tipo 1 davinci",
    "cuñete vinilo t1":            "cuñete vinilo tipo 1 davinci",
    "cunete vinilo blanco t2":     "cuñete vinilo t 2",
    "cuñete vinilo blanco t2":     "cuñete vinilo t 2",
    "cunete vinilo t2":            "cuñete vinilo t 2",
    "cuñete vinilo t2":            "cuñete vinilo t 2",
    "cunete vinilo blanco t3":     "cuñete vinilo t 3",
    "cuñete vinilo blanco t3":     "cuñete vinilo t 3",
    "cunete vinilo t3":            "cuñete vinilo t 3",
    "cuñete vinilo t3":            "cuñete vinilo t 3",
    "medio cunete t2":             "1/2 cuñete vinilo t2 blanco",
    "medio cuñete t2":             "1/2 cuñete vinilo t2 blanco",
    "medio cunete t1":             "1/2 cuñete vinilo t1 blanco",
    "medio cuñete t1":             "1/2 cuñete vinilo t1 blanco",
    "medio cunete t3":             "1/2 cuñete vinilo t3 blanco",
    "medio cuñete t3":             "1/2 cuñete vinilo t3 blanco",
    "medio cunete vinilo t1":      "1/2 cuñete vinilo t1 blanco",
    "medio cuñete vinilo t1":      "1/2 cuñete vinilo t1 blanco",
    "medio cunete vinilo t2":      "1/2 cuñete vinilo t2 blanco",
    "medio cuñete vinilo t2":      "1/2 cuñete vinilo t2 blanco",
    # ── Wayper ────────────────────────────────────────────────
    "waiper":       "wayper",
    "weiper":       "wayper",
    # ── Pele (tallas escritas de otro modo) ───────────────────
    "pele pequeña": "cinta pele s",
    "pele grande":  "cinta pele xl",
    # ── Pinturas coloquiales ──────────────────────────────────
    "vinilo davinci": "vinilo davinci t1",   # si no especifica tipo → T1
    "color preparado": "vinilo davinci t1",

    # ── Typos comunes de drywall ──────────────────────────────
    "drwayll":      "drywall",
    "drwayl":       "drywall",
    "drwall":       "drywall",
    "drawall":      "drywall",
    "drywll":       "drywall",
    "driwoll":      "drywall",
    "drygual":      "drywall",
    "drigual":      "drywall",
    "draigual":     "drywall",
    "draiwol":      "drywall",
    "draiwall":     "drywall",
    "drywal":       "drywall",
    "driwall":      "drywall",
    # ── Otros typos frecuentes ────────────────────────────────
    "rodachines":   "rodachina",
    "rodachin":     "rodachina",
    "bisagra armillar": "bisagra armillar",  # ya correcto en catálogo
    "armillar":     "bisagra armillar",
    # ── Racores / plomería ────────────────────────────────────
    "racor macho":  "racos p/p macho",
    "racor pp":     "racos p/p macho",
    # ── Silicona en taco (jerga colombiana = cartucho/tubo de silicona) ──
    "silicona blanca en taco": "Silicona Transparente X Tubo",
    "silicona en taco":        "Silicona Transparente X Tubo",
    "silicona blanca taco":    "Silicona Transparente X Tubo",
    "silicona taco":           "Silicona Transparente X Tubo",
    # ── Marcas de pegantes ────────────────────────────────────────────────
    "peganfer":     "pegante ceramico",
    "pega fer":     "pegante ceramico",
    # ── Typos simples de aliases ferretería (antes en ai/prompts._ALIAS_FERRETERIA) ──
    "pegaeternit":  "pegaternit",
    "3en1":         "3 en 1",
    "3-en-1":       "3 en 1",
}

# ─────────────────────────────────────────────
# ALIAS REGEX (M-06) — patterns con backreferences, sin lambda
# ─────────────────────────────────────────────
# Aplicados con re.sub IGNORECASE después de los aliases simples.
# Orden importante: patrones más específicos primero.
_ALIAS_REGEX: list[tuple] = [
    # Lija: "$N" → "#N" (el vendedor a veces escribe $60 en lugar de #60)
    (r'\blija[s]?\s+\$(\d+)\b',                              r'lija #\1'),
    # Puntilla: "caja de puntilla" → "puntilla"
    (r'\bcaja[s]?\s+de\s+puntilla[s]?\b',                    r'puntilla'),
    # Puntilla: abreviaciones s.c./c.c./sc/cc con artículo intermedio
    (r'\bpuntilla[s]?\s+(.*?)\bs\.c\.?\b',  r'puntilla \g<1> sin cabeza'),
    (r'\bpuntilla[s]?\s+(.*?)\bc\.c\.?\b',  r'puntilla \g<1> con cabeza'),
    (r'\bpuntilla[s]?\s+(.*?)\bsc\b',       r'puntilla \g<1> sin cabeza'),
    (r'\bpuntilla[s]?\s+(.*?)\bcc\b',       r'puntilla \g<1> con cabeza'),
    # sc genérico cerca de puntilla (lookahead)
    (r'\bsc\b(?=.*puntilla|\bpuntilla)',                      r'sin cabeza'),
    # Tornillos drywall: normalizar "NxM 3" → "NxM x3" (evitar confusión 6x3 vs 6x3/4)
    (r'\btornillo[s]?\s*(?:de\s*)?drywall\s*(\d+)\s*[xX]\s*3\b(?!/)', r'tornillo drywall \g<1>x3'),
    (r'\bdrywall\s*(\d+)\s*[xX]\s*3\b(?!/)',                            r'drywall \g<1>x3'),
    (r'\b(\d+)\s*[xX]\s*3\b(?!/)\s*(?=.*(?:tornillo|drywall))',        r'\g<1>x3'),
    # Selladores: normalizar "sellante" → "sellador" según variante
    (r'\b(?:sellante|sellador)\s+lijable\b',                  r'sellador corriente'),
    (r'\b(?:sellante|sellador)\s+corriente\b',                r'sellador corriente'),
    (r'\b(?:sellante|sellador)\s+catalizado\b',               r'sellador catalizado'),
    # Thinner / Varsol por galones (sin lambda — cantidad y solvente como grupos)
    (r'\b(\d+)\s*-\s*1/2\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b',          r'\g<1>.5 galones \g<2>'),
    (r'\b(\d+)\s+y\s+(?:medio|1/2)\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1>.5 galones \g<2>'),
    (r'\b(\d+)\s+(?:galon(?:es)?)\s+y\s+(?:medio|1/2)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1>.5 galones \g<2>'),
    (r'\b(?:medio|1/2)\s*(?:galon)?\s*(?:de\s*)?(thinner|varsol)\b',                   r'0.5 galones \g<1>'),
    (r'\b(\d+)\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b',                     r'\g<1> galones \g<2>'),
]

# ─────────────────────────────────────────────
# ALIAS LAMBDA (M-06) — transformaciones con cálculo Python, específicas de ferretería
# ─────────────────────────────────────────────
# Aplicados con re.sub IGNORECASE después de _ALIAS_REGEX.
# Usan lambda para calcular el reemplazo en tiempo de ejecución.
_ALIAS_LAMBDA: list[tuple] = [
    # Rodillo sin medida → Rodillo Convencional (el más vendido sin especificar tamaño)
    (r'\b(\d+)\s+rodillos?\b(?!\s*(?:de\s+)?\d)',
        lambda m: f"{m.group(1)} rodillo convencional"),
    # Pita sin color → pita para carpa azul (la más vendida en Punto Rojo)
    (r'\b(\d+)\s+(?:metros?\s+(?:de\s+)?)?pitas?\b'
     r'(?!\s*(?:para\s+)?(?:carpa\s+)?(?:azul|rojo|negro|blanco|amarillo))',
        lambda m: f"{m.group(1)} pita para carpa azul"),
    # Thinner / Varsol: botellita (pequeña) = 1/10 galón → $4.000
    # IMPORTANTE: la regex de botellita va ANTES que la de botella (no colisionan,
    # pero el orden deja la intención explícita: lo más específico primero).
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellitas?\s+(?:de\s+)?thinner\b',
        lambda m: "thinner 4000" if int(m.group(1) or 1) == 1 else f"{int(m.group(1)) * 4000} thinner"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellitas?\s+(?:de\s+)?varsol\b',
        lambda m: "varsol 4000"  if int(m.group(1) or 1) == 1 else f"{int(m.group(1)) * 4000} varsol"),
    # Thinner / Varsol: botella = 1/4 galón → $8.000 (la de 5.000 se pide como "5000 de thinner")
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellas?\s+(?:de\s+)?thinner\b',
        lambda m: "thinner 8000" if int(m.group(1) or 1) == 1 else f"{int(m.group(1)) * 8000} thinner"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellas?\s+(?:de\s+)?varsol\b',
        lambda m: "varsol 8000"  if int(m.group(1) or 1) == 1 else f"{int(m.group(1)) * 8000} varsol"),
    # Thinner / Varsol: litro = 1/4 galón → precio total (8000)
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*litros?\s+(?:de\s+)?thinner\b',
        lambda m: "thinner 8000" if int(m.group(1) or 1) == 1 else f"{int(m.group(1)) * 8000} thinner"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*litros?\s+(?:de\s+)?varsol\b',
        lambda m: "varsol 8000"  if int(m.group(1) or 1) == 1 else f"{int(m.group(1)) * 8000} varsol"),
    # Carbonato en bolsa → "Carbonato X 25 Kg". "bolsa de carbonato" sin el "25 kg"
    # no matchea el producto (la palabra "bolsa" arrastra otros productos en bolsa).
    # Inyectar "25 kg" hace que el MATCH encuentre el producto correcto.
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*bolsas?\s+(?:de\s+)?carbonato\b',
        lambda m: "carbonato 25 kg" if int(m.group(1) or 1) == 1 else f"{int(m.group(1))} carbonato 25 kg"),
    (r'\bcarbonato\s+(?:en\s+)?bolsa\b', lambda m: "carbonato 25 kg"),
]

# Cache en RAM — cargado una vez al iniciar, actualizado en cada /alias
_aliases: dict[str, str] = {}  # {termino_lower: reemplazo}
_lock = threading.Lock()


# ─────────────────────────────────────────────
# CARGA / GUARDADO
# ─────────────────────────────────────────────

def cargar_aliases() -> dict:
    """Carga aliases desde PostgreSQL. Llama al iniciar el bot."""
    global _aliases
    try:
        filas = db.query_all("SELECT termino, reemplazo FROM aliases")
        with _lock:
            _aliases = {row["termino"]: row["reemplazo"] for row in filas}
        logger.info(f"[ALIAS] {len(_aliases)} aliases cargados desde PostgreSQL")
    except Exception as e:
        logger.error(f"[ALIAS] Error cargando aliases desde PG: {e}")
    return dict(_aliases)


def _upsert_alias_pg(termino: str, reemplazo: str) -> None:
    """Persiste un alias en PostgreSQL (INSERT … ON CONFLICT UPDATE)."""
    db.execute(
        """
        INSERT INTO aliases (termino, reemplazo, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (termino) DO UPDATE
            SET reemplazo  = EXCLUDED.reemplazo,
                updated_at = NOW()
        """,
        (termino, reemplazo),
    )


def _delete_alias_pg(termino: str) -> None:
    """Elimina un alias de PostgreSQL."""
    db.execute("DELETE FROM aliases WHERE termino = %s", (termino,))


# ─────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────

def agregar_alias(termino: str, reemplazo: str) -> str:
    """
    Agrega o actualiza un alias.
    Retorna mensaje de confirmación.
    """
    termino_key = termino.strip().lower()
    reemplazo_val = reemplazo.strip().lower()

    if not termino_key or not reemplazo_val:
        return "❌ Necesito dos argumentos: /alias [termino] [reemplazo]"

    if len(termino_key) < 2:
        return "❌ El término debe tener al menos 2 caracteres."

    if termino_key == reemplazo_val:
        return "❌ El término y el reemplazo son iguales."

    with _lock:
        existia = termino_key in _aliases
        _aliases[termino_key] = reemplazo_val

    try:
        _upsert_alias_pg(termino_key, reemplazo_val)
    except Exception as e:
        logger.error(f"[ALIAS] Error guardando en PG: {e}")
        return "❌ Error guardando el alias en la base de datos."

    if existia:
        return f"✅ Alias actualizado: '{termino_key}' → '{reemplazo_val}'"
    return f"✅ Alias guardado: '{termino_key}' → '{reemplazo_val}'"


def borrar_alias(termino: str) -> str:
    """Elimina un alias. Retorna mensaje de confirmación."""
    termino_key = termino.strip().lower()

    with _lock:
        if termino_key not in _aliases:
            return f"❌ No existe el alias '{termino_key}'"
        del _aliases[termino_key]

    try:
        _delete_alias_pg(termino_key)
    except Exception as e:
        logger.error(f"[ALIAS] Error borrando en PG: {e}")
        return "❌ Error eliminando el alias de la base de datos."

    return f"🗑️ Alias eliminado: '{termino_key}'"


def listar_aliases() -> str:
    """Retorna string formateado con todos los aliases."""
    with _lock:
        copia = dict(_aliases)

    if not copia:
        return "📋 No hay aliases guardados.\n\nUsa /alias [termino] [reemplazo] para agregar uno."

    lineas = ["📋 *Aliases activos:*\n"]
    for termino, reemplazo in sorted(copia.items()):
        lineas.append(f"  `{termino}` → `{reemplazo}`")
    lineas.append(f"\nTotal: {len(copia)} aliases")
    return "\n".join(lineas)


# ─────────────────────────────────────────────
# APLICAR ALIASES AL MENSAJE
# ─────────────────────────────────────────────

def _resolver_wayper(mensaje: str) -> str:
    """
    Resuelve la ambigüedad wayper kilo vs unidad ANTES de los aliases.

    Regla del negocio:
      - Sin indicador de peso  → UNIDAD  ("3 wayper de color" → WAYPER DE COLOR UNIDAD)
      - Con kg/kilo/libra       → KG     ("2 kg wayper de color" → WAYPER DE COLOR)

    Usa placeholders para evitar que el reemplazo genérico capture
    lo que ya fue reemplazado por un patrón más específico.
    """
    import re as _re_w

    _PESO = r'\b(kilo|kilos|kg|libra|libras|gramo|gramos)\b'
    _tiene_peso = bool(_re_w.search(_PESO, mensaje, _re_w.IGNORECASE))

    msg = mensaje
    if _tiene_peso:
        msg = _re_w.sub(r'\bwaypers?\s+de\s+colou?r\b', '__WPC_KG__',  msg, flags=_re_w.IGNORECASE)
        msg = _re_w.sub(r'\bwaypers?\s+colou?r\b',        '__WPC_KG__',  msg, flags=_re_w.IGNORECASE)
        msg = _re_w.sub(r'\bwaypers?\s+blancos?\b',       '__WPB_KG__',  msg, flags=_re_w.IGNORECASE)
        msg = _re_w.sub(r'\bwaypers?\b',                   '__WPB_KG__',  msg, flags=_re_w.IGNORECASE)
        msg = msg.replace('__WPC_KG__', 'WAYPER DE COLOR').replace('__WPB_KG__', 'WAYPER BLANCO')
    else:
        msg = _re_w.sub(r'\bwaypers?\s+de\s+colou?r\b', '__WPC_U__',  msg, flags=_re_w.IGNORECASE)
        msg = _re_w.sub(r'\bwaypers?\s+colou?r\b',        '__WPC_U__',  msg, flags=_re_w.IGNORECASE)
        msg = _re_w.sub(r'\bwaypers?\s+blancos?\b',       '__WPB_U__',  msg, flags=_re_w.IGNORECASE)
        msg = _re_w.sub(r'\bwaypers?\b',                   '__WPB_U__',  msg, flags=_re_w.IGNORECASE)
        msg = msg.replace('__WPC_U__', 'WAYPER DE COLOR UNIDAD').replace('__WPB_U__', 'WAYPER BLANCO UNIDAD')

    return msg


def aplicar_aliases_dinamicos(mensaje: str) -> str:
    """
    Reemplaza términos simples del mensaje usando aliases en RAM.
    Se aplica ANTES que los aliases regex de ai.py.

    Solo reemplaza palabras completas (word boundary) para evitar
    que "lija" reemplace parte de "antihongolija".
    """
    with _lock:
        aliases_activos = dict(_aliases)

    # Combinar defaults + dinámicos (dinámicos tienen prioridad)
    todos = {**_ALIASES_DEFAULT, **aliases_activos}

    # ── Normalizar notación de lija: #120 → N°120 ──────────────────────────
    # Para que "lija #120" encuentre "Lija N°120" en el catálogo.
    resultado = re.sub(r'#(\d+)', r'N°\1', mensaje)

    # ── Normalizar abreviaciones de puntilla con puntos ──────────────────
    # "s.c." / "s.c" → "sin cabeza" | "c.c." / "c.c" → "con cabeza"
    resultado = re.sub(r'\bs\.c\.?\b', 'sin cabeza', resultado, flags=re.IGNORECASE)
    resultado = re.sub(r'\bc\.c\.?\b', 'con cabeza', resultado, flags=re.IGNORECASE)

    # ── Normalizar "t-N" → "tN" para vinil/cuñete ─────────────────────────
    # El catálogo usa "T1", "T2", "T3" pero el vendedor a veces escribe "t-1", "t-2"
    # Ejemplo: "1/2 cuñete vinilo t-1" → "1/2 cuñete vinilo t1"
    resultado = re.sub(r'\b(t)-(\d)\b', r'\1\2', resultado, flags=re.IGNORECASE)

    # Resolver wayper (kilo vs unidad) antes de los aliases generales
    resultado = _resolver_wayper(resultado)
    for termino, reemplazo in todos.items():
        # Word boundary para evitar falsos positivos
        patron = r'\b' + re.escape(termino) + r'\b'
        resultado = re.sub(patron, reemplazo, resultado, flags=re.IGNORECASE)

    return resultado


def aplicar_alias_completo(mensaje: str) -> str:
    """
    Aplica la cadena completa de alias al mensaje (M-06):
      1. Aliases dinámicos: defaults + BD (word boundaries)
      2. _ALIAS_REGEX: regex con backreferences (sin lambda)
      3. _ALIAS_LAMBDA: transformaciones con cálculo Python

    Reemplaza la lógica antes dispersa en ai/prompts._ALIAS_FERRETERIA.
    """
    resultado = aplicar_aliases_dinamicos(mensaje)
    for patron, reemplazo in _ALIAS_REGEX:
        resultado = re.sub(patron, reemplazo, resultado, flags=re.IGNORECASE)
    for patron, reemplazo in _ALIAS_LAMBDA:
        resultado = re.sub(patron, reemplazo, resultado, flags=re.IGNORECASE)
    return resultado


def probar_alias(mensaje: str) -> str:
    """Para el comando /alias test — muestra cómo queda el mensaje."""
    original = mensaje
    resultado = aplicar_aliases_dinamicos(mensaje)
    if resultado == original:
        return f"🔍 Sin cambios:\n`{original}`"
    return f"🔍 Transformación:\n`{original}`\n→ `{resultado}`"
