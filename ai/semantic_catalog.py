"""
ai/semantic_catalog.py — Búsqueda semántica del catálogo (fallback del fuzzy).

Cuando el matching léxico (memoria.buscar_producto_en_catalogo) y el fuzzy
(rapidfuzz, token_sort_ratio) fallan, este módulo busca por SIGNIFICADO usando
embeddings de OpenAI (text-embedding-3-small): capta sinónimos, jerga regional o
transcripciones lejanas léxicamente pero cercanas en sentido
("pega loca" → "Pegante Instantáneo"), que el fuzzy por caracteres no alcanza.

Diseño (= "el RAG útil" que se acordó: solo catálogo, no conocimiento genérico):
  - SIN base vectorial: el índice (producto → vector) vive en RAM, se construye
    una vez por proceso y se reusa. Se reconstruye SOLO si cambian los NOMBRES del
    catálogo (los cambios de precio no invalidan los embeddings de los nombres).
  - Fallback puro: el caso común (match léxico) NO toca este módulo → cero costo
    ni latencia. El embedding de la consulta solo se pide cuando el fuzzy ya falló.
  - Fail-safe: cualquier error (sin API key, red, formato) → None. Nunca rompe el
    flujo de voz; en el peor caso se comporta como si el módulo no existiera.
  - Solo SUGIERE (no auto-registra): corregir el nombre en silencio desincroniza
    la prosa hablada de Claude del registro real (mismo motivo que el riel de
    precio). Por eso devuelve un candidato para que el vendedor confirme.
  - Scoped a voz por ahora (lo invoca el riel R2 de existencia). No toca el bot ni
    el dashboard.
"""

# -- stdlib --
import logging
import math

# -- propios --
import config

log = logging.getLogger("ferrebot.semantic")

_MODELO_EMBED = "text-embedding-3-small"

# Umbral de similitud coseno para sugerir. Conservador (precisión > conveniencia):
# por debajo de esto NO se ofrece nada. text-embedding-3-small da ~0.5-0.8 para
# productos realmente relacionados; un score menor se trata como "sin match".
# TUNEAR en campo: como solo sugiere y el vendedor confirma, una sugerencia
# errada es de bajo daño, pero un umbral muy bajo molesta con propuestas absurdas.
UMBRAL_SUGERENCIA = 0.45

# Índice en RAM: lista de (producto_dict, vector). _firma rastrea con qué catálogo
# se generó para invalidarlo solo cuando cambian los nombres.
_indice: list[tuple[dict, list[float]]] = []
_firma: frozenset | None = None


def _firma_catalogo(catalogo: dict) -> frozenset:
    """Conjunto de nombres normalizados — cambia solo si se agregan/renombran productos."""
    return frozenset(
        (p.get("nombre_lower") or p.get("nombre") or "").strip()
        for p in catalogo.values()
        if (p.get("nombre_lower") or p.get("nombre"))
    )


def _embed(textos: list[str]) -> list[list[float]] | None:
    """Pide embeddings a OpenAI. Devuelve None ante cualquier fallo (fail-safe)."""
    if not textos:
        return []
    try:
        resp = config.openai_client.embeddings.create(model=_MODELO_EMBED, input=textos)
        return [d.embedding for d in resp.data]
    except Exception as e:
        log.warning("embeddings no disponibles, fallback semántico inactivo: %s", e)
        return None


def _construir_indice(catalogo: dict) -> None:
    """(Re)construye el índice de embeddings del catálogo. Cachea por firma de nombres."""
    global _indice, _firma
    firma = _firma_catalogo(catalogo)
    if firma == _firma and _indice:
        return  # ya está al día
    prods   = [p for p in catalogo.values() if (p.get("nombre_lower") or p.get("nombre"))]
    nombres = [(p.get("nombre") or p.get("nombre_lower") or "") for p in prods]
    vecs = _embed(nombres)
    if vecs is None or len(vecs) != len(prods):
        return  # falló: conservar el índice previo (o vacío) → fallback inactivo
    _indice = list(zip(prods, vecs))
    _firma  = firma
    log.info("[SEMANTIC] índice construido: %d productos", len(_indice))


def _coseno(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores. 0.0 si alguno es nulo."""
    num = sum(x * y for x, y in zip(a, b))
    da  = math.sqrt(sum(x * x for x in a))
    db  = math.sqrt(sum(y * y for y in b))
    if da == 0.0 or db == 0.0:
        return 0.0
    return num / (da * db)


def buscar_semantico(query: str, umbral: float = UMBRAL_SUGERENCIA) -> dict | None:
    """
    Producto del catálogo semánticamente más cercano a `query`, o None si ninguno
    supera `umbral`. Fail-safe: None ante cualquier error o si el flag está apagado.
    """
    if not getattr(config, "IA_SEMANTIC_CATALOGO", True):
        return None
    q = (query or "").strip()
    if len(q) < 3:
        return None

    from memoria import cargar_memoria
    catalogo = cargar_memoria().get("catalogo", {})
    if not catalogo:
        return None

    _construir_indice(catalogo)
    if not _indice:
        return None

    qv = _embed([q])
    if not qv:
        return None
    qvec = qv[0]

    mejor: dict | None = None
    mejor_score = 0.0
    for prod, vec in _indice:
        s = _coseno(qvec, vec)
        if s > mejor_score:
            mejor, mejor_score = prod, s

    if mejor is not None and mejor_score >= umbral:
        log.info("[SEMANTIC] '%s' → '%s' (%.3f)", q, mejor.get("nombre"), mejor_score)
        return mejor
    return None


def sugerencia_semantica(query: str) -> str | None:
    """Nombre del producto semánticamente más cercano (para '¿quisiste decir?'), o None."""
    prod = buscar_semantico(query)
    return prod.get("nombre") if prod else None
