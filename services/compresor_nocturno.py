"""
services/compresor_nocturno.py — Job que corre cada noche a las 3 AM Colombia
y comprime las conversaciones del día (que terminaron en venta registrada) en
notas estructuradas sobre productos, aliases y vendedores.

Modelo: Claude Haiku 4.5 (3x más barato que Sonnet, suficiente para extracción
estructurada). El compresor es deliberadamente cheap: si falla, simplemente
no hay nuevas notas — el bot sigue funcionando.

Pipeline:

  1. Cargar conversaciones del día anterior (Colombia) que tienen al menos
     una venta registrada en el mismo chat_id durante el mismo día.
  2. Agrupar por (chat_id, productos vendidos, vendedor).
  3. Mandarle a Haiku un prompt compacto pidiendo notas en JSON estructurado:
       { "productos": {nombre: nota}, "aliases": {alias: canonico},
         "vendedores": {nombre: nota} }
  4. Persistir vía memoria_entidad_service.guardar_nota.
  5. Purga: borrar notas > 90 días.

Idempotencia:
  Si el job corre dos veces el mismo día (ej. por restart manual), las notas
  se UPSERTEAN — no se duplican (ver UNIQUE en migración 020).

Falla limpia:
  Cualquier excepción se loguea como warning. El job NUNCA tira; APScheduler
  solo recibe `None` como retorno.
"""

# -- stdlib --
import json
import logging
from datetime import date as _date, datetime as _dt, timedelta as _td

# -- propios --
import config
import db as _db
from services import memoria_entidad_service as _me

# Métricas — fail-silent si no está disponible
try:
    import metrics as _metrics
except Exception:  # noqa: BLE001
    _metrics = None

log = logging.getLogger("ferrebot.services.compresor")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS_OUT = 1500
_MAX_CONV_CHARS = 12000   # cap del prompt input — protege gasto en Haiku
_MAX_PRODUCTOS = 30        # max productos a procesar por noche


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────────────────────────────────────────

def _fecha_objetivo() -> _date:
    """Fecha del día anterior en hora Colombia."""
    ahora = _dt.now(config.COLOMBIA_TZ)
    return (ahora - _td(days=1)).date()


def _cargar_conversaciones_del_dia(fecha: _date) -> list[dict]:
    """
    Trae conversaciones del día especificado (Colombia) que tengan al menos
    una venta registrada en el mismo chat_id durante el mismo día.

    Retorna lista de dicts: {chat_id, vendedor_id, role, content, creado}
    """
    try:
        return _db.query_all(
            """
            SELECT cb.chat_id,
                   cb.vendedor_id,
                   cb.role,
                   cb.content,
                   cb.creado
            FROM conversaciones_bot cb
            WHERE DATE(cb.creado AT TIME ZONE 'America/Bogota') = %s
              AND cb.chat_id IN (
                  SELECT DISTINCT v.chat_id
                  FROM ventas v
                  WHERE DATE(v.fecha AT TIME ZONE 'America/Bogota') = %s
                    AND v.estado = 'registrada'
                    AND v.chat_id IS NOT NULL
              )
            ORDER BY cb.chat_id, cb.creado
            """,
            [fecha, fecha],
        ) or []
    except Exception as e:
        log.warning("_cargar_conversaciones_del_dia(%s) falló: %s", fecha, e)
        return []


def _cargar_productos_vendidos(fecha: _date) -> list[str]:
    """
    Productos distintos vendidos el día (Colombia). Usado para acotar las
    notas a productos relevantes y no procesar todo el catálogo.
    """
    try:
        filas = _db.query_all(
            """
            SELECT DISTINCT vd.producto_nombre
            FROM ventas_detalle vd
            JOIN ventas v ON v.id = vd.venta_id
            WHERE DATE(v.fecha AT TIME ZONE 'America/Bogota') = %s
              AND v.estado = 'registrada'
              AND vd.producto_nombre IS NOT NULL
            ORDER BY vd.producto_nombre
            LIMIT %s
            """,
            [fecha, _MAX_PRODUCTOS],
        ) or []
        return [f["producto_nombre"] for f in filas if f.get("producto_nombre")]
    except Exception as e:
        log.warning("_cargar_productos_vendidos(%s) falló: %s", fecha, e)
        return []


def _cargar_vendedores_activos(fecha: _date) -> list[str]:
    """Vendedores que registraron al menos una venta el día."""
    try:
        filas = _db.query_all(
            """
            SELECT DISTINCT vendedor
            FROM ventas
            WHERE DATE(fecha AT TIME ZONE 'America/Bogota') = %s
              AND estado = 'registrada'
              AND vendedor IS NOT NULL
            """,
            [fecha],
        ) or []
        return [f["vendedor"] for f in filas if f.get("vendedor")]
    except Exception as e:
        log.warning("_cargar_vendedores_activos(%s) falló: %s", fecha, e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _serializar_conversaciones(filas: list[dict]) -> str:
    """
    Concatena las conversaciones en un solo bloque legible. Se trunca a
    `_MAX_CONV_CHARS` para acotar el costo del prompt.
    """
    bloques = []
    chat_actual = None
    for f in filas:
        if f["chat_id"] != chat_actual:
            chat_actual = f["chat_id"]
            bloques.append(f"\n[chat {chat_actual}]")
        role = (f.get("role") or "").upper()
        content = (f.get("content") or "").strip().replace("\n", " ")
        bloques.append(f"  {role}: {content[:400]}")
    texto = "\n".join(bloques)
    if len(texto) > _MAX_CONV_CHARS:
        texto = texto[:_MAX_CONV_CHARS] + "\n[...truncado...]"
    return texto


def _construir_prompt(
    fecha: _date,
    productos: list[str],
    vendedores: list[str],
    convs_texto: str,
) -> str:
    """
    Prompt para Haiku — pide JSON estructurado con notas concisas.
    """
    return f"""Sos un analista que extrae APRENDIZAJES OPERATIVOS de las conversaciones de un bot de ferretería en Colombia. La fecha analizada es {fecha.isoformat()}.

REGLAS:
1. Solo extraés patrones REPETIDOS o INSIGHTS ÚTILES. Si una conversación no aporta nada nuevo, la ignorás.
2. Cada nota debe ser CORTA (máx 1 oración, ~150 caracteres) y ACCIONABLE para un bot que asiste ventas mañana.
3. Si descubrís un alias/typo recurrente (ej. "tiner" → "thinner", "drwayll" → "drywall"), lo registrás en "aliases".
4. Para vendedores, solo notás patrones de horario, productos preferidos o estilo de venta — NUNCA juicios personales.
5. Salida estricta en JSON. Sin markdown, sin texto antes ni después.

PRODUCTOS VENDIDOS HOY: {", ".join(productos[:_MAX_PRODUCTOS])}
VENDEDORES ACTIVOS: {", ".join(vendedores) or "(ninguno)"}

CONVERSACIONES DEL DÍA:
{convs_texto}

FORMATO DE RESPUESTA (JSON estricto):
{{
  "productos": {{
    "nombre del producto en lowercase": "nota corta accionable",
    ...
  }},
  "aliases": {{
    "typo o alias en lowercase": "forma canónica del producto"
  }},
  "vendedores": {{
    "nombre del vendedor en lowercase": "nota corta sobre patrón observado"
  }}
}}

Si no encontrás nada útil para alguna sección, devolvé un objeto vacío {{}}.
"""


# ─────────────────────────────────────────────────────────────────────────────
# PARSER — JSON tolerante
# ─────────────────────────────────────────────────────────────────────────────

def _parsear_respuesta(texto: str) -> dict:
    """
    Intenta parsear el JSON. Si Haiku decoró con markdown o texto extra,
    intentamos extraer el primer bloque JSON y parsear eso.
    """
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except Exception:
        pass
    # fallback: buscar el primer { ... } balanceado
    start = texto.find("{")
    end = texto.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(texto[start:end + 1])
        except Exception as e:
            log.warning("Compresor: JSON malformado tras fallback: %s", e)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# JOB ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def compresor_nocturno_job() -> dict:
    """
    Orquesta el ciclo completo. Llamar desde APScheduler (cron 3 AM Colombia).

    Returns:
        Dict con métricas de la corrida (útil para logs y observabilidad):
        { "fecha": ..., "convs": N, "productos": M,
          "notas_guardadas": K, "purgadas": P, "ok": bool, "error": str|None }
    """
    fecha = _fecha_objetivo()
    resumen = {
        "fecha": fecha.isoformat(),
        "convs": 0,
        "productos": 0,
        "notas_guardadas": 0,
        "purgadas": 0,
        "ok": False,
        "error": None,
    }

    log.info("[compresor] Iniciando para fecha=%s", fecha)

    if not getattr(config, "claude_client", None):
        resumen["error"] = "claude_client no disponible"
        log.warning("[compresor] %s — abortando", resumen["error"])
        return resumen

    try:
        convs = _cargar_conversaciones_del_dia(fecha)
        productos = _cargar_productos_vendidos(fecha)
        vendedores = _cargar_vendedores_activos(fecha)

        resumen["convs"] = len(convs)
        resumen["productos"] = len(productos)

        if not convs or not productos:
            log.info(
                "[compresor] Nada que procesar (convs=%d, productos=%d)",
                len(convs), len(productos),
            )
            # Aún así, purgamos viejas
            resumen["purgadas"] = _me.purgar_antiguas(90)
            resumen["ok"] = True
            return resumen

        convs_txt = _serializar_conversaciones(convs)
        prompt = _construir_prompt(fecha, productos, vendedores, convs_txt)

        # Llamar a Haiku
        respuesta = config.claude_client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=_MAX_TOKENS_OUT,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(
            block.text for block in respuesta.content
            if hasattr(block, "text")
        ).strip()
        log.debug("[compresor] Respuesta cruda Haiku: %s", texto[:500])

        datos = _parsear_respuesta(texto)
        if not datos:
            resumen["error"] = "respuesta vacía o no parseable"
            log.warning("[compresor] %s", resumen["error"])
            return resumen

        # Persistir notas
        guardadas = 0
        _counts_por_tipo = {"producto": 0, "alias": 0, "vendedor": 0}
        for nombre, nota in (datos.get("productos") or {}).items():
            if _me.guardar_nota("producto", nombre, nota, fecha=fecha):
                guardadas += 1
                _counts_por_tipo["producto"] += 1
        for alias, canonico in (datos.get("aliases") or {}).items():
            if _me.guardar_nota("alias", alias, canonico, fecha=fecha):
                guardadas += 1
                _counts_por_tipo["alias"] += 1
        for nombre, nota in (datos.get("vendedores") or {}).items():
            if _me.guardar_nota("vendedor", nombre, nota, fecha=fecha):
                guardadas += 1
                _counts_por_tipo["vendedor"] += 1
        resumen["notas_guardadas"] = guardadas

        # Emit métricas por tipo (non-fatal)
        if _metrics is not None:
            try:
                for _tipo, _n in _counts_por_tipo.items():
                    if _n:
                        _metrics.compresor_notas_guardadas_total.labels(tipo=_tipo).inc(_n)
            except Exception:  # noqa: BLE001
                pass

        # Purga de mantenimiento
        resumen["purgadas"] = _me.purgar_antiguas(90)
        resumen["ok"] = True

        log.info(
            "[compresor] OK — fecha=%s convs=%d productos=%d notas=%d purgadas=%d",
            fecha, len(convs), len(productos), guardadas, resumen["purgadas"],
        )

    except Exception as e:
        resumen["error"] = str(e)
        log.error("[compresor] Falló: %s", e, exc_info=True)

    # ── Prometheus metrics ──────────────────────────────────────────────────
    if _metrics is not None:
        try:
            _metrics.compresor_last_run_timestamp.set_to_current_time()
            if resumen["ok"]:
                outcome = "sin_datos" if resumen["notas_guardadas"] == 0 else "ok"
            else:
                outcome = "error"
            _metrics.compresor_runs_total.labels(outcome=outcome).inc()
            if resumen["purgadas"]:
                _metrics.compresor_notas_purgadas_total.inc(resumen["purgadas"])
        except Exception:  # noqa: BLE001
            pass

    return resumen
