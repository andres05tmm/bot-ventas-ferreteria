"""
services/search_service.py — Búsqueda histórica híbrida (FTS + pg_trgm).

Capa 3 de memoria del bot: permite responder preguntas del vendedor sobre su
propio histórico sin mandar todas las filas al prompt de Claude.

Casos de uso típicos:

    "¿qué le vendí ayer a Pedro?"
        → buscar_ventas_por_producto("", cliente="pedro", dias=1)

    "¿cuándo pidieron drywall?"
        → buscar_ventas_por_producto("drywall", dias=60)

    "¿de qué hablamos con Juan sobre el fiado?"
        → buscar_conversaciones("fiado juan", chat_id=None, dias=30)

Estrategia híbrida
──────────────────
1. Primer intento: FTS nativo con `plainto_tsquery('spanish', q)` + ts_rank.
2. Si FTS devuelve menos de `min_fts` resultados → suplementa con pg_trgm
   (`similarity() > umbral`). Así toleramos typos sin perder precisión
   cuando la query es limpia.

Todos los queries:
  * Llevan LIMIT explícito (default 10 — Claude no necesita más contexto)
  * Filtran por antigüedad (default 30 días) para no traer basura vieja
  * Retornan listas de dicts — fallan-silencio devolviendo [] si DB está abajo

No toca cache ni estado en memoria. Es una capa read-only sobre Postgres.
"""

# -- stdlib --
import logging
from typing import Any

# -- propios --
import db as _db

log = logging.getLogger("ferrebot.services.search")


# ─────────────────────────────────────────────────────────────────────────
# CONSTANTES DE TUNING
# ─────────────────────────────────────────────────────────────────────────

# Si FTS devuelve menos que esto, suplementamos con trigram.
_MIN_FTS_HITS = 3

# Umbral de similaridad trigram. 0.3 tolera typos razonables;
# subir (0.4-0.5) si hay demasiados falsos positivos.
_TRGM_THRESHOLD = 0.30

# Límite duro para toda búsqueda — protege pool y tokens de Claude.
_HARD_LIMIT = 50


# ─────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────


def _limpiar_query(q: str) -> str:
    """
    Normaliza la query antes de meterla a tsquery. Quita caracteres que
    confunden a plainto_tsquery y recorta a 200 chars.
    """
    if not q:
        return ""
    limpio = " ".join(q.strip().split())[:200]
    return limpio


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


# ─────────────────────────────────────────────────────────────────────────
# BÚSQUEDA DE CONVERSACIONES
# ─────────────────────────────────────────────────────────────────────────


def buscar_conversaciones(
    query: str,
    chat_id: int | None = None,
    dias: int = 30,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Busca turnos en conversaciones_bot cuyo content coincida (FTS + trigram).

    Args:
        query:   texto a buscar. Si es vacío, retorna [].
        chat_id: si se pasa, filtra por chat (útil para "en esta conversación").
                 Si None, busca en todos los chats (útil para admin).
        dias:    antigüedad máxima en días (default 30).
        limit:   máximo de resultados (hard-cap a 50).

    Returns:
        Lista de dicts con: id, chat_id, vendedor_id, role, content, creado, rank.
        Orden: rank desc, creado desc. Retorna [] si la DB no está disponible.
    """
    q = _limpiar_query(query)
    if not q:
        return []

    limit = _clamp(limit, 1, _HARD_LIMIT)

    # ── 1) FTS nativo ────────────────────────────────────────────────────
    sql_fts = """
        SELECT id, chat_id, vendedor_id, role, content, creado,
               ts_rank(to_tsvector('spanish', content),
                       plainto_tsquery('spanish', %s)) AS rank
        FROM conversaciones_bot
        WHERE to_tsvector('spanish', content) @@ plainto_tsquery('spanish', %s)
          AND creado >= NOW() - (%s || ' days')::INTERVAL
          {chat_filter}
        ORDER BY rank DESC, creado DESC
        LIMIT %s;
    """
    chat_filter = "AND chat_id = %s" if chat_id is not None else ""
    params: list[Any] = [q, q, str(dias)]
    if chat_id is not None:
        params.append(chat_id)
    params.append(limit)

    try:
        filas_fts = _db.query_all(
            sql_fts.format(chat_filter=chat_filter), params
        ) or []
    except Exception as e:
        log.warning("FTS conversaciones falló: %s", e)
        filas_fts = []

    if len(filas_fts) >= _MIN_FTS_HITS or len(filas_fts) >= limit:
        return filas_fts

    # ── 2) Fallback trigram (tolera typos) ───────────────────────────────
    ids_ya = {f["id"] for f in filas_fts}
    restante = limit - len(filas_fts)

    sql_trgm = """
        SELECT id, chat_id, vendedor_id, role, content, creado,
               similarity(content, %s) AS rank
        FROM conversaciones_bot
        WHERE content %% %s
          AND similarity(content, %s) >= %s
          AND creado >= NOW() - (%s || ' days')::INTERVAL
          {chat_filter}
        ORDER BY rank DESC, creado DESC
        LIMIT %s;
    """
    params_trgm: list[Any] = [q, q, q, _TRGM_THRESHOLD, str(dias)]
    if chat_id is not None:
        params_trgm.append(chat_id)
    # Pedimos un poco más para descartar duplicados con los FTS ya traídos.
    params_trgm.append(restante * 2 if restante > 0 else 1)

    try:
        filas_trgm = _db.query_all(
            sql_trgm.format(chat_filter=chat_filter), params_trgm
        ) or []
    except Exception as e:
        log.warning(
            "Trigram conversaciones falló (pg_trgm no instalado?): %s", e
        )
        filas_trgm = []

    # Merge sin duplicados
    nuevos = [f for f in filas_trgm if f["id"] not in ids_ya][:restante]
    return filas_fts + nuevos


# ─────────────────────────────────────────────────────────────────────────
# BÚSQUEDA DE VENTAS POR PRODUCTO
# ─────────────────────────────────────────────────────────────────────────


def buscar_ventas_por_producto(
    query: str,
    dias: int = 30,
    limit: int = 10,
    vendedor: str | None = None,
) -> list[dict[str, Any]]:
    """
    Busca en ventas_detalle.producto_nombre + une con ventas para contexto.

    Args:
        query:    nombre (o fragmento) del producto. Vacío retorna [].
        dias:     antigüedad máxima (default 30). Usar 1 para "ayer".
        limit:    máximo de filas (hard-cap a 50).
        vendedor: si se pasa, filtra por ventas.vendedor (ILIKE %v%).

    Returns:
        Lista de dicts con:
            venta_id, consecutivo, fecha, hora, cliente_nombre, vendedor,
            metodo_pago, producto_nombre, cantidad, unidad_medida,
            precio_unitario, linea_total, rank.
        Orden: rank desc, fecha desc. Retorna [] si DB no disponible.
    """
    q = _limpiar_query(query)
    if not q:
        return []

    limit = _clamp(limit, 1, _HARD_LIMIT)

    vendedor_filter = "AND v.vendedor ILIKE %s" if vendedor else ""
    vendedor_param: list[Any] = [f"%{vendedor}%"] if vendedor else []

    # ── 1) FTS nativo sobre producto_nombre ──────────────────────────────
    sql_fts = f"""
        SELECT v.id                AS venta_id,
               v.consecutivo,
               v.fecha,
               v.hora,
               v.cliente_nombre,
               v.vendedor,
               v.metodo_pago,
               vd.producto_nombre,
               vd.cantidad,
               vd.unidad_medida,
               vd.precio_unitario,
               vd.total            AS linea_total,
               ts_rank(to_tsvector('spanish', vd.producto_nombre),
                       plainto_tsquery('spanish', %s)) AS rank
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        WHERE to_tsvector('spanish', vd.producto_nombre)
                 @@ plainto_tsquery('spanish', %s)
          AND v.fecha >= (CURRENT_DATE - (%s || ' days')::INTERVAL)
          {vendedor_filter}
        ORDER BY rank DESC, v.fecha DESC, v.hora DESC
        LIMIT %s;
    """
    params: list[Any] = [q, q, str(dias), *vendedor_param, limit]

    try:
        filas_fts = _db.query_all(sql_fts, params) or []
    except Exception as e:
        log.warning("FTS ventas_por_producto falló: %s", e)
        filas_fts = []

    if len(filas_fts) >= _MIN_FTS_HITS or len(filas_fts) >= limit:
        return filas_fts

    # ── 2) Fallback trigram (para typos tipo drwayll → drywall) ─────────
    ids_ya = {(f["venta_id"], f["producto_nombre"]) for f in filas_fts}
    restante = limit - len(filas_fts)

    sql_trgm = f"""
        SELECT v.id                AS venta_id,
               v.consecutivo,
               v.fecha,
               v.hora,
               v.cliente_nombre,
               v.vendedor,
               v.metodo_pago,
               vd.producto_nombre,
               vd.cantidad,
               vd.unidad_medida,
               vd.precio_unitario,
               vd.total            AS linea_total,
               similarity(vd.producto_nombre, %s) AS rank
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        WHERE vd.producto_nombre %% %s
          AND similarity(vd.producto_nombre, %s) >= %s
          AND v.fecha >= (CURRENT_DATE - (%s || ' days')::INTERVAL)
          {vendedor_filter}
        ORDER BY rank DESC, v.fecha DESC, v.hora DESC
        LIMIT %s;
    """
    params_trgm: list[Any] = [
        q, q, q, _TRGM_THRESHOLD, str(dias),
        *vendedor_param,
        restante * 2 if restante > 0 else 1,
    ]

    try:
        filas_trgm = _db.query_all(sql_trgm, params_trgm) or []
    except Exception as e:
        log.warning(
            "Trigram ventas_por_producto falló (pg_trgm no instalado?): %s", e
        )
        filas_trgm = []

    nuevos = [
        f for f in filas_trgm
        if (f["venta_id"], f["producto_nombre"]) not in ids_ya
    ][:restante]
    return filas_fts + nuevos


# ─────────────────────────────────────────────────────────────────────────
# BÚSQUEDA DE VENTAS POR CLIENTE
# ─────────────────────────────────────────────────────────────────────────


def buscar_ventas_por_cliente(
    nombre_cliente: str,
    dias: int = 30,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Lista ventas cuyo cliente_nombre contenga el texto (case-insensitive).

    No es FTS — cliente_nombre es corto y típicamente se busca por prefijo
    ("pedro" → "Pedro Pérez"), por lo que ILIKE es más útil que tsvector.

    Args:
        nombre_cliente: fragmento del nombre. Vacío retorna [].
        dias:           antigüedad máxima (default 30).
        limit:          máximo de filas (hard-cap a 50).

    Returns:
        Lista de dicts con: venta_id, consecutivo, fecha, cliente_nombre,
        vendedor, metodo_pago, total. Orden: fecha desc.
    """
    q = _limpiar_query(nombre_cliente)
    if not q:
        return []

    limit = _clamp(limit, 1, _HARD_LIMIT)

    sql = """
        SELECT v.id            AS venta_id,
               v.consecutivo,
               v.fecha,
               v.hora,
               v.cliente_nombre,
               v.vendedor,
               v.metodo_pago,
               v.total
        FROM ventas v
        WHERE v.cliente_nombre ILIKE %s
          AND v.fecha >= (CURRENT_DATE - (%s || ' days')::INTERVAL)
        ORDER BY v.fecha DESC, v.hora DESC
        LIMIT %s;
    """
    try:
        return _db.query_all(sql, [f"%{q}%", str(dias), limit]) or []
    except Exception as e:
        log.warning("buscar_ventas_por_cliente falló: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────
# FORMATEO LEGIBLE PARA INYECTAR EN RESPUESTAS
# ─────────────────────────────────────────────────────────────────────────


def formatear_resultados_ventas(filas: list[dict[str, Any]]) -> str:
    """
    Render humano de una lista de ventas para mostrar al vendedor.
    Usado cuando se inyecta el resultado directamente en la respuesta final
    (en vez de mandarlo a Claude para que lo parafraseé).
    """
    if not filas:
        return "No encontré ventas que coincidan."

    lineas = []
    for f in filas:
        fecha = f.get("fecha")
        fecha_str = fecha.strftime("%Y-%m-%d") if hasattr(fecha, "strftime") else str(fecha)
        cliente = f.get("cliente_nombre") or "Consumidor Final"
        vendedor = f.get("vendedor") or "?"
        prod = f.get("producto_nombre")
        if prod:
            cant = f.get("cantidad", 0)
            unidad = f.get("unidad_medida", "u")
            total = f.get("linea_total") or 0
            lineas.append(
                f"• {fecha_str} · {cliente} · {prod} × {cant} {unidad} · ${int(total):,}"
            )
        else:
            total = f.get("total") or 0
            lineas.append(
                f"• {fecha_str} · #{f.get('consecutivo','?')} · {cliente} · "
                f"{vendedor} · ${int(total):,}"
            )
    return "\n".join(lineas)


def formatear_resultados_conversaciones(filas: list[dict[str, Any]]) -> str:
    """Render humano de turnos de conversación encontrados."""
    if not filas:
        return "No encontré conversaciones que coincidan."

    lineas = []
    for f in filas:
        creado = f.get("creado")
        fecha_str = (
            creado.strftime("%Y-%m-%d %H:%M")
            if hasattr(creado, "strftime")
            else str(creado)
        )
        role = f.get("role", "?")
        content = (f.get("content") or "").replace("\n", " ")[:200]
        lineas.append(f"• [{fecha_str}] {role}: {content}")
    return "\n".join(lineas)
