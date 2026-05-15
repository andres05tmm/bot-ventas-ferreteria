"""
handlers/audio_sales.py — Intent detection para carrito conversacional de audio.

El flujo de audio multi-turno necesita reconocer *sin llamar a Claude* un puñado
de intenciones que ocurren muy frecuentemente:

    cierre            → "cobra", "cierra", "eso es todo", "finaliza", "cobrarle"
    cancelación       → "cancela", "olvídalo", "no, nada", "quita todo"
    método de pago    → "en efectivo", "transferencia", "con datáfono", "al fiado"
    cliente implícito → "ponle a pedro", "al fiado de juan", "para la doña maría"
    quitar último     → "quita el último", "el de clavos no", "borra el martillo"

Estas funciones son **puras**: regex sobre el texto normalizado, sin consultas
a DB ni red. Se ejecutan antes de `procesar_con_claude` en el flujo de audio
para ahorrar ~800ms + tokens cuando hay una intención obvia.

Filosofía idéntica a bypass.py: si no estamos seguros, retornar None y dejar
que Claude se encargue. El costo de un falso negativo (llamada a Claude
innecesaria) es mucho menor que el costo de un falso positivo (acción
equivocada sobre el carrito).
"""

# -- stdlib --
import re
import unicodedata

# ─────────────────────────────────────────────────────────────────────────
# NORMALIZACIÓN
# ─────────────────────────────────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    """Minúsculas + sin tildes + sin puntuación de borde."""
    if not texto:
        return ""
    t = texto.strip().lower()
    # Quitar tildes/diacríticos
    t = "".join(
        c for c in unicodedata.normalize("NFD", t)
        if unicodedata.category(c) != "Mn"
    )
    # Quitar signos de puntuación de borde pero mantener espacios internos
    t = re.sub(r"[¡!¿?.,;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ─────────────────────────────────────────────────────────────────────────
# CIERRE EXPLÍCITO DEL CARRITO
# ─────────────────────────────────────────────────────────────────────────
# El vendedor indica que ya terminó de listar productos y quiere registrar.
# Ej: "cobra", "cóbralo", "ciérralo", "eso es todo", "listo cobra", "finaliza"

_RE_CIERRE = re.compile(
    r"\b("
    r"cobra(lo|le|les)?|"
    r"cierr[aeo](lo|la|le)?|"
    r"finaliza(lo|la)?|"
    r"termina(lo|la)?|"
    r"eso es todo|"
    r"eso seria todo|"
    r"eso no mas|"
    r"ya esta|"
    r"ya quedo|"
    r"regis(tra|tralo|tren|tralo)|"
    r"guarda(lo|la)?"
    r")\b"
)


def detectar_cierre(texto: str) -> bool:
    """True si el texto indica 'cerrar el carrito y registrar'."""
    return bool(_RE_CIERRE.search(_normalizar(texto)))


# ─────────────────────────────────────────────────────────────────────────
# CANCELACIÓN DEL CARRITO
# ─────────────────────────────────────────────────────────────────────────
# El vendedor quiere tirar a la basura todo lo acumulado.

_RE_CANCELAR = re.compile(
    r"\b("
    r"cancela(lo|la)?|"
    r"olvida(lo|la)?|"
    r"olvidalo|"
    r"borra todo|"
    r"quita todo|"
    r"elimina todo|"
    r"nada nada|"
    r"no nada|"
    r"descarta(lo|la)?"
    r")\b"
)


def detectar_cancelacion(texto: str) -> bool:
    """True si el texto indica 'descarta el carrito completo'."""
    return bool(_RE_CANCELAR.search(_normalizar(texto)))


# ─────────────────────────────────────────────────────────────────────────
# MÉTODO DE PAGO IMPLÍCITO
# ─────────────────────────────────────────────────────────────────────────
# El vendedor dice cómo pagan sin darle el listado completo.

_METODOS = {
    "efectivo":      re.compile(r"\b(efectivo|cash|en plata|de contado|al contado)\b"),
    "transferencia": re.compile(r"\b(transferencia|nequi|daviplata|bancolombia|movii)\b"),
    "datafono":      re.compile(r"\b(datafono|tarjeta|con la tarjeta|bold)\b"),
}


def detectar_metodo_pago(texto: str) -> str | None:
    """
    Retorna 'efectivo' | 'transferencia' | 'datafono' si el texto menciona
    un método de pago de forma clara, None si no.
    """
    t = _normalizar(texto)
    for metodo, regex in _METODOS.items():
        if regex.search(t):
            return metodo
    return None


# ─────────────────────────────────────────────────────────────────────────
# CLIENTE / FIADO IMPLÍCITO
# ─────────────────────────────────────────────────────────────────────────
# "ponle al fiado de juan", "todo para pedro", "a la doña maría"

_RE_CLIENTE = re.compile(
    r"\b("
    r"al\s+fiado\s+de\s+(?P<c1>[a-zñáéíóúü ]+?)"
    r"|a\s+nombre\s+de\s+(?P<c2>[a-zñáéíóúü ]+?)"
    r"|para\s+(?:don|dona|doña|el|la|los|las)\s+(?P<c3>[a-zñáéíóúü ]+?)"
    r"|ponle\s+a\s+(?P<c4>[a-zñáéíóúü ]+?)"
    r")"
    r"(?:\s+(?:porfa|por favor|gracias|$)|$|\s*[,.]|\s+y\b)"
)


def detectar_cliente_implicito(texto: str) -> str | None:
    """
    Extrae el nombre del cliente si el texto lo menciona con frases típicas.
    Retorna el nombre normalizado (minúsculas sin tildes) o None.
    """
    t = _normalizar(texto)
    m = _RE_CLIENTE.search(t)
    if not m:
        return None
    nombre = (
        m.group("c1") or m.group("c2") or m.group("c3") or m.group("c4") or ""
    ).strip()
    # Cortar en "y" o coma residual
    nombre = re.split(r"\b(?:y|,)\b", nombre, maxsplit=1)[0].strip()
    return nombre or None


def detectar_fiado(texto: str) -> bool:
    """True si el texto menciona 'fiado' explícitamente (incluye conjugaciones)."""
    return bool(re.search(r"\bfia(d[oa]s?|r|rle|rlo|rla|le|lo|la|me|nos|ndo|do)\b", _normalizar(texto)))


# ─────────────────────────────────────────────────────────────────────────
# QUITAR ÚLTIMO ÍTEM DEL CARRITO
# ─────────────────────────────────────────────────────────────────────────

_RE_QUITAR_ULTIMO = re.compile(
    r"\b("
    r"quita\s+(?:el\s+)?ultimo|"
    r"quitar\s+(?:el\s+)?ultimo|"
    r"borra\s+(?:el\s+)?ultimo|"
    r"el\s+ultimo\s+no|"
    r"ese\s+ultimo\s+no|"
    r"no\s+ese\s+ultimo"
    r")\b"
)


def detectar_quitar_ultimo(texto: str) -> bool:
    """True si el vendedor quiere deshacer el último ítem añadido al carrito."""
    return bool(_RE_QUITAR_ULTIMO.search(_normalizar(texto)))


# ─────────────────────────────────────────────────────────────────────────
# FALLBACK: ¿ES SOLO UNA META-INSTRUCCIÓN?
# ─────────────────────────────────────────────────────────────────────────

def es_solo_meta(texto: str) -> bool:
    """
    True si el texto NO lista productos (es solo una instrucción sobre el
    carrito). Usado para decidir si se puede omitir la llamada a Claude.

    Heurística: es meta si detectamos cierre/cancelación/método/quitar último
    Y el texto tiene menos de 8 palabras (un audio largo casi siempre trae
    productos).
    """
    palabras = len(_normalizar(texto).split())
    if palabras >= 8:
        return False
    return (
        detectar_cierre(texto)
        or detectar_cancelacion(texto)
        or detectar_quitar_ultimo(texto)
        or (detectar_metodo_pago(texto) is not None and palabras <= 5)
    )
