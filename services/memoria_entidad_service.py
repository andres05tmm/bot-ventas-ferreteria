"""
services/memoria_entidad_service.py — CRUD de notas de memoria de entidad.

Capa 4 del sistema de memoria. Persiste y consulta notas estables sobre
productos, aliases y vendedores generadas por el compresor nocturno.

Decisiones de diseño:

  * Lookup inline en cada turno → debe ser rápido. Toda la lógica de búsqueda
    es por índice exacto sobre (tipo, entidad_key) + filtro vigente.
    No hay LIKE/FTS acá — el matching de la entidad al mensaje del usuario
    se hace en `prompt_context.py` usando catálogo en RAM (cero costo extra).

  * Compacto en tokens: cuando hay match, se inyectan máx 3 notas por entidad
    (configurable) ordenadas por fecha desc. Cada nota cap a ~200 chars.

  * Fail-silent: si la DB está caída, todas las funciones retornan [] o False.
    NUNCA propagan excepciones — Capa 4 es opcional, no debe tumbar el bot.

  * Idempotencia: `guardar_nota()` usa ON CONFLICT (tipo, entidad_key,
    fecha_generada) DO UPDATE — el compresor puede correrse dos veces el
    mismo día sin generar duplicados.

Las firmas públicas son las que consume `prompt_context.py` y `compresor_nocturno.py`.
"""

# -- stdlib --
import logging
import unicodedata
from datetime import date as _date

# -- propios --
import db as _db

log = logging.getLogger("ferrebot.services.memoria_entidad")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# Tipos válidos (espejo del CHECK constraint en la migración 020).
TIPOS_VALIDOS = ("producto", "alias", "vendedor")

# Cap defensivo para no inflar el prompt — el compresor también respeta esto
# pero aplicamos doble check al guardar.
_MAX_NOTA_CHARS = 280

# Cuántas notas devolver por entidad (lo más reciente primero)
_DEFAULT_LIMIT = 3


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _normalizar_key(key: str) -> str:
    """
    Normaliza la entidad_key: lowercase, sin tildes, sin espacios extra.
    Garantiza que 'Drywall 6mm' y 'drywall  6mm' colapsen al mismo bucket.
    """
    if not key:
        return ""
    s = unicodedata.normalize("NFKD", key)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _validar_tipo(tipo: str) -> str | None:
    """Retorna tipo normalizado o None si es inválido."""
    if not tipo:
        return None
    t = tipo.strip().lower()
    return t if t in TIPOS_VALIDOS else None


# ─────────────────────────────────────────────────────────────────────────────
# LECTURA — usado por prompt_context y por el tag [BUSCAR_MEMORIA]
# ─────────────────────────────────────────────────────────────────────────────

def obtener_notas(tipo: str, entidad_key: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """
    Retorna las notas vigentes de una entidad, lo más reciente primero.

    Args:
        tipo: 'producto' | 'alias' | 'vendedor'
        entidad_key: nombre de la entidad (se normaliza internamente)
        limit: cantidad máxima de notas (cap interno = 10 para evitar abuso)

    Returns:
        Lista de dicts con keys: id, nota, confidence, fecha_generada.
        Vacío si no hay match o si DB está abajo.
    """
    t = _validar_tipo(tipo)
    if not t:
        return []
    key = _normalizar_key(entidad_key)
    if not key:
        return []
    lim = max(1, min(int(limit or _DEFAULT_LIMIT), 10))
    try:
        return _db.query_all(
            """
            SELECT id, nota, confidence, fecha_generada
            FROM memoria_entidades
            WHERE tipo = %s
              AND entidad_key = %s
              AND vigente = TRUE
            ORDER BY fecha_generada DESC, id DESC
            LIMIT %s
            """,
            [t, key, lim],
        ) or []
    except Exception as e:
        log.warning("obtener_notas(%s, %s) falló: %s", tipo, key, e)
        return []


def obtener_notas_producto(nombre: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """Atajo — equivalente a obtener_notas('producto', nombre, limit)."""
    return obtener_notas("producto", nombre, limit)


def obtener_notas_vendedor(nombre: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """Atajo — equivalente a obtener_notas('vendedor', nombre, limit)."""
    return obtener_notas("vendedor", nombre, limit)


def obtener_aliases_aprendidos(limit: int = 20) -> list[dict]:
    """
    Retorna todos los aliases aprendidos vigentes ordenados por fecha desc.
    Útil para sembrar `alias_manager` en startup o para inspección manual.

    Returns:
        Lista de dicts con keys: entidad_key (alias), nota (forma canónica),
        fecha_generada, confidence.
    """
    lim = max(1, min(int(limit or 20), 200))
    try:
        return _db.query_all(
            """
            SELECT entidad_key, nota, confidence, fecha_generada
            FROM memoria_entidades
            WHERE tipo = 'alias' AND vigente = TRUE
            ORDER BY fecha_generada DESC, id DESC
            LIMIT %s
            """,
            [lim],
        ) or []
    except Exception as e:
        log.warning("obtener_aliases_aprendidos falló: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# ESCRITURA — usado solo por el compresor nocturno
# ─────────────────────────────────────────────────────────────────────────────

def guardar_nota(
    tipo: str,
    entidad_key: str,
    nota: str,
    fecha: _date | None = None,
    confidence: float = 1.0,
) -> bool:
    """
    Inserta o actualiza una nota para (tipo, entidad_key, fecha).
    Idempotente — si ya existe una nota para esa terna, la sobreescribe.

    Returns:
        True si se persistió, False si los inputs son inválidos o DB falló.
    """
    t = _validar_tipo(tipo)
    if not t:
        log.debug("guardar_nota: tipo inválido %r", tipo)
        return False
    key = _normalizar_key(entidad_key)
    if not key:
        log.debug("guardar_nota: entidad_key vacía")
        return False
    txt = (nota or "").strip()
    if not txt:
        log.debug("guardar_nota: nota vacía para %s/%s", t, key)
        return False
    if len(txt) > _MAX_NOTA_CHARS:
        txt = txt[:_MAX_NOTA_CHARS - 1].rstrip() + "…"
    f = fecha or _date.today()
    conf = max(0.0, min(float(confidence or 1.0), 1.0))

    try:
        _db.execute(
            """
            INSERT INTO memoria_entidades
                (tipo, entidad_key, nota, confidence, fecha_generada, vigente)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (tipo, entidad_key, fecha_generada)
            DO UPDATE SET
                nota       = EXCLUDED.nota,
                confidence = EXCLUDED.confidence,
                vigente    = TRUE
            """,
            [t, key, txt, conf, f],
        )
        return True
    except Exception as e:
        log.warning("guardar_nota(%s, %s) falló: %s", t, key, e)
        return False


def invalidar_nota(nota_id: int) -> bool:
    """
    Marca una nota como vigente=FALSE sin borrarla físicamente.
    Útil cuando una nota es claramente errónea y se quiere preservar el historial.
    """
    try:
        filas = _db.execute(
            "UPDATE memoria_entidades SET vigente = FALSE WHERE id = %s",
            [int(nota_id)],
        )
        return bool(filas)
    except Exception as e:
        log.warning("invalidar_nota(%s) falló: %s", nota_id, e)
        return False


def purgar_antiguas(dias: int = 90) -> int:
    """
    Borra físicamente notas más antiguas que `dias`. Pensado para job
    de mantenimiento (puede correrse al final del compresor nocturno).

    Returns:
        Cantidad de filas borradas (0 si DB falló).
    """
    d = max(7, int(dias or 90))
    try:
        return _db.execute(
            """
            DELETE FROM memoria_entidades
            WHERE fecha_generada < (CURRENT_DATE - INTERVAL '%s days')
            """ % d,  # noqa: S608 — INTERVAL no soporta parámetros en psycopg2
            [],
        )
    except Exception as e:
        log.warning("purgar_antiguas(%s) falló: %s", d, e)
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# FORMATEO — usado por prompt_context y por [BUSCAR_MEMORIA]
# ─────────────────────────────────────────────────────────────────────────────

def formatear_para_prompt(notas: list[dict], etiqueta: str) -> str:
    """
    Convierte una lista de notas en un string compacto para inyectar en el prompt.

    Formato:
        NOTAS DE MEMORIA — drywall 6mm:
          • [2026-04-15] se pide seguido con tornillos 6x1
          • [2026-04-10] clientes mayoristas suelen llevar 10+

    Returns:
        String formateado, o "" si la lista está vacía.
    """
    if not notas:
        return ""
    lineas = [f"NOTAS DE MEMORIA — {etiqueta}:"]
    for n in notas:
        fecha = n.get("fecha_generada")
        fecha_str = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha or "")
        nota = (n.get("nota") or "").strip()
        if nota:
            lineas.append(f"  • [{fecha_str}] {nota}")
    return "\n".join(lineas) if len(lineas) > 1 else ""
