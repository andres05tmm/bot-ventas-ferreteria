"""
Cache RAM de precios recién actualizados para FerreBot.

Propósito: override del cache de Anthropic cuando un precio cambia en BD,
para que el bot refleje el nuevo precio antes de que expire el prompt cache
(TTL 5 min = mismo valor que _PRECIO_TTL en ai.py original).

API pública:
  registrar(nombre_lower, precio, fraccion=None)  — guarda o sobreescribe
  get_activos()                                   — devuelve solo los no expirados
  invalidar(nombre_lower)                         — borra todas las entradas del producto
  limpiar_expirados()                             — purga entradas vencidas (mantenimiento)

Thread-safety: threading.RLock protege _cache internamente.
El módulo es standalone — no importa ai.py, memoria.py ni handlers.

IMPORTANTE — No crear ai/__init__.py junto a este archivo.
Si ai/__init__.py existe, Python trata ai/ como paquete y sombrea ai.py,
rompiendo todos los `from ai import procesar_con_claude`.
Verificar tras commit: python -c "import ai; print(type(ai.procesar_con_claude))"
"""

# -- stdlib --
import logging
import threading
import time

# -- terceros --
# (ninguno)

# -- propios --
# (ninguno — standalone por diseño)

logger = logging.getLogger("ferrebot.price_cache")

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

TTL: int = 300  # segundos — igual que _PRECIO_TTL en ai.py original

# ─────────────────────────────────────────────
# ESTADO INTERNO
# ─────────────────────────────────────────────

# Estructura: {clave: (precio: float, timestamp: float)}
# clave = "nombre_lower" o "nombre_lower___fraccion"
_cache: dict[str, tuple[float, float]] = {}
_lock = threading.RLock()  # RLock: permite re-entrada desde el mismo thread


def _make_key(nombre_lower: str, fraccion: str | None) -> str:
    """Genera la clave interna del cache."""
    if fraccion:
        return f"{nombre_lower}___{fraccion}"
    return nombre_lower


# ─────────────────────────────────────────────
# API PÚBLICA
# ─────────────────────────────────────────────

def registrar(nombre_lower: str, precio: float, fraccion: str | None = None) -> None:
    """
    Registra o sobreescribe el precio de un producto en el cache.

    Borra todas las entradas anteriores del mismo producto (cualquier fracción)
    antes de guardar la nueva, para evitar inconsistencias entre fracciones.

    Args:
        nombre_lower: Nombre del producto en minúsculas (clave de búsqueda).
        precio:       Precio actualizado.
        fraccion:     Fracción del producto, ej: "1/4", "1/2". None = precio base.
    """
    nueva_clave = _make_key(nombre_lower, fraccion)
    with _lock:
        # Limpiar entradas anteriores del mismo producto (todas las fracciones)
        claves_borrar = [
            k for k in _cache
            if k == nombre_lower or k.startswith(nombre_lower + "___")
        ]
        for k in claves_borrar:
            del _cache[k]
        _cache[nueva_clave] = (precio, time.time())
    logger.debug("price_cache: registrado %r = %.2f (fraccion=%r)", nombre_lower, precio, fraccion)


def get_activos() -> dict[str, float]:
    """
    Devuelve solo las entradas no expiradas del cache.

    Returns:
        dict[clave, precio] — solo entradas con timestamp dentro del TTL.
    """
    ahora = time.time()
    limite = ahora - TTL
    with _lock:
        activos = {k: v[0] for k, v in _cache.items() if v[1] > limite}
    return activos


def invalidar(nombre_lower: str) -> int:
    """
    Elimina todas las entradas del cache para un producto dado.

    Incluye precio base y todas las fracciones (claves con "___").

    Args:
        nombre_lower: Nombre del producto en minúsculas.

    Returns:
        Número de entradas eliminadas.
    """
    with _lock:
        claves_borrar = [
            k for k in _cache
            if k == nombre_lower or k.startswith(nombre_lower + "___")
        ]
        for k in claves_borrar:
            del _cache[k]
    if claves_borrar:
        logger.debug("price_cache: invalidado %r (%d entradas)", nombre_lower, len(claves_borrar))
    return len(claves_borrar)


def limpiar_expirados() -> int:
    """
    Elimina entradas vencidas del cache para evitar crecimiento indefinido.

    Llamar periódicamente (ej: al inicio de cada turno de conversación, o
    desde un job nocturno). Con el TTL de 5 min y uso normal del bot, el
    cache nunca crece a más de ~200 entradas, así que esta llamada es
    principalmente de mantenimiento defensivo.

    Returns:
        Número de entradas eliminadas.
    """
    ahora = time.time()
    limite = ahora - TTL
    with _lock:
        claves_expiradas = [k for k, v in _cache.items() if v[1] <= limite]
        for k in claves_expiradas:
            del _cache[k]
    if claves_expiradas:
        logger.debug("price_cache: %d entradas expiradas eliminadas", len(claves_expiradas))
    return len(claves_expiradas)


def tamaño() -> int:
    """Devuelve el número total de entradas en cache (incluye expiradas)."""
    with _lock:
        return len(_cache)
