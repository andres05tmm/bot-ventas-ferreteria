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
    # ── Otros typos frecuentes ────────────────────────────────
    "rodachines":   "rodachina",
    "rodachin":     "rodachina",
    "bisagra armillar": "bisagra armillar",  # ya correcto en catálogo
    "armillar":     "bisagra armillar",
    # ── Racores / plomería ────────────────────────────────────
    "racor macho":  "racos p/p macho",
    "racor pp":     "racos p/p macho",
}

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

    # Resolver wayper (kilo vs unidad) antes de los aliases generales
    resultado = _resolver_wayper(mensaje)
    for termino, reemplazo in todos.items():
        # Word boundary para evitar falsos positivos
        patron = r'\b' + re.escape(termino) + r'\b'
        resultado = re.sub(patron, reemplazo, resultado, flags=re.IGNORECASE)

    return resultado


def probar_alias(mensaje: str) -> str:
    """Para el comando /alias test — muestra cómo queda el mensaje."""
    original = mensaje
    resultado = aplicar_aliases_dinamicos(mensaje)
    if resultado == original:
        return f"🔍 Sin cambios:\n`{original}`"
    return f"🔍 Transformación:\n`{original}`\n→ `{resultado}`"
